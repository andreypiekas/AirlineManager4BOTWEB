"""Contract tests based only on simulated, profile-bound game observations."""

from __future__ import annotations

from copy import deepcopy

import pytest

from opportunity_models import evaluate_investment, fingerprint_snapshot


NOW = 1_800_000_000


def evidence(source, **fields):
    return {
        "source": source,
        "profile_id": "principal",
        "observed_at": NOW - 15,
        "verified": True,
        **fields,
    }


def sample():
    snapshot = evidence(
        "game_snapshot",
        schema_version=1,
        hubs=[evidence("game_hub_select", id="123", id_source="game", owned=True)],
        coverage=evidence(
            "game_fleet_scan",
            status="complete",
            observed_pages=2,
            expected_pages=2,
            expected_aircraft_count=3,
            count_source="game_fleet_total",
            observed_aircraft_ids=["101", "102", "103"],
            scopes={key: True for key in ("hubs", "fleet", "routes", "models", "engines", "prices")},
        ),
    )
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    candidate = {
        "schema_version": 1,
        "profile_id": "principal",
        "snapshot_id": snapshot["snapshot_id"],
        "kind": "aircraft_on_owned_hub",
        "hub": {"id": "123"},
        "route": evidence(
            "game_route_search",
            id_source="game",
            origin_id="123",
            destination_id="456",
            stopover_id=None,
            available=True,
            feasible=True,
            demand_verified=True,
            demand_remaining=300,
            distance_km=1000,
            range_km=3000,
            required_runway_m=1900,
            origin_runway_m=2700,
            destination_runway_m=2500,
        ),
        "aircraft": evidence(
            "game_aircraft_shop",
            id_source="game",
            model_id="789",
            engine_id="engine-02",
            engine_model_id="789",
            available=True,
        ),
        "costs": {
            "aircraft_cost": evidence("game_aircraft_shop", value=10_000, price_basis="base_without_engine"),
            "engine_delta_cost": evidence("game_aircraft_shop", value=500),
            "hub_cost": evidence("game_hub_select", value=0),
            "route_fee": evidence("game_route_search", value=100),
            "hangar_cost": evidence("game_hub_select", value=50),
        },
        "financial": evidence("route_optimizer", value=250, excluded_costs=[]),
    }
    identities = {"hub_id": "123", "origin_id": "123", "destination_id": "456", "model_id": "789", "engine_id": "engine-02"}
    for entry in (candidate["route"], candidate["aircraft"], candidate["financial"], *candidate["costs"].values()):
        entry["snapshot_id"] = snapshot["snapshot_id"]
    candidate["financial"].update(identities)
    for field, fields in {
        "aircraft_cost": ("model_id", "engine_id"),
        "engine_delta_cost": ("model_id", "engine_id"),
        "hub_cost": ("hub_id",),
        "route_fee": ("origin_id", "destination_id"),
        "hangar_cost": ("hub_id",),
    }.items():
        candidate["costs"][field].update({key: identities[key] for key in fields})
    return snapshot, candidate


def evaluate(snapshot, candidate):
    return evaluate_investment(snapshot, candidate, now=NOW)


def codes(result):
    return {reason["code"] for reason in result["policy"]["reasons"]}


def rebind(snapshot, candidate):
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    candidate["snapshot_id"] = snapshot["snapshot_id"]
    for entry in (candidate["route"], candidate["aircraft"], candidate["financial"], *candidate["costs"].values()):
        entry["snapshot_id"] = snapshot["snapshot_id"]


def test_success_is_read_only_reproducible_and_explainable():
    snapshot, candidate = sample()
    original_snapshot, original_candidate = deepcopy(snapshot), deepcopy(candidate)
    result = evaluate(snapshot, candidate)
    assert result["schema_version"] == 1
    assert result["status"] == "suggested"
    assert result["policy"] == {"approved": False, "read_only": True, "reasons": []}
    assert result["economics"] == {
        "aircraft_cost": 10_000.0,
        "engine_delta_cost": 500.0,
        "hub_cost": 0.0,
        "route_fee": 100.0,
        "hangar_cost": 50.0,
        "total_investment": 10_650.0,
        "daily_net_profit_estimate": 250.0,
        "payback_days": 42.6,
    }
    assert result["plan_id"].startswith("plan-v1-")
    assert result == evaluate(snapshot, candidate)
    assert snapshot == original_snapshot
    assert candidate == original_candidate

    candidate["costs"]["aircraft_cost"]["value"] = 11_000
    assert evaluate(snapshot, candidate)["plan_id"] != result["plan_id"]


def test_native_free_passenger_hangar_cost_is_bound_to_captured_evidence():
    from fleet_commitment_observations import SOURCE
    from opportunity_models import native_free_passenger_hangar_cost

    snapshot, candidate = sample()
    commitments = {"source": SOURCE, "status": "partial", "observed_at": NOW - 10,
                   "passenger_hangar": {"capacity": 4, "occupied": 3, "free": 1}}
    snapshot["observations"] = {"fleet_commitments": commitments}
    rebind(snapshot, candidate)
    evidence = native_free_passenger_hangar_cost(snapshot, "123", now=NOW)
    candidate["costs"]["hangar_cost"] = evidence.copy()
    result = evaluate(snapshot, candidate)
    assert result["status"] == "suggested"
    assert result["economics"]["total_investment"] == 10600
    for field, value in (("value", 50), ("observed_at", NOW), ("hub_id", "456")):
        candidate["costs"]["hangar_cost"] = {**evidence, field: value}
        assert "HANGAR_COST_UNVERIFIED" in codes(evaluate(snapshot, candidate))

    candidate["costs"]["hangar_cost"] = evidence.copy()
    for changes in ({"observed_at": NOW - 901}, {"source": "other"},
                    {"passenger_hangar": {"capacity": 4, "occupied": 4, "free": 0}},
                    {"passenger_hangar": {"capacity": 4, "occupied": 4, "free": 1}}):
        original = commitments.copy()
        commitments.update(changes)
        rebind(snapshot, candidate)
        assert native_free_passenger_hangar_cost(snapshot, "123", now=NOW) is None
        assert "HANGAR_COST_UNVERIFIED" in codes(evaluate(snapshot, candidate))
        commitments.clear()
        commitments.update(original)


@pytest.mark.parametrize(
    "field",
    [
        "aircraft_cost",
        "engine_delta_cost",
        "hub_cost",
        "route_fee",
        "hangar_cost",
    ],
)
def test_unknown_cost_blocks_without_defaulting_to_zero(field):
    snapshot, candidate = sample()
    candidate["costs"][field]["value"] = None
    result = evaluate(snapshot, candidate)
    assert result["status"] == "blocked"
    assert "COST_UNKNOWN" in codes(result)
    assert result["economics"][field] is None
    assert result["economics"]["total_investment"] is None
    assert result["economics"]["payback_days"] is None
    assert any(reason["field"] == f"costs.{field}" for reason in result["policy"]["reasons"])


@pytest.mark.parametrize("bad_value", ["unknown", "0", True, -2, float("nan"), float("inf")])
def test_invalid_aircraft_price_is_rejected(bad_value):
    snapshot, candidate = sample()
    candidate["costs"]["aircraft_cost"]["value"] = bad_value
    result = evaluate(snapshot, candidate)
    assert "COST_INVALID" in codes(result)
    assert result["economics"]["total_investment"] is None
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["coverage"].update(status="partial"),
        lambda s: s["coverage"]["scopes"].update(engines=False),
        lambda s: s["coverage"].update(observed_pages=1),
        lambda s: s["coverage"].update(expected_aircraft_count=4),
        lambda s: s["coverage"].update(observed_aircraft_ids=["101", "102", "102"]),
        lambda s: s["coverage"].update(count_source="inferred"),
    ],
)
def test_partial_or_incoherent_coverage_blocks(change):
    snapshot, candidate = sample()
    change(snapshot)
    rebind(snapshot, candidate)
    result = evaluate(snapshot, candidate)
    assert result["status"] == "blocked"
    assert codes(result) & {"COVERAGE_INCOMPLETE", "COVERAGE_INCOHERENT"}
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize("native_verified,routed,unrouted,valid", [
    (True, 0, 3, True),
    (False, 0, 3, False),
    (True, 0, 2, False),
    (True, 1, 2, False),
    (True, False, 3, False),
])
def test_nonempty_fleet_without_route_pages_requires_native_partition(native_verified, routed, unrouted, valid):
    snapshot, candidate = sample()
    snapshot["coverage"].update(
        observed_pages=0, expected_pages=0, routed_aircraft_count=routed,
        unrouted_aircraft_count=unrouted, native_unrouted_identity_verified=native_verified,
    )
    rebind(snapshot, candidate)
    result = evaluate(snapshot, candidate)
    assert (result["status"] == "suggested") is valid
    assert ("COVERAGE_INCOHERENT" in codes(result)) is not valid


@pytest.mark.parametrize(
    "path",
    [
        ("snapshot",),
        ("coverage",),
        ("hubs",),
        ("route",),
        ("aircraft",),
        ("costs",),
        ("financial",),
    ],
)
def test_stale_evidence_blocks_at_each_level(path):
    snapshot, candidate = sample()
    targets = {
        "snapshot": snapshot,
        "coverage": snapshot["coverage"],
        "hubs": snapshot["hubs"][0],
        "route": candidate["route"],
        "aircraft": candidate["aircraft"],
        "costs": candidate["costs"]["aircraft_cost"],
        "financial": candidate["financial"],
    }
    targets[path[0]]["observed_at"] = NOW - 901
    if path[0] in ("snapshot", "coverage", "hubs"):
        rebind(snapshot, candidate)
    result = evaluate(snapshot, candidate)
    assert "EVIDENCE_STALE" in codes(result)
    assert result["economics"]["payback_days"] is None
    if path[0] == "costs":
        assert result["economics"]["total_investment"] is None


def test_future_evidence_is_rejected():
    snapshot, candidate = sample()
    candidate["route"]["observed_at"] = NOW + 1
    assert "EVIDENCE_STALE" in codes(evaluate(snapshot, candidate))


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("hub", "ROUTE_HUB_MISMATCH"),
        ("engine", "ENGINE_MODEL_MISMATCH"),
        ("runway", "ROUTE_PHYSICALLY_INFEASIBLE"),
        ("distance", "ROUTE_PHYSICALLY_INFEASIBLE"),
        ("demand", "DEMAND_UNVERIFIED"),
        ("unavailable", "ROUTE_UNAVAILABLE"),
    ],
)
def test_incoherent_route_model_and_hub_are_blocked(path, code):
    snapshot, candidate = sample()
    if path == "hub":
        candidate["route"]["origin_id"] = "999"
    elif path == "engine":
        candidate["aircraft"]["engine_model_id"] = "999"
    elif path == "runway":
        candidate["route"]["origin_runway_m"] = 800
    elif path == "distance":
        candidate["route"]["distance_km"] = 4000
    elif path == "demand":
        candidate["route"]["demand_remaining"] = 0
    else:
        candidate["route"]["available"] = False
    result = evaluate(snapshot, candidate)
    assert code in codes(result)
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize("updates,negative", [
    ({"distance_km": 4000, "origin_runway_m": None}, True),
    ({"origin_runway_m": 800, "destination_runway_m": None}, True),
    ({"destination_runway_m": 800, "range_km": None}, True),
    ({"range_km": 0, "origin_runway_m": None}, False),
    ({"origin_runway_m": -1, "destination_runway_m": None}, False),
    ({"origin_runway_m": None}, False),
])
def test_partial_direct_route_data_retains_independent_negative_constraints(updates, negative):
    snapshot, candidate = sample()
    candidate["route"].update(updates)
    result = evaluate(snapshot, candidate)
    assert "ROUTE_PHYSICAL_DATA_UNKNOWN" in codes(result)
    assert ("ROUTE_PHYSICALLY_INFEASIBLE" in codes(result)) is negative
    assert result["status"] == "blocked"


@pytest.mark.parametrize("updates", [
    {"required_runway_m": None, "legs_km": [3100, 200]},
    {"range_km": None, "stopover_runway_m": 800},
    {"range_km": None, "legs_km": [100, 100]},
])
def test_partial_verified_stopover_data_retains_independent_negative_constraints(updates):
    snapshot, candidate = sample()
    candidate["route"].update(stopover_id="333", stopover_verified=True,
                              legs_km=[700, 800], stopover_runway_m=2400)
    candidate["route"].update(updates)
    result = evaluate(snapshot, candidate)
    assert {"ROUTE_PHYSICAL_DATA_UNKNOWN", "ROUTE_PHYSICALLY_INFEASIBLE"} <= codes(result)
    assert result["status"] == "blocked"


@pytest.mark.parametrize("updates", [
    {"stopover_runway_m": None, "legs_km": [3100, 200]},
    {"legs_km": None, "stopover_runway_m": 800},
])
def test_incomplete_stopover_keeps_negative_constraints_only_when_verified(updates):
    snapshot, candidate = sample()
    candidate["route"].update(stopover_id="333", stopover_verified=True,
                              legs_km=[700, 800], stopover_runway_m=2400)
    candidate["route"].update(updates)
    assert {"STOPOVER_UNVERIFIED", "ROUTE_PHYSICALLY_INFEASIBLE"} <= codes(evaluate(snapshot, candidate))
    candidate["route"]["stopover_verified"] = False
    result = evaluate(snapshot, candidate)
    assert "STOPOVER_UNVERIFIED" in codes(result)
    assert "ROUTE_PHYSICALLY_INFEASIBLE" not in codes(result)
    assert result["status"] == "blocked"


@pytest.mark.parametrize(
    ("target", "source"),
    [
        ("route", "manual"),
        ("aircraft", "route_optimizer"),
        ("costs", "cache"),
        ("financial", "manual"),
    ],
)
def test_untrusted_sources_are_rejected(target, source):
    snapshot, candidate = sample()
    entry = candidate["costs"]["aircraft_cost"] if target == "costs" else candidate[target]
    entry["source"] = source
    result = evaluate(snapshot, candidate)
    assert "EVIDENCE_SOURCE_INVALID" in codes(result)
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize("key", ["profile_id", "id_source", "verified"])
def test_identity_evidence_must_be_profile_bound_and_game_verified(key):
    snapshot, candidate = sample()
    candidate["aircraft"][key] = {"profile_id": "other", "id_source": "inferred", "verified": False}[key]
    result = evaluate(snapshot, candidate)
    assert codes(result) & {"PROFILE_MISMATCH", "EVIDENCE_UNVERIFIED"}


@pytest.mark.parametrize(
    ("target", "field", "value", "expected"),
    [
        ("candidate", "profile_id", "outro", "PROFILE_MISMATCH"),
        ("snapshot", "profile_id", "../principal", "PROFILE_INVALID"),
        ("candidate", "snapshot_id", "another", "SNAPSHOT_ID_MISMATCH"),
        ("candidate", "schema_version", 2, "SCHEMA_UNSUPPORTED"),
        ("route", "destination_id", "GRU", "ROUTE_ID_UNVERIFIED"),
        ("hub", "id", "XAP", "HUB_ID_UNVERIFIED"),
        ("aircraft", "engine_id", None, "ENGINE_ID_UNVERIFIED"),
    ],
)
def test_ids_schema_and_profile_are_validated(target, field, value, expected):
    snapshot, candidate = sample()
    subjects = {
        "candidate": candidate,
        "snapshot": snapshot,
        "route": candidate["route"],
        "hub": candidate["hub"],
        "aircraft": candidate["aircraft"],
    }
    subjects[target][field] = value
    if target == "snapshot":
        rebind(snapshot, candidate)
    result = evaluate(snapshot, candidate)
    assert expected in codes(result)
    assert result["status"] == "blocked"


def test_mutating_snapshot_without_rehash_invalidates_it():
    snapshot, candidate = sample()
    snapshot["hubs"][0]["owned"] = False
    result = evaluate(snapshot, candidate)
    assert "SNAPSHOT_ID_INVALID" in codes(result)
    assert "HUB_OWNERSHIP_MISMATCH" in codes(result)


def test_profit_must_be_known_positive_complete_and_verified():
    snapshot, candidate = sample()
    candidate["financial"]["value"] = None
    assert "PROFIT_UNKNOWN" in codes(evaluate(snapshot, candidate))
    candidate["financial"]["value"] = -2
    assert "PROFIT_NON_POSITIVE" in codes(evaluate(snapshot, candidate))
    candidate["financial"]["value"] = 250
    candidate["financial"]["excluded_costs"] = ["maintenance"]
    assert "PROFIT_INCOMPLETE" in codes(evaluate(snapshot, candidate))
    assert evaluate(snapshot, candidate)["economics"]["payback_days"] is None


def test_new_hub_requires_explicit_positive_hub_price():
    snapshot, candidate = sample()
    snapshot["hubs"][0]["owned"] = False
    rebind(snapshot, candidate)
    candidate["kind"] = "aircraft_on_new_hub"
    candidate["costs"]["hub_cost"]["value"] = 1200
    result = evaluate(snapshot, candidate)
    assert result["status"] == "suggested"
    assert result["economics"]["total_investment"] == 11_850.0
    candidate["costs"]["hub_cost"]["value"] = 0
    assert "HUB_COST_INCOHERENT" in codes(evaluate(snapshot, candidate))


def test_verified_stopover_needs_real_airport_and_physical_checks():
    snapshot, candidate = sample()
    candidate["route"].update(
        stopover_id="333",
        stopover_verified=True,
        legs_km=[700, 800],
        stopover_runway_m=2400,
    )
    candidate["financial"]["stopover_id"] = "333"
    candidate["costs"]["route_fee"]["stopover_id"] = "333"
    assert evaluate(snapshot, candidate)["status"] == "suggested"
    candidate["route"]["legs_km"] = [3100, 200]
    assert "ROUTE_PHYSICALLY_INFEASIBLE" in codes(evaluate(snapshot, candidate))
    candidate["route"]["stopover_verified"] = False
    assert "STOPOVER_UNVERIFIED" in codes(evaluate(snapshot, candidate))


@pytest.mark.parametrize("route_stop,proof_stop", [("333", "999"), ("333", None), (None, "333")])
def test_stopover_must_match_financial_and_route_fee_evidence(route_stop, proof_stop):
    snapshot, candidate = sample()
    if route_stop:
        candidate["route"].update(stopover_id=route_stop, stopover_verified=True,
                                  legs_km=[700, 800], stopover_runway_m=2400)
    candidate["financial"]["stopover_id"] = proof_stop
    candidate["costs"]["route_fee"]["stopover_id"] = proof_stop
    result = evaluate(snapshot, candidate)
    assert result["status"] == "blocked"
    assert {"COST_IDENTITY_MISMATCH", "PROFIT_IDENTITY_MISMATCH"} <= codes(result)
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize(
    ("section", "field", "wrong_value", "expected_code"),
    [
        ("costs.aircraft_cost", "engine_id", "engine-03", "COST_IDENTITY_MISMATCH"),
        ("costs.route_fee", "destination_id", "999", "COST_IDENTITY_MISMATCH"),
        ("financial", "model_id", "other", "PROFIT_IDENTITY_MISMATCH"),
        ("aircraft", "snapshot_id", "old-snapshot", "EVIDENCE_SNAPSHOT_MISMATCH"),
    ],
)
def test_evidence_must_bind_exact_selection_and_snapshot(section, field, wrong_value, expected_code):
    snapshot, candidate = sample()
    entry = candidate
    for part in section.split("."):
        entry = entry[part]
    entry[field] = wrong_value
    result = evaluate(snapshot, candidate)
    assert expected_code in codes(result)
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize(
    ("basis", "engine_cost", "expected_code"),
    [
        (None, 0, "PRICE_BASIS_UNKNOWN"),
        ("final_including_engine", 500, "COST_DOUBLE_COUNT"),
    ],
)
def test_aircraft_price_basis_prevents_double_counting(basis, engine_cost, expected_code):
    snapshot, candidate = sample()
    candidate["costs"]["aircraft_cost"]["price_basis"] = basis
    candidate["costs"]["engine_delta_cost"]["value"] = engine_cost
    result = evaluate(snapshot, candidate)
    assert expected_code in codes(result)
    assert result["economics"]["total_investment"] is None


def checkout_proof(candidate):
    cost = candidate["costs"]["aircraft_cost"]
    return evidence("game_aircraft_checkout", snapshot_id=candidate["snapshot_id"],
                    model_id=cost["model_id"], engine_id=cost["engine_id"],
                    amount_usd=cost["value"], price_source="data_final_price",
                    status="verified", reason=None, price_includes_engine=True)


def test_final_price_with_verified_checkout_and_explicit_zero_delta_is_accepted():
    snapshot, candidate = sample()
    candidate["costs"]["aircraft_cost"]["price_basis"] = "final_including_engine"
    candidate["costs"]["engine_delta_cost"]["value"] = 0
    candidate["costs"]["aircraft_cost"]["checkout"] = checkout_proof(candidate)
    result = evaluate(snapshot, candidate)
    assert result["status"] == "suggested"
    assert result["economics"]["total_investment"] == 10_150.0


@pytest.mark.parametrize(
    ("section", "source"),
    [
        ("snapshot", "manual"),
        ("coverage", "cache"),
        ("hub", "inferred"),
    ],
)
def test_invalid_source_in_snapshot_evidence_is_blocked(section, source):
    snapshot, candidate = sample()
    entry = {"snapshot": snapshot, "coverage": snapshot["coverage"], "hub": snapshot["hubs"][0]}[section]
    entry["source"] = source
    rebind(snapshot, candidate)
    result = evaluate(snapshot, candidate)
    assert "EVIDENCE_SOURCE_INVALID" in codes(result)


def test_same_game_id_in_two_hub_rows_is_ambiguous():
    snapshot, candidate = sample()
    snapshot["hubs"].append(deepcopy(snapshot["hubs"][0]))
    rebind(snapshot, candidate)
    assert "HUB_NOT_UNIQUE" in codes(evaluate(snapshot, candidate))


def test_rounded_component_values_are_consistent_with_total():
    snapshot, candidate = sample()
    candidate["costs"]["aircraft_cost"]["value"] = 10_000.005
    result = evaluate(snapshot, candidate)
    assert "COST_INVALID" in codes(result)
    assert result["economics"]["total_investment"] is None


def test_incoherent_hub_price_suppresses_total_and_payback():
    snapshot, candidate = sample()
    candidate["costs"]["hub_cost"]["value"] = 1000
    result = evaluate(snapshot, candidate)
    assert "HUB_COST_INCOHERENT" in codes(result)
    assert result["economics"]["total_investment"] is None
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize(
    ("now", "ttl", "block"),
    [
        ("invalid", 900, "VALIDATION_CLOCK_INVALID"),
        (NOW, None, "VALIDATION_MAX_AGE_INVALID"),
        (NOW, -1, "VALIDATION_MAX_AGE_INVALID"),
    ],
)
def test_invalid_validation_parameters_fail_closed(now, ttl, block):
    snapshot, candidate = sample()
    result = evaluate_investment(snapshot, candidate, now=now, max_age_seconds=ttl)
    assert block in codes(result)
    assert result["economics"]["payback_days"] is None


def test_sub_cent_profit_is_not_presented_as_zero():
    snapshot, candidate = sample()
    candidate["financial"]["value"] = 0.001
    result = evaluate(snapshot, candidate)
    assert "PROFIT_INVALID" in codes(result)
    assert result["economics"]["daily_net_profit_estimate"] is None


def test_placeholder_engine_id_is_blocked():
    snapshot, candidate = sample()
    candidate["aircraft"]["engine_id"] = "0"
    assert "ENGINE_ID_UNVERIFIED" in codes(evaluate(snapshot, candidate))


@pytest.mark.parametrize("expiry", [NOW, NOW - 1, None, True, "later", float("inf"), 10**400])
@pytest.mark.parametrize("field", ["financial", "aircraft_cost"])
def test_financial_explicit_expiry_blocks_even_recent_observations(expiry, field):
    snapshot, candidate = sample()
    proof = candidate["financial"] if field == "financial" else candidate["costs"][field]
    proof["expires_at"] = expiry
    result = evaluate(snapshot, candidate)
    assert "EVIDENCE_STALE" in codes(result)
    assert result["economics"]["payback_days"] is None


@pytest.mark.parametrize("changes", [
    None, {"engine_id": "other"}, {"model_id": "999"}, {"amount_usd": 10001},
    {"price_source": "displayed_cost_usd"}, {"price_includes_engine": False},
    {"status": "unknown"}, {"verified": False}, {"snapshot_id": "foreign"},
    {"profile_id": "foreign"}, {"expires_at": NOW},
])
def test_final_price_requires_current_exact_variant_checkout(changes):
    snapshot, candidate = sample()
    cost = candidate["costs"]["aircraft_cost"]
    cost["price_basis"] = "final_including_engine"
    candidate["costs"]["engine_delta_cost"]["value"] = 0
    if changes is not None:
        cost["checkout"] = {**checkout_proof(candidate), **changes}
    result = evaluate(snapshot, candidate)
    assert result["status"] == "blocked"
    assert result["economics"]["total_investment"] is None
