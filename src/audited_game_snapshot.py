"""Collect the actual planning observations into an immutable A3 snapshot.

The acquisition contract requires complete coverage. Bounded research and
catalogue prices are preserved as observations without certifying that scope.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

import paths
from fleet_commitment_observations import SOURCE as HANGAR_SOURCE, _hangar
from finance_observations import SOURCE as FINANCE_SOURCE, validate_summary
from investment_policy import AUDITED_POLICY_LIMITS, InvestmentPolicy, audited_policy_values
from opportunity_models import DEFAULT_MAX_AGE_SECONDS, fingerprint_snapshot

FILENAME = "audited_game_snapshot.json"


def _fresh(stamp, now):
    try:
        return (type(stamp) in (int, float) and math.isfinite(stamp)
                and stamp > 0 and 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS)
    except OverflowError:
        return False


def _game_id(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,11}", value) is not None


def _verified_owned_hubs(inventory, now):
    rows = inventory.get("hubs", [])
    if (inventory.get("source") == "game_hub_select"
            and inventory.get("hub_catalog_fresh") is True
            and _fresh(inventory.get("observed_at"), now) and isinstance(rows, list) and bool(rows)
            and all(isinstance(row, dict) and _game_id(row.get("id")) for row in rows)
            and len({row["id"] for row in rows}) == len(rows)):
        return {row["id"] for row in rows}
    return set()


def _unique_rows(rows, identity):
    """Discard ambiguous identities instead of choosing a conflicting row."""
    if not isinstance(rows, list):
        return []
    keyed = [(identity(row), row) for row in rows if isinstance(row, dict)]
    counts = Counter(key for key, _ in keyed if key is not None)
    return [row for key, row in keyed if key is not None and counts[key] == 1]


def _external_research(external, owned_ids, now):
    from hub_expansion import _amount, _demand_sample, _points

    result = {"coverage": "partial", "origin_scope": None, "candidate_source": None,
              "candidate_inventory": [], "samples": [], "hub_progress": []}
    if (not owned_ids or not isinstance(external, dict)
            or external.get("origin_scope") != "external_catalog"
            or external.get("candidate_source") != "game_purchase_catalog"):
        return result
    result.update(origin_scope="external_catalog", candidate_source="game_purchase_catalog")
    candidates = _unique_rows(external.get("candidate_inventory"),
                              lambda row: row["id"] if _game_id(row.get("id")) else None)
    for row in candidates:
        if row["id"] in owned_ids or not _fresh(row.get("observed_at"), now):
            continue
        candidate = {"id": row["id"], "observed_at": row["observed_at"]}
        if isinstance(row.get("code"), str):
            candidate["code"] = row["code"]
        for field, normalize in (("hub_price", _amount), ("hub_points", _points)):
            stamp = row.get(f"{field}_observed_at")
            value = normalize(row.get(field))
            if (value is not None and row.get(f"{field}_conflict_at") is None
                    and _fresh(stamp, now) and stamp <= row["observed_at"]):
                candidate.update({field: value, f"{field}_observed_at": stamp})
        result["candidate_inventory"].append(candidate)

    candidate_ids = {row["id"] for row in result["candidate_inventory"]}

    def route_identity(row):
        origin, destination = row.get("origin_id"), row.get("destination_id")
        if _game_id(origin) and _game_id(destination) and origin != destination:
            return origin, destination
        return None

    for row in _unique_rows(external.get("samples"), route_identity):
        if (row["origin_id"] not in candidate_ids or row.get("source") != "game_route_search"
                or not _fresh(row.get("observed_at"), now)):
            continue
        sample = _demand_sample(row["origin_id"], {"arr_id": row["destination_id"],
                                "distance": row.get("distance_km"), "y": row.get("y"),
                                "j": row.get("j"), "f": row.get("f")})
        if sample is not None:
            result["samples"].append(deepcopy(row))
    for row in _unique_rows(external.get("hub_progress"),
                            lambda row: row["hub_id"] if _game_id(row.get("hub_id")) else None):
        stamp = row.get("last_attempt_at")
        if (row["hub_id"] in candidate_ids and row.get("coverage") == "partial"
                and (stamp is None or _fresh(stamp, now))):
            result["hub_progress"].append(deepcopy(row))
    return result


def _catalog_scopes(coverage, now):
    """Certify only the native passenger list/detail crosswalk, independently of prices."""
    from engine_catalog import ROSTER_SOURCE

    def active(key):
        expires = coverage.get(key)
        return (type(expires) in (int, float) and math.isfinite(expires)
                and now <= expires <= coverage["observed_at"] + DEFAULT_MAX_AGE_SECONDS)

    listed = coverage.get("listed_model_count")
    verified = coverage.get("verified_model_count")
    available = coverage.get("available_variant_count")
    observed = coverage.get("observed_variant_count")
    full_details = coverage.get("models_with_all_variant_details")
    models = (coverage.get("source") == ROSTER_SOURCE
              and coverage.get("status") in ("partial", "details_observed")
              and _fresh(coverage.get("observed_at"), now)
              and type(listed) is int and listed > 0
              and type(verified) is int and verified == listed
              and active("models_expires_at"))
    engines = (models and coverage.get("status") == "details_observed"
               and type(full_details) is int and full_details == listed
               and type(available) is int and available >= listed
               and type(observed) is int and observed == available
               and active("engines_expires_at"))
    return {"models": models, "engines": engines}


def compose_snapshot(*, profile_id, routes, inventory, demand, engines, market,
                     quotes, cash, cash_at, now, mode=None, mode_at=None,
                     preview_margin=0.10, native_quotes=(), configured_prices=None, policy_values=None,
                     external_demand=None, operational_reserve=None):
    """Translate independently collected observations without upgrading their provenance."""
    hub_at = inventory.get("observed_at")
    raw_hubs = inventory.get("hubs", [])
    owned_ids = _verified_owned_hubs(inventory, now)
    hubs_verified = bool(owned_ids)
    hubs = [{"id": row["id"], "code": row.get("code"), "owned": True,
             "profile_id": profile_id, "source": "game_hub_select", "id_source": "game",
             "verified": True, "observed_at": hub_at} for row in raw_hubs] if hubs_verified else []

    fleet = routes.get("fleet_coverage") or {}
    fleet_at = fleet.get("observed_at")
    roster_at = fleet.get("roster_observed_at")
    scan = routes.get("scan_coverage") or {}
    run = scan.get("audit_run") or {}
    rows = routes.get("current_relations", [])
    ids = [row.get("aircraft_id") for row in rows]
    total = fleet.get("total")
    counts = [fleet.get(key) for key in ("routes", "parked", "pending")]
    counts_valid = all(type(count) is int and count >= 0 for count in counts)
    unrouted_verified = counts_valid and (
        fleet.get("native_identity_status") == "matched" and bool(fleet.get("native_observation_id"))
        or counts[1:] == [0, 0] and fleet.get("native_identity_status") != "different"
    )
    expected_pages = scan.get("total_pages") if counts_valid and counts[0] else 0
    pages = scan.get("pages") or {}
    if expected_pages == 0:
        pages = {}
    pages_verified = (type(expected_pages) is int and expected_pages >= 0
                      and len(pages) == expected_pages
                      and set(pages) == {str(page) for page in range(1, expected_pages + 1)}
                      and (expected_pages == 0 and counts_valid and counts[0] == 0 or (
                          expected_pages > 0
                          and counts_valid and counts[0] > 0
                          and scan.get("full_page_coverage_verified") is True
                          and run.get("id") == fleet.get("audit_run_id")
                          and run.get("invalidated") is False)))
    fleet_verified = (routes.get("current_fleet_coverage_verified") is True
                      and fleet.get("source") == "game_roster_and_route_audit"
                      and _fresh(fleet_at, now) and _fresh(roster_at, now)
                      and counts_valid and unrouted_verified and pages_verified
                      and type(total) is int and total == sum(counts) == len(ids)
                      and all(_game_id(identity) for identity in ids)
                      and len(set(ids)) == total)

    # The route search is bounded, and the model detail catalogue does not
    # establish checkout prices. Even a full fleet audit cannot prove these.
    engine_coverage = engines.get("order_list_coverage") or {}
    scopes = {"hubs": hubs_verified, "fleet": fleet_verified,
              "routes": False, **_catalog_scopes(engine_coverage, now), "prices": False}
    observed = [stamp for stamp in (hub_at if hubs_verified else None,
                                    roster_at if fleet_verified else None) if _fresh(stamp, now)]
    cash_verified = type(cash) is int and cash >= 0 and _fresh(cash_at, now)
    coverage = {"source": "game_fleet_scan", "profile_id": profile_id,
                "verified": fleet_verified, "observed_at": roster_at if fleet_verified else None,
                "status": "partial", "scopes": scopes,
                "observed_pages": len(pages) if fleet_verified else None,
                "expected_pages": expected_pages if fleet_verified else None,
                "expected_aircraft_count": total if fleet_verified else None,
                "routed_aircraft_count": counts[0] if fleet_verified else None,
                "unrouted_aircraft_count": sum(counts[1:]) if fleet_verified else None,
                "native_unrouted_identity_verified": bool(
                    fleet_verified and fleet.get("native_identity_status") == "matched"
                    and fleet.get("native_observation_id")),
                "count_source": "game_fleet_total" if fleet_verified else None,
                "observed_aircraft_ids": sorted(ids) if fleet_verified else []}
    snapshot = {"schema_version": 1, "profile_id": profile_id,
                "source": "game_snapshot", "observed_at": min(observed, default=None),
                "verified": hubs_verified and fleet_verified, "hubs": hubs, "coverage": coverage,
                "observations": {
                    "captured_at": now,
                    "fleet": {"observed_at": fleet_at if fleet_verified else None,
                              "routes": counts[0] if fleet_verified else None,
                              "parked": counts[1] if fleet_verified else None,
                              "pending": counts[2] if fleet_verified else None,
                              "relations": rows if fleet_verified else []},
                    "route_research": demand,
                    "native_route_quotes": [row for row in native_quotes
                                            if row.get("profile_id") == profile_id
                                            and _fresh(row.get("observed_at"), now)],
                    "engine_catalog": engines,
                    "aircraft_market": market,
                    "engine_coverage": engine_coverage,
                    "market_quotes": quotes,
                    "research_inputs": {
                        "mode": mode, "mode_observed_at": mode_at,
                        "preview_margin": preview_margin,
                        "operational_reserve": operational_reserve,
                        "configured_prices": configured_prices,
                        "route_report": {key: routes.get(key) for key in (
                            "current_roster_verified", "current_roster_observed_at",
                            "current_roster_total", "current_fleet_coverage_verified",
                            "fleet_coverage", "current_relations",
                        )},
                    },
                    "fleet_commitments": inventory.get("fleet_commitment_observations"),
                    "finance_history": inventory.get("finance_observations"),
                    "staff_salary": inventory.get("staff_observations"),
                    "cash": {"available": cash if cash_verified else None,
                             "observed_at": cash_at if cash_verified else None,
                             "committed": None, "reserve": None},
                }}
    if policy_values is not None:
        snapshot["observations"]["investment_policy"] = policy_values
    if external_demand is not None:
        # Keep the authenticated external registry distinct from owned research.
        # Ownership must be current even if the external catalogue is fresh.
        snapshot["observations"]["external_route_research"] = _external_research(
            external_demand, owned_ids, now)
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    return snapshot


def capture_game_snapshot(bot):
    """Called on the browser-owning worker after the cycle's market/finance reads."""
    from dashboard import recent_verified_money
    from economy import load_market_evidence
    from engine_catalog import EngineCatalogRegistry
    from hub_expansion import HubExpansionRegistry
    from hub_registry import HubRegistry
    from market import recent_market_quotes
    from native_route_quotes import native_route_quotes
    from route_registry import RouteRegistry
    from research_economics_preview import configured_price_assumptions, research_mode
    from gamemode import EASY, REALISM

    profile = paths.current()
    routes = RouteRegistry().snapshot()
    inventory = HubRegistry().snapshot(routes)
    now = time.time()
    expansion = HubExpansionRegistry()
    owned_ids = _verified_owned_hubs(inventory, now)
    demand = expansion.demand_research_snapshot(owned_ids, now=now)
    external = expansion.external_demand_snapshot(owned_ids, now=now)
    cash, cash_at = recent_verified_money(bot, now=now)
    stats = bot.stats()
    mode_key = research_mode(stats, now)
    mode = next((item.label for item in (EASY, REALISM) if item.key == mode_key), None)
    config = getattr(bot, "config", None)
    margin = (max(0, min(100, config.get_int("investment", "preview_margin_pct", 10))) / 100
              if config else 0.10)
    snapshot = compose_snapshot(profile_id=profile.label, routes=routes, inventory=inventory,
                                demand=demand, engines=EngineCatalogRegistry().snapshot(now=now),
                                market=load_market_evidence(now=now),
                                quotes=recent_market_quotes(stats, now), cash=cash,
                                cash_at=cash_at, now=now, mode=mode,
                                mode_at=stats.mode_read_at if mode else None, preview_margin=margin,
                                native_quotes=native_route_quotes(bot, now=now),
                                configured_prices=configured_price_assumptions(config), external_demand=external,
                                operational_reserve=config.get_int("settings", "cash_reserve", -1) if config else None,
                                policy_values=audited_policy_values(
                                    InvestmentPolicy.from_config(config),
                                    config.get_int("settings", "cash_reserve", -1) if config else -1))
    paths.write_atomic(profile.data / FILENAME, json.dumps(snapshot, ensure_ascii=False, allow_nan=False),
                       private=True)
    return snapshot


def _load_snapshot(path):
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if (snapshot["profile_id"] != paths.current().label or snapshot["schema_version"] != 1
            or fingerprint_snapshot(snapshot) != snapshot["snapshot_id"]):
        raise ValueError("invalid snapshot")
    return snapshot


def _captured_owned_inventory(snapshot, now):
    hubs = snapshot["hubs"]
    captured = snapshot["observations"]["captured_at"]
    if not snapshot["coverage"]["scopes"]["hubs"] or not hubs or not all(
        hub.get("owned") is True and hub.get("verified") is True
        and hub.get("source") == "game_hub_select" and hub.get("profile_id") == snapshot["profile_id"]
        and _fresh(hub["observed_at"], now) and hub["observed_at"] <= captured for hub in hubs
    ):
        return None
    inventory = {"source": "game_hub_select", "hubs": [{"id": hub["id"]} for hub in hubs],
                 "observed_at": min(hub["observed_at"] for hub in hubs), "hub_catalog_fresh": True}
    if not _verified_owned_hubs(inventory, now):
        return None
    # Ownership alone does not establish the fleet-to-hub link.
    return {**inventory, "profile_id": snapshot["profile_id"], "snapshot_id": snapshot["snapshot_id"],
            "partial_fleet": True}


def replay_research_page(*, offset=0, expected_snapshot=None, expected_fingerprint=None,
                         expected_layout_fingerprint=None, now=None, path=None):
    """Replay a bounded page using only the captured inputs and capture clock."""
    from types import SimpleNamespace

    from market import MarketQuote
    from native_route_quotes import reference_for_route
    from owned_hub_research_feed import build_owned_hub_research_queue
    from research_accounting_gate import evaluate_research_gate

    now = time.time() if now is None else now
    path = path if path is not None else paths.current().data / FILENAME
    unavailable = {"snapshot_id": None, "items": [], "read_only": True,
                   "purchase_eligible": False, "coverage": "partial"}
    try:
        snapshot = _load_snapshot(path)
        observed = snapshot["observations"]
        captured = observed["captured_at"]
        unavailable["snapshot_id"] = snapshot["snapshot_id"]
        if not _fresh(captured, now):
            return {**unavailable, "status": "expirado"}
        if "research_inputs" not in observed:
            return {**unavailable, "status": "recoleta_necessaria"}
        if (offset or expected_snapshot is not None) and expected_snapshot != snapshot["snapshot_id"]:
            return {**unavailable, "status": "snapshot_alterado"}
        inputs = observed["research_inputs"]
        stats = SimpleNamespace(mode=inputs["mode"], mode_read_at=inputs["mode_observed_at"])
        for kind in ("fuel", "co2"):
            quote = observed["market_quotes"].get(kind)
            if quote is not None and quote.get("source") == "game_market" and quote.get("unit") == "USD/1000":
                setattr(stats, f"{kind}_quote", MarketQuote(quote["price"], quote["observed_at"], quote["expires_at"]))
        hubs = snapshot["hubs"]
        inventory = {"source": "game_hub_select", "hubs": hubs,
                     "observed_at": min((hub["observed_at"] for hub in hubs), default=None),
                     "fleet_commitment_observations": observed["fleet_commitments"],
                     "staff_observations": observed.get("staff_salary")}
        demand = observed["route_research"]
        result = build_owned_hub_research_queue(
            inventory, demand["samples"], observed["aircraft_market"], now=captured,
            engines=observed["engine_catalog"], hub_progress=demand.get("hub_progress"),
            operating_market_stats=stats, preview_margin=inputs["preview_margin"],
            configured_prices=inputs.get("configured_prices"),
            route_report=inputs["route_report"], offset=offset, expected_fingerprint=expected_fingerprint,
            expected_layout_fingerprint=expected_layout_fingerprint,
        )
        for item in result["items"]:
            stop = item.get("stopover_research")
            reference = reference_for_route(
                observed.get("native_route_quotes", []), profile_id=snapshot["profile_id"],
                origin_id=item["hub_id"], destination_id=item["destination_id"],
                distance_km=stop["first_km"] + stop["second_km"] if stop else item["distance_km"],
                stopover_id=stop["stop_id"] if stop else None, now=captured,
            )
            if reference is not None:
                item["native_route_quote_reference"] = reference
                if reference["aircraft_on_route_range"]["max"] > 0:
                    # The form was bound to an existing aircraft. Its positive
                    # count vetoes an optimistic preview, but its fares and
                    # fees still cannot price a future aircraft.
                    item["economics_preview"] = None
                    if "rota_ocupada_frota_propria" not in item["pending"]:
                        item["pending"].append("rota_ocupada_frota_propria")
            item["accounting_gate"] = evaluate_research_gate(
                snapshot, item, now=captured, margin=inputs["preview_margin"],
                native_reference=reference,
            )
        return {**result, "status": "parcial", "snapshot_id": snapshot["snapshot_id"],
                "captured_at": captured, "historical_replay": True}
    except FileNotFoundError:
        return {**unavailable, "status": "sem_coleta"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {**unavailable, "status": "registro_invalido"}


def replay_external_research_page(*, offset=0, expected_fingerprint=None, now=None, path=None):
    """Evaluate external research exclusively from the current profile's captured evidence."""
    from types import SimpleNamespace

    from market import MarketQuote
    from owned_hub_research_feed import build_external_hub_research_queue

    now = time.time() if now is None else now
    path = path if path is not None else paths.current().data / FILENAME
    unavailable = {"source": "derived_external_research_queue", "snapshot_id": None,
                   "items": [], "offset": 0, "next_offset": None, "read_only": True,
                   "purchase_eligible": False, "coverage": "partial"}
    try:
        snapshot = _load_snapshot(path)
        observed = snapshot["observations"]
        captured = observed["captured_at"]
        snapshot_id = snapshot["snapshot_id"]
        unavailable["snapshot_id"] = snapshot_id
        if not _fresh(captured, now):
            return {**unavailable, "status": "expirado"}
        if "external_route_research" not in observed or "research_inputs" not in observed:
            return {**unavailable, "status": "recoleta_necessaria"}
        inputs = observed["research_inputs"]
        inventory = {**(_captured_owned_inventory(snapshot, now) or {}),
                     "fleet_commitment_observations": observed["fleet_commitments"],
                     "staff_observations": observed.get("staff_salary")}
        external = _external_research(observed["external_route_research"],
                                      _verified_owned_hubs(inventory, now), now)
        stats = SimpleNamespace(mode=inputs["mode"], mode_read_at=inputs["mode_observed_at"])
        for kind in ("fuel", "co2"):
            quote = observed["market_quotes"].get(kind)
            if quote is not None and quote.get("source") == "game_market" and quote.get("unit") == "USD/1000":
                setattr(stats, f"{kind}_quote", MarketQuote(quote["price"], quote["observed_at"], quote["expires_at"]))
        reserve = inputs.get("operational_reserve")
        if reserve is None:
            reserve = (observed.get("investment_policy") or {}).get("operational_reserve")
        minimum, maximum = AUDITED_POLICY_LIMITS["operational_reserve"]
        if type(reserve) is not int or not minimum <= reserve <= maximum:
            reserve = None
        cash = observed["cash"]
        prefix = snapshot_id + ":"
        inner = (expected_fingerprint[len(prefix):] if isinstance(expected_fingerprint, str)
                 and expected_fingerprint.startswith(prefix) else None)
        result = build_external_hub_research_queue(
            inventory, external, observed["aircraft_market"], now=now,
            engines=observed["engine_catalog"], offset=offset, expected_fingerprint=inner,
            cash=cash["available"], cash_observed_at=cash["observed_at"], reserve=reserve,
            operating_market_stats=stats, preview_margin=inputs["preview_margin"],
            configured_prices=inputs.get("configured_prices"), route_report=inputs["route_report"],
        )
        return {**result, "status": "parcial", "snapshot_id": snapshot_id,
                "captured_at": captured, "snapshot_fingerprint": prefix + result["snapshot_fingerprint"]}
    except FileNotFoundError:
        return {**unavailable, "status": "sem_coleta"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {**unavailable, "status": "registro_invalido"}


def snapshot_summary(*, now=None, path: Path | None = None):
    """Expose progress and scoped controls without returning aircraft identities."""
    now = time.time() if now is None else now
    path = path if path is not None else paths.current().data / FILENAME
    try:
        snapshot = _load_snapshot(path)
        coverage = snapshot["coverage"]
        observations = snapshot["observations"]
        if not _fresh(observations["captured_at"], now):
            return {"status": "expirado", "snapshot_id": snapshot["snapshot_id"]}
        scopes = dict(coverage["scopes"])
        owned_inventory = _captured_owned_inventory(snapshot, now)
        scopes["hubs"] = owned_inventory is not None
        fleet = observations["fleet"]
        counts = [fleet["routes"], fleet["parked"], fleet["pending"]]
        scopes["fleet"] = (scopes["fleet"] and coverage["verified"] is True
                           and _fresh(coverage["observed_at"], now)
                           and _fresh(fleet["observed_at"], now)
                           and all(type(count) is int and count >= 0 for count in counts)
                           and coverage["expected_aircraft_count"] == sum(counts)
                           and coverage["unrouted_aircraft_count"] == sum(counts[1:]))
        unrouted = ({"source": "game_fleet_scan", "profile_id": snapshot["profile_id"],
                     "snapshot_id": snapshot["snapshot_id"], "verified": True,
                     "observed_at": min(coverage["observed_at"], fleet["observed_at"]),
                     "value": sum(counts[1:])} if scopes["fleet"] else None)
        commitments = observations.get("fleet_commitments") or {}
        hangar = (_hangar(commitments.get("passenger_hangar"))
                  if commitments.get("source") == HANGAR_SOURCE
                  and commitments.get("status") in ("observed", "partial")
                  and _fresh(commitments.get("observed_at"), now) else None)
        hangar_control = ({"source": HANGAR_SOURCE, "profile_id": snapshot["profile_id"],
                           "snapshot_id": snapshot["snapshot_id"], "verified": True,
                           "observed_at": commitments["observed_at"], "value": hangar["free"]}
                          if hangar is not None else None)
        for scope, valid in _catalog_scopes(observations["engine_coverage"], now).items():
            scopes[scope] = scopes[scope] and valid
        policy_controls = {}
        finance = observations.get("finance_history")
        historical_spending = None
        if (isinstance(finance, dict) and finance.get("status") == "observed"
                and finance.get("source") == FINANCE_SOURCE and finance.get("historical_only") is True
                and finance.get("profile_id") == snapshot["profile_id"]
                and _fresh(finance.get("observed_at"), now)
                and finance["observed_at"] <= observations["captured_at"]):
            summary = validate_summary(finance.get("summary"))
            if summary is not None:
                historical_spending = {
                    "source": FINANCE_SOURCE, "profile_id": snapshot["profile_id"],
                    "snapshot_id": snapshot["snapshot_id"], "verified": True,
                    "observed_at": finance["observed_at"], "historical_only": True,
                    "window_hours": 24,
                    "value": sum(summary[key] for key in ("aircraft_orders", "hubs", "route_fees")),
                }
        policy_values = observations.get("investment_policy")
        if isinstance(policy_values, dict):
            for name, (minimum, maximum) in AUDITED_POLICY_LIMITS.items():
                value = policy_values.get(name)
                if type(value) is int and minimum <= value <= maximum:
                    policy_controls[name] = {"source": "investment_policy", "profile_id": snapshot["profile_id"],
                                             "snapshot_id": snapshot["snapshot_id"], "verified": True,
                                             "observed_at": observations["captured_at"], "value": value}
        cash = observations["cash"]
        cash_amount = cash["available"]
        cash_stamp = cash["observed_at"]
        cash_control = (
            {"source": "game_snapshot", "profile_id": snapshot["profile_id"],
             "snapshot_id": snapshot["snapshot_id"], "verified": True,
             "observed_at": cash_stamp, "value": cash_amount}
            if type(cash_amount) is int and cash_amount >= 0
            and _fresh(cash_stamp, now) and cash_stamp <= observations["captured_at"]
            else None
        )
        external_summary = {}
        if "external_route_research" in observations:
            external = _external_research(
                observations["external_route_research"],
                {hub["id"] for hub in snapshot["hubs"]} if scopes["hubs"] else set(), now)
            candidates = external["candidate_inventory"]
            external_summary["external_route_research"] = {
                "coverage": "partial", "candidate_count": len(candidates),
                "fresh_price_count": sum("hub_price" in row for row in candidates),
                "fresh_points_count": sum("hub_points" in row for row in candidates),
                "fresh_sample_count": len(external["samples"]),
                "read_only": True, "purchase_eligible": False,
            }
        return {"status": "parcial", "snapshot_id": snapshot["snapshot_id"],
                "captured_at": observations["captured_at"],
                "observed_at": snapshot["observed_at"],
                "scopes": scopes,
                "owned_hub_count": len(snapshot["hubs"]) if scopes["hubs"] else None,
                "owned_inventory": owned_inventory,
                "fleet_count": coverage["expected_aircraft_count"] if scopes["fleet"] else None,
                "unrouted_aircraft_control": unrouted,
                "passenger_hangar_control": hangar_control,
                "historical_investment_spending": historical_spending,
                **({"policy_controls": policy_controls} if "investment_policy" in observations else {}),
                "route_samples": len(observations["route_research"]["samples"]),
                **external_summary,
                "native_route_quote_count": sum(_fresh(row.get("observed_at"), now)
                                                for row in observations.get("native_route_quotes", [])),
                "engine_coverage": observations["engine_coverage"],
                "cash_observed": cash_control is not None,
                "cash_control": cash_control,
                "read_only": True}
    except FileNotFoundError:
        return {"status": "sem_coleta", "snapshot_id": None}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "registro_invalido", "snapshot_id": None}
