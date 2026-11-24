"""Explicit what-if scenarios for pending research; never purchase evidence."""
from __future__ import annotations

from math import ceil, isfinite
from types import SimpleNamespace

from expansion_economics import DEFAULT_STRESS
from gamemode import EASY, REALISM
from route_optimizer import CLASS_WEIGHTS, CO2_PER_PAX_KM, TURNAROUND_H, estimate_route


def configured_price_assumptions(config):
    """Use positive purchase thresholds as explicit planning assumptions."""
    if config is None:
        return None
    prices = {kind: config.get_int("settings", f"{kind}_price_good", 0)
              for kind in ("fuel", "co2")}
    return normalize_configured_prices(prices)


def normalize_configured_prices(prices):
    if not isinstance(prices, dict):
        return None
    if not all(type(prices.get(kind)) in (int, float) and
               isfinite(prices[kind]) and prices[kind] > 0 for kind in ("fuel", "co2")):
        return None
    return {kind: prices[kind] for kind in ("fuel", "co2")}


def research_mode(stats: object, now: float) -> str | None:
    stamp = getattr(stats, "mode_read_at", None)
    if type(stamp) not in (float, int) or not 0 <= now - stamp <= 900:
        return None
    return next((mode.key for mode in (EASY, REALISM)
                 if mode.label == getattr(stats, "mode", None)), None)


def attach_capital_recovery_preview(economics, capital, *, now):
    """Compare recovery of the displayed subtotal under explicitly partial assumptions."""
    if not economics or not capital or capital.get("aircraft_price_source") != "observed_variant":
        return
    subtotal = capital.get("displayed_subtotal")
    expiry = min(economics["expires_at"], capital["expires_at"])
    if type(subtotal) not in (int, float) or not isfinite(subtotal) or subtotal <= 0 or now >= expiry:
        return
    contribution_key = ("conditional_contribution_after_a_check_per_day"
                        if economics.get("a_check_projection") else "projected_contribution_per_day")
    for row in economics["layouts"]:
        scenarios = {}
        for name in ("base", "stress"):
            contribution = row[name][contribution_key]
            scenarios[name] = {
                "subtotal_recovery_days": round(subtotal / contribution, 2) if contribution > 0 else None,
                "annual_contribution_to_subtotal_pct": round(contribution * 36500 / subtotal, 2),
            }
        row["capital_recovery_preview"] = {
            "source": "displayed_subtotal_what_if_v1", "purchase_eligible": False,
            "expires_at": expiry, "displayed_subtotal": subtotal,
            "contribution_basis": contribution_key, **scenarios,
        }


def optimal_layout(capacity, demand, fares, passengers_per_seat, *, margin, co2_per_passenger):
    """Maximize contribution over integer Y/J/F layouts with weighted capacity.

    Fuel is constant for the flight schedule. For each F count, the objective
    over J is discrete concave: increasing J adds its diminishing marginal
    revenue and removes two Y capacity units. Binary search finds its maximum.
    Seats beyond demand or with nonpositive contribution are unnecessary.
    """
    unit_profit = tuple(fare * (1 - margin) - weight * co2_per_passenger
                        for fare, weight in zip(fares, CLASS_WEIGHTS))
    limits = tuple(min(capacity // weight, ceil(value / passengers_per_seat))
                   if profit > 0 else 0
                   for value, weight, profit in zip(demand, CLASS_WEIGHTS, unit_profit))

    def contribution(index, count):
        return min(demand[index], count * passengers_per_seat) * unit_profit[index]

    def economy_count(remaining, business):
        return min(limits[0], remaining - 2 * business)

    def score(remaining, business):
        return contribution(0, economy_count(remaining, business)) + contribution(1, business)

    best, best_value = None, 0.0
    for first in range(limits[2] + 1):
        remaining = capacity - 3 * first
        low, high = 0, min(limits[1], remaining // 2)
        while low < high:
            middle = (low + high) // 2
            if score(remaining, middle) < score(remaining, middle + 1):
                low = middle + 1
            else:
                high = middle
        value = score(remaining, low) + contribution(2, first)
        if value > best_value:
            best, best_value = (economy_count(remaining, low), low, first), value
    return best


def research_economics_preview(sample: dict, model: dict, variant: dict | None,
                               engine_evidence: dict | None, quotes: dict,
                               mode_key: str | None, margin: float = 0.10, *,
                               physical: dict, stopover: dict | None = None,
                               configured_prices: dict | None = None) -> dict | None:
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
    configured = normalize_configured_prices(configured_prices)
    load = 0.80
    # Do not credit the detour with a higher fare without a native fare read.
    fares = tuple(mode.fare(i, direct_distance) for i in range(3))
    stress = DEFAULT_STRESS
    stressed_candidate = SimpleNamespace(distance=distance, **{
        key: int(value * stress["demand"]) for key, value in demand.items()})
    a_check_cost = metrics.get("a_check_cost_usd")
    a_check_interval = metrics.get("maintenance_interval_hours")
    # The order detail supplies the amount and interval, but does not establish
    # how Easy mode increments the maintenance clock. Show both flight-hour
    # assumptions and use the larger reserve for the conditional contribution.
    a_check = None
    if a_check_cost is not None and a_check_interval is not None:
        a_check = {"source": "observed_variant", "cost_usd": a_check_cost,
                   "interval_hours": a_check_interval, "observed_at": detail["observed_at"],
                   "clock_verified": False,
                   "reserve_basis": "max_real_time_or_nominal_airborne_hours"}

    def serialize(result):
        contribution = result.profit_per_day - result.revenue_per_day * margin
        scenario = {
            "departures_per_day": round(result.legs_per_day, 4),
            "passengers_per_day": dict(zip(("y", "j", "f"), map(lambda x: round(x, 2), result.passengers_per_day))),
            "revenue_by_class": {key: round(sold * fare, 2) for key, sold, fare in
                                 zip(("y", "j", "f"), result.passengers_per_day, fares)},
            "revenue_per_day": round(result.revenue_per_day, 2),
            "fuel_cost_per_day": round(result.fuel_cost_per_day, 2),
            "co2_cost_per_day": round(result.co2_cost_per_day, 2),
            "margin_per_day": round(result.revenue_per_day * margin, 2),
            "projected_contribution_per_day": round(contribution, 2),
        }
        if a_check is not None:
            nominal_hours = distance / spec["speed"] * result.legs_per_day
            real_hours = nominal_hours / mode.speed
            hourly_reserve = a_check_cost / a_check_interval
            reserve = hourly_reserve * max(real_hours, nominal_hours)
            scenario.update({
                "a_check_reserve_real_time_per_day": round(hourly_reserve * real_hours, 2),
                "a_check_reserve_nominal_per_day": round(hourly_reserve * nominal_hours, 2),
                "a_check_reserve_per_day": round(reserve, 2),
                "conditional_contribution_after_a_check_per_day": round(contribution - reserve, 2),
            })
        return scenario

    layouts = []

    def add_layout(base, strategy):
        if base is None:
            return
        layout = dict(zip(("y", "j", "f"), base.layout))
        existing = next((row for row in layouts if row["layout"] == layout), None)
        if existing is not None:
            existing["strategies"].append(strategy)
            return
        if not any(base.layout):
            return
        def scenario(route=candidate, *, occupancy=load, fuel_price=fuel, co2_price=co2):
            return estimate_route(route, seats=capacity, model=spec, mode=mode,
                                  load_factor=occupancy, fuel_price=fuel_price,
                                  co2_price=co2_price, premium=True, prices=fares,
                                  fixed_layout=base.layout, co2_kg_per_pax_km=co2_rate, extra_stops=extra_stops)

        stressed = scenario(stressed_candidate, occupancy=load * stress["occupancy"],
                            fuel_price=fuel * stress["fuel_price"], co2_price=co2 * stress["co2_price"])
        if stressed is not None:
            sensitivities = {
                "fuel_price": scenario(fuel_price=fuel * stress["fuel_price"]),
                "co2_price": scenario(co2_price=co2 * stress["co2_price"]),
                "occupancy": scenario(occupancy=load * stress["occupancy"]),
                "demand": scenario(stressed_candidate),
            }
            layouts.append({"layout": layout, "strategies": [strategy],
                            "base": serialize(base), "stress": serialize(stressed),
                            "sensitivity": {key: serialize(result) if result is not None else None
                                            for key, result in sensitivities.items()}})
            if configured is not None:
                configured_base = scenario(fuel_price=configured["fuel"], co2_price=configured["co2"])
                configured_stress = scenario(stressed_candidate, occupancy=load * stress["occupancy"],
                                             fuel_price=configured["fuel"] * stress["fuel_price"],
                                             co2_price=configured["co2"] * stress["co2_price"])
                if configured_base is not None and configured_stress is not None:
                    layouts[-1]["configured_price_scenarios"] = {
                        "base": serialize(configured_base), "stress": serialize(configured_stress),
                    }

    def estimate(premium, fixed_layout=None):
        return estimate_route(candidate, seats=capacity, model=spec, mode=mode, load_factor=load,
                              fuel_price=fuel, co2_price=co2, premium=premium, prices=fares,
                              co2_kg_per_pax_km=co2_rate, extra_stops=extra_stops, fixed_layout=fixed_layout)

    economy = estimate(False)
    if economy is None:
        return None
    add_layout(economy, "economy")
    add_layout(estimate(True), "premium")
    optimization_scenarios = [
        ("optimized_base", candidate, load, co2),
        ("optimized_stress", stressed_candidate, load * stress["occupancy"], co2 * stress["co2_price"]),
    ]
    if configured is not None:
        optimization_scenarios.extend([
            ("optimized_configured_base", candidate, load, configured["co2"]),
            ("optimized_configured_stress", stressed_candidate, load * stress["occupancy"],
             configured["co2"] * stress["co2_price"]),
        ])
    for strategy, scenario, occupancy, carbon_price in optimization_scenarios:
        layout = optimal_layout(capacity, (scenario.y, scenario.j, scenario.f), fares,
                                economy.legs_per_day * occupancy, margin=margin,
                                co2_per_passenger=co2_rate * distance * carbon_price / 1000)
        if layout is None:
            continue
        add_layout(estimate(True, layout), strategy)
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
            **({"configured_price_assumptions": {"source": "configured_purchase_thresholds",
                                                  "unit": "USD/1000", "verified": False,
                                                  **configured}} if configured is not None else {}),
            "co2_kg_per_pax_km": co2_rate,
            "co2_rate_source": "observed_variant" if observed_co2 is not None else "assumed_default",
            **({"a_check_projection": a_check} if a_check is not None else {}),
            "excluded_costs": excluded,
            "layouts": layouts}
