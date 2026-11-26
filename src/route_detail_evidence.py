"""Independent, bounded observations of native route details for planning."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path

import paths
from airport_catalog import by_id
from helpers import game_whole_number
from route_stopover import research_details

SOURCE = "game_route_detail"
MAX_AGE = 900
_MAX_RECORDS = 10000
_ID = re.compile(r"[1-9][0-9]{0,11}")
_FEET = re.compile(r"([0-9]{1,5}|[0-9]{1,2}(?:,[0-9]{3}))\s*ft", re.I)
_OBSERVED_DEMAND = ("observed_daily_demand", "observed_today_demand")
_VOLATILE_FIELDS = {*_OBSERVED_DEMAND, "observed_capable_aircraft", "event_demand_boosted"}
_LOCK = threading.RLock()


def _key(origin, destination):
    if (isinstance(origin, str) and isinstance(destination, str) and origin != destination
            and _ID.fullmatch(origin) and _ID.fullmatch(destination)):
        return f"{origin}:{destination}"
    return None


def _runway(raw):
    match = _FEET.fullmatch(raw.strip()) if isinstance(raw, str) else None
    value = int(match[1].replace(",", "")) if match else 0
    return value if 0 < value <= 30000 else None


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _observed_count(value):
    if isinstance(value, str) and len(value) > 11:
        return None
    return game_whole_number(value)


def _retain_observations(raw, result):
    for field in _OBSERVED_DEMAND:
        demand = raw.get(field)
        if isinstance(demand, dict) and set(demand) == set("yjf"):
            counts = {key: _observed_count(demand[key]) for key in "yjf"}
            if all(value is not None and value <= 100_000_000 for value in counts.values()):
                result[field] = counts
    capable = _observed_count(raw.get("observed_capable_aircraft"))
    if capable is not None and capable <= 999_999_999:
        result["observed_capable_aircraft"] = capable
    if raw.get("event_demand_boosted") is True:
        result["event_demand_boosted"] = True


def validated_detail(raw, origin, destination, *, expected_runway=None, hub_code=None):
    """Correlate the ordered response using the game airport catalogue.

    Label-bound values remain observations. Route occupancy requires independent
    fleet reconciliation, and passenger demand requires economic eligibility checks.
    """
    if not _key(origin, destination) or not isinstance(raw, dict):
        return None
    codes, runways = raw.get("codes"), raw.get("runways")
    if not isinstance(codes, list) or len(codes) != 2 or not isinstance(runways, list) or len(runways) != 2:
        return None
    airports = (by_id(origin), by_id(destination))
    if any(airport is None or not isinstance(code, str)
           or code.strip().upper() not in (airport.iata, airport.icao)
           for airport, code in zip(airports, codes)):
        return None
    if hub_code and (not isinstance(hub_code, str)
                     or hub_code.strip().upper() not in (airports[0].iata, airports[0].icao)):
        return None
    first, second = map(_runway, runways)
    if first is None or second is None or (expected_runway is not None and second != expected_runway):
        return None
    result = {"origin_runway_ft": first, "destination_runway_ft": second,
              "occupied_aircraft": None}
    count = raw.get("occupied")
    if (raw.get("occupancy_label") == "A/C on route" and isinstance(count, str)
            and re.fullmatch(r"[0-9]{1,9}", count)):
        result["observed_aircraft_on_route"] = int(count)
    _retain_observations(raw, result)
    return result


def current_detail(raw, origin, destination, now, *, expected_runway=None):
    """Validate cached proof independently of the older route search sample."""
    if (not isinstance(raw, dict) or raw.get("source") != SOURCE
            or raw.get("origin_id") != origin or raw.get("destination_id") != destination
            or not _key(origin, destination) or not _time(raw.get("observed_at"))
            or not 0 <= now - raw["observed_at"] <= MAX_AGE):
        return None
    a, b = raw.get("origin_runway_ft"), raw.get("destination_runway_ft")
    if (type(a) is not int or type(b) is not int or not 0 < a <= 30000 or not 0 < b <= 30000
            or (expected_runway is not None and b != expected_runway)):
        return None
    result = {"source": SOURCE, "origin_id": origin, "destination_id": destination,
              "observed_at": raw["observed_at"], "origin_runway_ft": a,
              "destination_runway_ft": b, "occupied_aircraft": None}
    count = raw.get("observed_aircraft_on_route")
    if type(count) is int and 0 <= count <= 999999999:
        result["observed_aircraft_on_route"] = count
    _retain_observations(raw, result)
    return result


class RouteDetailRegistry:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else paths.current().data / "hub_expansion_route_details.json"

    def _load(self):
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return saved if isinstance(saved, dict) else {}

    def reserve(self, samples, *, now=None):
        """Rotate across hubs and their routes even after unsuccessful reads."""
        now = time.time() if now is None else now
        with _LOCK:
            records = self._load()
            candidates = {}
            for row in samples:
                if not isinstance(row, dict) or row.get("source") != "game_route_search":
                    continue
                key = _key(row.get("origin_id"), row.get("destination_id"))
                if key:
                    candidates[key] = row
            if not candidates:
                return None
            last_hub = {}
            last_route = {}
            for key, row in records.items():
                stamp = row.get("attempted_at") if isinstance(row, dict) else None
                if _time(stamp) and stamp <= now:
                    hub = key.partition(":")[0]
                    last_hub[hub] = max(last_hub.get(hub, 0), stamp)
                    last_route[key] = stamp
            key = min(candidates, key=lambda key: (last_hub.get(candidates[key]["origin_id"], 0),
                                                   last_route.get(key, 0), key))
            records[key] = {"attempted_at": now}
            self._save(records)
            return candidates[key], now

    def _save(self, records):
        valid = [(key, row) for key, row in records.items() if isinstance(row, dict)
                 and _time(row.get("attempted_at"))]
        valid.sort(key=lambda entry: entry[1]["attempted_at"], reverse=True)
        paths.write_atomic(self.path, json.dumps(dict(valid[:_MAX_RECORDS]), ensure_ascii=False))

    def finish(self, origin, destination, attempted_at, detail, *, observed_at):
        key = _key(origin, destination)
        if not key or not _time(observed_at) or not _time(attempted_at) or observed_at < attempted_at:
            return False
        proof = current_detail({**(detail or {}), "source": SOURCE, "origin_id": origin,
                                "destination_id": destination, "observed_at": observed_at},
                               origin, destination, observed_at)
        with _LOCK:
            records = self._load()
            previous = records.get(key)
            if not isinstance(previous, dict) or previous.get("attempted_at") != attempted_at or not proof:
                return False
            records[key] = {"attempted_at": attempted_at, "detail": proof}
            self._save(records)
        return True

    def enrich(self, samples, *, now=None):
        now = time.time() if now is None else now
        with _LOCK:
            records = self._load()
        result = []
        for sample in samples:
            origin, dest = sample.get("origin_id"), sample.get("destination_id")
            record = records.get(_key(origin, dest), {})
            proof = current_detail(record.get("detail") if isinstance(record, dict) else None,
                                   origin, dest, now)
            row = {key: value for key, value in sample.items()
                   if key not in ("route_detail", "route_detail_conflict")}
            if proof:
                expected = sample.get("destination_runway_ft")
                if expected is not None and expected != proof["destination_runway_ft"]:
                    row["route_detail_conflict"] = True
                else:
                    row["route_detail"] = proof
                    if proof.get("event_demand_boosted") is True:
                        row["event_demand_boosted"] = True
            result.append(row)
        return result


def collect_route_details(bot, registry, samples, hub_codes, *, per_cycle=2):
    """Double-read detached responses from the existing Selenium owner."""
    count = 0
    remaining = list(samples)
    for _ in range(min(3, max(0, per_cycle))):
        if getattr(bot, "stopping", False):
            break
        reserved = registry.reserve(remaining)
        if not reserved:
            break
        sample, attempted_at = reserved
        remaining.remove(sample)
        origin, dest = sample["origin_id"], sample["destination_id"]
        try:
            first = research_details(bot, origin, dest)
            if getattr(bot, "stopping", False):
                break
            second = research_details(bot, origin, dest)
        except Exception:
            # Selenium errors may contain authenticated URLs or session details.
            continue
        observed_at = time.time()
        if (not isinstance(first, dict) or not isinstance(second, dict)
                or getattr(bot, "stopping", False)):
            continue
        identity = (first.keys() | second.keys()) - _VOLATILE_FIELDS
        if any(first.get(key) != second.get(key) for key in identity):
            continue
        # Preserve stable physical data when boarding changes Today between reads.
        # A warning on either response still qualifies the correlated observation.
        stable = {key: value for key, value in second.items() if first.get(key) == value}
        if first.get("event_demand_boosted") is True or second.get("event_demand_boosted") is True:
            stable["event_demand_boosted"] = True
        proof = validated_detail(stable, origin, dest,
                                 expected_runway=sample.get("destination_runway_ft"),
                                 hub_code=hub_codes.get(origin))
        if proof and registry.finish(origin, dest, attempted_at, proof, observed_at=observed_at):
            count += 1
    return count
