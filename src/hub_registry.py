"""Read-only, per-profile inventory of hubs proven by the game's selector.

An aircraft's current route or at-base flag never proves its home hub.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from airport_catalog import game_code
from route_registry import HOME_HUB_EVIDENCE, RouteRegistry

_LOCK = threading.RLock()
_AIRPORT_ID = re.compile(r"^[0-9]{1,12}$")
_MAX_ESTIMATE_AGE = 3 * 86400
_MAX_CATALOG_AGE = 3 * 86400


def _hub_id(value: object) -> str:
    """Normalize a positive game airport ID without accepting arbitrary values."""
    if isinstance(value, bool) or value is None:
        return ""
    raw = str(value).strip()
    if not _AIRPORT_ID.fullmatch(raw):
        return ""
    number = int(raw)
    return str(number) if number else ""


def _current_route_profit(row: dict, now: int) -> Optional[float]:
    """Only aggregate a finite, dated estimate for the aircraft's current route."""
    value = row.get("profit_per_day")
    stamp = row.get("profit_estimated_at")
    if (not row.get("route_key") or row.get("profit_route_key") != row.get("route_key")
            or isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or isinstance(stamp, bool)
            or not isinstance(stamp, (int, float))
            or not 0 <= now - stamp <= _MAX_ESTIMATE_AGE):
        return None
    return float(value)


def _home_hub_verification(row: dict, owned_hubs: set[str], now: int) -> dict:
    """Validate a per-aircraft game observation without using its route or position.

    Source and observation time are stored by RouteRegistry alongside the
    aircraft. The hub selector establishes ownership, not that aircraft's base.
    Legacy observations missing provenance remain available for investigation.
    """
    home_id = _hub_id(row.get("home_hub_id"))
    source = row.get("home_hub_source")
    observed_at = row.get("home_hub_verified_at")
    evidence = row.get("home_hub_evidence")
    aircraft_id = str(row.get("aircraft_id") or "").strip()
    evidence_matches = (evidence == HOME_HUB_EVIDENCE
                        and bool(re.fullmatch(r"[0-9]{1,14}", aircraft_id))
                        and row.get("home_hub_evidence_aircraft_id") == aircraft_id)
    valid_time = (not isinstance(observed_at, bool)
                  and isinstance(observed_at, (int, float))
                  and math.isfinite(observed_at)
                  and 0 < observed_at <= now)
    if not home_id:
        reason = "home_hub_not_observed"
    elif source != "game":
        reason = "source_unverified"
    elif not valid_time:
        reason = "timestamp_unverified"
    elif not evidence_matches:
        reason = "evidence_unverified"
    elif row.get("home_hub_conflict_id"):
        reason = "conflicting_game_observations"
    elif home_id not in owned_hubs:
        reason = "hub_not_in_owned_catalog"
    else:
        reason = "confirmed"
    return {
        "status": "confirmed" if reason == "confirmed" else "unknown",
        "reason": reason,
        "home_hub_id": home_id or None,
        "source": source if isinstance(source, str) else None,
        "verified_at": observed_at if valid_time else None,
        "evidence": evidence if evidence_matches else None,
    }


class HubRegistry:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else paths.current().data / "hubs_registry.json"

    def record_options(self, options: object, *, selector_present: bool = True) -> bool:
        """Store a complete, authenticated hub selector read.

        Missing/empty selectors are inconclusive and cannot erase earlier hubs.
        """
        if not selector_present or not isinstance(options, list):
            return False
        hubs = {}
        for item in options:
            if not isinstance(item, dict):
                return False
            raw_id = item.get("id")
            airport_id = _hub_id(raw_id)
            if not airport_id:
                if (isinstance(raw_id, bool)
                        or raw_id is not None and not isinstance(raw_id, (str, int))
                        or str(raw_id or "").strip() not in {"", "0"}):
                    # A malformed non-placeholder option makes the snapshot
                    # incomplete, so never replace the last verified catalog.
                    return False
                continue
            title = (str(item.get("text") or "").strip()
                     or str(item.get("title") or "").strip())[:160]
            code = game_code(airport_id, item.get("code"))
            hub = {"id": airport_id, "code": code, "name": title}
            if airport_id in hubs and hubs[airport_id] != hub:
                return False
            hubs[airport_id] = hub
        if not hubs:
            return False
        with _LOCK:
            current = self._load()
            current.update({"source": "game_hub_select", "observed_at": int(time.time()),
                            "hubs": sorted(hubs.values(), key=lambda h: (h["code"], h["id"]))})
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and isinstance(data.get("hubs"), list) else {}
        except (OSError, ValueError):
            return {}

    def snapshot(self, routes: Optional[dict] = None, *, now: Optional[int] = None) -> dict:
        with _LOCK:
            saved = deepcopy(self._load())
        now = int(time.time() if now is None else now)
        # Older records may contain padded IDs. Normalize them only in the
        # snapshot so reading a historical registry never rewrites its file.
        normalized = {}
        for hub in saved.get("hubs", []):
            if not isinstance(hub, dict):
                continue
            airport_id = _hub_id(hub.get("id"))
            if airport_id:
                normalized[airport_id] = {**hub, "id": airport_id}
        hubs = list(normalized.values())
        # Hub and route records belong to the same profile/data directory,
        # even if another profile becomes active after this instance is made.
        route_report = (routes if routes is not None else
                        RouteRegistry(self.path.with_name("routes_registry.json")).snapshot())
        relations = (route_report.get("current_relations", [])
                     if route_report.get("current_roster_available")
                     else route_report.get("relations", []))
        valid_relations = isinstance(relations, list)
        relations = relations if valid_relations else []
        confirmed = {hub["id"]: [] for hub in hubs}
        owned_hub_ids = set(confirmed)
        unknown = []
        for row in relations:
            if not isinstance(row, dict):
                continue
            # Retain the original source/timestamp and annotate the snapshot
            # without changing either the supplied rows or the stored route file.
            verification = _home_hub_verification(row, owned_hub_ids, now)
            aircraft = {**row, "home_hub_verification": verification}
            if verification["status"] == "confirmed":
                confirmed[verification["home_hub_id"]].append(aircraft)
            else:
                unknown.append(aircraft)
        result = []
        for hub in hubs:
            aircraft = confirmed[hub["id"]]
            estimates = [_current_route_profit(row, now) for row in aircraft]
            current_estimates = [amount for amount in estimates if amount is not None]
            result.append({**hub, "aircraft_count": len(aircraft), "aircraft": aircraft,
                           "estimated_profit_per_day": round(sum(current_estimates), 2) if current_estimates else None,
                           "estimated_routes": len(current_estimates),
                           "estimates_pending": len(aircraft) - len(current_estimates)})
        stamp = saved.get("observed_at")
        catalog_fresh = (bool(hubs) and saved.get("source") == "game_hub_select"
                         and type(stamp) in (int, float) and 0 <= now - stamp <= _MAX_CATALOG_AGE)
        fleet_coverage = route_report.get("fleet_coverage")
        identities = {str(row.get("aircraft_id") or "") for row in relations if isinstance(row, dict)}
        fleet_verified = (route_report.get("current_fleet_coverage_verified") is True
                          and route_report.get("current_roster_available") is True
                          and valid_relations
                          and isinstance(fleet_coverage, dict)
                          and fleet_coverage.get("source") == "game_roster_and_route_audit"
                          and type(fleet_coverage.get("total")) is int
                          and fleet_coverage["total"] == len(relations) == len(identities)
                          and all(re.fullmatch(r"[0-9]{1,14}", identity) for identity in identities))
        links_verified = fleet_verified and catalog_fresh and not unknown
        from owned_delivery_coverage import coverage_snapshot
        from fleet_commitment_observations import FILENAME, observations_snapshot, reconcile_route_coverage
        from finance_observations import FILENAME as FINANCE_FILENAME, finance_snapshot

        commitments = observations_snapshot(self.path.with_name(FILENAME), now=now)
        return {"hubs": result, "unconfirmed_aircraft": unknown,
                "delivery_coverage": coverage_snapshot(self.path.with_name("owned_delivery_coverage.json"), now=now),
                "fleet_commitment_observations": commitments,
                "fleet_route_reconciliation": reconcile_route_coverage(
                    commitments, fleet_coverage if fleet_verified else None, now=now),
                "finance_observations": finance_snapshot(self.path.with_name(FINANCE_FILENAME), now=now),
                "observed_at": saved.get("observed_at"), "source": saved.get("source"),
                "partial_fleet": not links_verified, "known_aircraft": len(relations),
                "fleet_coverage": fleet_coverage if fleet_verified else None,
                "current_fleet_coverage_verified": fleet_verified,
                "home_hub_coverage_verified": links_verified,
                "hub_catalog_fresh": catalog_fresh,
                "current_roster_available": route_report.get("current_roster_available") is True,
                "last_fleet_scan": route_report.get("last_scan"),
                "last_verified_full_audit": route_report.get("last_verified_full_audit")}
