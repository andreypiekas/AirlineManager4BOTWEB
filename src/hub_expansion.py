"""Read-only acquisition scenarios backed by separately verified game observations.

The catalog and route research are collected independently. An airport cannot
be ranked until both observations are present and the investment is complete.
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

_LOCK = threading.RLock()
_ID = re.compile(r"^[1-9][0-9]{0,11}$")
MAX_AGE_SECONDS = 3 * 86400


def _amount(value: object) -> Optional[float]:
    """Accept explicit nonnegative costs, including zero, and reject unknowns."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 2) if math.isfinite(number) and number >= 0 else None


def _profit(value: object) -> Optional[float]:
    """Daily operating profit may legitimately be negative."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 2) if math.isfinite(number) else None


class HubExpansionRegistry:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else paths.current().data / "hub_expansion.json"

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def record_catalog(self, options: object, *, complete: bool = False) -> bool:
        """Persist a game-confirmed purchasable catalog or partial page.

        Missing and empty responses cannot erase previous observations.
        A partial page merges by airport ID instead of dropping unseen pages.
        """
        if not isinstance(options, list):
            return False
        incoming = {}
        for item in options:
            if not isinstance(item, dict):
                continue
            airport_id = str(item.get("id") or "").strip()
            if not _ID.fullmatch(airport_id) or item.get("purchasable") is not True:
                continue
            incoming[airport_id] = {
                "id": airport_id,
                "name": str(item.get("name") or "").strip()[:160],
                "code": game_code(airport_id, item.get("code")),
                "hub_price": _amount(item.get("hub_price")),
            }
        if not incoming:
            return False
        with _LOCK:
            current = self._load()
            previous = {c["id"]: c for c in current.get("candidates", [])
                        if isinstance(c, dict) and _ID.fullmatch(str(c.get("id") or ""))}
            if not complete:
                for airport_id, item in incoming.items():
                    # New price evidence takes precedence. Previous route research
                    # survives a catalog refresh for the same airport.
                    previous[airport_id] = {**previous.get(airport_id, {}), **item}
                incoming = previous
            else:
                incoming = {airport_id: {**previous.get(airport_id, {}), **item}
                            for airport_id, item in incoming.items()}
            current.update({"source": "game_purchase_catalog", "observed_at": int(time.time()),
                            "catalog_complete": bool(complete),
                            "candidates": sorted(incoming.values(), key=lambda row: (row.get("code") or "", row["id"]))})
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_research(self, airport_id: str, research: dict) -> bool:
        """Store a game-researched and model-specific projected route scenario."""
        airport_id = str(airport_id or "").strip()
        if not _ID.fullmatch(airport_id) or not isinstance(research, dict):
            return False
        if research.get("source") != "game_research":
            return False
        with _LOCK:
            current = self._load()
            candidates = current.get("candidates", [])
            row = next((item for item in candidates if item.get("id") == airport_id), None)
            if row is None:
                return False
            row["scenario"] = {
                "source": "game_research", "observed_at": int(time.time()),
                "model": str(research.get("model") or "").strip()[:100],
                "route": str(research.get("route") or "").strip()[:100],
                "route_feasible": research.get("route_feasible") is True,
                "demand_verified": research.get("demand_verified") is True,
                "aircraft_price": _amount(research.get("aircraft_price")),
                "route_fee": _amount(research.get("route_fee")),
                "hangar_price": _amount(research.get("hangar_price")),
                "profit_per_day": _profit(research.get("profit_per_day")),
            }
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def snapshot(self, *, cash: object = None, reserve: object = 0,
                 now: Optional[int] = None, owned_hub_ids: Optional[set[str]] = None) -> dict:
        """Evaluate evidence age, affordability and payback without game writes."""
        with _LOCK:
            saved = deepcopy(self._load())
        now = int(time.time() if now is None else now)
        cash_value = _amount(cash)
        reserve_value = _amount(reserve)
        available = max(0, cash_value - reserve_value) if cash_value is not None and reserve_value is not None else None
        catalog_time = saved.get("observed_at")
        catalog_fresh = (isinstance(catalog_time, int) and 0 <= now - catalog_time <= MAX_AGE_SECONDS)
        candidates = []
        for raw in saved.get("candidates", []):
            if not isinstance(raw, dict) or raw.get("id") in (owned_hub_ids or set()):
                continue
            row = {k: raw.get(k) for k in ("id", "name", "code", "hub_price")}
            scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
            row.update({"scenario": scenario, "observed_at": catalog_time})
            costs = [raw.get("hub_price"), scenario.get("aircraft_price"),
                     scenario.get("route_fee"), scenario.get("hangar_price")]
            valid_costs = [_amount(v) for v in costs]
            investment = round(sum(valid_costs), 2) if all(v is not None for v in valid_costs) else None
            profit = _profit(scenario.get("profit_per_day"))
            research_time = scenario.get("observed_at")
            fresh_research = (isinstance(research_time, int) and
                              0 <= now - research_time <= MAX_AGE_SECONDS)
            ready = (catalog_fresh and fresh_research and scenario.get("source") == "game_research"
                     and scenario.get("route_feasible") is True and scenario.get("demand_verified") is True
                     and bool(scenario.get("model")) and bool(scenario.get("route"))
                     and investment is not None and profit is not None and available is not None)
            if not ready:
                status = "dados_a_confirmar"
            elif profit <= 0:
                status = "sem_lucro"
            elif investment > available:
                status = "saldo_insuficiente"
            else:
                status = "viavel"
            row.update({"investment": investment, "profit_per_day": profit,
                        "payback_days": round(investment / profit, 1) if ready and profit > 0 else None,
                        "status": status})
            candidates.append(row)
        candidates.sort(key=lambda row: (row["status"] != "viavel",
                                         -(row["profit_per_day"] or 0) if row["status"] == "viavel" else 0,
                                         row.get("code") or "", row.get("id") or ""))
        return {"candidates": candidates, "source": saved.get("source"),
                "observed_at": catalog_time, "catalog_complete": saved.get("catalog_complete", False),
                "available_cash": available, "cash": cash_value, "reserve": reserve_value,
                "availability_pending": not bool(saved.get("candidates"))}
