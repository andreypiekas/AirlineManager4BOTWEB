"""Conservative direct-route screening of correlated research observations."""
from __future__ import annotations

from route_detail_evidence import MAX_AGE as ROUTE_DETAIL_MAX_AGE


def assess_direct_route(sample: dict, variant: dict | None, engine_evidence: dict | None,
                        *, max_evidence_age: int) -> dict:
    """Compare only normalized evidence from the current research queue.

    This assesses physical dimensions, independently of game mode and rules.
    A short range calls for stopover research; no stopover is assumed.
    """
    detail = variant.get("engine_detail") if variant else None
    correlated = bool(detail and detail["model_identity_verified"] and engine_evidence
                      and engine_evidence["model_detail_identity_verified"]
                      and variant["engine_available"])
    metrics = detail["metrics"] if correlated else {}
    route = sample.get("route_detail") or {}
    range_km = metrics.get("range_km")
    required = metrics.get("required_runway_ft")
    distance = sample["distance_km"]

    def compare(available, minimum):
        if available is None or minimum is None:
            return "unknown"
        return "sufficient" if available >= minimum else "short"

    checks = {
        "range": compare(range_km, distance),
        "origin_runway": compare(route.get("origin_runway_ft"), required),
        "destination_runway": compare(route.get("destination_runway_ft"), required),
    }
    expiries = [sample["observed_at"] + max_evidence_age]
    if correlated:
        expiries.extend([detail["observed_at"] + max_evidence_age,
                         engine_evidence["observed_at"] + max_evidence_age])
    if route:
        expiries.append(route["observed_at"] + ROUTE_DETAIL_MAX_AGE)
    status = ("direct_shortfall" if "short" in checks.values() else
              "direct_dimensions_sufficient" if all(v == "sufficient" for v in checks.values())
              else "unknown")
    return {
        "source": "observed_direct_dimensions_v1", "status": status,
        "checks": checks, "distance_km": distance, "variant_range_km": range_km,
        "required_runway_ft": required,
        "origin_runway_ft": route.get("origin_runway_ft"),
        "destination_runway_ft": route.get("destination_runway_ft"),
        "stopover_research_required": checks["range"] == "short",
        "game_rules_verified": False, "purchase_eligible": False,
        "expires_at": min(expiries),
    }
