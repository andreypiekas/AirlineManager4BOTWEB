"""Read-only, per-profile inventory of hubs proven by the game's selector.

An aircraft's current route or at-base flag never proves its home hub.
"""
from __future__ import annotations

import json
import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from airport_catalog import game_code
from route_registry import RouteRegistry, endpoint

_LOCK = threading.RLock()
_AIRPORT_ID = re.compile(r"^[0-9]{1,12}$")


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
                continue
            airport_id = str(item.get("id") or "").strip()
            if not _AIRPORT_ID.fullmatch(airport_id) or int(airport_id) == 0:
                continue
            title = str(item.get("text") or item.get("title") or "").strip()[:160]
            code = game_code(airport_id, item.get("code"))
            hubs[airport_id] = {"id": airport_id, "code": code, "name": title}
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

    def snapshot(self, routes: Optional[dict] = None) -> dict:
        with _LOCK:
            saved = deepcopy(self._load())
        hubs = saved.get("hubs", [])
        relations = (routes if routes is not None else RouteRegistry().snapshot()).get("relations", [])
        confirmed = {hub["id"]: [] for hub in hubs}
        unknown = []
        for row in relations:
            # Existing route records lack a verified per-aircraft home hub.
            # Only a separate game-confirmed home_hub_id/source pair is sufficient.
            home_id = str(row.get("home_hub_id") or "")
            if row.get("home_hub_source") == "game" and home_id in confirmed:
                confirmed[home_id].append(row)
            else:
                unknown.append(row)
        result = []
        for hub in hubs:
            aircraft = confirmed[hub["id"]]
            estimates = [r["profit_per_day"] for r in aircraft
                         if r.get("route_key") and r.get("profit_route_key") == r.get("route_key")
                         and isinstance(r.get("profit_per_day"), (int, float))
                         and not isinstance(r.get("profit_per_day"), bool)]
            result.append({**hub, "aircraft_count": len(aircraft), "aircraft": aircraft,
                           "estimated_profit_per_day": round(sum(estimates), 2) if estimates else None,
                           "estimated_routes": len(estimates)})
        return {"hubs": result, "unconfirmed_aircraft": unknown,
                "observed_at": saved.get("observed_at"), "source": saved.get("source"),
                "partial_fleet": True}
