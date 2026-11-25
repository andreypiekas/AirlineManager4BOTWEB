"""Per-profile storage for game-observed next-aircraft hub scenarios.

Research evidence is kept independently of the owned-hub inventory. A saved
scenario can be incomplete: the ranking engine checks its source, timestamps,
cash, route occupancy and physical constraints before recommending anything.
"""
from __future__ import annotations

import json
import math
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from hub_recommendations import _RESEARCH_EVIDENCE_FIELDS
from route_registry import endpoint, route_key


_LOCK = threading.RLock()
_HUB_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
        """Persist one explicitly game-observed hub, model, route and engine.

        The caller must supply evidence timestamps and origins for research,
        prices and estimates. They are preserved verbatim so the ranker can
        reject stale or unconfirmed evidence instead of refreshing it here.
        Missing engine_id identifies a legacy observation independently of all
        explicitly identified engine variants. Never derive an ID from a name.
        """
        if not isinstance(scenario, dict) or scenario.get("source") != "game_research":
            return False
        hub_id = str(scenario.get("hub_id") or "").strip()
        model = str(scenario.get("model") or "").strip()
        if not _HUB_ID.fullmatch(hub_id) or not model or len(model) > 100:
            return False
        model_id = scenario.get("model_id")
        if model_id is not None and (not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id)):
            return False
        has_engine_id = "engine_id" in scenario
        engine_id = self._engine_id(scenario) if has_engine_id else None
        if has_engine_id and engine_id is None:
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
        if has_engine_id:
            saved["engine_id"] = engine_id

        def same_identity(entry: dict) -> bool:
            same_model = (entry.get("model_id") == model_id if model_id is not None
                          else entry.get("model_id") is None
                          and str(entry.get("model") or "").strip().casefold() == model.casefold())
            return (str(entry.get("hub_id") or "").strip() == hub_id
                    and same_model
                    and self._scenario_key(entry) == key
                    and ("engine_id" in entry) == has_engine_id
                    and (not has_engine_id or self._engine_id(entry) == engine_id))

        with _LOCK:
            scenarios = self._load()
            matching = [entry for entry in scenarios if same_identity(entry)]
            if len(matching) == 1 and matching[0] == saved:
                return True

            incoming_stamp = self._observed_at(saved)
            latest_stamp = max((self._observed_at(entry) for entry in matching),
                               default=float("-inf"))
            if incoming_stamp < latest_stamp:
                # Delayed observations must not downgrade newer research.
                return True
            if matching and incoming_stamp == latest_stamp and incoming_stamp > 0:
                latest = [entry for entry in matching
                          if self._observed_at(entry) == latest_stamp]
                if any(self._same_evidence(entry, saved) for entry in latest):
                    return True
                # Keep two contradictory latest readings. The ranking engine
                # already quarantines equal-time conflicts until a newer read.
                if len(latest) >= 2:
                    return True
                scenarios = [entry for entry in scenarios
                             if not same_identity(entry)
                             or self._observed_at(entry) == latest_stamp]
            else:
                scenarios = [entry for entry in scenarios if not same_identity(entry)]
            scenarios.append(saved)
            paths.write_atomic(self.path, json.dumps({"scenarios": scenarios}, ensure_ascii=False, indent=2))
        return True

    @staticmethod
    def _observed_at(scenario: dict) -> float:
        stamp = scenario.get("observed_at")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return float("-inf")
        try:
            value = float(stamp)
        except OverflowError:
            return float("-inf")
        return value if math.isfinite(value) and value > 0 else float("-inf")

    @staticmethod
    def _same_evidence(first: dict, second: dict) -> bool:
        # Match the ranker's conflict contract, ignoring route direction,
        # spelling and presentation-only changes to the same scenario.
        return all(first.get(field) == second.get(field)
                   for field in _RESEARCH_EVIDENCE_FIELDS)

    @staticmethod
    def _engine_id(scenario: dict) -> Optional[str]:
        value = scenario.get("engine_id")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None
        engine_id = str(value).strip()
        return engine_id if _ENGINE_ID.fullmatch(engine_id) else None

    @staticmethod
    def _scenario_key(scenario: dict) -> str:
        origin = scenario.get("origin") or {}
        destination = scenario.get("destination") or {}
        if not isinstance(origin, dict) or not isinstance(destination, dict):
            return ""
        return route_key(endpoint(origin.get("id"), origin.get("code"), origin.get("name")),
                         endpoint(destination.get("id"), destination.get("code"), destination.get("name")))
