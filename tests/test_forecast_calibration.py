"""Synthetic evidence only. Never pretend that cached route margins are observed net profit."""

from __future__ import annotations

from copy import deepcopy

import pytest

from forecast_calibration import compare_forecast
from opportunity_models import evaluate_investment, fingerprint_snapshot


NOW = 1_900_000_000
DAY = 86400
PLAN_AT = NOW - 6 * DAY
DELIVERED_AT = NOW - 4 * DAY
IDENTITY = {
    "profile_id": "principal", "hub_id": "123", "origin_id": "123",
    "destination_id": "456", "stopover_id": None,
    "model_id": "789", "engine_id": "motor-02",
}


def evidence(source, *, observed_at=PLAN_AT, **fields):
    return {"source": source, "verified": True, "profile_id": "principal",
            "observed_at": observed_at, **fields}


def validated_plan():
    snapshot = evidence(
        "game_snapshot", schema_version=1,
        hubs=[evidence("game_hub_select", id="123", id_source="game", owned=True)],
        coverage=evidence(
            "game_fleet_scan", status="complete", observed_pages=0,
            expected_pages=0, expected_aircraft_count=0,
            count_source="game_fleet_total", observed_aircraft_ids=[],
            scopes={key: True for key in ("hubs", "fleet", "routes", "models", "engines", "prices")},
        ),
    )
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    candidate = {
        "schema_version": 1, "profile_id": "principal",
        "snapshot_id": snapshot["snapshot_id"],
        "kind": "aircraft_on_owned_hub", "hub": {"id": "123"},
        "route": evidence(
            "game_route_search", id_source="game", origin_id="123",
            destination_id="456", stopover_id=None, available=True,
            feasible=True, demand_verified=True, demand_remaining=100,
            distance_km=500, range_km=1500, required_runway_m=1800,
            origin_runway_m=2500, destination_runway_m=2600,
        ),
        "aircraft": evidence(
            "game_aircraft_shop", id_source="game", model_id="789",
            engine_model_id="789", engine_id="motor-02", available=True,
        ),
        "costs": {
            "aircraft_cost": evidence("game_aircraft_shop", value=10000, price_basis="base_without_engine"),
            "engine_delta_cost": evidence("game_aircraft_shop", value=500),
            "hub_cost": evidence("game_hub_select", value=0),
            "route_fee": evidence("game_route_search", value=100),
            "hangar_cost": evidence("game_hub_select", value=50),
        },
        "financial": evidence("route_optimizer", value=250, excluded_costs=[]),
    }
    for component in (candidate["route"], candidate["aircraft"],
                      candidate["financial"], *candidate["costs"].values()):
        component["snapshot_id"] = snapshot["snapshot_id"]
    candidate["financial"].update({key: IDENTITY[key] for key in
                                    ("hub_id", "origin_id", "destination_id", "model_id", "engine_id")})
    for name, names in {
        "aircraft_cost": ("model_id", "engine_id"),
        "engine_delta_cost": ("model_id", "engine_id"),
        "hub_cost": ("hub_id",),
        "route_fee": ("origin_id", "destination_id"),
        "hangar_cost": ("hub_id",),
    }.items():
        candidate["costs"][name].update({key: IDENTITY[key] for key in names})
    result = evaluate_investment(snapshot, candidate, now=PLAN_AT + 10)
    assert result["status"] == "suggested", result["policy"]["reasons"]
    result["planning_evidence"] = {
        "snapshot": deepcopy(snapshot), "candidate": deepcopy(candidate),
        "evaluated_at": PLAN_AT + 10,
    }
    return result


def supplied_evidence():
    plan = validated_plan()
    intent = {
        "state": "CONFIRMED", "kind": "aircraft",
        "intent_key": "sha256:" + "a" * 64,
        "plan_id": plan["plan_id"], "snapshot_id": plan["snapshot_id"],
        **{key: IDENTITY[key] for key in
           ("profile_id", "hub_id", "origin_id", "destination_id", "model_id", "engine_id")},
    }
    confirmation_at = PLAN_AT + 1000
    confirmation = {
        "previous_state": "SUBMITTED", "new_state": "CONFIRMED",
        "observed_at": confirmation_at + 10,
        "evidence": evidence(
            "game_order_list", observed_at=confirmation_at,
            **{key: IDENTITY[key] for key in
               ("profile_id", "hub_id", "origin_id", "destination_id", "model_id", "engine_id")},
            purchase_id="22222",
        ),
    }
    delivery = evidence(
        "game_fleet_details", observed_at=NOW - 5,
        **{**IDENTITY, "aircraft_id": "98765"},
        status="delivered", delivered_at=DELIVERED_AT, purchase_id="22222",
        purchase={"intent": intent, "confirmation": confirmation},
    )
    windows = []
    for day, other_cost in enumerate((50, 150, 100)):
        start = NOW - 3 * DAY + day * DAY
        end = start + DAY
        flights = [
            evidence(
                "game_flight_history", observed_at=end,
                **{**IDENTITY, "aircraft_id": "98765"},
                flight_id=str(1001 + day * 2 + index),
                completed_at=start + (index + 1) * 1000,
                revenue=amount,
            ) for index, amount in enumerate((200, 300))
        ]
        windows.append(evidence(
            "game_flight_history", observed_at=end,
            **{**IDENTITY, "aircraft_id": "98765"},
            status="complete", window_start=start, window_end=end,
            count_source="game_flight_history",
            expected_flight_ids=[flight["flight_id"] for flight in flights],
            flight_count=len(flights), flights=flights,
            financial=evidence(
                "game_accounting_ledger", observed_at=end,
                **{**IDENTITY, "aircraft_id": "98765"},
                window_start=start, window_end=end, revenue=500,
                costs={"fuel": 100, "co2": 20, "recurring": 30, "other": other_cost},
                costs_complete=True, excluded_costs=[],
            ),
        ))
    return plan, delivery, windows


def compare(data, **kwargs):
    return compare_forecast(*data, now=NOW, **kwargs)


def codes(result):
    return {reason["code"] for reason in result["reasons"]}


def inconclusive(data, expected_code):
    result = compare(data)
    assert result["status"] == "inconclusivo"
    assert expected_code in codes(result), result["reasons"]
    assert result["metrics"] is None
    assert result["parameter_changes"] == {}


def test_full_reconciliation_is_deterministic_and_read_only():
    data = supplied_evidence()
    unchanged = deepcopy(data)
    first = compare(data)
    assert first == compare(data)
    assert data == unchanged
    assert first["status"] == "conclusivo"
    assert first["reasons"] == []
    assert first["profile_id"] == "principal"
    assert first["aircraft_id"] == "98765"
    assert first["snapshot_id"] == data[0]["snapshot_id"]
    assert first["route"] == {key: IDENTITY[key] for key in
                              ("hub_id", "origin_id", "destination_id", "stopover_id")}
    assert first["evidence"] == {"complete_windows": 3, "independent_flights": 6}
    assert first["parameter_changes"] == {}
    assert first["metrics"] == {
        "currency": "USD", "period_start": NOW - 3 * DAY, "period_end": NOW,
        "complete_days": 3, "independent_flights": 6,
        "flight_ids": ["1001", "1002", "1003", "1004", "1005", "1006"],
        "forecast_daily_net_profit": 250.0,
        "observed_revenue_total": 1500.0,
        "observed_costs_total": 750.0,
        "observed_net_profit_total": 750.0,
        "observed_daily_net_profit": 250.0,
        "daily_error_observed_minus_forecast": 0.0,
        "daily_absolute_error": 0.0,
        "daily_percentage_error": 0.0,
        "mean_absolute_daily_error": 33.33,
    }


def test_negative_profit_and_signed_error_are_not_clamped():
    data = supplied_evidence()
    for window in data[2]:
        window["financial"]["costs"]["other"] += 400
    result = compare(data)
    assert result["status"] == "conclusivo"
    assert result["metrics"]["observed_daily_net_profit"] == -150.0
    assert result["metrics"]["daily_error_observed_minus_forecast"] == -400.0
    assert result["metrics"]["daily_percentage_error"] == -160.0


@pytest.mark.parametrize("mutation,code", [
    (lambda p, d, w: p.update(status="blocked"), "PLAN_UNVERIFIED"),
    (lambda p, d, w: p["policy"].update(reasons=[{"code": "stale"}]), "PLAN_UNVERIFIED"),
    (lambda p, d, w: p["economics"].update(daily_net_profit_estimate=None), "FORECAST_INVALID"),
    (lambda p, d, w: p["economics"].update(daily_net_profit_estimate=float("nan")), "FORECAST_INVALID"),
    (lambda p, d, w: p["economics"].update(daily_net_profit_estimate=True), "FORECAST_INVALID"),
    (lambda p, d, w: p.update(snapshot_id="sha256:invalid"), "PLAN_UNVERIFIED"),
    (lambda p, d, w: p.pop("planning_evidence"), "PLAN_SOURCE_UNVERIFIED"),
    (lambda p, d, w: p["planning_evidence"].update(evaluated_at=PLAN_AT - 1), "PLAN_SOURCE_UNVERIFIED"),
    (lambda p, d, w: p["planning_evidence"].update(evaluated_at=DELIVERED_AT + 1), "PLAN_SOURCE_UNVERIFIED"),
    (lambda p, d, w: p["planning_evidence"]["snapshot"].update(verified=False), "PLAN_TAMPERED"),
    (lambda p, d, w: p["planning_evidence"]["candidate"]["financial"].update(value=999), "PLAN_TAMPERED"),
    (lambda p, d, w: p["economics"].update(daily_net_profit_estimate=999), "PLAN_TAMPERED"),
    (lambda p, d, w: p.update(profile_id="outro"), "PLAN_TAMPERED"),
    (lambda p, d, w: d.update(status="pending"), "DELIVERY_UNVERIFIED"),
    (lambda p, d, w: d.update(source="simulation_fleet_details"), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: d.update(verified=False), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: d.update(profile_id="other"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(model_id="790"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(engine_id="motor-03"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(hub_id="987"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(destination_id="999"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(stopover_id="789"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d.update(aircraft_id="unknown"), "DELIVERY_UNVERIFIED"),
    (lambda p, d, w: d.pop("purchase"), "JOURNAL_UNCONFIRMED"),
    (lambda p, d, w: d.update(purchase_id="22223"), "PURCHASE_LINK_UNVERIFIED"),
    (lambda p, d, w: d["purchase"]["intent"].update(state="UNKNOWN"), "JOURNAL_UNCONFIRMED"),
    (lambda p, d, w: d["purchase"]["intent"].update(plan_id="other"), "JOURNAL_UNCONFIRMED"),
    (lambda p, d, w: d["purchase"]["intent"].update(snapshot_id="sha256:" + "b" * 64), "JOURNAL_UNCONFIRMED"),
    (lambda p, d, w: d["purchase"]["intent"].update(model_id="123"), "JOURNAL_UNCONFIRMED"),
    (lambda p, d, w: d["purchase"]["confirmation"].update(new_state="FAILED"), "PURCHASE_LINK_UNVERIFIED"),
    (lambda p, d, w: d["purchase"]["confirmation"]["evidence"].update(source="simulation_order_list"), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: d["purchase"]["confirmation"]["evidence"].update(purchase_id="22223"), "PURCHASE_LINK_UNVERIFIED"),
    (lambda p, d, w: d["purchase"]["confirmation"]["evidence"].update(engine_id="motor-03"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: d["purchase"]["confirmation"].update(observed_at=DELIVERED_AT + 1), "PURCHASE_LINK_UNVERIFIED"),
    (lambda p, d, w: d.update(delivered_at=NOW + 1), "DELIVERY_UNVERIFIED"),
    (lambda p, d, w: d.update(delivered_at=PLAN_AT - 1), "DELIVERY_UNVERIFIED"),
    (lambda p, d, w: d.update(observed_at=NOW - 32 * DAY), "EVIDENCE_STALE"),
    (lambda p, d, w: w[0].update(source="route_registry"), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: w[0].update(status="partial"), "COVERAGE_INCOMPLETE"),
    (lambda p, d, w: w[0].update(count_source="estimated"), "COVERAGE_UNVERIFIED"),
    (lambda p, d, w: w[0].update(observed_at=w[0]["window_end"] - 1), "COVERAGE_UNVERIFIED"),
    (lambda p, d, w: w[0].update(profile_id="other"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: w[0].update(aircraft_id="99999"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: w[0].update(model_id="another"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: w[0].update(verified=False), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: w[0].update(window_start=w[0]["window_start"] - 100), "WINDOW_INVALID"),
    (lambda p, d, w: w[1].update(window_start=w[1]["window_start"] + 1,
                               window_end=w[1]["window_end"] + 1), "WINDOW_INVALID"),
    (lambda p, d, w: w[1].update(window_start=w[0]["window_start"],
                               window_end=w[0]["window_end"]), "WINDOW_INVALID"),
    (lambda p, d, w: w[0].update(expected_flight_ids=[]), "COVERAGE_UNVERIFIED"),
    (lambda p, d, w: w[0].update(flight_count=0), "COVERAGE_UNVERIFIED"),
    (lambda p, d, w: w[0]["flights"][0].update(flight_id="1002"), "FLIGHT_NOT_INDEPENDENT"),
    (lambda p, d, w: w[1]["flights"][0].update(flight_id="1001"), "FLIGHT_NOT_INDEPENDENT"),
    (lambda p, d, w: w[0]["flights"][0].update(flight_id=None), "FLIGHT_NOT_INDEPENDENT"),
    (lambda p, d, w: w[0]["flights"][0].update(source="route_registry"), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: w[0]["flights"][0].update(revenue=None), "REVENUE_UNVERIFIED"),
    (lambda p, d, w: w[0]["flights"][0].update(completed_at=DELIVERED_AT), "FLIGHT_OUT_OF_WINDOW"),
    (lambda p, d, w: w[0]["flights"][0].update(observed_at=PLAN_AT), "FLIGHT_OUT_OF_WINDOW"),
    (lambda p, d, w: w[0]["flights"][0].update(destination_id="999"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: w[0]["financial"].update(source="game_flight_history"), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: w[0]["financial"].update(verified=False), "SOURCE_UNVERIFIED"),
    (lambda p, d, w: w[0]["financial"].update(aircraft_id="99999"), "IDENTITY_MISMATCH"),
    (lambda p, d, w: w[0]["financial"].update(window_end=NOW), "ACCOUNTING_INCOMPLETE"),
    (lambda p, d, w: w[0]["financial"].update(costs_complete=False), "ACCOUNTING_INCOMPLETE"),
    (lambda p, d, w: w[0]["financial"].update(excluded_costs=["maintenance"]), "ACCOUNTING_INCOMPLETE"),
    (lambda p, d, w: w[0]["financial"].update(revenue=501), "REVENUE_MISMATCH"),
    (lambda p, d, w: w[0]["financial"].update(revenue="500.001"), "ACCOUNTING_INVALID"),
    (lambda p, d, w: w[0]["financial"]["costs"].update(fuel=None), "ACCOUNTING_INVALID"),
    (lambda p, d, w: w[0]["financial"]["costs"].update(fuel=-1), "ACCOUNTING_INVALID"),
    (lambda p, d, w: w[0]["financial"]["costs"].update(co2=float("inf")), "ACCOUNTING_INVALID"),
    (lambda p, d, w: w[0]["financial"]["costs"].update(other=True), "ACCOUNTING_INVALID"),
    (lambda p, d, w: w[0]["financial"]["costs"].update(maintenance=100), "ACCOUNTING_INCOMPLETE"),
])
def test_invalid_or_unattributable_evidence_never_generates_metrics(mutation, code):
    plan, delivery, windows = supplied_evidence()
    mutation(plan, delivery, windows)
    inconclusive((plan, delivery, windows), code)


def test_insufficient_independent_flights_even_with_full_days():
    plan, delivery, windows = supplied_evidence()
    for window in windows:
        window["flights"] = window["flights"][:1]
        window["flights"][0]["revenue"] = 500
        window["expected_flight_ids"] = [window["flights"][0]["flight_id"]]
        window["flight_count"] = 1
    result = compare((plan, delivery, windows), min_independent_flights=5)
    assert result["status"] == "inconclusivo"
    assert "INSUFFICIENT_INDEPENDENT_FLIGHTS" in codes(result)
    assert result["metrics"] is None


def test_insufficient_full_windows_cannot_use_short_partial_days():
    plan, delivery, windows = supplied_evidence()
    inconclusive((plan, delivery, windows[:2]), "INSUFFICIENT_WINDOWS")
    result = compare((plan, delivery, windows), min_complete_windows=4)
    assert result["status"] == "inconclusivo"
    assert "INSUFFICIENT_WINDOWS" in codes(result)


def test_no_flight_day_with_verified_fixed_costs_is_kept_in_daily_average():
    plan, delivery, windows = supplied_evidence()
    empty_day = windows[1]
    empty_day["flights"] = []
    empty_day["flight_count"] = 0
    empty_day["expected_flight_ids"] = []
    empty_day["financial"]["revenue"] = 0
    result = compare((plan, delivery, windows))
    assert result["status"] == "conclusivo"
    assert result["metrics"]["independent_flights"] == 4
    assert result["metrics"]["observed_daily_net_profit"] == 83.33


@pytest.mark.parametrize("options,code", [
    ({"now": -1}, "CLOCK_INVALID"),
    ({"now": True}, "CLOCK_INVALID"),
    ({"max_observation_age_seconds": -1}, "POLICY_INVALID"),
    ({"max_history_age_seconds": 10}, "POLICY_INVALID"),
    ({"min_complete_windows": True}, "POLICY_INVALID"),
    ({"min_complete_windows": 1}, "POLICY_INVALID"),
    ({"min_independent_flights": 1}, "POLICY_INVALID"),
])
def test_invalid_settings_fail_closed(options, code):
    data = supplied_evidence()
    result = compare_forecast(*data, **({"now": NOW} | options))
    assert result["status"] == "inconclusivo"
    assert code in codes(result)
    assert result["metrics"] is None


def test_stale_completed_window_and_delivered_later_are_inconclusive():
    plan, delivery, windows = supplied_evidence()
    inconclusive((plan, delivery, windows[:-1]), "INSUFFICIENT_WINDOWS")
    result = compare((plan, delivery, windows), max_observation_age_seconds=60)
    assert result["status"] == "conclusivo"
    delivery["delivered_at"] = windows[0]["window_start"] + 1
    inconclusive((plan, delivery, windows), "WINDOW_INVALID")


def test_route_registry_cached_finance_is_not_promoted_to_real_profit():
    plan, delivery, _ = supplied_evidence()
    cached = [{"aircraft_id": "98765", "last_24h": {
        "source": "game_flight_history", "flight_count": 7,
        "estimated_operating_margin": 500, "observed_at": NOW,
    }}]
    inconclusive((plan, delivery, cached), "SOURCE_UNVERIFIED")


def test_unsupported_portfolio_row_and_journal_without_forecast_remain_inconclusive():
    _, delivery, windows = supplied_evidence()
    portfolio = {"status": "viavel", "profit_per_day": 250,
                 "hub_id": "123", "engine_id": "motor-02", "model": "A320"}
    journal = {"state": "CONFIRMED", "kind": "aircraft", "estimated_cost": 5000,
               "plan_id": "candidate-123", "snapshot_id": "sha256:" + "a" * 64}
    for plan in (portfolio, journal):
        inconclusive((plan, delivery, windows), "PLAN_UNVERIFIED")


def test_missing_objects_and_unstructured_input_return_inconclusive():
    for args in ((None, None, None), ({}, {}, []), (validated_plan(), None, []),
                 (validated_plan(), supplied_evidence()[1], ["invalid"])):
        result = compare_forecast(*args, now=NOW)
        assert result["status"] == "inconclusivo"
        assert result["metrics"] is None
        assert result["parameter_changes"] == {}
