"""Read-only stopover hypotheses for future aircraft, isolated from route creation."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path

import paths
from airport_catalog import by_id
from route_detail_evidence import MAX_AGE, current_detail, validated_detail
from route_stopover import _CANDIDATES, research_details

SOURCE = "game_map_and_leg_details_v1"
_LOCK = threading.RLock()
_MAX_RECORDS = 10000
_MAP_SNAPSHOT = r"""
const [from, to] = arguments;
const airports = window.airportIconData || [];
const origins = airports.filter(a => String(a.Id) === from);
const destinations = airports.filter(a => String(a.Id) === to);
if (origins.length !== 1 || destinations.length !== 1 || typeof getDistance !== 'function') return null;
const origin = origins[0], destination = destinations[0];
const direct = getDistance(+origin.lat, +origin.lon, +destination.lat, +destination.lon);
const candidates = (() => {
""" + _CANDIDATES + r"""
})();
return {direct, candidates: candidates.filter(row =>
    airports.filter(a => String(a.Id) === row.id).length === 1)};
"""


def _positive(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _airport(value):
    return isinstance(value, str) and value.isascii() and value.isdecimal() and by_id(value) is not None


def _key(subject):
    fields = tuple(subject.get(field) for field in ("origin_id", "destination_id", "model_id", "engine_id"))
    if (all(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,11}", value) for value in fields[:2])
            and all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) for value in fields[2:])
            and fields[0] != fields[1]):
        return ":".join(fields)
    return None


def subject_for(sample, model, variant, now):
    """Bind a hypothesis to actual selected-form dimensions and route evidence."""
    detail = variant.get("engine_detail") if variant else None
    if (not detail or variant.get("engine_available") is not True
            or detail.get("model_identity_verified") is not True):
        return None
    metrics = detail.get("metrics") or {}
    distance, reach = sample.get("distance_km"), metrics.get("range_km")
    runway = metrics.get("required_runway_ft")
    stamp, route_stamp = detail.get("observed_at"), sample.get("observed_at")
    origin, destination = sample.get("origin_id"), sample.get("destination_id")
    if (not _airport(origin) or not _airport(destination)
            or not _positive(distance) or not _positive(reach) or not reach < distance <= 25000
            or type(runway) is not int or not 0 < runway <= 30000
            or any(not _positive(value) or not 0 <= now - value <= 3 * 86400
                   for value in (stamp, route_stamp))):
        return None
    subject = {"origin_id": origin, "destination_id": destination,
               "model_id": model.get("id"), "engine_id": variant.get("engine_id"),
               "range_km": reach, "required_runway_ft": runway, "direct_distance_km": distance,
               "engine_observed_at": stamp, "route_observed_at": route_stamp}
    return subject if _key(subject) else None


def current_stopover(raw, subject, sample, now):
    if (not isinstance(raw, dict) or not subject or sample.get("route_detail_conflict") is True
            or raw.get("source") != SOURCE
            or any(raw.get(key) != value for key, value in subject.items())
            or raw.get("purchase_eligible") is not False or raw.get("game_rules_verified") is not False
            or not _positive(raw.get("observed_at")) or not 0 <= now - raw["observed_at"] <= MAX_AGE
            or raw["observed_at"] < max(subject["engine_observed_at"], subject["route_observed_at"])):
        return None
    stop = raw.get("stop_id")
    if not _airport(stop) or stop in (subject["origin_id"], subject["destination_id"]):
        return None
    first, second = raw.get("first_km"), raw.get("second_km")
    map_direct = raw.get("map_direct_km")
    if (not _positive(map_direct) or abs(map_direct - subject["direct_distance_km"]) > 5
            or any(not _positive(value) or value > subject["range_km"] for value in (first, second))
            or not subject["direct_distance_km"] - 5 <= first + second <= 25000):
        return None
    runway_keys = ("origin_runway_ft", "stop_runway_ft", "destination_runway_ft")
    if any(type(raw.get(key)) is not int or not subject["required_runway_ft"] <= raw[key] <= 30000
           for key in runway_keys):
        return None
    expected = sample.get("destination_runway_ft")
    direct = current_detail(sample.get("route_detail"), subject["origin_id"], subject["destination_id"], now)
    if (expected is not None and expected != raw["destination_runway_ft"]
            or direct and any(direct[key] != raw[key] for key in (runway_keys[0], runway_keys[2]))):
        return None
    return {**subject, "source": SOURCE, "observed_at": raw["observed_at"],
            "expires_at": min(raw["observed_at"] + MAX_AGE, subject["engine_observed_at"] + 3 * 86400,
                              subject["route_observed_at"] + 3 * 86400),
            "stop_id": stop, "stop_code": by_id(stop).iata, "map_direct_km": map_direct,
            "first_km": first, "second_km": second,
            **{key: raw[key] for key in runway_keys},
            "purchase_eligible": False, "game_rules_verified": False}


def select_current_stopover(sample, model, variant, now):
    """Select a uniquely consistent proof for the current route and engine."""
    subject = subject_for(sample, model, variant, now)
    raw_proofs = sample.get("stopover_research")
    if not subject or not isinstance(raw_proofs, list):
        return None
    proofs = [proof for raw in raw_proofs
              if (proof := current_stopover(raw, subject, sample, now)) is not None]
    if proofs and all(proof == proofs[0] for proof in proofs):
        return proofs[0]
    return None


class StopoverResearchRegistry:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return records if isinstance(records, dict) else {}

    def _save(self, records):
        valid = [(key, row) for key, row in records.items() if isinstance(row, dict)
                 and _positive(row.get("attempted_at")) and not key.startswith("@hub:")]
        valid.sort(key=lambda entry: entry[1]["attempted_at"], reverse=True)
        cursors = {key: row for key, row in records.items() if key.startswith("@hub:")
                   and isinstance(row, dict) and _airport(key[5:]) and _positive(row.get("attempted_at"))}
        paths.write_atomic(self.path, json.dumps({**dict(valid[:_MAX_RECORDS]), **cursors}))

    def reserve(self, subjects, now):
        with _LOCK:
            records = self._load()

            def priority(pair):
                key = _key(pair[0])
                hub = pair[0]["origin_id"]
                cursor = records.get("@hub:" + hub)
                cursor = cursor if isinstance(cursor, dict) else {}
                stamp = cursor.get("attempted_at")
                last_key = cursor.get("last_key")
                wrapped = isinstance(last_key, str) and key <= last_key
                return (stamp if _positive(stamp) and stamp <= now else 0, hub, wrapped, key)
            selected = min(subjects, key=priority, default=None)
            if selected is None:
                return None
            key = _key(selected[0])
            cursor_key = "@hub:" + selected[0]["origin_id"]
            prior = records.get(cursor_key)
            offset = prior.get("offset", 0) if isinstance(prior, dict) else 0
            offset = offset if type(offset) is int and 0 <= offset < 8 else 0
            if isinstance(prior, dict) and isinstance(prior.get("last_key"), str) and key <= prior["last_key"]:
                offset = (offset + 2) % 8
            records[cursor_key] = {"attempted_at": now, "last_key": key, "offset": offset}
            records[key] = {"attempted_at": now}
            self._save(records)
            return (*selected, offset)

    def finish(self, subject, sample, attempt, raw, now):
        proof = current_stopover(raw, subject, sample, now)
        if not proof or proof["observed_at"] < attempt:
            return False
        with _LOCK:
            records = self._load()
            key = _key(subject)
            record = records.get(key)
            if not isinstance(record, dict) or record.get("attempted_at") != attempt or "proof" in record:
                return False
            records[key] = {**record, "proof": proof}
            self._save(records)
        return True

    def enrich(self, samples, now):
        with _LOCK:
            records = self._load()
        by_route = {}
        for row in records.values():
            proof = row.get("proof") if isinstance(row, dict) else None
            if isinstance(proof, dict) and _positive(proof.get("observed_at")) and 0 <= now - proof["observed_at"] <= MAX_AGE:
                route = (proof.get("origin_id"), proof.get("destination_id"))
                if all(isinstance(value, str) for value in route):
                    by_route.setdefault(route, []).append(proof)
        result = []
        for sample in samples:
            row = {key: value for key, value in sample.items() if key != "stopover_research"}
            proofs = by_route.get((row.get("origin_id"), row.get("destination_id")))
            if proofs and row.get("route_detail_conflict") is not True:
                row["stopover_research"] = sorted(proofs, key=lambda proof: _key(proof) or "")
            result.append(row)
        return result


def collect_stopover(bot, registry, subjects):
    """At most two suggested stops and two reads of each leg per cycle."""
    if getattr(bot, "stopping", False):
        return 0
    attempt = time.time()
    selected = registry.reserve(subjects, attempt)
    if selected is None:
        return 0
    subject, sample, offset = selected
    origin, destination = subject["origin_id"], subject["destination_id"]
    try:
        args = (origin, destination, subject["range_km"], 25000)
        snapshot = bot.js(_MAP_SNAPSHOT, *args)
        if not isinstance(snapshot, dict) or snapshot != bot.js(_MAP_SNAPSHOT, *args):
            return 0
        direct, suggestions = snapshot.get("direct"), snapshot.get("candidates")
        if (not _positive(direct) or abs(direct - subject["direct_distance_km"]) > 5
                or not isinstance(suggestions, list)):
            return 0
        suggestions = suggestions[:8]
        if suggestions:
            offset %= len(suggestions)
        for candidate in (suggestions[offset:] + suggestions[:offset])[:2]:
            if getattr(bot, "stopping", False):
                return 0
            if not isinstance(candidate, dict):
                continue
            stop, first, second = candidate.get("id"), candidate.get("first"), candidate.get("second")
            if (not _airport(stop) or stop in (origin, destination)
                    or any(not _positive(value) or value > subject["range_km"] for value in (first, second))
                    or not subject["direct_distance_km"] - 5 <= first + second <= 25000):
                continue
            legs = []
            for dep, arr in ((origin, stop), (stop, destination)):
                if getattr(bot, "stopping", False):
                    return 0
                a = research_details(bot, dep, arr)
                if getattr(bot, "stopping", False):
                    return 0
                b = research_details(bot, dep, arr)
                legs.append(validated_detail(b, dep, arr) if a == b else None)
            left, right = legs
            if not left or not right or left["destination_runway_ft"] != right["origin_runway_ft"]:
                continue
            now = time.time()
            proof = {**subject, "source": SOURCE, "observed_at": now, "stop_id": stop,
                     "first_km": first, "second_km": second, "map_direct_km": direct,
                     "origin_runway_ft": left["origin_runway_ft"],
                     "stop_runway_ft": left["destination_runway_ft"],
                     "destination_runway_ft": right["destination_runway_ft"],
                     "game_rules_verified": False, "purchase_eligible": False}
            if not getattr(bot, "stopping", False) and registry.finish(subject, sample, attempt, proof, now):
                return 1
    except Exception:
        # Authenticated Selenium failures can expose sensitive session parameters.
        return 0
    return 0
