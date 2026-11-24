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


def record_native_route_quote(bot, *, aircraft_id, origin_id, destination_id,
                             distance, fee, occupied, fares, stopover_id=None,
                             total_demand=None, now=None):
    """Called only after matching reads of the bound native form and fares."""
    if (not all(_identity(value) for value in (aircraft_id, origin_id, destination_id))
            or origin_id == destination_id
            or (stopover_id is not None and (not _identity(stopover_id)
                                            or stopover_id in (origin_id, destination_id)))
            or not _numbers((distance, fee, occupied), 3) or distance == 0
            or not _numbers(fares, 3) or not any(fares)
            or (total_demand is not None and not _numbers(total_demand, 3))):
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
    previous = native_route_quotes(bot, now=now)
    previous = [old for old in previous if not all(old[key] == value for key, value in identity.items())]
    bot._native_route_quotes = [*previous, row][-_MAX_QUOTES:]
    return True
