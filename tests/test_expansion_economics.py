"""A3 economics: reproducible, evidence-bound accounting, without game I/O."""

from __future__ import annotations

from copy import deepcopy

import pytest

from expansion_economics import evaluate_expansion_economics, rank_expansion_economics
from opportunity_models import fingerprint_snapshot


NOW = 1_800_000_000
PROFILE = "principal"
IDENTITY = {
    "hub_id": "123", "origin_id": "123", "destination_id": "456",
    "model_id": "789", "engine_id": "engine-02",
}
SUBJECTS = {
    "layout": ("model_id", "engine_id"),
    "capacity": ("model_id", "engine_id"),
    "daily_demand": ("hub_id", "origin_id", "destination_id"),
    "fares": ("hub_id", "origin_id", "destination_id"),
    "departures_per_day": tuple(IDENTITY),
    "load_factor": tuple(IDENTITY),
    "fuel_units_per_day": tuple(IDENTITY),
    "fuel_price_per_1000": (),
    "co2_units_per_passenger": tuple(IDENTITY),
    "co2_price_per_1000": (),
    "recurring_costs": tuple(IDENTITY),
    "other_fees": tuple(IDENTITY),
    "cash": (),
}
SOURCES = {
    "layout": "game_aircraft_shop", "capacity": "game_aircraft_shop",
    "daily_demand": "game_route_search", "fares": "game_route_search",
    "departures_per_day": "route_optimizer", "load_factor": "route_optimizer",
    "fuel_units_per_day": "route_optimizer", "fuel_price_per_1000": "game_market",
    "co2_units_per_passenger": "route_optimizer", "co2_price_per_1000": "game_market",
    "recurring_costs": "game_research", "other_fees": "game_market",
    "cash": "game_snapshot",
}


def evidence(source, **fields):
    return {"source": source, "profile_id": PROFILE, "observed_at": NOW - 20,
            "verified": True, **fields}


def fixture():
    snapshot = evidence(
        "game_snapshot", schema_version=1,
        hubs=[evidence("game_hub_select", id="123", id_source="game", owned=True)],
        coverage=evidence(
            "game_fleet_scan", status="complete", observed_pages=1, expected_pages=1,
            expected_aircraft_count=1, count_source="game_fleet_total",
            observed_aircraft_ids=["101"],
            scopes={name: True for name in (
                "hubs", "fleet", "routes", "models", "engines", "prices")},
        ),
    )
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    candidate = {
        "schema_version": 1, "profile_id": PROFILE, "snapshot_id": snapshot["snapshot_id"],
        "kind": "aircraft_on_owned_hub", "hub": {"id": "123"},
        "route": evidence(
            "game_route_search", id_source="game", origin_id="123", destination_id="456",
            stopover_id=None, available=True, feasible=True, occupied=False,
            demand_verified=True, demand_remaining=300, demand_unit="passengers_per_day", distance_km=1000,
            range_km=3000, required_runway_m=1900, origin_runway_m=2700,
            destination_runway_m=2500,
        ),
        "aircraft": evidence(
            "game_aircraft_shop", id_source="game", model_id="789",
            engine_id="engine-02", engine_model_id="789", available=True,
        ),
        "costs": {
            "aircraft_cost": evidence("game_aircraft_shop", value=10000, price_basis="base_without_engine"),
            "engine_delta_cost": evidence("game_aircraft_shop", value=500),
            "hub_cost": evidence("game_hub_select", value=0),
            "route_fee": evidence("game_route_search", value=100),
            "hangar_cost": evidence("game_hub_select", value=50),
        },
        "financial": evidence("route_optimizer", value=7996.50, excluded_costs=[]),
    }
    for item in (candidate["route"], candidate["aircraft"], candidate["financial"],
                 *candidate["costs"].values()):
        item["snapshot_id"] = snapshot["snapshot_id"]
    candidate["financial"].update(IDENTITY)
    for name, fields in {
        "aircraft_cost": ("model_id", "engine_id"),
        "engine_delta_cost": ("model_id", "engine_id"),
        "hub_cost": ("hub_id",),
        "route_fee": ("origin_id", "destination_id"),
        "hangar_cost": ("hub_id",),
    }.items():
        candidate["costs"][name].update({key: IDENTITY[key] for key in fields})

    values = {
        "layout": {"y": 100, "j": 20, "f": 10},
        "capacity": 180,
        "daily_demand": {"y": 250, "j": 30, "f": 20},
        "fares": {"y": 50, "j": 100, "f": 150},
        "departures_per_day": 2,
        "load_factor": 0.8,
        "fuel_units_per_day": 8000,
        "fuel_price_per_1000": 650,
        "co2_units_per_passenger": {"y": 1, "j": 2, "f": 3},
        "co2_price_per_1000": 125,
        "recurring_costs": {"maintenance": 100, "a_check": 50, "other": 20},
        "other_fees": 50,
        "cash": {"available": 40000, "committed": 1000, "reserve": 5000},
    }
    inputs = {
        name: evidence(source, snapshot_id=snapshot["snapshot_id"], value=values[name],
                       **{key: IDENTITY[key] for key in SUBJECTS[name]})
        for name, source in SOURCES.items()
    }
    return snapshot, candidate, inputs


def evaluate(data, **kwargs):
    return evaluate_expansion_economics(*data, now=NOW, **kwargs)


def codes(result):
    return {item["code"] for item in result["blocking_reasons"]}


def test_success_is_deterministic_auditable_and_read_only():
    data = fixture()
    original = deepcopy(data)
    result = evaluate(data)
    assert result["status"] == "evaluated", result["blocking_reasons"]
    assert result["read_only"] and result["execution_available"] is False
    assert result["configuration_yjf"] == {"y": 100, "j": 20, "f": 10}
    assert result["components"]["passengers_per_day"] == {"y": 160, "j": 30, "f": 16}
    assert result["components"]["revenue_by_class"] == {"y": 8000, "j": 3000, "f": 2400}
    assert result["components"]["revenue_per_day"] == 13400
    assert result["components"]["fuel_cost_per_day"] == 5200
    assert result["components"]["co2_cost_per_day"] == 33.5
    assert result["components"]["known_recurring_cost_per_day"] == 170
    assert result["components"]["safety_margin_per_day"] == 1340
    assert result["components"]["daily_net_profit_estimate"] == 6656.5
    assert result["capital_costs"]["total_investment"] == 10700
    assert result["cash_after_purchase"] == 28300
    assert result["components"]["payback_days"] == 1.61
    assert result["components"]["roi_365d_percent"] == pytest.approx(22706.75, abs=0.02)
    assert result["evidence_confidence"] == "provenance_complete"
    assert result["methodology"]["seat_capacity_source"] == "route_optimizer.CLASS_WEIGHTS"
    assert result["provenance"]["fuel_units_per_day"]["source"] == "route_optimizer"
    assert result["provenance"]["fuel_price_per_1000"]["value"] == 650
    assert result["observed_at_oldest"] == NOW - 20
    assert result == evaluate(data)
    assert data == original


def test_sensitivity_recomputes_revenue_and_emissions_from_class_demand():
    result = evaluate(fixture())
    baseline = result["components"]
    scenarios = result["sensitivity"]
    assert set(scenarios) == {"fuel_price", "co2_price", "occupancy", "demand", "combined"}
    assert scenarios["fuel_price"]["fuel_cost_per_day"] == 6240
    assert scenarios["fuel_price"]["daily_net_profit_estimate"] == baseline["daily_net_profit_estimate"] - 1040
    assert scenarios["co2_price"]["co2_cost_per_day"] == 40.2
    assert scenarios["occupancy"]["revenue_per_day"] < baseline["revenue_per_day"]
    assert scenarios["occupancy"]["co2_cost_per_day"] < baseline["co2_cost_per_day"]
    assert scenarios["demand"]["passengers_per_day"]["j"] == 27
    assert scenarios["demand"]["passengers_per_day"]["y"] == 160
    combined = scenarios["combined"]
    assert combined["multipliers"] == result["methodology"]["stress_factors"]
    assert combined["fuel_cost_per_day"] == scenarios["fuel_price"]["fuel_cost_per_day"]
    assert combined["revenue_per_day"] <= scenarios["demand"]["revenue_per_day"]
    assert combined["revenue_per_day"] <= scenarios["occupancy"]["revenue_per_day"]
    assert combined["daily_net_profit_estimate"] < min(
        row["daily_net_profit_estimate"] for key, row in scenarios.items() if key != "combined"
    )


@pytest.mark.parametrize("field", ["layout", "daily_demand", "fares", "departures_per_day",
                                   "fuel_units_per_day", "co2_units_per_passenger", "cash"])
def test_missing_required_evidence_never_substitutes_zero(field):
    data = fixture()
    del data[2][field]
    result = evaluate(data)
    assert result["status"] == "blocked"
    assert "EVIDENCE_MISSING" in codes(result)
    assert result["components"] is None or result["components"]["daily_net_profit_estimate"] is None


@pytest.mark.parametrize("mutation,code", [
    (lambda d: d[2]["layout"]["value"].update(j=100), "LAYOUT_CAPACITY_EXCEEDED"),
    (lambda d: d[1]["route"].update(occupied=True), "ROUTE_OCCUPIED"),
    (lambda d: d[1]["route"].update(occupied=None), "ROUTE_OCCUPANCY_UNVERIFIED"),
    (lambda d: d[2]["daily_demand"]["value"].update(y=300), "DEMAND_CONTRADICTORY"),
    (lambda d: d[2]["layout"].update(engine_id="wrong-engine"), "EVIDENCE_CONTRADICTORY"),
    (lambda d: d[2]["fares"].update(verified=False), "EVIDENCE_CONTRADICTORY"),
    (lambda d: d[2]["fuel_price_per_1000"].update(observed_at=NOW - 1000), "EVIDENCE_STALE"),
    (lambda d: d[2]["co2_price_per_1000"].update(source="operator_config"), "EVIDENCE_CONTRADICTORY"),
    (lambda d: d[1]["financial"].update(value=9999), "FINANCIAL_CONTRADICTORY"),
    (lambda d: d[2]["cash"]["value"].update(reserve=30000), "CASH_RESERVE_INSUFFICIENT"),
    (lambda d: d[2]["fares"]["value"].update(f=0), "FARE_UNKNOWN"),
    (lambda d: d[2]["load_factor"].update(value=1.2), "OCCUPANCY_INVALID"),
])
def test_contradictions_and_infeasibility_fail_closed(mutation, code):
    data = fixture()
    mutation(data)
    result = evaluate(data)
    assert result["status"] == "blocked"
    assert code in codes(result)
    assert result["components"] is None or result["components"]["payback_days"] is None


def test_unknown_recurring_cost_exposes_upper_bound_and_blocks_roi():
    data = fixture()
    data[2]["recurring_costs"]["value"]["a_check"] = None
    data[1]["financial"]["excluded_costs"] = ["a_check"]
    result = evaluate(data)
    assert "UNMODELED_RECURRING_COSTS" in codes(result)
    assert "PROFIT_INCOMPLETE" in codes(result)
    assert result["excluded_costs"] == ["a_check"]
    assert result["components"]["profit_ceiling_before_unknown_costs"] == 6706.5
    assert result["components"]["daily_net_profit_estimate"] is None
    assert result["sensitivity"]["fuel_price"]["roi_365d_percent"] is None
    assert result["evidence_confidence"] == "incomplete"


def test_fees_engine_price_basis_and_reserve_are_consistent():
    data = fixture()
    data[1]["costs"]["aircraft_cost"]["price_basis"] = "final_including_engine"
    assert "COST_DOUBLE_COUNT" in codes(evaluate(data))
    data = fixture()
    data[2]["other_fees"]["value"] = None
    assert "ACCOUNTING_INPUT_INVALID" in codes(evaluate(data))
    data = fixture()
    data[2]["cash"]["value"].update(committed=None)
    assert "ACCOUNTING_INPUT_INVALID" in codes(evaluate(data))

    data = fixture()
    data[1]["costs"]["aircraft_cost"]["price_basis"] = "final_including_engine"
    data[1]["costs"]["aircraft_cost"]["value"] = 10500
    data[1]["costs"]["engine_delta_cost"]["value"] = 0
    assert evaluate(data)["status"] == "evaluated"


def test_content_id_tracks_layout_and_snapshot_changes_without_mutation():
    original = fixture()
    old = evaluate(original)
    changed = deepcopy(original)
    changed[2]["layout"]["value"].update(y=95)
    newer = evaluate(changed)
    assert newer["status"] == "blocked"
    assert "FINANCIAL_CONTRADICTORY" in codes(newer)
    assert newer["plan_id"] == old["plan_id"]
    assert newer["economics_id"] != old["economics_id"]
    assert newer["components"]["revenue_per_day"] < old["components"]["revenue_per_day"]

    changed = deepcopy(original)
    changed[0]["coverage"]["scopes"]["prices"] = False
    changed[0]["snapshot_id"] = fingerprint_snapshot(changed[0])
    changed[1]["snapshot_id"] = changed[0]["snapshot_id"]
    for proof in (changed[1]["route"], changed[1]["aircraft"], changed[1]["financial"],
                  *changed[1]["costs"].values(), *changed[2].values()):
        proof["snapshot_id"] = changed[0]["snapshot_id"]
    assert "COVERAGE_INCOMPLETE" in codes(evaluate(changed))


def test_excessively_large_projection_fails_closed_without_raising():
    data = fixture()
    data[2]["fares"]["value"]["y"] = 10**15
    result = evaluate(data)
    assert result["status"] == "blocked"
    assert "ACCOUNTING_OVERFLOW" in codes(result)


@pytest.mark.parametrize("kwargs,code", [
    ({"safety_margin_fraction": -0.1}, "SAFETY_MARGIN_INVALID"),
    ({"safety_margin_fraction": float("nan")}, "SAFETY_MARGIN_INVALID"),
    ({"stress": {"fuel_price": 0.9, "co2_price": 1.2, "occupancy": 0.9, "demand": 0.9}}, "STRESS_INVALID"),
    ({"stress": {"fuel_price": 1.2, "co2_price": 1.2, "occupancy": 1.1, "demand": 0.9}}, "STRESS_INVALID"),
])
def test_invalid_stress_and_margin_are_blocked(kwargs, code):
    result = evaluate(fixture(), **kwargs)
    assert result["status"] == "blocked"
    assert code in codes(result)


def test_global_ranking_deduplicates_and_blocks_contradictory_same_identity():
    original = evaluate(fixture())
    alternate_data = fixture()
    alternate_data[1]["aircraft"]["engine_id"] = "engine-03"
    alternate_data[2]["layout"]["engine_id"] = "engine-03"
    alternate_data[2]["capacity"]["engine_id"] = "engine-03"
    for item in (alternate_data[1]["financial"], *alternate_data[1]["costs"].values()):
        if "engine_id" in item:
            item["engine_id"] = "engine-03"
    for field, fields in SUBJECTS.items():
        if "engine_id" in fields:
            alternate_data[2][field]["engine_id"] = "engine-03"
    alternate_data[2]["other_fees"]["value"] = 300
    alternate = evaluate(alternate_data)
    assert alternate["status"] == "evaluated", alternate["blocking_reasons"]
    best = rank_expansion_economics([alternate, original, deepcopy(original)])
    assert best["best"] == original
    assert len(best["alternatives"]) == 2
    assert best["read_only"] and best["execution_available"] is False

    conflict = deepcopy(original)
    conflict["economics_id"] += "-conflicting"
    result = rank_expansion_economics([original, conflict, alternate])
    assert result["conflicting_identities"] == 1
    assert result["excluded_count"] == 2
    assert result["best"] == alternate


@pytest.mark.parametrize("corrupt", [
    lambda row: row["components"].update(roi_365d_percent=float("inf")),
    lambda row: row["components"].update(roi_365d_percent=float("nan")),
    lambda row: row["components"].update(roi_365d_percent=-1),
    lambda row: row.update(components="invalid"),
    lambda row: row.update(capital_costs=["invalid"]),
])
def test_ranking_rejects_invalid_financial_rows_without_poisoning_valid_identity(corrupt):
    valid = evaluate(fixture())
    invalid = deepcopy(valid)
    corrupt(invalid)

    result = rank_expansion_economics([invalid, valid, deepcopy(valid)])
    assert result["best"] == valid
    assert result["alternatives"] == [valid]
    assert result["excluded_count"] == 1
    assert result["conflicting_identities"] == 0


@pytest.mark.parametrize("change", [0.01, 1.0, 50.0])
def test_ranking_rejects_financially_inconsistent_roi(change):
    valid = evaluate(fixture())
    inconsistent = deepcopy(valid)
    inconsistent["components"]["roi_365d_percent"] += change

    result = rank_expansion_economics([inconsistent, valid])
    assert result["best"] == valid
    assert result["alternatives"] == [valid]
    assert result["excluded_count"] == 1
    assert result["conflicting_identities"] == 0


def test_ranking_across_hubs_routes_and_models_uses_same_contract():
    first = evaluate(fixture())
    data = fixture()
    altered = {"hub_id": "777", "origin_id": "777", "destination_id": "888",
               "model_id": "new-model", "engine_id": "engine-09"}
    data[0]["hubs"][0]["id"] = altered["hub_id"]
    data[1]["hub"]["id"] = altered["hub_id"]
    data[1]["route"].update(origin_id=altered["origin_id"], destination_id=altered["destination_id"])
    data[1]["aircraft"].update(model_id=altered["model_id"], engine_id=altered["engine_id"],
                                engine_model_id=altered["model_id"])
    data[1]["financial"].update(altered)
    for field, fields in {
        "aircraft_cost": ("model_id", "engine_id"), "engine_delta_cost": ("model_id", "engine_id"),
        "hub_cost": ("hub_id",), "route_fee": ("origin_id", "destination_id"),
        "hangar_cost": ("hub_id",),
    }.items():
        data[1]["costs"][field].update({key: altered[key] for key in fields})
    data[0]["snapshot_id"] = fingerprint_snapshot(data[0])
    data[1]["snapshot_id"] = data[0]["snapshot_id"]
    for proof in (data[1]["route"], data[1]["aircraft"], data[1]["financial"],
                  *data[1]["costs"].values()):
        proof["snapshot_id"] = data[0]["snapshot_id"]
    for name, proof in data[2].items():
        proof["snapshot_id"] = data[0]["snapshot_id"]
        proof.update({key: altered[key] for key in SUBJECTS[name]})
    other = evaluate(data)
    assert other["status"] == "evaluated", other["blocking_reasons"]
    result = rank_expansion_economics([first, other])
    assert len(result["alternatives"]) == 2
    assert {row["identity"]["hub_id"] for row in result["alternatives"]} == {"123", "777"}


def test_invalid_extreme_inputs_do_not_create_a_usable_recommendation():
    data = fixture()
    data[2]["fares"]["value"]["y"] = float("inf")
    result = evaluate(data)
    assert result["status"] == "blocked"
    assert result["components"] is None
    assert "ACCOUNTING_INPUT_INVALID" in codes(result)
