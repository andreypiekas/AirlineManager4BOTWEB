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
from route_registry import RouteRegistry

_LOCK = threading.RLock()
_AIRPORT_ID = re.compile(r"^[0-9]{1,12}$")
_MAX_ESTIMATE_AGE = 3 * 86400


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
        relations = route_report.get("relations", [])
        confirmed = {hub["id"]: [] for hub in hubs}
        unknown = []
        for row in relations:
            # Existing route records lack a verified per-aircraft home hub.
            # Only a separate game-confirmed home_hub_id/source pair is sufficient.
            home_id = _hub_id(row.get("home_hub_id"))
            if row.get("home_hub_source") == "game" and home_id in confirmed:
                confirmed[home_id].append(row)
            else:
                unknown.append(row)
        result = []
        for hub in hubs:
            aircraft = confirmed[hub["id"]]
            estimates = [_current_route_profit(row, now) for row in aircraft]
            current_estimates = [amount for amount in estimates if amount is not None]
            result.append({**hub, "aircraft_count": len(aircraft), "aircraft": aircraft,
                           "estimated_profit_per_day": round(sum(current_estimates), 2) if current_estimates else None,
                           "estimated_routes": len(current_estimates),
                           "estimates_pending": len(aircraft) - len(current_estimates)})
        return {"hubs": result, "unconfirmed_aircraft": unknown,
                "observed_at": saved.get("observed_at"), "source": saved.get("source"),
                "partial_fleet": True, "known_aircraft": len(relations),
                "last_fleet_scan": route_report.get("last_scan")}
