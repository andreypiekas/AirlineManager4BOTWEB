"""Explicit what-if scenarios for pending research; never purchase evidence."""
from __future__ import annotations

from types import SimpleNamespace

from expansion_economics import DEFAULT_STRESS
from gamemode import EASY, REALISM
from route_optimizer import CO2_PER_PAX_KM, TURNAROUND_H, estimate_route


def research_mode(stats: object, now: float) -> str | None:
    stamp = getattr(stats, "mode_read_at", None)
    if type(stamp) not in (float, int) or not 0 <= now - stamp <= 900:
        return None
    return next((mode.key for mode in (EASY, REALISM)
                 if mode.label == getattr(stats, "mode", None)), None)


def research_economics_preview(sample: dict, model: dict, variant: dict | None,
                               engine_evidence: dict | None, quotes: dict,
                               mode_key: str | None, margin: float = 0.10, *,
                               physical: dict, stopover: dict | None = None) -> dict | None:
    mode = {EASY.key: EASY, REALISM.key: REALISM}.get(mode_key)
    variant_range = physical["variant_range_km"]
    reach = variant_range if variant_range is not None else model["range_km"]
    detail = (variant or {}).get("engine_detail") or {}
    metrics = detail.get("metrics", {}) if detail.get("model_identity_verified") is True else {}
    observed_capacity = metrics.get("capacity_pax")
    seats = observed_capacity if observed_capacity is not None else model["capacity"]
    # Only a correlated, current map/leg observation selected by the research
    # queue can support a hypothetical stop. Native route-form rules and fares
    # still require independent verification before the route could be eligible.
    via_stop = (stopover is not None and physical["stopover_research_required"]
                and not any(physical["checks"][key] == "short"
                            for key in ("origin_runway", "destination_runway")))
    if (mode is None or not variant or not engine_evidence
            or not engine_evidence.get("model_detail_identity_verified")
            or not variant["engine_available"] or sample.get("event_demand_boosted") is True
            or ((sample.get("route_detail") or {}).get("observed_aircraft_on_route") or 0) > 0
            or ((sample.get("fleet_occupancy") or {}).get("own_aircraft_count") or 0) > 0
            or (sample.get("fleet_occupancy") or {}).get("game_count_disagrees") is True
            or not reach or (not via_stop and (physical["status"] == "direct_shortfall"
                                              or sample["distance_km"] > reach))
            or not seats or not float(seats).is_integer()
            or seats > 10000 or not variant["engine_speed"] or not variant["engine_fuel"]
            or variant["engine_speed"] > 10000 or variant["engine_fuel"] > 1000
            or not all(quotes.get(kind) for kind in ("fuel", "co2"))
            or not 0 <= margin <= 1):
        return None

    demand = sample["demand"]
    direct_distance = sample["distance_km"]
    distance = stopover["first_km"] + stopover["second_km"] if via_stop else direct_distance
    extra_stops = int(via_stop)
    candidate = SimpleNamespace(distance=distance, **demand)
    capacity = int(seats)
    spec = {"capacity": capacity, "speed": variant["engine_speed"], "fuel": variant["engine_fuel"]}
    observed_co2 = metrics.get("co2_kg_per_pax_km")
    co2_rate = observed_co2 if observed_co2 is not None else CO2_PER_PAX_KM
    fuel, co2 = quotes["fuel"]["price"], quotes["co2"]["price"]
    load = 0.80
    # Do not credit the detour with a higher fare without a native fare read.
    fares = tuple(mode.fare(i, direct_distance) for i in range(3))
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
                              fuel_price=fuel, co2_price=co2, premium=premium, prices=fares,
                              co2_kg_per_pax_km=co2_rate, extra_stops=extra_stops)
        if base is None or any(row["layout"] == dict(zip(("y", "j", "f"), base.layout)) for row in layouts):
            continue
        stressed = estimate_route(stressed_candidate, seats=capacity, model=spec, mode=mode,
                                  load_factor=load * stress["occupancy"], fuel_price=fuel * stress["fuel_price"],
                                  co2_price=co2 * stress["co2_price"], premium=True, prices=fares,
                                  fixed_layout=base.layout, co2_kg_per_pax_km=co2_rate, extra_stops=extra_stops)
        if stressed is not None:
            layouts.append({"layout": dict(zip(("y", "j", "f"), base.layout)),
                            "base": serialize(base), "stress": serialize(stressed)})
    if not layouts:
        return None
    expiry = min(quotes[k]["expires_at"] for k in ("fuel", "co2"))
    excluded = ["maintenance", "a_check", "other_recurring", "capex"]
    if via_stop:
        expiry = min(expiry, stopover["expires_at"])
        excluded.append("stopover_specific_charges")
    return {"source": "route_optimizer_what_if_v1", "purchase_eligible": False,
            "demand_basis": "observed_total_not_residual", "mode": mode.key,
            "route_kind": "exploratory_stopover" if via_stop else "direct",
            "travel_distance_km": distance, "fare_distance_km": direct_distance,
            "assumed_turnaround_hours": TURNAROUND_H * (1 + extra_stops),
            **({"stopover_id": stopover["stop_id"], "game_rules_verified": False} if via_stop else {}),
            "range_km": reach, "range_source": "observed_variant" if variant_range is not None else "catalog_model",
            "capacity_pax": capacity,
            "capacity_source": "observed_variant" if observed_capacity is not None else "catalog_model",
            "assumed_load_factor": load, "safety_margin_fraction": margin,
            "expires_at": expiry,
            "estimated_fares": dict(zip(("y", "j", "f"), fares)), "stress_factors": dict(stress),
            "co2_kg_per_pax_km": co2_rate,
            "co2_rate_source": "observed_variant" if observed_co2 is not None else "assumed_default",
            "excluded_costs": excluded,
            "layouts": layouts}
