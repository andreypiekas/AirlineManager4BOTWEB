"""Retain verified native form quotes for the aircraft that produced them.

The game form is scoped to an existing aircraft. These observations are
historical research, not price evidence for a future aircraft or residual demand.
Only the browser-owning bot writes this bounded in-memory collection; the cycle
snapshot persists it privately with the original observation timestamps.
"""
from __future__ import annotations

import math
import re
import time
from copy import deepcopy

import paths
from opportunity_models import DEFAULT_MAX_AGE_SECONDS

_MAX_QUOTES = 256


def _identity(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,13}", value) is not None


def _numbers(values, length):
    return (isinstance(values, (tuple, list)) and len(values) == length
            and all(type(value) is int and value >= 0 for value in values))


def _fresh(row, now, profile_id):
    stamp = row.get("observed_at")
    return (row.get("profile_id") == profile_id and type(stamp) in (int, float)
            and math.isfinite(stamp) and 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS)


def native_route_quotes(bot, *, now=None):
    now = time.time() if now is None else now
    profile_id = paths.current().label
    return deepcopy([row for row in getattr(bot, "_native_route_quotes", [])
                     if _fresh(row, now, profile_id)])


def reference_for_route(rows, *, profile_id, origin_id, destination_id, distance_km,
                        stopover_id=None, now):
    """Summarize captured form observations without transferring aircraft-specific prices.

    Use the exact direction, distance and stop identity. A direct quote can
    carry the independently correlated search distance alongside its form distance.
    The caller supplies the capture clock for reproducible historical replay.
    """
    matching = []
    for row in rows:
        if (not isinstance(row, dict) or not _fresh(row, now, profile_id)
                or row.get("source") != "game_native_route_form"
                or row.get("scope") != "existing_aircraft_only"
                or row.get("purchase_eligible") is not False
                or not _identity(row.get("aircraft_id"))
                or row.get("origin_id") != origin_id or row.get("destination_id") != destination_id
                or row.get("stopover_id") != stopover_id):
            continue
        native_distance = row.get("distance_km")
        search_distance = row.get("research_distance_km")
        if (not _numbers((native_distance,), 1) or not native_distance
                or (native_distance != distance_km and (stopover_id is not None
                    or search_distance != distance_km or not _correlated_distance(search_distance, native_distance)))):
            continue
        fares = row.get("fares")
        if (not isinstance(fares, dict) or set(fares) != set("yjf")
                or not _numbers(tuple(fares.values()), 3) or not any(fares.values())
                or not _numbers((row.get("route_fee"), row.get("aircraft_on_route")), 2)):
            continue
        matching.append(row)
    if not matching:
        return None

    def bounds(values):
        return {"min": min(values), "max": max(values)}

    stamps = [row["observed_at"] for row in matching]
    reference = {"source": "game_native_route_form", "scope": "existing_aircraft_only",
            "purchase_eligible": False, "quote_count": len(matching),
            "oldest_observed_at": min(stamps), "newest_observed_at": max(stamps),
            "expires_at": min(stamps) + DEFAULT_MAX_AGE_SECONDS,
            "stopover_id": stopover_id, "distance_km": distance_km,
            "route_fee_range": bounds([row["route_fee"] for row in matching]),
            "aircraft_on_route_range": bounds([row["aircraft_on_route"] for row in matching]),
            "fare_ranges": {key: bounds([row["fares"][key] for row in matching]) for key in "yjf"},
            "daily_demand_residual": None}
    if any(row["distance_km"] != distance_km for row in matching):
        reference["native_distance_range"] = bounds([row["distance_km"] for row in matching])
    if any(row.get("event_demand_boosted") is True for row in matching):
        reference["event_demand_boosted"] = True
    return reference


def _correlated_distance(search_distance, native_distance):
    return (type(search_distance) in (int, float) and 0 < search_distance <= 25000
            and abs(search_distance - native_distance) <= 5)


def record_native_route_quote(bot, *, aircraft_id, origin_id, destination_id,
                             distance, fee, occupied, fares, stopover_id=None,
                             total_demand=None, today_demand=None, event_demand_boosted=None,
                             research_distance_km=None, now=None):
    """Called only after matching reads of the bound native form and fares."""
    if (not all(_identity(value) for value in (aircraft_id, origin_id, destination_id))
            or origin_id == destination_id
            or (stopover_id is not None and (not _identity(stopover_id)
                                            or stopover_id in (origin_id, destination_id)))
            or not _numbers((distance, fee, occupied), 3) or distance == 0
            or not _numbers(fares, 3) or not any(fares)
            or (total_demand is not None and not _numbers(total_demand, 3))
            or (today_demand is not None and not _numbers(today_demand, 3))
            or (research_distance_km is not None and (stopover_id is not None
                or not _correlated_distance(research_distance_km, distance)))):
        return False
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
        return False
    identity = {"aircraft_id": aircraft_id, "origin_id": origin_id,
                "destination_id": destination_id, "stopover_id": stopover_id}
    row = {**identity, "profile_id": paths.current().label, "observed_at": now,
           "source": "game_native_route_form", "scope": "existing_aircraft_only",
           "purchase_eligible": False, "distance_km": distance, "route_fee": fee,
           "aircraft_on_route": occupied, "fares": dict(zip("yjf", fares)),
           "daily_demand_total": (dict(zip("yjf", total_demand)) if total_demand is not None else None),
           "daily_demand_residual": None}
    if event_demand_boosted is True:
        row["event_demand_boosted"] = True
    if today_demand is not None:
        row["observed_today_demand"] = dict(zip("yjf", today_demand))
    if research_distance_km is not None:
        row["research_distance_km"] = research_distance_km
    previous = native_route_quotes(bot, now=now)
    previous = [old for old in previous if not all(old[key] == value for key, value in identity.items())]
    bot._native_route_quotes = [*previous, row][-_MAX_QUOTES:]
    return True
