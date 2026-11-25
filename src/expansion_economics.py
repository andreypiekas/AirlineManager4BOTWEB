"""Auditable, read-only A3 accounting for one hub/route/model/engine/layout.

Inputs are explicit, snapshot-bound observations. This module deliberately has
no game-specific fuel, emissions, ticket-price or flight-frequency formula.
The existing route optimizer may supply projections, with its own provenance;
it must not be represented as an observation made directly in the game.

``evaluate_expansion_economics`` consumes the v1 opportunity snapshot and
candidate, plus evidenced accounting inputs. Each input is an envelope with
``value``, ``source``, ``profile_id``, ``snapshot_id``, ``observed_at``,
``verified=True`` and the identity fields required by ``_SUBJECTS``.

``recurring_costs.value`` explicitly declares maintenance, a_check and other.
Unknown entries are ``None``. They produce an upper bound and block a net
profit, payback, ROI and ranking. A configurable revenue haircut is disclosed
independently of actual costs and never substitutes for unknown expenses.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from opportunity_models import DEFAULT_MAX_AGE_SECONDS, evaluate_investment
from route_optimizer import CLASS_WEIGHTS


_CLASSES = ("y", "j", "f")
_RECURRING = ("maintenance", "a_check", "other")
_CENT = Decimal("0.01")
_MAX_VALUE = Decimal("1000000000000000")
_IDENTITY = ("hub_id", "origin_id", "destination_id", "model_id", "engine_id")
_SUBJECTS = {
    "layout": ("model_id", "engine_id"),
    "capacity": ("model_id", "engine_id"),
    "daily_demand": ("hub_id", "origin_id", "destination_id"),
    "fares": ("hub_id", "origin_id", "destination_id"),
    "departures_per_day": _IDENTITY,
    "load_factor": _IDENTITY,
    "fuel_units_per_day": _IDENTITY,
    "fuel_price_per_1000": (),
    "co2_units_per_passenger": _IDENTITY,
    "co2_price_per_1000": (),
    "recurring_costs": _IDENTITY,
    "other_fees": _IDENTITY,
    "cash": (),
}
_ROUTE_INPUTS = frozenset(field for field, subjects in _SUBJECTS.items()
                          if "destination_id" in subjects)
_SOURCES = {
    "layout": "game_aircraft_shop",
    "capacity": "game_aircraft_shop",
    "daily_demand": "game_route_search",
    "fares": "game_route_search",
    "departures_per_day": "route_optimizer",
    "load_factor": "route_optimizer",
    "fuel_units_per_day": "route_optimizer",
    "fuel_price_per_1000": "game_market",
    "co2_units_per_passenger": "route_optimizer",
    "co2_price_per_1000": "game_market",
    "recurring_costs": "game_research",
    "other_fees": "game_market",
    "cash": "game_snapshot",
}
DEFAULT_STRESS = {
    "fuel_price": 1.20,
    "co2_price": 1.20,
    "occupancy": 0.90,
    "demand": 0.90,
}


def _decimal(value: object, *, minimum: Decimal = Decimal(0)) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and minimum <= number <= _MAX_VALUE else None


def _money(value: Decimal | None) -> float | None:
    if value is None or abs(value) > _MAX_VALUE:
        return None
    try:
        return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError):
        return None


def _reason(reasons: list[dict[str, str]], code: str, field: str) -> None:
    item = {"code": code, "field": field}
    if item not in reasons:
        reasons.append(item)


def _evidenced_inputs(
    raw: object, profile_id: object, snapshot_id: object, identity: Mapping[str, object],
    now: float, max_age_seconds: float, reasons: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    inputs = raw if isinstance(raw, Mapping) else {}
    values: dict[str, Any] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for field, source in _SOURCES.items():
        item = inputs.get(field)
        if not isinstance(item, Mapping):
            _reason(reasons, "EVIDENCE_MISSING", f"inputs.{field}")
            continue
        stamp = _decimal(item.get("observed_at"), minimum=Decimal("0.000001"))
        if (item.get("verified") is not True or item.get("source") != source
                or item.get("profile_id") != profile_id or item.get("snapshot_id") != snapshot_id
                or any(item.get(key) != identity.get(key) or identity.get(key) is None
                       for key in _SUBJECTS[field])
                or (field in _ROUTE_INPUTS and item.get("stopover_id") != identity.get("stopover_id"))):
            _reason(reasons, "EVIDENCE_CONTRADICTORY", f"inputs.{field}")
            continue
        if stamp is None or not 0 <= Decimal(str(now)) - stamp <= Decimal(str(max_age_seconds)):
            _reason(reasons, "EVIDENCE_STALE", f"inputs.{field}")
            continue
        values[field] = item.get("value")
        provenance[field] = {
            "source": source, "observed_at": float(stamp), "verified": True,
            "profile_id": profile_id, "snapshot_id": snapshot_id,
            **{key: item[key] for key in _SUBJECTS[field]},
            **({"stopover_id": item["stopover_id"]}
               if field in _ROUTE_INPUTS and identity.get("stopover_id") is not None else {}),
            "value": deepcopy(item.get("value")),
        }
    return values, provenance


def _class_values(raw: object, *, integral: bool = False, positive: bool = False) -> dict[str, Decimal] | None:
    if not isinstance(raw, Mapping) or set(raw) != set(_CLASSES):
        return None
    result = {key: _decimal(raw[key]) for key in _CLASSES}
    if (any(value is None for value in result.values())
            or (integral and any(value != value.to_integral_value() for value in result.values()))
            or (positive and not any(value > 0 for value in result.values()))):
        return None
    return result


def _stress_factors(raw: Mapping[str, Any] | None) -> dict[str, Decimal] | None:
    factors = DEFAULT_STRESS if raw is None else raw
    if not isinstance(factors, Mapping) or set(factors) != set(DEFAULT_STRESS):
        return None
    parsed = {name: _decimal(factors[name]) for name in DEFAULT_STRESS}
    if any(value is None or value > 5 for value in parsed.values()):
        return None
    if (any(parsed[name] < 1 for name in ("fuel_price", "co2_price"))
            or any(parsed[name] > 1 for name in ("occupancy", "demand"))):
        return None
    return parsed


def _scenario(
    *, layout: Mapping[str, Decimal], demand: Mapping[str, Decimal],
    fares: Mapping[str, Decimal], emissions: Mapping[str, Decimal],
    legs: Decimal, load: Decimal, fuel_units: Decimal, fuel_price: Decimal,
    co2_price: Decimal, known_recurring: Decimal, margin: Decimal,
    investment: Decimal | None, complete: bool,
) -> dict[str, Any]:
    sold = {name: min(demand[name], layout[name] * legs * load) for name in _CLASSES}
    revenue_by_class = {name: sold[name] * fares[name] for name in _CLASSES}
    revenue = sum(revenue_by_class.values(), Decimal(0))
    fuel_cost = fuel_units * fuel_price / 1000
    co2_cost = sum((sold[name] * emissions[name] for name in _CLASSES), Decimal(0)) * co2_price / 1000
    haircut = revenue * margin
    known_costs_profit_ceiling = revenue - fuel_cost - co2_cost - known_recurring - haircut
    profit = known_costs_profit_ceiling if complete else None
    payback = investment / profit if profit is not None and profit > 0 and investment is not None else None
    roi = profit * 36500 / investment if profit is not None and investment is not None and investment > 0 else None
    return {
        "passengers_per_day": {name: float(sold[name]) for name in _CLASSES},
        "revenue_by_class": {name: _money(revenue_by_class[name]) for name in _CLASSES},
        "revenue_per_day": _money(revenue),
        "fuel_cost_per_day": _money(fuel_cost),
        "co2_cost_per_day": _money(co2_cost),
        "known_recurring_cost_per_day": _money(known_recurring),
        "safety_margin_per_day": _money(haircut),
        "profit_ceiling_before_unknown_costs": _money(known_costs_profit_ceiling),
        "daily_net_profit_estimate": _money(profit),
        "payback_days": _money(payback),
        "roi_365d_percent": _money(roi),
    }


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


def evaluate_expansion_economics(
    snapshot: Mapping[str, Any], candidate: Mapping[str, Any], inputs: Mapping[str, Any],
    *, now: float | None = None, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    safety_margin_fraction: float = 0.10, stress: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compute an auditable candidate and independent downside sensitivities.

    The v1 opportunity gate still validates the selected hub, route, engine,
    costs, coverage and route-optimizer financial evidence. A candidate whose
    declared optimizer profit conflicts with the explicit accounting is blocked.
    All estimates are read-only, regardless of their status.
    """
    reasons: list[dict[str, str]] = []
    now = time.time() if now is None else now
    if (_decimal(now, minimum=Decimal("0.000001")) is None
            or _decimal(max_age_seconds, minimum=Decimal("0.000001")) is None):
        _reason(reasons, "VALIDATION_CLOCK_INVALID", "now")
        now, max_age_seconds = 0, 0
    margin = _decimal(safety_margin_fraction)
    if margin is None or margin > 1:
        _reason(reasons, "SAFETY_MARGIN_INVALID", "safety_margin_fraction")
    factors = _stress_factors(stress)
    if factors is None:
        _reason(reasons, "STRESS_INVALID", "stress")

    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    candidate = candidate if isinstance(candidate, Mapping) else {}
    base = evaluate_investment(snapshot, candidate, now=now, max_age_seconds=max_age_seconds)
    reasons.extend({"code": entry["code"], "field": entry["field"]} for entry in base["policy"]["reasons"])
    identity = {
        "hub_id": candidate.get("hub", {}).get("id") if isinstance(candidate.get("hub"), Mapping) else None,
        "origin_id": base["route"]["origin_id"],
        "destination_id": base["route"]["destination_id"],
        "model_id": base["aircraft"]["model_id"],
        "engine_id": base["aircraft"]["engine_id"],
    }
    if base["route"]["stopover_id"] is not None:
        identity["stopover_id"] = base["route"]["stopover_id"]
    route = candidate.get("route") if isinstance(candidate.get("route"), Mapping) else {}
    if route.get("occupied") is True:
        _reason(reasons, "ROUTE_OCCUPIED", "candidate.route.occupied")
    elif route.get("occupied") is not False:
        _reason(reasons, "ROUTE_OCCUPANCY_UNVERIFIED", "candidate.route.occupied")
    if route.get("demand_unit") != "passengers_per_day":
        _reason(reasons, "DEMAND_UNIT_UNVERIFIED", "candidate.route.demand_unit")
    values, provenance = _evidenced_inputs(inputs, snapshot.get("profile_id"), snapshot.get("snapshot_id"),
                                          identity, now, max_age_seconds, reasons)

    layout = _class_values(values.get("layout"), integral=True, positive=True)
    demand = _class_values(values.get("daily_demand"), positive=True)
    fares = _class_values(values.get("fares"))
    emissions = _class_values(values.get("co2_units_per_passenger"))
    capacity = _decimal(values.get("capacity"), minimum=Decimal(1))
    legs = _decimal(values.get("departures_per_day"), minimum=Decimal("0.000001"))
    load = _decimal(values.get("load_factor"), minimum=Decimal("0.000001"))
    fuel_units = _decimal(values.get("fuel_units_per_day"), minimum=Decimal("0.000001"))
    fuel_price = _decimal(values.get("fuel_price_per_1000"), minimum=Decimal("0.000001"))
    co2_price = _decimal(values.get("co2_price_per_1000"), minimum=Decimal("0.000001"))
    other_fees = _decimal(values.get("other_fees"))
    cash = values.get("cash")
    if not isinstance(cash, Mapping) or set(cash) != {"available", "committed", "reserve"}:
        cash_values = None
    else:
        cash_values = {name: _decimal(cash[name]) for name in ("available", "committed", "reserve")}
        if any(value is None for value in cash_values.values()):
            cash_values = None

    for field, parsed in (("layout", layout), ("daily_demand", demand), ("fares", fares),
                          ("co2_units_per_passenger", emissions), ("capacity", capacity),
                          ("departures_per_day", legs), ("load_factor", load),
                          ("fuel_units_per_day", fuel_units), ("fuel_price_per_1000", fuel_price),
                          ("co2_price_per_1000", co2_price), ("other_fees", other_fees), ("cash", cash_values)):
        if parsed is None:
            _reason(reasons, "ACCOUNTING_INPUT_INVALID", f"inputs.{field}")
    if layout is not None and capacity is not None:
        if sum((layout[name] * CLASS_WEIGHTS[index] for index, name in enumerate(_CLASSES)), Decimal(0)) > capacity:
            _reason(reasons, "LAYOUT_CAPACITY_EXCEEDED", "inputs.layout")
    if load is not None and load > 1:
        _reason(reasons, "OCCUPANCY_INVALID", "inputs.load_factor")
    if capacity is not None and capacity != capacity.to_integral_value():
        _reason(reasons, "CAPACITY_INVALID", "inputs.capacity")
    if other_fees is not None and other_fees != other_fees.quantize(_CENT):
        _reason(reasons, "COST_PRECISION_INVALID", "inputs.other_fees")
    if cash_values is not None and any(amount != amount.quantize(_CENT) for amount in cash_values.values()):
        _reason(reasons, "COST_PRECISION_INVALID", "inputs.cash")
    if layout is not None and fares is not None and any(layout[name] and not fares[name] for name in _CLASSES):
        _reason(reasons, "FARE_UNKNOWN", "inputs.fares")
    if (demand is not None and route.get("demand_unit") == "passengers_per_day"
            and _decimal(route.get("demand_remaining")) is not None):
        # Both fields claim residual daily passengers for this route. A larger
        # class sum would count the same demand more than once.
        if sum(demand.values(), Decimal(0)) > Decimal(str(route["demand_remaining"])):
            _reason(reasons, "DEMAND_CONTRADICTORY", "inputs.daily_demand")

    recurring = values.get("recurring_costs")
    if not isinstance(recurring, Mapping) or set(recurring) != set(_RECURRING):
        _reason(reasons, "RECURRING_COSTS_INVALID", "inputs.recurring_costs")
        known_recurring, excluded = None, list(_RECURRING)
    else:
        parsed_costs = {name: _decimal(recurring[name]) for name in _RECURRING}
        excluded = [name for name in _RECURRING if recurring[name] is None]
        if any(parsed_costs[name] is None and name not in excluded for name in _RECURRING):
            _reason(reasons, "RECURRING_COSTS_INVALID", "inputs.recurring_costs")
            known_recurring = None
        else:
            known_recurring = sum((value for value in parsed_costs.values() if value is not None), Decimal(0))
            if any(value is not None and value != value.quantize(_CENT) for value in parsed_costs.values()):
                _reason(reasons, "COST_PRECISION_INVALID", "inputs.recurring_costs")
    if excluded:
        _reason(reasons, "UNMODELED_RECURRING_COSTS", "inputs.recurring_costs")

    prices = base["economics"]
    base_capex = _decimal(prices.get("total_investment"))
    investment = base_capex + other_fees if base_capex is not None and other_fees is not None else None
    cash_after = (cash_values["available"] - cash_values["committed"] - investment
                  if cash_values is not None and investment is not None else None)
    if cash_after is not None and cash_after < cash_values["reserve"]:
        _reason(reasons, "CASH_RESERVE_INSUFFICIENT", "inputs.cash")

    complete = not excluded and known_recurring is not None
    required = (layout, demand, fares, emissions, legs, load, fuel_units, fuel_price, co2_price, known_recurring, margin)
    economics = None
    sensitivity: dict[str, dict[str, Any]] = {}
    if all(item is not None for item in required) and factors is not None:
        parameters = dict(layout=layout, demand=demand, fares=fares, emissions=emissions,
                          legs=legs, load=load, fuel_units=fuel_units, fuel_price=fuel_price,
                          co2_price=co2_price, known_recurring=known_recurring,
                          margin=margin, investment=investment, complete=complete)
        economics = _scenario(**parameters)
        required_components = ["revenue_per_day", "fuel_cost_per_day", "co2_cost_per_day",
                               "profit_ceiling_before_unknown_costs"]
        if complete and investment is not None and investment > 0:
            required_components.append("roi_365d_percent")
        if any(economics[name] is None for name in required_components):
            _reason(reasons, "ACCOUNTING_OVERFLOW", "components")
        scenarios = {
            "fuel_price": {"fuel_price": fuel_price * factors["fuel_price"]},
            "co2_price": {"co2_price": co2_price * factors["co2_price"]},
            "occupancy": {"load": load * factors["occupancy"]},
            "demand": {"demand": {key: demand[key] * factors["demand"] for key in _CLASSES}},
        }
        for name, changed in scenarios.items():
            sensitivity[name] = {"multiplier": float(factors[name]),
                                 **_scenario(**{**parameters, **changed})}
        combined = {key: value for changes in scenarios.values() for key, value in changes.items()}
        sensitivity["combined"] = {
            "multipliers": {key: float(value) for key, value in factors.items()},
            **_scenario(**{**parameters, **combined}),
        }
        # The v1 route-optimizer evidence must agree with the independently
        # reproducible component accounting before a financial claim is made.
        financial = candidate.get("financial")
        observed_net = _decimal(financial.get("value"), minimum=-_MAX_VALUE) if isinstance(financial, Mapping) else None
        if all(economics[name] is not None for name in (
                "revenue_per_day", "fuel_cost_per_day", "co2_cost_per_day")):
            estimated_pre_margin = (Decimal(str(economics["revenue_per_day"]))
                                    - Decimal(str(economics["fuel_cost_per_day"]))
                                    - Decimal(str(economics["co2_cost_per_day"]))
                                    - known_recurring)
            if observed_net is None or abs(observed_net - estimated_pre_margin) > Decimal("0.03"):
                _reason(reasons, "FINANCIAL_CONTRADICTORY", "candidate.financial.value")
        if complete and economics["daily_net_profit_estimate"] is None:
            _reason(reasons, "ACCOUNTING_OVERFLOW", "components.daily_net_profit_estimate")
        elif complete and economics["daily_net_profit_estimate"] <= 0:
            _reason(reasons, "PROFIT_NON_POSITIVE", "economics.daily_net_profit_estimate")

    # Immutable, canonical identity for reproducible comparisons and auditing.
    economics_id = None
    try:
        canonical = json.dumps({"snapshot_id": snapshot.get("snapshot_id"), "candidate": candidate,
                                "inputs": inputs, "margin": safety_margin_fraction, "stress": factors},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                               allow_nan=False, default=_json_default)
        economics_id = "economics-v1-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    except (TypeError, ValueError, OverflowError):
        _reason(reasons, "INPUTS_NOT_SERIALIZABLE", "inputs")

    status = "blocked" if reasons else "evaluated"
    if status == "blocked" and economics is not None:
        economics["daily_net_profit_estimate"] = None
        economics["payback_days"] = None
        economics["roi_365d_percent"] = None
        for variant in sensitivity.values():
            variant["daily_net_profit_estimate"] = None
            variant["payback_days"] = None
            variant["roi_365d_percent"] = None
    return {
        "schema_version": 1, "economics_id": economics_id,
        "plan_id": base["plan_id"], "profile_id": base["profile_id"],
        "snapshot_id": base["snapshot_id"], "status": status,
        "identity": identity,
        "configuration_yjf": {key: int(layout[key]) for key in _CLASSES} if layout is not None else None,
        "components": economics, "sensitivity": sensitivity,
        "capital_costs": {**{field: prices.get(field) for field in (
            "aircraft_cost", "engine_delta_cost", "hub_cost", "route_fee", "hangar_cost")},
            "other_fees": _money(other_fees), "total_investment": _money(investment)},
        "cash_after_purchase": _money(cash_after),
        "cash_required_reserve": _money(cash_values["reserve"]) if cash_values is not None else None,
        "excluded_costs": excluded, "safety_margin_fraction": float(margin) if margin is not None else None,
        "provenance": provenance, "observed_at_oldest": min((v["observed_at"] for v in provenance.values()), default=None),
        "evidence_confidence": "provenance_complete" if status == "evaluated" else "incomplete",
        "methodology": {
            "fare": "min(daily_residual_demand, seats * departures_per_day * load_factor) * fare",
            "fuel": "evidenced_daily_fuel_units * evidenced_price_per_1000 / 1000",
            "co2": "sum(passengers_by_class * evidenced_co2_units_per_passenger) * evidenced_price_per_1000 / 1000",
            "seat_capacity_weights": dict(zip(_CLASSES, CLASS_WEIGHTS)),
            "seat_capacity_source": "route_optimizer.CLASS_WEIGHTS",
            "safety_margin": "observed_fare_revenue * configured_fraction",
            "roi": "daily_net_profit * 365 / total_investment * 100",
            "stress_factors": {key: float(value) for key, value in factors.items()} if factors else None,
        },
        "blocking_reasons": reasons, "read_only": True, "execution_available": False,
    }


def rank_expansion_economics(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic cross-hub ranking of fully evidenced read-only results.

    Repeated identical results count once. Conflicting accounts for the same
    hub, route, model, engine and layout invalidate that identity entirely.
    """
    unique: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    conflicts: set[tuple[Any, ...]] = set()
    excluded = 0
    for row in evaluations:
        if (not isinstance(row, Mapping) or row.get("status") != "evaluated"
                or row.get("blocking_reasons") != []
                or row.get("evidence_confidence") != "provenance_complete"
                or row.get("read_only") is not True
                or row.get("execution_available") is not False
                or not isinstance(row.get("economics_id"), str)):
            excluded += 1
            continue
        identity = row.get("identity") or {}
        layout = row.get("configuration_yjf") or {}
        components = row.get("components") or {}
        costs = row.get("capital_costs") or {}
        if (not isinstance(identity, Mapping) or not isinstance(layout, Mapping)
                or not isinstance(components, Mapping) or not isinstance(costs, Mapping)
                or any(not isinstance(identity.get(key), str) or not identity[key] for key in _IDENTITY)
                or (identity.get("stopover_id") is not None
                    and (not isinstance(identity["stopover_id"], str) or not identity["stopover_id"]))
                or not all(type(layout.get(key)) is int and layout[key] >= 0 for key in _CLASSES)
                or _decimal(components.get("daily_net_profit_estimate"), minimum=Decimal("0.000001")) is None
                or _decimal(costs.get("total_investment"), minimum=Decimal("0.000001")) is None
                or _decimal(components.get("payback_days"), minimum=Decimal("0.000001")) is None
                or _decimal(components.get("roi_365d_percent")) is None):
            excluded += 1
            continue
        expected_payback = (Decimal(str(costs["total_investment"]))
                            / Decimal(str(components["daily_net_profit_estimate"])))
        if abs(expected_payback - Decimal(str(components["payback_days"]))) > Decimal("0.011"):
            excluded += 1
            continue
        try:
            expected_roi = (Decimal(str(components["daily_net_profit_estimate"]))
                            * Decimal("36500") / Decimal(str(costs["total_investment"])))
            rounded_roi = expected_roi.quantize(_CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, OverflowError, ZeroDivisionError):
            excluded += 1
            continue
        if Decimal(str(components["roi_365d_percent"])) != rounded_roi:
            excluded += 1
            continue
        key = (tuple(identity[key] for key in _IDENTITY) + (identity.get("stopover_id"),)
               + tuple(layout[key] for key in _CLASSES))
        if key in conflicts:
            excluded += 1
        elif key in unique and unique[key] != row:
            del unique[key]
            conflicts.add(key)
            excluded += 2
        elif key not in unique:
            unique[key] = row
    ranked = sorted(unique.values(), key=lambda row: (
        -row["components"]["daily_net_profit_estimate"] / row["capital_costs"]["total_investment"],
        -row["components"]["daily_net_profit_estimate"],
        row["capital_costs"]["total_investment"],
        tuple(str(row["identity"][key]) for key in _IDENTITY),
        row["identity"].get("stopover_id") or "",
        tuple(row["configuration_yjf"][key] for key in _CLASSES),
    ))
    return {"best": ranked[0] if ranked else None, "alternatives": ranked,
            "excluded_count": excluded, "conflicting_identities": len(conflicts),
            "read_only": True, "execution_available": False}
