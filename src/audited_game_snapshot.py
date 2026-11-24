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
from opportunity_models import DEFAULT_MAX_AGE_SECONDS, fingerprint_snapshot

FILENAME = "audited_game_snapshot.json"


def _fresh(stamp, now):
    return (type(stamp) in (int, float) and math.isfinite(stamp)
            and stamp > 0 and 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS)


def _game_id(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,11}", value) is not None


def compose_snapshot(*, profile_id, routes, inventory, demand, engines, market,
                     quotes, cash, cash_at, now):
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
              "routes": False, "models": False, "engines": False, "prices": False}
    observed = [stamp for stamp in (hub_at if hubs_verified else None,
                                    roster_at if fleet_verified else None) if _fresh(stamp, now)]
    cash_verified = type(cash) is int and cash >= 0 and _fresh(cash_at, now)
    coverage = {"source": "game_fleet_scan", "profile_id": profile_id,
                "verified": fleet_verified, "observed_at": roster_at if fleet_verified else None,
                "status": "partial", "scopes": scopes,
                "observed_pages": len(pages) if fleet_verified else None,
                "expected_pages": expected_pages if fleet_verified else None,
                "expected_aircraft_count": total if fleet_verified else None,
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
                    "engine_catalog": engines,
                    "aircraft_market": market,
                    "engine_coverage": engine_coverage,
                    "market_quotes": quotes,
                    "fleet_commitments": inventory.get("fleet_commitment_observations"),
                    "finance_history": inventory.get("finance_observations"),
                    "cash": {"available": cash if cash_verified else None,
                             "observed_at": cash_at if cash_verified else None,
                             "committed": None, "reserve": None},
                }}
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
    from route_registry import RouteRegistry

    profile = paths.current()
    routes = RouteRegistry().snapshot()
    inventory = HubRegistry().snapshot(routes)
    now = time.time()
    demand = HubExpansionRegistry().demand_research_snapshot(
        {row["id"] for row in inventory["hubs"]}, now=now)
    cash, cash_at = recent_verified_money(bot, now=now)
    snapshot = compose_snapshot(profile_id=profile.label, routes=routes, inventory=inventory,
                                demand=demand, engines=EngineCatalogRegistry().snapshot(now=now),
                                market=load_market_evidence(now=now),
                                quotes=recent_market_quotes(bot.stats(), now), cash=cash,
                                cash_at=cash_at, now=now)
    paths.write_atomic(profile.data / FILENAME, json.dumps(snapshot, ensure_ascii=False, allow_nan=False),
                       private=True)
    return snapshot


def snapshot_summary(*, now=None, path: Path | None = None):
    """Expose aggregate progress only. Never return private aircraft identities."""
    now = time.time() if now is None else now
    path = path if path is not None else paths.current().data / FILENAME
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if (snapshot["profile_id"] != paths.current().label or snapshot["schema_version"] != 1
                or fingerprint_snapshot(snapshot) != snapshot["snapshot_id"]):
            raise ValueError("invalid snapshot")
        coverage = snapshot["coverage"]
        observations = snapshot["observations"]
        if not _fresh(observations["captured_at"], now):
            return {"status": "expirado", "snapshot_id": snapshot["snapshot_id"]}
        scopes = dict(coverage["scopes"])
        scopes["hubs"] = scopes["hubs"] and all(
            _fresh(hub["observed_at"], now) for hub in snapshot["hubs"])
        scopes["fleet"] = scopes["fleet"] and _fresh(coverage["observed_at"], now)
        return {"status": "parcial", "snapshot_id": snapshot["snapshot_id"],
                "captured_at": observations["captured_at"],
                "observed_at": snapshot["observed_at"],
                "scopes": scopes,
                "owned_hub_count": len(snapshot["hubs"]) if scopes["hubs"] else None,
                "fleet_count": coverage["expected_aircraft_count"] if scopes["fleet"] else None,
                "route_samples": len(observations["route_research"]["samples"]),
                "engine_coverage": observations["engine_coverage"],
                "cash_observed": _fresh(observations["cash"]["observed_at"], now),
                "read_only": True}
    except FileNotFoundError:
        return {"status": "sem_coleta", "snapshot_id": None}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "registro_invalido", "snapshot_id": None}
