"""Explicit what-if scenarios for pending research; never purchase evidence."""
from __future__ import annotations

from types import SimpleNamespace

from expansion_economics import DEFAULT_STRESS
from gamemode import EASY, REALISM
from route_optimizer import estimate_route


def research_mode(stats: object, now: float) -> str | None:
    stamp = getattr(stats, "mode_read_at", None)
    if type(stamp) not in (float, int) or not 0 <= now - stamp <= 900:
        return None
    return next((mode.key for mode in (EASY, REALISM)
                 if mode.label == getattr(stats, "mode", None)), None)


def research_economics_preview(sample: dict, model: dict, variant: dict | None,
                               engine_evidence: dict | None, quotes: dict,
                               mode_key: str | None, margin: float = 0.10) -> dict | None:
    mode = {EASY.key: EASY, REALISM.key: REALISM}.get(mode_key)
    if (mode is None or not variant or not engine_evidence
            or not engine_evidence.get("model_detail_identity_verified")
            or not variant["engine_available"] or sample.get("event_demand_boosted") is True
            or ((sample.get("route_detail") or {}).get("observed_aircraft_on_route") or 0) > 0
            or not model["range_km"] or sample["distance_km"] > model["range_km"]
            or not model["capacity"] or not float(model["capacity"]).is_integer()
            or model["capacity"] > 10000 or not variant["engine_speed"] or not variant["engine_fuel"]
            or variant["engine_speed"] > 10000 or variant["engine_fuel"] > 1000
            or not all(quotes.get(kind) for kind in ("fuel", "co2"))
            or not 0 <= margin <= 1):
        return None

    demand = sample["demand"]
    distance = sample["distance_km"]
    candidate = SimpleNamespace(distance=distance, **demand)
    capacity = int(model["capacity"])
    spec = {"capacity": capacity, "speed": variant["engine_speed"], "fuel": variant["engine_fuel"]}
    fuel, co2 = quotes["fuel"]["price"], quotes["co2"]["price"]
    load = 0.80
    fares = tuple(mode.fare(i, distance) for i in range(3))
    stress = DEFAULT_STRESS
    stressed_candidate = SimpleNamespace(distance=distance, **{
        key: int(value * stress["demand"]) for key, value in demand.items()})

    def serialize(result):
        return {
            "departures_per_day": round(result.legs_per_day, 4),
            "passengers_per_day": dict(zip(("y", "j", "f"), map(lambda x: round(x, 2), result.passengers_per_day))),
            "revenue_per_day": round(result.revenue_per_day, 2),
            "fuel_cost_per_day": round(result.fuel_cost_per_day, 2),
            "co2_cost_per_day": round(result.co2_cost_per_day, 2),
            "margin_per_day": round(result.revenue_per_day * margin, 2),
            "projected_contribution_per_day": round(result.profit_per_day - result.revenue_per_day * margin, 2),
        }

    layouts = []
    for premium in (False, True):
        base = estimate_route(candidate, seats=capacity, model=spec, mode=mode, load_factor=load,
                              fuel_price=fuel, co2_price=co2, premium=premium, prices=fares)
        if base is None or any(row["layout"] == dict(zip(("y", "j", "f"), base.layout)) for row in layouts):
            continue
        stressed = estimate_route(stressed_candidate, seats=capacity, model=spec, mode=mode,
                                  load_factor=load * stress["occupancy"], fuel_price=fuel * stress["fuel_price"],
                                  co2_price=co2 * stress["co2_price"], premium=True, prices=fares,
                                  fixed_layout=base.layout)
        if stressed is not None:
            layouts.append({"layout": dict(zip(("y", "j", "f"), base.layout)),
                            "base": serialize(base), "stress": serialize(stressed)})
    if not layouts:
        return None
    return {"source": "route_optimizer_what_if_v1", "purchase_eligible": False,
            "demand_basis": "observed_total_not_residual", "mode": mode.key,
            "assumed_load_factor": load, "safety_margin_fraction": margin,
            "expires_at": min(quotes[k]["expires_at"] for k in ("fuel", "co2")),
            "estimated_fares": dict(zip(("y", "j", "f"), fares)), "stress_factors": dict(stress),
            "excluded_costs": ["maintenance", "a_check", "other_recurring", "capex"],
            "layouts": layouts}
