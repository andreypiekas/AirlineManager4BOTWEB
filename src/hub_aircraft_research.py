"""Per-profile storage for game-observed next-aircraft hub scenarios.

Research evidence is kept independently of the owned-hub inventory. A saved
scenario can be incomplete: the ranking engine checks its source, timestamps,
cash, route occupancy and physical constraints before recommending anything.
"""
from __future__ import annotations

import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from route_registry import endpoint, route_key


_LOCK = threading.RLock()
_HUB_ID = re.compile(r"^[1-9][0-9]{0,11}$")


class HubAircraftResearchRegistry:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else paths.current().data / "hub_aircraft_research.json"

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, dict) or not isinstance(data.get("scenarios"), list):
            return []
        return [entry for entry in data["scenarios"] if isinstance(entry, dict)]

    def snapshot(self) -> list[dict]:
        """Read saved observations without contacting or changing the game."""
        with _LOCK:
            return deepcopy(self._load())

    def record(self, scenario: dict) -> bool:
        """Persist one explicitly game-observed hub, model and route scenario.

        The caller must supply evidence timestamps and origins for research,
        prices and estimates. They are preserved verbatim so the ranker can
        reject stale or unconfirmed evidence instead of refreshing it here.
        """
        if not isinstance(scenario, dict) or scenario.get("source") != "game_research":
            return False
        hub_id = str(scenario.get("hub_id") or "").strip()
        model = str(scenario.get("model") or "").strip()
        if not _HUB_ID.fullmatch(hub_id) or not model or len(model) > 100:
            return False
        origin = scenario.get("origin")
        destination = scenario.get("destination")
        if not isinstance(origin, dict) or not isinstance(destination, dict):
            return False
        key = route_key(endpoint(origin.get("id"), origin.get("code"), origin.get("name")),
                        endpoint(destination.get("id"), destination.get("code"), destination.get("name")))
        if not key:
            return False
        saved = deepcopy(scenario)
        saved["hub_id"] = hub_id
        saved["model"] = model
        with _LOCK:
            scenarios = self._load()
            scenarios = [entry for entry in scenarios if not (
                entry.get("hub_id") == hub_id
                and str(entry.get("model") or "").casefold() == model.casefold()
                and self._scenario_key(entry) == key)]
            scenarios.append(saved)
            paths.write_atomic(self.path, json.dumps({"scenarios": scenarios}, ensure_ascii=False, indent=2))
        return True

    @staticmethod
    def _scenario_key(scenario: dict) -> str:
        origin = scenario.get("origin") or {}
        destination = scenario.get("destination") or {}
        if not isinstance(origin, dict) or not isinstance(destination, dict):
            return ""
        return route_key(endpoint(origin.get("id"), origin.get("code"), origin.get("name")),
                         endpoint(destination.get("id"), destination.get("code"), destination.get("name")))
