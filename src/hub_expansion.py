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


def _airport_id(value: object) -> Optional[str]:
    """Normalize old integer identifiers without admitting arbitrary values."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    airport_id = str(value).strip()
    return airport_id if _ID.fullmatch(airport_id) else None


def _points(value: object) -> Optional[int]:
    """Keep hub point costs separate from dollar prices."""
    if type(value) is not int or not 0 <= value <= 10_000_000:
        return None
    return value


def _stored_candidates(value: object) -> list[dict]:
    """Read legacy catalog rows defensively and keep their evidence conservative."""
    if not isinstance(value, list):
        return []
    candidates = {}
    duplicate_ids = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        airport_id = _airport_id(raw.get("id"))
        if airport_id is None or airport_id in duplicate_ids:
            continue
        normalized = {
            **raw,
            "id": airport_id,
            "name": str(raw.get("name") or "").strip()[:160],
            "code": game_code(airport_id, raw.get("code")),
            "hub_price": _amount(raw.get("hub_price")),
            "hub_points": _points(raw.get("hub_points", 0)),
            "scenario": raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {},
        }
        if airport_id in candidates:
            # Conflicting persisted duplicates cannot be treated as fresh evidence.
            candidates[airport_id].update({"observed_at": None, "scenario": {}})
            duplicate_ids.add(airport_id)
            continue
        candidates[airport_id] = normalized
    return list(candidates.values())


def _demand_sample(origin: str, row: object) -> Optional[dict]:
    """Validate a single route observation without inventing missing demand."""
    if not isinstance(row, dict):
        return None
    destination = _airport_id(row.get("arr_id"))
    if destination is None or destination == origin or isinstance(row.get("distance"), bool):
        return None
    try:
        distance = float(row.get("distance"))
    except (TypeError, ValueError, OverflowError):
        return None
    demand = [row.get(key) for key in ("y", "j", "f")]
    if (not math.isfinite(distance) or not 0 < distance <= 25000
            or any(type(value) is not int or not 0 <= value <= 100_000_000 for value in demand)):
        return None
    return {"origin_id": origin, "destination_id": destination,
            "distance_km": round(distance, 3),
            "y": demand[0], "j": demand[1], "f": demand[2],
            "source": "game_route_search"}


def _stored_demand(value: object) -> dict[str, dict]:
    """Ignore corrupt legacy rows rather than propagating false freshness."""
    if not isinstance(value, dict):
        return {}
    valid = {}
    for key, row in value.items():
        if not isinstance(row, dict) or row.get("source") != "game_route_search":
            continue
        origin = _airport_id(row.get("origin_id"))
        timestamp = row.get("observed_at")
        if origin is None or type(timestamp) is not int or timestamp <= 0:
            continue
        sample = _demand_sample(origin, {"arr_id": row.get("destination_id"),
                                         "distance": row.get("distance_km"),
                                         "y": row.get("y"), "j": row.get("j"), "f": row.get("f")})
        if sample is not None and key == f"{origin}:{sample['destination_id']}":
            valid[key] = {**sample, "observed_at": timestamp}
    return valid


class HubExpansionRegistry:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else paths.current().data / "hub_expansion.json"

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def catalog_scan_position(self) -> dict:
        """Return the last inspected country/airport for incremental price collection."""
        with _LOCK:
            raw = self._load().get("catalog_scan")
        if not isinstance(raw, dict):
            return {}
        country = raw.get("country")
        airport_id = raw.get("airport_id")
        if not isinstance(country, str) or not country.strip():
            return {}
        return {"country": country, "airport_id": _airport_id(airport_id)}

    def record_catalog_scan_position(self, country: str, airport_id: object) -> bool:
        """Persist progress even if a game price is temporarily unavailable."""
        if not isinstance(country, str) or not 0 < len(country.strip()) <= 120:
            return False
        if airport_id is not None and _airport_id(airport_id) is None:
            return False
        with _LOCK:
            current = self._load()
            current["catalog_scan"] = {"country": country.strip(),
                                       "airport_id": _airport_id(airport_id),
                                       "visited_at": int(time.time())}
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def due_catalog_retries(self, *, now: Optional[int] = None) -> list[dict]:
        """Expose failed airport reads eligible for a bounded future retry."""
        now = int(time.time() if now is None else now)
        with _LOCK:
            retries = self._load().get("catalog_retries", [])
        if not isinstance(retries, list):
            return []
        due = []
        for row in retries:
            if (isinstance(row, dict) and isinstance(row.get("country"), str)
                    and 0 < len(row["country"].strip()) <= 120
                    and _airport_id(row.get("airport_id")) is not None
                    and type(row.get("retry_after")) is int
                    and row["retry_after"] <= now):
                due.append({"country": row["country"], "airport_id": row["airport_id"]})
        return due[:1]

    def record_catalog_attempt(self, country: str, airport_id: object, *, success: bool) -> bool:
        """Persist a bounded backoff queue without losing the forward scan cursor."""
        airport_id = _airport_id(airport_id)
        if (not isinstance(country, str) or not 0 < len(country.strip()) <= 120
                or airport_id is None):
            return False
        with _LOCK:
            current = self._load()
            queue = current.get("catalog_retries", [])
            queue = queue if isinstance(queue, list) else []
            pending = [row for row in queue if isinstance(row, dict)
                       and (row.get("country"), row.get("airport_id")) != (country, airport_id)]
            if not success:
                previous = next((row for row in queue if isinstance(row, dict)
                                 and (row.get("country"), row.get("airport_id")) == (country, airport_id)), {})
                attempts = min(20, max(0, previous.get("attempts", 0)
                                       if type(previous.get("attempts")) is int else 0) + 1)
                now = int(time.time())
                pending.append({"country": country, "airport_id": airport_id,
                                "attempts": attempts,
                                "retry_after": now + min(3600, 30 * (2 ** min(attempts - 1, 7)))})
            current["catalog_retries"] = pending[-500:]
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_catalog(self, options: object, *, complete: bool = False) -> bool:
        """Persist a game-confirmed purchasable catalog or partial page.

        Missing and empty responses cannot erase previous observations.
        A partial page merges by airport ID instead of dropping unseen pages.
        """
        if not isinstance(options, list):
            return False
        incoming = {}
        incomplete = False
        for item in options:
            if not isinstance(item, dict):
                incomplete = True
                continue
            if item.get("purchasable") is not True:
                continue
            airport_id = _airport_id(item.get("id"))
            if airport_id is None:
                incomplete = True
                continue
            candidate = {
                "id": airport_id,
                "name": str(item.get("name") or "").strip()[:160],
                "code": game_code(airport_id, item.get("code")),
                "hub_price": _amount(item.get("hub_price")),
                "hub_points": _points(item.get("hub_points", 0)),
            }
            if candidate["hub_points"] is None:
                return False
            if airport_id in incoming and incoming[airport_id] != candidate:
                return False
            incoming[airport_id] = candidate
        if not incoming:
            return False
        verified_complete = complete is True and not incomplete
        with _LOCK:
            current = self._load()
            observed_at = int(time.time())
            previous = {c["id"]: c for c in _stored_candidates(current.get("candidates"))}
            if not verified_complete:
                # Legacy records inherited the catalog timestamp. Capture it
                # before the partial refresh advances the catalog timestamp.
                for item in previous.values():
                    item.setdefault("observed_at", current.get("observed_at"))
                for airport_id, item in incoming.items():
                    # New price evidence takes precedence. Previous route research
                    # survives a catalog refresh for the same airport.
                    previous[airport_id] = {**previous.get(airport_id, {}), **item,
                                            "observed_at": observed_at}
                incoming = previous
            else:
                incoming = {airport_id: {**previous.get(airport_id, {}), **item,
                                         "observed_at": observed_at}
                            for airport_id, item in incoming.items()}
            current.update({"source": "game_purchase_catalog", "observed_at": observed_at,
                            "catalog_complete": verified_complete,
                            "candidates": sorted(incoming.values(), key=lambda row: (row.get("code") or "", row["id"]))})
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_research(self, airport_id: str, research: dict) -> bool:
        """Store a game-researched and model-specific projected route scenario."""
        airport_id = _airport_id(airport_id)
        if airport_id is None or not isinstance(research, dict):
            return False
        if research.get("source") != "game_research":
            return False
        with _LOCK:
            current = self._load()
            candidates = _stored_candidates(current.get("candidates"))
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
            current["candidates"] = candidates
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_demand(self, origin_id: object, results: object) -> int:
        """Store independently observed route demand keyed by game airport IDs.

        A partial search only updates the destinations it actually returned.
        These samples provide demand evidence, not investment projections.
        """
        origin = _airport_id(origin_id)
        if origin is None or not isinstance(results, list):
            return 0
        if not results or len(results) > 1000:
            return 0
        observations = {}
        for row in results:
            sample = _demand_sample(origin, row)
            if sample is None:
                # A partly decoded page must not stamp valid rows as complete.
                return 0
            key = f"{origin}:{sample['destination_id']}"
            if key in observations and observations[key] != sample:
                return 0
            observations[key] = sample
        with _LOCK:
            current = self._load()
            previous = _stored_demand(current.get("route_demand"))
            now = int(time.time())
            previous.update({key: {**sample, "observed_at": now}
                             for key, sample in observations.items()})
            # Keep the newest observations when a large airline searches many routes.
            if len(previous) > 5000:
                previous = dict(sorted(previous.items(),
                                       key=lambda item: item[1].get("observed_at", 0)
                                       if isinstance(item[1], dict) else 0,
                                       reverse=True)[:5000])
            current["route_demand"] = previous
            current["route_demand_last_at"] = now
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return len(observations)

    def next_demand_origin(self, owned_ids: list[str]) -> Optional[str]:
        """Rotate research toward the owned hub least recently sampled."""
        hubs = sorted({_airport_id(value) for value in owned_ids} - {None}, key=int)
        if not hubs:
            return None
        with _LOCK:
            records = _stored_demand(self._load().get("route_demand"))
        now = int(time.time())
        last_seen = {hub: 0 for hub in hubs}
        for row in records.values():
            origin = row.get("origin_id")
            when = row.get("observed_at")
            if origin in last_seen and when <= now:
                last_seen[origin] = max(last_seen[origin], when)
        return min(hubs, key=lambda hub: (last_seen[hub], int(hub)))

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
        stored_candidates = _stored_candidates(saved.get("candidates"))
        demand = _stored_demand(saved.get("route_demand"))
        fresh_demand = {key: item for key, item in demand.items()
                        if 0 <= now - item["observed_at"] <= MAX_AGE_SECONDS}
        owned = {_airport_id(value) for value in (owned_hub_ids or set())}
        candidates = []
        for raw in stored_candidates:
            if raw["id"] in owned:
                continue
            row = {k: raw.get(k) for k in ("id", "name", "code", "hub_price", "hub_points")}
            scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
            row_time = raw.get("observed_at", catalog_time)
            catalog_fresh = (type(row_time) is int and 0 <= now - row_time <= MAX_AGE_SECONDS)
            row.update({"scenario": scenario, "observed_at": row_time})
            costs = [raw.get("hub_price"), scenario.get("aircraft_price"),
                     scenario.get("route_fee"), scenario.get("hangar_price")]
            valid_costs = [_amount(v) for v in costs]
            investment = round(sum(valid_costs), 2) if all(v is not None for v in valid_costs) else None
            profit = _profit(scenario.get("profit_per_day"))
            research_time = scenario.get("observed_at")
            fresh_research = (type(research_time) is int and
                              0 <= now - research_time <= MAX_AGE_SECONDS)
            ready = (catalog_fresh and raw.get("hub_points") == 0 and fresh_research
                     and scenario.get("source") == "game_research"
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
                                         row["investment"] if row["status"] == "viavel" else float("inf"),
                                         row.get("code") or "", row.get("id") or ""))
        return {"candidates": candidates, "source": saved.get("source"),
                "observed_at": catalog_time, "catalog_complete": saved.get("catalog_complete") is True,
                "available_cash": available, "cash": cash_value, "reserve": reserve_value,
                "availability_pending": not bool(stored_candidates),
                "demand_samples": len(demand),
                "demand_fresh_samples": len(fresh_demand),
                "demand_observed_at": max((item["observed_at"] for item in demand.values()), default=None)}
