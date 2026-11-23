"""Read-only acquisition scenarios backed by separately verified game observations.

The catalog and route research are collected independently. An airport cannot
be ranked conclusively until its route, engine and cost evidence is complete.
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
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_AGE_SECONDS = 3 * 86400
_UNSET = object()


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


def _engine_id(value: object) -> Optional[str]:
    """Accept only an explicit selection ID, never a derived engine name."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    identifier = str(value).strip()
    return identifier if _ENGINE_ID.fullmatch(identifier) else None


def _fresh(stamp: object, now: int) -> bool:
    return (type(stamp) in (int, float) and 0 < stamp <= now
            and now - stamp <= MAX_AGE_SECONDS)


def _scenario_identity(scenario: dict) -> tuple:
    """Keep different engine variants and routes independently addressable."""
    return (str(scenario.get("model") or "").strip().casefold(),
            _engine_id(scenario.get("engine_id")),
            _airport_id(scenario.get("origin_id")),
            _airport_id(scenario.get("destination_id")),
            str(scenario.get("route") or "").strip().casefold())


def _scenarios(candidate: dict) -> list[dict]:
    """Combine the old single-slot format with variant-aware observations."""
    stored = candidate.get("scenarios")
    scenarios = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    legacy_slot = candidate.get("scenario")
    if (isinstance(legacy_slot, dict) and legacy_slot
            and not any(_scenario_identity(item) == _scenario_identity(legacy_slot)
                        for item in scenarios)):
        scenarios.append(legacy_slot)
    return scenarios


def _research_stamp(scenario: dict) -> float:
    stamp = scenario.get("observed_at")
    if type(stamp) not in (int, float):
        return float("-inf")
    try:
        stamp = float(stamp)
    except OverflowError:
        return float("-inf")
    return stamp if math.isfinite(stamp) and stamp > 0 else float("-inf")


_RESEARCH_PROOF_FIELDS = (
    "source", "observed_at", "route_feasible", "demand_verified",
    "external_demand_verified", "engine_verified", "costs", "financial",
    "aircraft_price", "route_fee", "hangar_price", "other_fees",
    "aircraft_price_includes_engine", "engine_delta_cost", "profit_per_day",
)


def _same_research_proof(first: dict, second: dict) -> bool:
    """Ignore display labels while comparing decision-making evidence."""
    return all(first.get(field) == second.get(field)
               for field in _RESEARCH_PROOF_FIELDS)


def _latest_research(candidate: dict) -> list[tuple[dict, bool]]:
    """Exclude stale variants and quarantine contradictory latest observations."""
    groups = {}
    for scenario in _scenarios(candidate):
        identity = _scenario_identity(scenario)
        stamp = _research_stamp(scenario)
        current = groups.get(identity)
        if current is None or stamp > current[0]:
            groups[identity] = (stamp, [scenario])
        elif stamp == current[0] and not any(
                _same_research_proof(scenario, saved) for saved in current[1]):
            current[1].append(scenario)
    return [(scenario, len(group) > 1) for _, group in groups.values()
            for scenario in group]


def _evaluate_scenario(scenario: dict, candidate: dict, *, now: int,
                       price_fresh: bool, points_fresh: bool,
                       available: Optional[float], reserve: Optional[float],
                       research_conflict: bool = False) -> dict:
    """Prove each external-hub alternative independently before ranking it."""
    engine_id = _engine_id(scenario.get("engine_id"))
    model = scenario.get("model")
    model = model.strip() if isinstance(model, str) else ""
    route = scenario.get("route")
    route = route.strip() if isinstance(route, str) else ""
    origin = _airport_id(scenario.get("origin_id"))
    destination = _airport_id(scenario.get("destination_id"))
    costs = scenario.get("costs") if isinstance(scenario.get("costs"), dict) else {}
    financial = scenario.get("financial") if isinstance(scenario.get("financial"), dict) else {}
    explicit_engine = "engine_id" in scenario and engine_id is not None

    # Old flat prices are useful historical information, but cannot prove the
    # selected engine's price or operating profit.
    aircraft_price = _amount(costs.get("aircraft_price") if explicit_engine
                             else scenario.get("aircraft_price"))
    route_fee = _amount(costs.get("route_fee") if explicit_engine
                        else scenario.get("route_fee"))
    hangar_price = _amount(costs.get("hangar_price") if explicit_engine
                           else scenario.get("hangar_price"))
    other_fees = _amount(costs.get("other_fees")) if explicit_engine else None
    engine_delta = _amount(costs.get("engine_delta_cost")) if explicit_engine else None
    includes_engine = costs.get("aircraft_price_includes_engine") if explicit_engine else None
    engine_extra = (0 if includes_engine is True and engine_delta in (None, 0) else engine_delta
                    if includes_engine is False else None)
    components = [candidate.get("hub_price"), aircraft_price, route_fee, hangar_price]
    if explicit_engine:
        components.extend((engine_extra, other_fees))
    valid_costs = [_amount(value) for value in components]
    total_cost = sum(valid_costs) if all(value is not None for value in valid_costs) else None
    investment = round(total_cost, 2) if total_cost is not None and math.isfinite(total_cost) else None
    profit = _profit(financial.get("profit_per_day") if explicit_engine
                     else scenario.get("profit_per_day"))

    pending = []
    if research_conflict:
        pending.append("pesquisa_externa_conflitante")
    if candidate.get("hub_price_conflict_at") is not None:
        pending.append("preco_hub_conflitante")
    if candidate.get("hub_points_conflict_at") is not None:
        pending.append("pontos_hub_conflitantes")
    if not price_fresh or _amount(candidate.get("hub_price")) is None:
        pending.append("preco_hub_a_confirmar")
    if candidate.get("hub_points") is None:
        pending.append("pontos_a_confirmar")
    elif not points_fresh:
        pending.append("pontos_desatualizados")
    elif candidate["hub_points"] > 0:
        pending.append("pontos_necessarios")
    if scenario.get("source") != "game_research" or not _fresh(scenario.get("observed_at"), now):
        pending.append("pesquisa_desatualizada")
    if not model:
        pending.append("modelo_a_confirmar")
    if not route or origin != candidate["id"] or destination in (None, origin):
        pending.append("rota_da_base_a_confirmar")
    if not explicit_engine or scenario.get("engine_verified") is not True:
        pending.append("motor_a_confirmar")
    if scenario.get("route_feasible") is not True:
        pending.append("rota_a_confirmar")
    if scenario.get("demand_verified") is not True or scenario.get("external_demand_verified") is not True:
        pending.append("demanda_externa_a_confirmar")

    def matches_identity(block: dict) -> bool:
        name = block.get("model")
        block_route = block.get("route")
        return (isinstance(name, str) and name.strip().casefold() == model.casefold()
                and isinstance(block_route, str) and block_route.strip().casefold() == route.casefold()
                and _engine_id(block.get("engine_id")) == engine_id
                and _airport_id(block.get("origin_id")) == origin
                and _airport_id(block.get("destination_id")) == destination)

    if (not explicit_engine or costs.get("source") not in ("game_market", "game_research")
            or not _fresh(costs.get("observed_at"), now)
            or not matches_identity(costs)
            or type(includes_engine) is not bool
            or costs.get("engine_delta_invalid") is True
            or ("engine_delta_cost" in costs and costs["engine_delta_cost"] is not None
                and engine_delta is None)
            or investment is None):
        pending.append("custos_motor_rota_a_confirmar")
    if (not explicit_engine or financial.get("source") not in ("route_optimizer", "game_research")
            or not _fresh(financial.get("observed_at"), now)
            or not matches_identity(financial) or profit is None):
        pending.append("lucro_motor_rota_a_confirmar")
    if available is None:
        pending.append("saldo_ou_reserva_a_confirmar")

    ready = not pending
    status = ("dados_a_confirmar" if not ready else "sem_lucro" if profit <= 0
              else "saldo_insuficiente" if investment > available else "viavel")
    return {
        **scenario,
        "engine_id": engine_id,
        "investment": investment,
        "profit_per_day": profit,
        "payback_days": round(investment / profit, 1) if ready and profit > 0 else None,
        "status": status,
        "pending": pending,
        "ranking_conclusive": ready,
        "purchase_evidence": status == "viavel",
        "cost_breakdown": {
            "hub_price": _amount(candidate.get("hub_price")),
            "hub_points": candidate.get("hub_points"),
            "aircraft_price": aircraft_price,
            "aircraft_price_includes_engine": includes_engine,
            "engine_delta_cost": engine_delta,
            "engine_extra_charged": engine_extra,
            "route_fee": route_fee,
            "hangar_price": hangar_price,
            "other_fees": other_fees,
            "reserve": reserve,
            "cash_required": round(investment + reserve, 2)
            if investment is not None and reserve is not None else None,
            "total": investment,
        },
    }


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
            "hub_price_observed_at": raw.get("hub_price_observed_at"),
            "hub_points": _points(raw.get("hub_points")),
            "hub_points_observed_at": raw.get("hub_points_observed_at"),
            "scenario": raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {},
            "scenarios": raw.get("scenarios") if isinstance(raw.get("scenarios"), list) else [],
        }
        if airport_id in candidates:
            # Conflicting persisted duplicates cannot be treated as fresh evidence.
            candidates[airport_id].update({"observed_at": None, "scenario": {},
                                           "scenarios": []})
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
        if (origin is None or type(timestamp) not in (int, float)
                or not math.isfinite(timestamp) or timestamp <= 0):
            continue
        sample = _demand_sample(origin, {"arr_id": row.get("destination_id"),
                                         "distance": row.get("distance_km"),
                                         "y": row.get("y"), "j": row.get("j"), "f": row.get("f")})
        if sample is not None and key == f"{origin}:{sample['destination_id']}":
            valid[key] = {**sample, "observed_at": timestamp}
    return valid


def _stored_demand_conflicts(value: object) -> dict[str, dict]:
    """Retain time-bound quarantine markers without accepting disputed demand."""
    if not isinstance(value, dict):
        return {}
    conflicts = {}
    for key, row in value.items():
        if not isinstance(row, dict) or row.get("source") != "game_route_search":
            continue
        parts = key.split(":") if isinstance(key, str) else []
        stamp = row.get("observed_at")
        if (len(parts) != 2 or any(_airport_id(part) != part for part in parts)
                or parts[0] == parts[1] or type(stamp) not in (int, float)
                or not math.isfinite(stamp) or stamp <= 0):
            continue
        conflicts[key] = {"observed_at": stamp, "source": "game_route_search"}
    return conflicts


def _trusted_demand(saved: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    """A persisted conflict wins unless a strictly later reading resolved it."""
    samples = _stored_demand(saved.get("route_demand"))
    conflicts = _stored_demand_conflicts(saved.get("route_demand_conflicts"))
    for key in samples.keys() & conflicts.keys():
        if samples[key]["observed_at"] > conflicts[key]["observed_at"]:
            conflicts.pop(key)
        else:
            samples.pop(key)
    return samples, conflicts


def _stored_demand_attempts(value: object) -> dict[str, dict]:
    """Recover valid research cursor entries, including inconclusive reads."""
    if not isinstance(value, dict):
        return {}
    attempts = {}
    for key, raw in value.items():
        if (_airport_id(key) != key or not isinstance(raw, dict)
                or type(raw.get("attempted_at")) is not int or raw["attempted_at"] <= 0
                or raw.get("status") not in ("inconclusive", "samples_observed")
                or type(raw.get("sequence")) is not int or raw["sequence"] <= 0):
            continue
        attempts[key] = {"attempted_at": raw["attempted_at"],
                         "status": raw["status"], "sequence": raw["sequence"]}
    return attempts


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

    def record_catalog(self, options: object, *, complete: bool = False,
                       observed_at: Optional[float] = None) -> bool:
        """Persist a game-confirmed purchasable catalog or partial page.

        Missing and empty responses cannot erase previous observations.
        A partial page merges by airport ID instead of dropping unseen pages.
        """
        explicit_time = observed_at is not None
        now = time.time()
        if (explicit_time and (type(observed_at) not in (int, float)
                               or not _fresh(observed_at, now))):
            return False
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
            }
            if "hub_points" in item:
                candidate["hub_points"] = _points(item["hub_points"])
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
            observed_at = observed_at if explicit_time else int(time.time())
            previous = {c["id"]: c for c in _stored_candidates(current.get("candidates"))}

            def valid_stamp(value: object) -> bool:
                return type(value) in (int, float) and 0 < value <= now

            catalog_at = current.get("observed_at")
            if not valid_stamp(catalog_at):
                catalog_at = 0

            if (explicit_time and observed_at < catalog_at
                    and current.get("catalog_complete") is True):
                # Airports absent from a later complete scan cannot be
                # resurrected by an older page arriving out of order.
                incoming = {airport_id: item for airport_id, item in incoming.items()
                            if airport_id in previous}
                if not incoming:
                    return False

            # A complete scan must be newer than every previously ingested
            # page before it may discard airports absent from that scan.
            if explicit_time and observed_at <= catalog_at:
                verified_complete = False

            def refresh(airport_id: str, item: dict) -> dict:
                older = previous.get(airport_id, {})
                if explicit_time and older:
                    older_at = older.get("observed_at", catalog_at)
                    if not valid_stamp(older_at):
                        older_at = catalog_at
                    # Name and airport identity come from the newest page,
                    # while each price/points observation has its own clock.
                    result = {**older, **item, "observed_at": max(observed_at, older_at)}
                    if observed_at < older_at:
                        result["name"] = older.get("name")
                        result["code"] = older.get("code")
                    for field in ("hub_price", "hub_points"):
                        stamp_key = f"{field}_observed_at"
                        conflict_key = f"{field}_conflict_at"
                        former_at = older.get(stamp_key)
                        if former_at is None:
                            former_at = older.get("observed_at", catalog_at)
                        conflict_at = older.get(conflict_key)
                        incoming_value = item.get(field)
                        if incoming_value is None:
                            result[field] = older.get(field)
                            result[stamp_key] = older.get(stamp_key, former_at)
                            if conflict_key in older:
                                result[conflict_key] = conflict_at
                            continue
                        if valid_stamp(conflict_at) and observed_at <= conflict_at:
                            result[field] = None
                            result[stamp_key] = None
                            result[conflict_key] = conflict_at
                        elif valid_stamp(former_at) and observed_at < former_at:
                            result[field] = older.get(field)
                            result[stamp_key] = former_at
                        elif (observed_at == former_at and older.get(field) != incoming_value):
                            # Simultaneous contradictory observations cannot
                            # support a purchase, even after a process restart.
                            result[field] = None
                            result[stamp_key] = None
                            result[conflict_key] = observed_at
                        else:
                            result[field] = incoming_value
                            result[stamp_key] = observed_at
                            result.pop(conflict_key, None)
                    return result
                result = {**older, **item, "observed_at": observed_at}
                if item["hub_price"] is not None:
                    result["hub_price_observed_at"] = observed_at
                else:
                    # Incomplete game reads may not erase an earlier known price
                    # or make that earlier observation appear freshly verified.
                    result["hub_price"] = older.get("hub_price")
                    result["hub_price_observed_at"] = older.get(
                        "hub_price_observed_at") or older.get("observed_at", current.get("observed_at"))
                if "hub_points" in item:
                    result["hub_points_observed_at"] = observed_at
                else:
                    # A price-only read must not silently refresh stale points.
                    result["hub_points_observed_at"] = older.get(
                        "hub_points_observed_at") or older.get("observed_at", current.get("observed_at"))
                return result

            if not verified_complete:
                # Legacy records inherited the catalog timestamp. Capture it
                # before the partial refresh advances the catalog timestamp.
                for item in previous.values():
                    item.setdefault("observed_at", current.get("observed_at"))
                for airport_id, item in incoming.items():
                    # New price evidence takes precedence. Previous route research
                    # survives a catalog refresh for the same airport.
                    previous[airport_id] = refresh(airport_id, item)
                incoming = previous
            else:
                incoming = {airport_id: refresh(airport_id, item)
                            for airport_id, item in incoming.items()}
            # A delayed page cannot roll the catalog clock backward or
            # revoke an independently newer complete scan.
            if explicit_time and observed_at < catalog_at:
                catalog_complete = current.get("catalog_complete") is True
            else:
                catalog_complete = verified_complete
            current.update({"source": "game_purchase_catalog",
                            "observed_at": max(observed_at, catalog_at) if explicit_time else observed_at,
                            "catalog_complete": catalog_complete,
                            "candidates": sorted(incoming.values(), key=lambda row: (row.get("code") or "", row["id"]))})
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_research(self, airport_id: str, research: dict) -> bool:
        """Store separate hub/model/route/engine observations without losing legacy data.

        A new observation needs its own timestamps and linked cost/profit proof
        to rank conclusively. Legacy flat research remains readable but pending.
        """
        airport_id = _airport_id(airport_id)
        if airport_id is None or not isinstance(research, dict):
            return False
        if research.get("source") != "game_research":
            return False
        explicit_engine = "engine_id" in research
        engine_id = _engine_id(research.get("engine_id")) if explicit_engine else None
        if explicit_engine and engine_id is None:
            return False

        costs = research.get("costs") if isinstance(research.get("costs"), dict) else {}
        financial = research.get("financial") if isinstance(research.get("financial"), dict) else {}

        def proof(block: dict, *, price: bool) -> dict:
            evidence = {
                "source": block.get("source"), "observed_at": block.get("observed_at"),
                "model": str(block.get("model") or "").strip()[:100],
                "route": str(block.get("route") or "").strip()[:100],
                "engine_id": _engine_id(block.get("engine_id")),
                "origin_id": _airport_id(block.get("origin_id")),
                "destination_id": _airport_id(block.get("destination_id")),
            }
            if price:
                evidence.update({
                    "aircraft_price": _amount(block.get("aircraft_price")),
                    "engine_delta_cost": _amount(block.get("engine_delta_cost")),
                    "engine_delta_invalid": (
                        block.get("engine_delta_cost") is not None
                        and _amount(block.get("engine_delta_cost")) is None),
                    "aircraft_price_includes_engine": block.get("aircraft_price_includes_engine"),
                    "route_fee": _amount(block.get("route_fee")),
                    "hangar_price": _amount(block.get("hangar_price")),
                    "other_fees": _amount(block.get("other_fees")),
                })
            else:
                evidence["profit_per_day"] = _profit(block.get("profit_per_day"))
            return evidence

        scenario = {
            "source": "game_research",
            # Receipt time is not evidence of when an external-hub route was read.
            "observed_at": research.get("observed_at") if explicit_engine else int(time.time()),
            "model": str(research.get("model") or "").strip()[:100],
            "route": str(research.get("route") or "").strip()[:100],
            "origin_id": _airport_id(research.get("origin_id")),
            "destination_id": _airport_id(research.get("destination_id")),
            "route_feasible": research.get("route_feasible") is True,
            "demand_verified": research.get("demand_verified") is True,
            "external_demand_verified": research.get("external_demand_verified") is True,
            "engine_verified": research.get("engine_verified") is True,
            "aircraft_price": _amount(research.get("aircraft_price", costs.get("aircraft_price"))),
            "route_fee": _amount(research.get("route_fee", costs.get("route_fee"))),
            "hangar_price": _amount(research.get("hangar_price", costs.get("hangar_price"))),
            "other_fees": _amount(research.get("other_fees", costs.get("other_fees"))),
            "aircraft_price_includes_engine": costs.get("aircraft_price_includes_engine"),
            "engine_delta_cost": _amount(costs.get("engine_delta_cost")),
            "profit_per_day": _profit(research.get("profit_per_day", financial.get("profit_per_day"))),
        }
        if explicit_engine:
            scenario.update({"engine_id": engine_id,
                             "engine_label": str(research.get("engine_label") or "").strip()[:100],
                             "costs": proof(costs, price=True),
                             "financial": proof(financial, price=False)})

        with _LOCK:
            current = self._load()
            candidates = _stored_candidates(current.get("candidates"))
            row = next((item for item in candidates if item.get("id") == airport_id), None)
            if row is None:
                return False
            identity = _scenario_identity(scenario)
            existing = _scenarios(row)
            matching = [entry for entry in existing
                        if _scenario_identity(entry) == identity]
            incoming_stamp = _research_stamp(scenario)
            latest_stamp = max((_research_stamp(entry) for entry in matching),
                               default=float("-inf"))
            if incoming_stamp < latest_stamp:
                return True
            if matching and incoming_stamp == latest_stamp and incoming_stamp > 0:
                latest = [entry for entry in matching
                          if _research_stamp(entry) == latest_stamp]
                if any(_same_research_proof(entry, scenario) for entry in latest):
                    return True
                if len(latest) >= 2:
                    return True
                # Both readings remain durable so the evaluator can quarantine
                # their identity until a genuinely later research observation.
                alternatives = [entry for entry in existing
                                if _scenario_identity(entry) != identity
                                or _research_stamp(entry) == latest_stamp]
                alternatives.append(scenario)
            else:
                alternatives = [entry for entry in existing
                                if _scenario_identity(entry) != identity]
                alternatives.append(scenario)
            row["scenarios"] = alternatives
            row["scenario"] = scenario  # Legacy single-slot reader.
            current["candidates"] = candidates
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def record_demand(self, origin_id: object, results: object, *,
                      observed_at: object = _UNSET) -> int:
        """Store independently observed route demand keyed by game airport IDs.

        A partial search only updates the destinations it actually returned.
        Delayed reads cannot replace newer observations. Contradictory samples
        from the same instant quarantine that route until a later verified read.
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
        now = time.time()
        timestamp = now if observed_at is _UNSET else observed_at
        if (type(timestamp) not in (int, float) or not math.isfinite(timestamp)
                or timestamp <= 0 or not 0 <= now - timestamp <= MAX_AGE_SECONDS):
            return 0
        with _LOCK:
            current = self._load()
            previous, conflicts = _trusted_demand(current)
            accepted = 0
            changed = False
            for key, sample in observations.items():
                prior = previous.get(key)
                disputed = conflicts.get(key)
                latest = max(prior["observed_at"] if prior else 0,
                             disputed["observed_at"] if disputed else 0)
                if timestamp < latest or (disputed and timestamp == latest):
                    continue
                candidate = {**sample, "observed_at": timestamp}
                if prior and timestamp == latest and candidate != prior:
                    previous.pop(key)
                    conflicts[key] = {"observed_at": timestamp,
                                      "source": "game_route_search"}
                    changed = True
                    continue
                if candidate != prior:
                    previous[key] = candidate
                    changed = True
                if disputed:
                    conflicts.pop(key)
                    changed = True
                accepted += 1
            if not changed and not accepted:
                return 0
            # Keep the newest observations when a large airline searches many routes.
            if len(previous) > 5000:
                previous = dict(sorted(previous.items(),
                                       key=lambda item: item[1].get("observed_at", 0)
                                       if isinstance(item[1], dict) else 0,
                                       reverse=True)[:5000])
            if len(conflicts) > 5000:
                conflicts = dict(sorted(conflicts.items(),
                                        key=lambda item: item[1]["observed_at"],
                                        reverse=True)[:5000])
            current["route_demand"] = previous
            current["route_demand_conflicts"] = conflicts
            if accepted:
                current["route_demand_last_at"] = max(
                    current.get("route_demand_last_at") or 0, timestamp)
                attempts = _stored_demand_attempts(current.get("route_demand_attempts"))
                if (origin not in attempts or attempts[origin]["attempted_at"] <= timestamp):
                    self._write_demand_attempt(current, origin, int(now), "samples_observed")
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return accepted

    @staticmethod
    def _write_demand_attempt(current: dict, origin: str, now: int, status: str) -> None:
        """Update the per-hub research cursor in the same atomic JSON write."""
        attempts = _stored_demand_attempts(current.get("route_demand_attempts"))
        sequence = max((entry["sequence"] for entry in attempts.values()), default=0) + 1
        attempts[origin] = {"attempted_at": now, "status": status, "sequence": sequence}
        current["route_demand_attempts"] = attempts

    def record_demand_attempt(self, origin_id: object) -> bool:
        """Persist an inconclusive attempt before search, even if Selenium fails.

        This is scheduling evidence only. It never implies zero demand or
        completed coverage, and verified samples are preserved independently.
        """
        origin = _airport_id(origin_id)
        if origin is None:
            return False
        with _LOCK:
            current = self._load()
            self._write_demand_attempt(current, origin, int(time.time()), "inconclusive")
            paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, indent=2))
        return True

    def next_demand_origin(self, owned_ids: list[str]) -> Optional[str]:
        """Rotate on attempted research, even when a hub has no valid results."""
        hubs = sorted({_airport_id(value) for value in owned_ids} - {None}, key=int)
        if not hubs:
            return None
        with _LOCK:
            saved = self._load()
            records, _ = _trusted_demand(saved)
            attempts = _stored_demand_attempts(saved.get("route_demand_attempts"))
        now = time.time()
        last_seen = {hub: 0 for hub in hubs}
        for row in records.values():
            origin = row.get("origin_id")
            when = row.get("observed_at")
            if origin in last_seen and when <= now:
                last_seen[origin] = max(last_seen[origin], when)
        sequences = {hub: 0 for hub in hubs}
        for hub in hubs:
            attempt = attempts.get(hub)
            if attempt and attempt["attempted_at"] <= now:
                last_seen[hub] = max(last_seen[hub], attempt["attempted_at"])
                sequences[hub] = attempt["sequence"]
        return min(hubs, key=lambda hub: (last_seen[hub], sequences[hub], int(hub)))

    def demand_research_snapshot(self, owned_hub_ids: set[str], *,
                                 now: Optional[float] = None) -> dict:
        """Read demand, unresolved conflicts and research attempts atomically.

        Search attempts only prove that research was tried. They never certify
        complete coverage, zero demand or a route's remaining availability.
        """
        owned = {_airport_id(value) for value in owned_hub_ids} - {None}
        now = time.time() if now is None else now
        with _LOCK:
            saved = self._load()
            samples, conflicts = _trusted_demand(saved)
            attempts = _stored_demand_attempts(saved.get("route_demand_attempts"))
        rows = [deepcopy(row) for row in samples.values()
                if row["origin_id"] in owned
                and 0 <= now - row["observed_at"] <= MAX_AGE_SECONDS]
        rows.sort(key=lambda row: (int(row["origin_id"]), int(row["destination_id"])))
        progress = []
        for hub in sorted(owned, key=int):
            attempt = attempts.get(hub)
            attempted_at = attempt["attempted_at"] if attempt else None
            if attempted_at is not None and not 0 <= now - attempted_at:
                attempted_at = None
            progress.append({
                "hub_id": hub,
                "last_attempt_at": attempted_at,
                "last_attempt_status": (attempt["status"] if attempted_at is not None
                                        else "unattempted"),
                "conflicted_routes": sum(
                    key.startswith(hub + ":")
                    and 0 <= now - conflict["observed_at"] <= MAX_AGE_SECONDS
                    for key, conflict in conflicts.items()),
                "coverage": "partial",
            })
        return {"samples": rows, "hub_progress": progress, "coverage": "partial"}

    def demand_observations(self, owned_hub_ids: set[str], *,
                            now: Optional[float] = None) -> list[dict]:
        """Return fresh raw traffic samples for owned hubs without inferred demand."""
        return self.demand_research_snapshot(owned_hub_ids, now=now)["samples"]

    def snapshot(self, *, cash: object = None, reserve: object = 0,
                 now: Optional[int] = None, owned_hub_ids: Optional[set[str]] = None) -> dict:
        """Evaluate evidence age, affordability and payback without game writes."""
        with _LOCK:
            saved = deepcopy(self._load())
        now = time.time() if now is None else now
        cash_value = _amount(cash)
        reserve_value = _amount(reserve)
        available = max(0, cash_value - reserve_value) if cash_value is not None and reserve_value is not None else None
        catalog_time = saved.get("observed_at")
        stored_candidates = _stored_candidates(saved.get("candidates"))
        demand, demand_conflicts = _trusted_demand(saved)
        attempts = _stored_demand_attempts(saved.get("route_demand_attempts"))
        fresh_demand = {key: item for key, item in demand.items()
                        if 0 <= now - item["observed_at"] <= MAX_AGE_SECONDS}
        owned = {_airport_id(value) for value in (owned_hub_ids or set())} - {None}
        attempted_owned = {hub for hub in owned if hub in attempts and
                           0 <= now - attempts[hub]["attempted_at"]}
        sampled_owned = {item["origin_id"] for item in demand.values()} & owned
        fresh_sampled_owned = {item["origin_id"] for item in fresh_demand.values()} & owned
        progress = {
            hub: {"hub_id": hub, "last_attempt_at": attempts[hub]["attempted_at"]
                  if hub in attempted_owned else None,
                  "last_attempt_status": attempts[hub]["status"]
                  if hub in attempted_owned else "unattempted",
                  "sample_count": 0, "fresh_sample_count": 0,
                  "conflict_count": 0,
                  "last_sample_at": None, "coverage": "partial"}
            for hub in sorted(owned, key=int)
        }
        for key, sample in demand.items():
            hub = progress.get(sample["origin_id"])
            if hub is None:
                continue
            hub["sample_count"] += 1
            hub["last_sample_at"] = max(hub["last_sample_at"] or 0,
                                        sample["observed_at"])
            if key in fresh_demand:
                hub["fresh_sample_count"] += 1
        for key in demand_conflicts:
            hub = progress.get(key.split(":", 1)[0])
            if hub is not None:
                hub["conflict_count"] += 1
        candidates = []
        for raw in stored_candidates:
            if raw["id"] in owned:
                continue
            row = {k: raw.get(k) for k in (
                "id", "name", "code", "hub_price", "hub_points",
                "hub_price_conflict_at", "hub_points_conflict_at")}
            row_time = raw.get("observed_at", catalog_time)
            price_time = raw.get("hub_price_observed_at")
            if price_time is None:
                price_time = row_time
            points_time = raw.get("hub_points_observed_at")
            if points_time is None:
                points_time = row_time
            evaluated = [_evaluate_scenario(
                scenario, raw, now=now, research_conflict=conflict,
                price_fresh=saved.get("source") == "game_purchase_catalog"
                and _fresh(row_time, now) and _fresh(price_time, now),
                points_fresh=_fresh(points_time, now), available=available,
                reserve=reserve_value) for scenario, conflict in _latest_research(raw)]
            evaluated.sort(key=lambda option: (
                option["status"] != "viavel",
                option["status"] == "dados_a_confirmar",
                option["engine_id"] is None,
                -(option["profit_per_day"] or 0) if option["ranking_conclusive"] else 0,
                option["investment"] if option["investment"] is not None else float("inf"),
                str(option.get("model") or "").casefold(),
                option.get("engine_id") or "",
                str(option.get("route") or "").casefold()))
            best = evaluated[0] if evaluated else None
            row.update({
                "scenario": {key: value for key, value in best.items()
                             if key not in ("investment", "payback_days", "status", "pending",
                                            "ranking_conclusive", "purchase_evidence", "cost_breakdown")}
                if best is not None else {},
                "alternatives": evaluated,
                "observed_at": row_time,
                "hub_price_observed_at": price_time,
                "hub_points_observed_at": points_time,
                "investment": best["investment"] if best else None,
                "profit_per_day": best["profit_per_day"] if best else None,
                "payback_days": best["payback_days"] if best else None,
                "engine_id": best["engine_id"] if best else None,
                "status": best["status"] if best else "dados_a_confirmar",
                "pending": best["pending"] if best else [
                    *(["preco_hub_conflitante"] if raw.get("hub_price_conflict_at") is not None else []),
                    *(["pontos_hub_conflitantes"] if raw.get("hub_points_conflict_at") is not None else []),
                    "pesquisa_externa_a_confirmar"],
                "ranking_conclusive": best["ranking_conclusive"] if best else False,
                "purchase_evidence": best["purchase_evidence"] if best else False,
                "cost_breakdown": best["cost_breakdown"] if best else None,
            })
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
                "demand_conflicts": len(demand_conflicts),
                "demand_fresh_samples": len(fresh_demand),
                "demand_observed_at": max((item["observed_at"] for item in demand.values()), default=None),
                "demand_owned_hubs_total": len(owned),
                "demand_owned_hubs_attempted": len(attempted_owned),
                "demand_owned_hubs_inconclusive": sum(
                    attempts[hub]["status"] == "inconclusive" for hub in attempted_owned),
                "demand_owned_hubs_with_samples": len(sampled_owned),
                "demand_owned_hubs_fresh_samples": len(fresh_sampled_owned),
                "demand_last_attempt_at": max(
                    (attempts[hub]["attempted_at"] for hub in attempted_owned), default=None),
                "demand_hub_progress": list(progress.values()),
                "demand_coverage": "partial"}
