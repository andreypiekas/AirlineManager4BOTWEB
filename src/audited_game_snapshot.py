"""Collect the actual planning observations into an immutable A3 snapshot.

The acquisition contract requires complete coverage. Bounded research and
catalogue prices are preserved as observations without certifying that scope.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

import paths
from fleet_commitment_observations import SOURCE as HANGAR_SOURCE, _hangar
from finance_observations import SOURCE as FINANCE_SOURCE, validate_summary
from investment_policy import AUDITED_POLICY_LIMITS, InvestmentPolicy, audited_policy_values
from opportunity_models import DEFAULT_MAX_AGE_SECONDS, fingerprint_snapshot

FILENAME = "audited_game_snapshot.json"


def _fresh(stamp, now):
    return (type(stamp) in (int, float) and math.isfinite(stamp)
            and stamp > 0 and 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS)


def _game_id(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,11}", value) is not None


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
                     preview_margin=0.10, native_quotes=(), configured_prices=None, policy_values=None):
    """Translate independently collected observations without upgrading their provenance."""
    hub_at = inventory.get("observed_at")
    raw_hubs = inventory.get("hubs", [])
    hubs_verified = (inventory.get("source") == "game_hub_select"
                     and inventory.get("hub_catalog_fresh") is True
                     and _fresh(hub_at, now) and bool(raw_hubs)
                     and all(_game_id(row.get("id")) for row in raw_hubs)
                     and len({row["id"] for row in raw_hubs}) == len(raw_hubs))
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
    demand = HubExpansionRegistry().demand_research_snapshot(
        {row["id"] for row in inventory["hubs"]}, now=now)
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
                                configured_prices=configured_price_assumptions(config),
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


def snapshot_summary(*, now=None, path: Path | None = None):
    """Expose aggregate progress only. Never return private aircraft identities."""
    now = time.time() if now is None else now
    path = path if path is not None else paths.current().data / FILENAME
    try:
        snapshot = _load_snapshot(path)
        coverage = snapshot["coverage"]
        observations = snapshot["observations"]
        if not _fresh(observations["captured_at"], now):
            return {"status": "expirado", "snapshot_id": snapshot["snapshot_id"]}
        scopes = dict(coverage["scopes"])
        scopes["hubs"] = scopes["hubs"] and all(
            _fresh(hub["observed_at"], now) for hub in snapshot["hubs"])
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
        return {"status": "parcial", "snapshot_id": snapshot["snapshot_id"],
                "captured_at": observations["captured_at"],
                "observed_at": snapshot["observed_at"],
                "scopes": scopes,
                "owned_hub_count": len(snapshot["hubs"]) if scopes["hubs"] else None,
                "fleet_count": coverage["expected_aircraft_count"] if scopes["fleet"] else None,
                "unrouted_aircraft_control": unrouted,
                "passenger_hangar_control": hangar_control,
                "historical_investment_spending": historical_spending,
                **({"policy_controls": policy_controls} if "investment_policy" in observations else {}),
                "route_samples": len(observations["route_research"]["samples"]),
                "native_route_quote_count": sum(_fresh(row.get("observed_at"), now)
                                                for row in observations.get("native_route_quotes", [])),
                "engine_coverage": observations["engine_coverage"],
                "cash_observed": _fresh(observations["cash"]["observed_at"], now),
                "read_only": True}
    except FileNotFoundError:
        return {"status": "sem_coleta", "snapshot_id": None}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "registro_invalido", "snapshot_id": None}
