"""Auditable, read-only A9 comparison between planned and observed daily profit.

``compare_forecast`` accepts the *suggested* proposal returned by
``opportunity_models.evaluate_investment``, an independently verified delivery
linked to a confirmed InvestmentJournal intent, and consecutive, complete
24-hour accounting windows after delivery.

Every window needs game flight-history IDs/revenues and independent, complete
game accounting for revenue and fuel, CO2, recurring and other actual costs.
These are INPUT CONTRACTS for future authenticated collectors. In particular,
``route_registry.last_flight`` / ``last_24h`` have approximate margins and no
stable flight IDs, so they cannot substantiate actual net profit here.

No network, registry, journal, configuration or calibration parameters are
modified. ``verified=True`` is an assertion by a trusted upstream collector,
not cryptographic source authentication performed by this module.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from opportunity_models import evaluate_investment


DEFAULT_MAX_OBSERVATION_AGE_SECONDS = 900
DEFAULT_MAX_HISTORY_AGE_SECONDS = 30 * 86400
DEFAULT_MIN_COMPLETE_WINDOWS = 3
DEFAULT_MIN_INDEPENDENT_FLIGHTS = 3
WINDOW_SECONDS = 86400

_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_GAME_ID = re.compile(r"^[1-9][0-9]{0,13}$")
_CHOICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_PLAN_ID = re.compile(r"^plan-v1-[0-9a-f]{32}$")
_SNAPSHOT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_CENT = Decimal("0.01")
_MAX_AMOUNT = Decimal("1000000000000000")
_COST_KEYS = ("fuel", "co2", "recurring", "other")
_IDENTITY_KEYS = ("profile_id", "hub_id", "origin_id", "destination_id",
                  "stopover_id", "model_id", "engine_id")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stamp(value: object) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _money(value: object, *, positive: bool = False) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if (not number.is_finite() or abs(number) > _MAX_AMOUNT
            or number != number.quantize(_CENT)
            or (number <= 0 if positive else number < 0)):
        return None
    return number


def _rounded(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _reason(reasons: list[dict[str, str]], code: str, field: str) -> None:
    item = {"code": code, "field": field}
    if item not in reasons:
        reasons.append(item)


def _result(plan: Mapping[str, Any], identity: Mapping[str, Any],
            reasons: list[dict[str, str]], metrics: dict | None = None,
            window_count: int = 0, flight_count: int = 0) -> dict:
    return {
        "status": "conclusivo" if metrics is not None and not reasons else "inconclusivo",
        "profile_id": identity.get("profile_id"),
        "plan_id": plan.get("plan_id"),
        "snapshot_id": plan.get("snapshot_id"),
        "aircraft_id": identity.get("aircraft_id"),
        "route": {key: identity.get(key) for key in ("hub_id", "origin_id", "destination_id", "stopover_id")},
        "model_id": identity.get("model_id"),
        "engine_id": identity.get("engine_id"),
        "evidence": {"complete_windows": window_count, "independent_flights": flight_count},
        "reasons": reasons,
        "metrics": metrics if not reasons else None,
        "parameter_changes": {},
    }


def _evidence(record: object, source: str, identity: Mapping[str, Any],
              now: float, max_age: float, reasons: list[dict[str, str]], field: str) -> Mapping:
    data = _mapping(record)
    if data.get("source") != source or data.get("verified") is not True:
        _reason(reasons, "SOURCE_UNVERIFIED", field)
    if any(data.get(key, object()) != expected for key, expected in identity.items()):
        _reason(reasons, "IDENTITY_MISMATCH", field)
    observed = _stamp(data.get("observed_at"))
    if observed is None or not 0 <= now - observed <= max_age:
        _reason(reasons, "EVIDENCE_STALE", field)
    return data


def _plan_identity(plan: Mapping[str, Any], delivered_at: float | None,
                   reasons: list[dict[str, str]]) -> tuple[dict, Decimal | None]:
    hub, route, aircraft = (_mapping(plan.get(field)) for field in ("hub", "route", "aircraft"))
    identity = {
        "profile_id": plan.get("profile_id"),
        "hub_id": hub.get("id"),
        "origin_id": route.get("origin_id"),
        "destination_id": route.get("destination_id"),
        "stopover_id": route.get("stopover_id"),
        "model_id": aircraft.get("model_id"),
        "engine_id": aircraft.get("engine_id"),
    }
    if (plan.get("schema_version") != 1 or plan.get("status") != "suggested"
            or _PLAN_ID.fullmatch(str(plan.get("plan_id") or "")) is None
            or _SNAPSHOT_ID.fullmatch(str(plan.get("snapshot_id") or "")) is None
            or plan.get("kind") not in ("aircraft_on_owned_hub", "aircraft_on_new_hub")
            or _mapping(plan.get("policy")).get("read_only") is not True
            or _mapping(plan.get("policy")).get("reasons") != []
            or _mapping(plan.get("evidence")).get("source") != "game_snapshot"
            or _mapping(plan.get("evidence")).get("coverage") != "complete"
            or _stamp(_mapping(plan.get("evidence")).get("observed_at")) is None):
        _reason(reasons, "PLAN_UNVERIFIED", "plan")
    if (not isinstance(identity["profile_id"], str)
            or _PROFILE.fullmatch(identity["profile_id"]) is None
            or any(not isinstance(identity[key], str) or _GAME_ID.fullmatch(identity[key]) is None
                   for key in ("hub_id", "origin_id", "destination_id"))
            or identity["origin_id"] == identity["destination_id"]
            or identity["origin_id"] != identity["hub_id"]
            or identity["stopover_id"] is not None
            and (not isinstance(identity["stopover_id"], str)
                 or _GAME_ID.fullmatch(identity["stopover_id"]) is None
                 or identity["stopover_id"] in (identity["origin_id"], identity["destination_id"]))
            or any(not isinstance(identity[key], str) or _CHOICE_ID.fullmatch(identity[key]) is None
                   or identity[key].casefold() in ("default", "inferred", "unknown", "none", "null")
                   for key in ("model_id", "engine_id"))):
        _reason(reasons, "PLAN_IDENTITY_INVALID", "plan")
    forecast = _money(_mapping(plan.get("economics")).get("daily_net_profit_estimate"), positive=True)
    if forecast is None:
        _reason(reasons, "FORECAST_INVALID", "plan.economics.daily_net_profit_estimate")
    # The v1 plan hash binds the original candidate, not the emitted result.
    # Re-evaluate the immutable inputs to detect modified forecasts/identities.
    provenance = _mapping(plan.get("planning_evidence"))
    evaluated_at = _stamp(provenance.get("evaluated_at"))
    original_snapshot = provenance.get("snapshot")
    original_candidate = provenance.get("candidate")
    plan_at = _stamp(_mapping(plan.get("evidence")).get("observed_at"))
    if (evaluated_at is None or plan_at is None or evaluated_at < plan_at
            or (delivered_at is not None and delivered_at >= plan_at
                and evaluated_at > delivered_at)
            or not isinstance(original_snapshot, Mapping)
            or not isinstance(original_candidate, Mapping)):
        _reason(reasons, "PLAN_SOURCE_UNVERIFIED", "plan.planning_evidence")
    else:
        try:
            recalculated = evaluate_investment(original_snapshot, original_candidate,
                                               now=evaluated_at)
        except (TypeError, ValueError, OverflowError):
            recalculated = None
        if recalculated != {key: value for key, value in plan.items()
                            if key != "planning_evidence"}:
            _reason(reasons, "PLAN_TAMPERED", "plan")
    return identity, forecast


def _purchase_proof(plan: Mapping[str, Any], delivery: Mapping[str, Any],
                    identity: Mapping[str, Any], now: float, max_age: float,
                    delivered_at: float | None, reasons: list[dict[str, str]]) -> None:
    """Bind the delivered game aircraft to a journal-confirmed game order."""
    purchase = _mapping(delivery.get("purchase"))
    intent = _mapping(purchase.get("intent"))  # InvestmentJournal.get(intent_key)
    event = _mapping(purchase.get("confirmation"))  # CONFIRMED entry from history(intent_key)
    if (intent.get("state") != "CONFIRMED" or intent.get("kind") != "aircraft"
            or intent.get("plan_id") != plan.get("plan_id")
            or intent.get("snapshot_id") != plan.get("snapshot_id")
            or _SNAPSHOT_ID.fullmatch(str(intent.get("intent_key") or "")) is None
            or any(intent.get(key) != identity[key] for key in
                   ("profile_id", "hub_id", "origin_id", "destination_id", "model_id", "engine_id"))):
        _reason(reasons, "JOURNAL_UNCONFIRMED", "delivery.purchase.intent")
    proof = _evidence(event.get("evidence"), "game_order_list",
                      {key: identity[key] for key in
                       ("profile_id", "hub_id", "origin_id", "destination_id", "model_id", "engine_id")},
                      now, max_age, reasons, "delivery.purchase.confirmation.evidence")
    purchase_id = proof.get("purchase_id")
    confirmation_at = _stamp(proof.get("observed_at"))
    event_at = _stamp(event.get("observed_at"))
    planned_at = _stamp(_mapping(plan.get("evidence")).get("observed_at"))
    if (event.get("new_state") != "CONFIRMED"
            or event.get("previous_state") not in ("SUBMITTED", "UNKNOWN")
            or not isinstance(purchase_id, str) or _GAME_ID.fullmatch(purchase_id) is None
            or delivery.get("purchase_id") != purchase_id
            or delivered_at is None or planned_at is None or confirmation_at is None or event_at is None
            or not planned_at <= confirmation_at <= event_at <= delivered_at):
        _reason(reasons, "PURCHASE_LINK_UNVERIFIED", "delivery.purchase")


def compare_forecast(
    plan: Mapping[str, Any],
    delivery: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    *,
    now: float | None = None,
    max_observation_age_seconds: float = DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
    max_history_age_seconds: float = DEFAULT_MAX_HISTORY_AGE_SECONDS,
    min_complete_windows: int = DEFAULT_MIN_COMPLETE_WINDOWS,
    min_independent_flights: int = DEFAULT_MIN_INDEPENDENT_FLIGHTS,
) -> dict:
    """Compare daily net forecast with independent, complete observed days.

    Delivery requires ``source='game_fleet_details'``, ``status='delivered'``,
    ``aircraft_id``, ``purchase_id``, ``delivered_at``, ``observed_at``,
    ``verified=True`` and matching profile, hub, route, model and engine IDs.
    Its ``purchase`` bundle has ``intent`` from InvestmentJournal.get() and
    ``confirmation`` from InvestmentJournal.history() with a CONFIRMED event,
    verified ``game_order_list`` evidence and matching game purchase ID.

    The plan additionally carries ``planning_evidence={snapshot, candidate,
    evaluated_at}`` with the original inputs to ``evaluate_investment``. The
    exact evaluated plan must reproduce from those inputs.

    Each 86400-second window requires source ``game_flight_history``, status
    ``complete``, verified provenance/identity, ``window_start``/``window_end``,
    ``observed_at``, ``count_source='game_flight_history'``,
    ``expected_flight_ids``, ``flight_count`` and ``flights``.
    Each flight requires a unique numeric game ``flight_id``, ``completed_at``,
    ``observed_at``, ``revenue``, verified game_flight_history provenance and
    identity. The windows must be consecutive and end recently.

    Each window also requires ``financial`` with source
    ``game_accounting_ledger``, verified provenance and identity, matching
    ``window_start``/``window_end``, ``revenue``, ``costs`` (fuel, co2,
    recurring, other), ``costs_complete=True`` and ``excluded_costs=[]``.
    Its revenue must exactly reconcile with the individual flight revenues.
    The current route registry supplies neither this ledger nor unique flight
    IDs, so passing its cached margins necessarily remains inconclusive.

    Results are deterministic for a supplied ``now``. If any evidence is
    missing, stale, overlapping, incomplete or contradictory, all financial
    metrics remain None and no calibration changes are suggested or applied.
    """
    reasons: list[dict[str, str]] = []
    plan = _mapping(plan)
    current = time.time() if now is None else _stamp(now)
    if current is None:
        _reason(reasons, "CLOCK_INVALID", "now")
    if (type(max_observation_age_seconds) not in (int, float)
            or not math.isfinite(max_observation_age_seconds) or max_observation_age_seconds <= 0
            or type(max_history_age_seconds) not in (int, float)
            or not math.isfinite(max_history_age_seconds)
            or max_history_age_seconds < max_observation_age_seconds
            or type(min_complete_windows) is not int or not 2 <= min_complete_windows <= 90
            or type(min_independent_flights) is not int or not 2 <= min_independent_flights <= 10000):
        _reason(reasons, "POLICY_INVALID", "options")
    identity, forecast = _plan_identity(plan, _stamp(_mapping(delivery).get("delivered_at")), reasons)
    if reasons:
        return _result(plan, identity, reasons)

    delivery = _evidence(delivery, "game_fleet_details", identity, current,
                         max_history_age_seconds, reasons, "delivery")
    aircraft_id = delivery.get("aircraft_id")
    identity["aircraft_id"] = aircraft_id
    delivered_at = _stamp(delivery.get("delivered_at"))
    plan_at = _stamp(_mapping(plan.get("evidence")).get("observed_at"))
    evaluated_at = _stamp(_mapping(plan.get("planning_evidence")).get("evaluated_at"))
    if (not isinstance(aircraft_id, str) or _GAME_ID.fullmatch(aircraft_id) is None
            or delivery.get("status") != "delivered"
            or delivered_at is None or plan_at is None
            or not plan_at <= delivered_at <= current):
        _reason(reasons, "DELIVERY_UNVERIFIED", "delivery")
    if evaluated_at is None or delivered_at is None or evaluated_at > delivered_at:
        _reason(reasons, "PLAN_SOURCE_UNVERIFIED", "plan.planning_evidence")
    _purchase_proof(plan, delivery, identity, current, max_history_age_seconds,
                    delivered_at, reasons)
    if reasons:
        return _result(plan, identity, reasons)

    if (not isinstance(windows, (list, tuple)) or not windows or len(windows) > 90):
        _reason(reasons, "WINDOWS_INVALID", "windows")
        return _result(plan, identity, reasons)

    complete_windows = 0
    flight_ids: set[str] = set()
    period_rows: list[tuple[float, float, Decimal, Decimal, Decimal]] = []
    for index, raw in enumerate(windows):
        label = f"windows[{index}]"
        window = _evidence(raw, "game_flight_history", identity, current,
                           max_history_age_seconds, reasons, label)
        start, end = _stamp(window.get("window_start")), _stamp(window.get("window_end"))
        if (start is None or end is None or end - start != WINDOW_SECONDS
                or start < delivered_at or end > current
                or current - end > max_history_age_seconds
                or (period_rows and start != period_rows[-1][1])):
            _reason(reasons, "WINDOW_INVALID", label)
        if window.get("status") != "complete":
            _reason(reasons, "COVERAGE_INCOMPLETE", label)
        if window.get("count_source") != "game_flight_history":
            _reason(reasons, "COVERAGE_UNVERIFIED", label)
        observed_window_at = _stamp(window.get("observed_at"))
        if end is None or observed_window_at is None or observed_window_at < end:
            _reason(reasons, "COVERAGE_UNVERIFIED", label)

        flights = window.get("flights")
        expected_ids = window.get("expected_flight_ids")
        if (not isinstance(flights, list) or not isinstance(expected_ids, list)
                or type(window.get("flight_count")) is not int
                or window["flight_count"] != len(flights)
                or len(expected_ids) != len(flights)
                or any(not isinstance(fid, str) or _GAME_ID.fullmatch(fid) is None
                       for fid in expected_ids)
                or len(set(expected_ids)) != len(expected_ids)):
            _reason(reasons, "COVERAGE_UNVERIFIED", label)
            flights = flights if isinstance(flights, list) else []
            expected_ids = []

        revenue_sum = Decimal(0)
        seen_here: set[str] = set()
        for j, raw_flight in enumerate(flights):
            f_label = f"{label}.flights[{j}]"
            flight = _evidence(raw_flight, "game_flight_history", identity, current,
                               max_history_age_seconds, reasons, f_label)
            flight_id = flight.get("flight_id")
            completed = _stamp(flight.get("completed_at"))
            observed = _stamp(flight.get("observed_at"))
            amount = _money(flight.get("revenue"))
            if (not isinstance(flight_id, str) or _GAME_ID.fullmatch(flight_id) is None
                    or flight_id in flight_ids or flight_id in seen_here):
                _reason(reasons, "FLIGHT_NOT_INDEPENDENT", f_label)
            else:
                seen_here.add(flight_id)
            if (completed is None or start is None or end is None
                    or not start <= completed < end
                    or observed is None or observed < completed):
                _reason(reasons, "FLIGHT_OUT_OF_WINDOW", f_label)
            if amount is None:
                _reason(reasons, "REVENUE_UNVERIFIED", f_label)
            else:
                revenue_sum += amount
        flight_ids.update(seen_here)
        if seen_here != set(expected_ids):
            _reason(reasons, "COVERAGE_UNVERIFIED", label)

        financial = _evidence(window.get("financial"), "game_accounting_ledger", identity,
                              current, max_history_age_seconds, reasons, f"{label}.financial")
        financial_time = _stamp(financial.get("observed_at"))
        if (financial.get("window_start") != start or financial.get("window_end") != end
                or end is None or financial_time is None or financial_time < end
                or financial.get("costs_complete") is not True
                or financial.get("excluded_costs") != []):
            _reason(reasons, "ACCOUNTING_INCOMPLETE", f"{label}.financial")
        observed_revenue = _money(financial.get("revenue"))
        costs = _mapping(financial.get("costs"))
        components = [_money(costs.get(key)) for key in _COST_KEYS]
        if set(costs) != set(_COST_KEYS):
            _reason(reasons, "ACCOUNTING_INCOMPLETE", f"{label}.financial.costs")
        if observed_revenue is None or any(component is None for component in components):
            _reason(reasons, "ACCOUNTING_INVALID", f"{label}.financial")
        elif observed_revenue != revenue_sum:
            _reason(reasons, "REVENUE_MISMATCH", f"{label}.financial")
        if start is not None and end is not None:
            period_rows.append((start, end, observed_revenue or Decimal(0),
                                sum((component or Decimal(0) for component in components), Decimal(0)),
                                revenue_sum))
        if window.get("status") == "complete":
            complete_windows += 1

    if (period_rows and current - period_rows[-1][1] > max_observation_age_seconds):
        _reason(reasons, "WINDOW_STALE", "windows[-1]")
    if complete_windows < min_complete_windows or len(period_rows) != len(windows):
        _reason(reasons, "INSUFFICIENT_WINDOWS", "windows")
    if len(flight_ids) < min_independent_flights:
        _reason(reasons, "INSUFFICIENT_INDEPENDENT_FLIGHTS", "windows")
    if reasons:
        return _result(plan, identity, reasons, window_count=complete_windows,
                       flight_count=len(flight_ids))

    day_profits = [revenue - cost for _, _, revenue, cost, _ in period_rows]
    count = Decimal(len(day_profits))
    average = sum(day_profits, Decimal(0)) / count
    delta = average - forecast
    absolute_errors = [abs(day - forecast) for day in day_profits]
    revenue_total = sum((row[2] for row in period_rows), Decimal(0))
    costs_total = sum((row[3] for row in period_rows), Decimal(0))
    metrics = {
        "currency": "USD",
        "period_start": period_rows[0][0],
        "period_end": period_rows[-1][1],
        "complete_days": len(day_profits),
        "independent_flights": len(flight_ids),
        "flight_ids": sorted(flight_ids),
        "forecast_daily_net_profit": _rounded(forecast),
        "observed_revenue_total": _rounded(revenue_total),
        "observed_costs_total": _rounded(costs_total),
        "observed_net_profit_total": _rounded(revenue_total - costs_total),
        "observed_daily_net_profit": _rounded(average),
        "daily_error_observed_minus_forecast": _rounded(delta),
        "daily_absolute_error": _rounded(abs(delta)),
        "daily_percentage_error": _rounded(100 * delta / forecast),
        "mean_absolute_daily_error": _rounded(sum(absolute_errors) / count),
    }
    return _result(plan, identity, reasons, metrics, complete_windows, len(flight_ids))
