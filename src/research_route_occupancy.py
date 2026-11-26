"""Independent own-fleet route occupancy, without assuming residual demand."""
from __future__ import annotations

import math
import re
from collections import Counter

from airport_catalog import by_code, by_id


_ID = re.compile(r"[1-9][0-9]{0,11}")
_OBSERVATION_ID = re.compile(r"[0-9a-f]{32}")


def _recent(stamp, now, age):
    if type(stamp) not in (int, float):
        return False
    try:
        return math.isfinite(stamp) and stamp > 0 and 0 <= now - stamp < age
    except OverflowError:
        return False


def _airport_id(endpoint):
    if not isinstance(endpoint, dict):
        return None
    raw_id, code = endpoint.get("id"), endpoint.get("code")
    if type(raw_id) is int and 0 < raw_id < 10**12:
        raw_id = str(raw_id)
    if isinstance(raw_id, str):
        raw_id = raw_id.strip()
    if isinstance(code, str):
        code = code.strip().upper()
    if isinstance(raw_id, str) and _ID.fullmatch(raw_id):
        airport = by_id(raw_id)
        if airport and code and code not in (airport.iata, airport.icao):
            return None
        code_airport = by_code(code) if isinstance(code, str) and code else None
        if code_airport and code_airport.game_id != raw_id:
            return None
        return raw_id
    if raw_id is not None and raw_id != "" or not isinstance(code, str):
        return None
    airport = by_code(code)
    return airport.game_id if airport else None


def _pair(origin_id, destination_id):
    return tuple(sorted((origin_id, destination_id)))


def _partition_verified(coverage):
    """The audit covers every routed aircraft; verify its unrouted complement."""
    status = coverage.get("native_identity_status")
    if status == "matched":
        observation = coverage.get("native_observation_id")
        return isinstance(observation, str) and bool(_OBSERVATION_ID.fullmatch(observation))
    if status is not None or coverage.get("native_observation_id") is not None:
        return False
    # A complete route audit with no unrouted aircraft already covers the roster.
    return coverage["parked"] == coverage["pending"] == 0


class FleetRouteOccupancy:
    """Project the registry's current roster onto undirected airport ID pairs.

    Positive matches are useful even during a partial audit. Zero is an exact
    own-fleet count only after a fresh, complete, resolvable fleet audit and
    reconciliation of any unrouted aircraft against the native inventory.
    Neither count certifies the game's residual demand or route availability.
    """

    def __init__(self, report: dict | None, now: float):
        self.counts = Counter()
        self.complete = False
        self.observed_at = None
        self.expires_at = None
        if not isinstance(report, dict) or report.get("current_roster_verified") is not True:
            return
        stamp = report.get("current_roster_observed_at")
        rows = report.get("current_relations")
        if not _recent(stamp, now, 900) or not isinstance(rows, list):
            return
        self.observed_at = stamp
        self.expires_at = stamp + 900
        coverage = report.get("fleet_coverage")
        total = report.get("current_roster_total")
        complete = (report.get("current_fleet_coverage_verified") is True
                    and isinstance(coverage, dict)
                    and coverage.get("source") == "game_roster_and_route_audit"
                    and coverage.get("roster_observed_at") == stamp
                    and _recent(coverage.get("observed_at"), now, 900)
                    and stamp <= coverage["observed_at"]
                    and type(total) is int and type(coverage.get("total")) is int
                    and total == len(rows) == coverage["total"]
                    and all(type(coverage.get(key)) is int and coverage[key] >= 0
                            for key in ("routes", "parked", "pending"))
                    and total == sum(coverage[key] for key in ("routes", "parked", "pending"))
                    and _partition_verified(coverage))
        identifiers = Counter(row.get("aircraft_id") for row in rows if isinstance(row, dict)
                              and isinstance(row.get("aircraft_id"), str)
                              and row["aircraft_id"])
        route_ids = Counter(row["game_route_id"] for row in rows if isinstance(row, dict)
                            and type(row.get("game_route_id")) is int and row["game_route_id"] > 0)
        for row in rows:
            if not isinstance(row, dict):
                complete = False
                continue
            identity = row.get("aircraft_id")
            route_id = row.get("game_route_id")
            if (not isinstance(identity, str) or not identity or identifiers[identity] != 1
                    or type(route_id) is not int or route_id < 0):
                complete = False
                continue
            if route_id == 0:
                if row.get("pending_game_route_id"):
                    # Routes omits this assignment while the aircraft is in maintenance.
                    complete = False
                continue
            if route_ids[route_id] != 1:
                complete = False
                continue
            seen = row.get("last_seen")
            if (row.get("source") != "game" or row.get("route_data_stale") is not False
                    or type(row.get("observed_route_id")) is not int
                    or row["observed_route_id"] != route_id or not _recent(seen, now, 3600)):
                complete = False
                continue
            origin, destination = (_airport_id(row.get(key)) for key in ("origin", "destination"))
            if not origin or not destination or origin == destination:
                complete = False
                continue
            self.counts[_pair(origin, destination)] += 1
            self.expires_at = min(self.expires_at, seen + 3600)
        self.complete = bool(complete and sum(self.counts.values()) == coverage["routes"])

    def evidence_for_endpoints(self, origin: dict, destination: dict,
                               route_detail: dict | None = None) -> dict | None:
        origin_id, destination_id = _airport_id(origin), _airport_id(destination)
        if not origin_id or not destination_id:
            return None
        return self.evidence(origin_id, destination_id, route_detail)

    def evidence(self, origin_id: str, destination_id: str, route_detail: dict | None) -> dict | None:
        if (not isinstance(origin_id, str) or not _ID.fullmatch(origin_id)
                or not isinstance(destination_id, str) or not _ID.fullmatch(destination_id)
                or origin_id == destination_id):
            return None
        count = self.counts[_pair(origin_id, destination_id)]
        if not self.complete and not count:
            return None
        observed = (route_detail or {}).get("observed_aircraft_on_route")
        disagreement = (type(observed) is int and
                        (observed < count or (self.complete and observed != count)))
        return {"source": "game_roster_and_route_audit" if self.complete else "game_current_roster",
                "observed_at": self.observed_at, "expires_at": self.expires_at,
                "own_aircraft_count": count, "count_complete": self.complete,
                "game_count_disagrees": disagreement}
