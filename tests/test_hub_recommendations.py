"""Conservative, reproducible next-aircraft rankings with game provenance."""
from __future__ import annotations

from copy import deepcopy

import pytest

from hub_recommendations import (MAX_AGE_SECONDS, MAX_CASH_AGE_SECONDS,
                                 rank_next_aircraft)
from route_registry import endpoint, route_key


NOW = 1_800_000_000
_UNSET = object()


def _inventory(*ids, observed_at=NOW, source="game_hub_select"):
    return {"source": source, "observed_at": observed_at, "partial_fleet": True,
            "hubs": [{"id": ident, "code": f"H{ident}", "name": f"Hub {ident}",
                      "aircraft_count": 0} for ident in ids]}


def _scenario(hub_id="123", destination_id="456", **changes):
    row = {
        "hub_id": hub_id, "model": "A320", "source": "game_research",
        "observed_at": NOW, "origin": endpoint(hub_id),
        "destination": endpoint(destination_id),
        "distance_km": 1200, "range_km": 3000,
        "runway_m": 3000, "required_runway_m": 2000,
        "demand_remaining": 300, "demand_verified": True,
        "range_verified": True, "runway_verified": True,
        "route_feasible": True, "route_available": True,
        "financial": {"source": "route_optimizer", "observed_at": NOW,
                      "profit_per_day": 2500},
        "costs": {"source": "game_market", "observed_at": NOW,
                  "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0},
    }
    row.update(changes)
    return row


def _audited_fleet(*routes, now=NOW, complete=True, historical=None):
    rows = [{"aircraft_id": str(index), "game_route_id": index,
             "observed_route_id": index, "source": "game", "route_data_stale": False,
             "last_seen": now - 2, "origin": origin, "destination": destination}
            for index, (origin, destination) in enumerate(routes, 1)]
    return {"relations": historical or [], "partial": not complete,
            "current_roster_verified": True, "current_roster_observed_at": now - 3,
            "current_roster_total": len(rows), "current_relations": rows,
            "current_fleet_coverage_verified": complete,
            "fleet_coverage": {"source": "game_roster_and_route_audit",
                               "observed_at": now - 1, "roster_observed_at": now - 3,
                               "total": len(rows), "routes": len(rows), "parked": 0, "pending": 0}}


def _rank(hubs=None, scenarios=_UNSET, **kwargs):
    return rank_next_aircraft(
        hubs if hubs is not None else _inventory("123"),
        [_scenario()] if scenarios is _UNSET else scenarios,
        route_report=kwargs.pop("route_report", _audited_fleet()),
        cash=20000, cash_observed_at=NOW, reserve=2000,
        now=NOW, **kwargs,
    )


def _variant_catalog(*, range_km=3000, available=True, observed_at=NOW, verified=True):
    source = "game_aircraft_order_detail"
    return {"source": source, "models": {"11": {
        "source": source, "model_id": "11", "model": "A320",
        "observed_at": observed_at, "engine_prices_verified": False,
        "model_detail_identity_verified": verified,
        "observed_model_id": "11" if verified else None,
        "selected_engine_id": "1" if available else None,
        "variants": [{"engine_id": "1", "label": "CFM", "available": available,
                      "selected": available}],
        "variant_details": {"1": {"observed_at": observed_at, "metrics": {
            "range_km": range_km, "required_runway_ft": 6500}}} if available else {},
    }}}


def test_rank_requires_native_partition_for_unrouted_fleet():
    report = _audited_fleet()
    report["current_roster_total"] = 1
    report["current_relations"] = [{"aircraft_id": "1", "game_route_id": 0}]
    report["fleet_coverage"].update(total=1, pending=1)
    incomplete = _rank(route_report=report)
    assert not incomplete["recommendations"]
    assert "ocupacao_da_frota_a_confirmar" in incomplete["candidates"][0]["pending"]

    report["fleet_coverage"].update(native_identity_status="matched", native_observation_id="a" * 32)
    reconciled = _rank(route_report=report)
    assert len(reconciled["recommendations"]) == 1


def _variant_scenario(**changes):
    row = _scenario(model_id="11", engine_id="1")
    row["financial"]["engine_id"] = "1"
    row["costs"].update(engine_id="1", aircraft_price_includes_engine=True)
    row["route_detail"] = {"source": "game_route_detail", "origin_id": "123",
                           "destination_id": "456", "observed_at": NOW,
                           "origin_runway_ft": 7000, "destination_runway_ft": 7000}
    row.update(changes)
    return row


def test_rank_recomputes_physical_shortfall_and_expires_independent_route_detail():
    scenario = _variant_scenario()
    scenario["route_detail"]["destination_runway_ft"] = 6499
    scenario["destination_runway_ft"] = 7000
    scenario["physical_feasibility"] = {"status": "direct_dimensions_sufficient"}
    result = _rank(scenarios=[scenario], engine_catalog=_variant_catalog())
    row = result["candidates"][0]
    assert not result["recommendations"]
    assert row["status"] == "dados_a_confirmar"
    assert "pista_observada_insuficiente" in row["pending"]
    assert row["physical_feasibility"]["checks"]["destination_runway"] == "short"
    assert row["physical_feasibility"]["purchase_eligible"] is False
    scenario["route_detail"]["observed_at"] = NOW - 901
    result = _rank(scenarios=[scenario], engine_catalog=_variant_catalog())
    row = result["candidates"][0]
    assert row["physical_feasibility"]["checks"]["destination_runway"] == "unknown"
    assert "pista_observada_insuficiente" not in row["pending"]


def test_rank_uses_current_variant_range_and_checks_verified_stopover():
    scenario = _variant_scenario(distance_km=2200)
    catalog = _variant_catalog(range_km=1500)
    row = _rank(scenarios=[scenario], engine_catalog=catalog)["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "escala_e_trechos_a_confirmar" in row["pending"]
    scenario["stopover"] = {"verified": True, "airport_id": "999",
                            "legs_km": [1100, 1200], "runway_m": 2000,
                            "runway_verified": True}
    row = _rank(scenarios=[scenario], engine_catalog=catalog)["candidates"][0]
    assert row["status"] == "viavel"
    assert row["physical_feasibility"]["checks"]["range"] == "short"
    assert row["physical_feasibility"]["stopover_research_required"] is False
    scenario["stopover"]["legs_km"] = [800, 1600]
    row = _rank(scenarios=[scenario], engine_catalog=catalog)["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "escala_e_trechos_a_confirmar" in row["pending"]


@pytest.mark.parametrize("catalog,model_id", [(_variant_catalog(verified=False), "11"),
    (_variant_catalog(observed_at=NOW - MAX_AGE_SECONDS - 1), "11"),
    (_variant_catalog(range_km=500), "12")])
def test_rank_does_not_apply_unrelated_or_stale_engine_dimensions(catalog, model_id):
    scenario = _variant_scenario(model_id=model_id)
    row = _rank(scenarios=[scenario], engine_catalog=catalog)["candidates"][0]
    assert row["physical_feasibility"]["status"] == "unknown"
    assert row["status"] == "viavel"


def test_rank_blocks_current_unavailable_engine_and_derived_count_disagreement():
    scenario = _variant_scenario()
    row = _rank(scenarios=[scenario], engine_catalog=_variant_catalog(available=False))["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "motor_indisponivel" in row["pending"]
    scenario.update(source="derived_research_queue", research_evidence={
        "route": {"source": "game_route_search", "observed_at": NOW - 15}})
    scenario["route_detail"]["observed_aircraft_on_route"] = 1
    row = _rank(scenarios=[scenario], engine_catalog=_variant_catalog())["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "contagem_rota_divergente" in row["pending"]
    assert row["physical_feasibility"]["status"] == "direct_dimensions_sufficient"


def test_ranks_explicit_financial_scenario_and_preserves_empty_hubs():
    inventory = _inventory("123", "789")
    scenario = _scenario()
    original = deepcopy((inventory, scenario))
    result = _rank(hubs=inventory, scenarios=[scenario])
    assert len(result["recommendations"]) == 1
    row = result["recommendations"][0]
    assert row["hub_id"] == "123"
    assert row["investment"] == 11000
    assert row["payback_days"] == 4.4
    assert row["status"] == "viavel"
    assert row["financial_source"] == "route_optimizer"
    assert row["costs_source"] == "game_market"
    assert [h["id"] for h in result["hubs"]] == ["123", "789"]
    assert result["hubs"][1]["recommendation"] is None
    assert result["partial_fleet"] and result["read_only"]
    assert (inventory, scenario) == original


def test_ranks_best_viable_candidate_per_hub_in_deterministic_order():
    hubs = _inventory("123", "789")
    scenarios = [
        _scenario("123", "456"),
        _scenario("123", "333", financial={"source": "route_optimizer",
                                             "observed_at": NOW, "profit_per_day": 3200}),
        _scenario("789", "456", financial={"source": "route_optimizer",
                                             "observed_at": NOW, "profit_per_day": 3200}),
    ]
    first = _rank(hubs=hubs, scenarios=scenarios)
    reversed_result = _rank(hubs=hubs, scenarios=list(reversed(scenarios)))
    assert first["recommendations"] == reversed_result["recommendations"]
    assert [(row["hub_id"], row["destination"]["id"]) for row in first["recommendations"]] == [
        ("123", "333"), ("789", "456")]
    assert len(first["candidates"]) == 3
    assert first["hubs"][0]["scenario_count"] == 2


def test_variantes_de_motor_sao_oportunidades_independentes():
    motor_a = _scenario(
        engine_id="engine-1", engine_label="Trent 970",
        financial={"source": "route_optimizer", "observed_at": NOW,
                   "profit_per_day": 2000, "engine_id": "engine-1"},
        costs={"source": "game_market", "observed_at": NOW,
               "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0,
               "engine_id": "engine-1", "aircraft_price_includes_engine": True},
    )
    motor_b = _scenario(
        engine_id="engine-2", engine_label="Trent 972",
        financial={"source": "route_optimizer", "observed_at": NOW,
                   "profit_per_day": 2800, "engine_id": "engine-2"},
        costs={"source": "game_market", "observed_at": NOW,
               "aircraft_price": 12000, "route_fee": 1000, "hangar_price": 0,
               "engine_id": "engine-2", "aircraft_price_includes_engine": True},
    )
    ranked = _rank(scenarios=[motor_a, motor_b])
    assert len(ranked["candidates"]) == 2
    assert all(item["status"] == "viavel" for item in ranked["candidates"])
    assert ranked["recommendations"][0]["engine_id"] == "engine-2"
    assert ranked == _rank(scenarios=[motor_b, motor_a])


def test_variacao_de_motor_sem_preco_final_e_lucro_vinculados_fica_pendente():
    unknown_price = _scenario(engine_id="engine-2", engine_label="Trent 972")
    wrong_engine = _scenario(
        engine_id="engine-1", engine_label="Trent 970",
        costs={"source": "game_market", "observed_at": NOW,
               "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0,
               "engine_id": "engine-2", "aircraft_price_includes_engine": True},
        financial={"source": "route_optimizer", "observed_at": NOW,
                   "profit_per_day": 2500, "engine_id": "engine-2"},
    )
    report = _rank(scenarios=[unknown_price, wrong_engine])
    assert report["recommendations"] == []
    for row in report["candidates"]:
        assert row["status"] == "dados_a_confirmar"
        assert "preco_motor_a_confirmar" in row["pending"]
        assert "lucro_motor_a_confirmar" in row["pending"]


def test_newer_observation_supersedes_older_profitable_route_even_if_reversed():
    older = _scenario(
        observed_at=NOW - 120,
        origin=endpoint("456"),
        destination=endpoint("123"),
        model="a320",
        financial={"source": "route_optimizer", "observed_at": NOW - 120,
                   "profit_per_day": 9000},
    )
    newer = _scenario(
        financial={"source": "route_optimizer", "observed_at": NOW,
                   "profit_per_day": 2000},
    )
    first = _rank(scenarios=[older, newer])
    reversed_result = _rank(scenarios=[newer, older])

    assert first == reversed_result
    assert len(first["recommendations"]) == 1
    assert first["recommendations"][0]["profit_per_day"] == 2000
    superseded = next(row for row in first["candidates"]
                      if row["profit_per_day"] == 9000)
    assert superseded["status"] == "dados_a_confirmar"
    assert "pesquisa_substituida" in superseded["pending"]


def test_conflicting_observations_at_same_time_do_not_recommend_route():
    first = _scenario(financial={"source": "route_optimizer", "observed_at": NOW,
                                 "profit_per_day": 2000})
    conflicting = _scenario(
        model="a320",
        financial={"source": "route_optimizer", "observed_at": NOW,
                   "profit_per_day": 9000},
    )
    report = _rank(scenarios=[first, conflicting])
    reversed_report = _rank(scenarios=[conflicting, first])

    assert report == reversed_report
    assert report["recommendations"] == []
    assert len(report["candidates"]) == 2
    assert all(row["status"] == "dados_a_confirmar" for row in report["candidates"])
    assert all("pesquisas_conflitantes" in row["pending"] for row in report["candidates"])


def test_newest_incomplete_research_blocks_fallback_to_outdated_profitable_data():
    older = _scenario(
        observed_at=NOW - 60,
        financial={"source": "route_optimizer", "observed_at": NOW - 60,
                   "profit_per_day": 9000},
    )
    incomplete = _scenario(demand_verified=False)
    result = _rank(scenarios=[older, incomplete])

    assert result["recommendations"] == []
    assert all(row["status"] == "dados_a_confirmar" for row in result["candidates"])
    assert "pesquisa_substituida" in next(
        row for row in result["candidates"] if row["profit_per_day"] == 9000
    )["pending"]
    assert "demanda_a_confirmar" in next(
        row for row in result["candidates"] if row["profit_per_day"] == 2500
    )["pending"]


def test_exact_repeated_observation_does_not_create_false_conflict():
    scenario = _scenario()
    result = _rank(scenarios=[scenario, deepcopy(scenario)])

    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["status"] == "viavel"
    assert all(not row["pending"] for row in result["candidates"])


def test_equivalent_reverse_route_and_model_case_do_not_create_false_conflict():
    forward = _scenario()
    reversed_route = _scenario(
        model="a320", origin=endpoint("456"), destination=endpoint("123"),
    )
    result = _rank(scenarios=[forward, reversed_route])

    assert len(result["recommendations"]) == 1
    assert all(row["status"] == "viavel" for row in result["candidates"])


def test_tied_conflicts_have_stable_order_with_reversed_endpoints_and_model_case():
    forward = _scenario()
    reversed_route = _scenario(
        model="a320", origin=endpoint("456"), destination=endpoint("123"),
        demand_remaining=200,
    )
    first = _rank(scenarios=[forward, reversed_route])
    second = _rank(scenarios=[reversed_route, forward])

    assert first == second
    assert first["recommendations"] == []
    assert all("pesquisas_conflitantes" in row["pending"]
               for row in first["candidates"])


@pytest.mark.parametrize("input_scenarios", [None, [], [None, "bad", 5]])
def test_empty_or_malformed_scenarios_keep_owned_hubs_pending(input_scenarios):
    result = _rank(hubs=_inventory("123", "789"), scenarios=input_scenarios)
    assert result["recommendations"] == []
    assert result["candidates"] == []
    assert len(result["hubs"]) == 2
    assert all(h["status"] == "dados_a_confirmar" for h in result["hubs"])


def test_unconfirmed_and_old_inventory_cannot_recommend():
    for hubs in (_inventory("123", source="manual"),
                 _inventory("123", observed_at=NOW - MAX_AGE_SECONDS - 1),
                 _inventory("123", observed_at=NOW + 1),
                 _inventory("123", observed_at=True)):
        result = _rank(hubs=hubs)
        assert not result["recommendations"]
        assert result["candidates"][0]["status"] == "dados_a_confirmar"
        assert "inventario_hubs_desatualizado" in result["candidates"][0]["pending"]


def test_requires_recent_verified_money_and_nonnegative_reserve():
    for cash, stamp, reserve in ((None, NOW, 0),
                                 (20000, None, 0),
                                 (20000, NOW - MAX_CASH_AGE_SECONDS - 1, 0),
                                 (20000, NOW + 1, 0),
                                 (True, NOW, 0),
                                 (float("nan"), NOW, 0),
                                 (20000, NOW, -1)):
        result = rank_next_aircraft(
            _inventory("123"), [_scenario()], route_report=_audited_fleet(),
            cash=cash, cash_observed_at=stamp, reserve=reserve, now=NOW)
        assert result["recommendations"] == []
        assert result["candidates"][0]["status"] == "dados_a_confirmar"
        assert "saldo_ou_reserva_a_confirmar" in result["candidates"][0]["pending"]


def test_cash_reserve_and_profit_classifications():
    scenario = _scenario()
    insufficient = rank_next_aircraft(
        _inventory("123"), [scenario], route_report=_audited_fleet(),
        cash=12000, cash_observed_at=NOW, reserve=2000, now=NOW)
    assert insufficient["available_cash"] == 10000
    assert insufficient["candidates"][0]["status"] == "saldo_insuficiente"
    for value in (-100.0, 0):
        scenario["financial"]["profit_per_day"] = value
        report = _rank(scenarios=[scenario])
        assert report["recommendations"] == []
        assert report["candidates"][0]["status"] == "sem_lucro"
        assert report["candidates"][0]["payback_days"] is None


def test_occupied_route_is_rejected_even_on_partial_page():
    candidate = _scenario()
    result = rank_next_aircraft(
        _inventory("123"), [candidate],
        route_report=_audited_fleet((endpoint("456"), endpoint("123")), complete=False),
        cash=20000, cash_observed_at=NOW, now=NOW)
    assert result["candidates"][0]["status"] == "rota_ocupada"
    assert result["candidates"][0]["fleet_occupancy"]["count_complete"] is False
    assert result["recommendations"] == []


def test_verified_current_fleet_supersedes_historical_route_occupancy():
    old_route = {"origin": endpoint("456"), "destination": endpoint("123")}
    result = rank_next_aircraft(
        _inventory("123"), [_scenario()],
        route_report=_audited_fleet(historical=[old_route]),
        cash=20000, cash_observed_at=NOW, now=NOW)
    assert result["candidates"][0]["status"] == "viavel"
    assert result["candidates"][0]["fleet_occupancy"]["own_aircraft_count"] == 0


@pytest.mark.parametrize("report", [
    {"relations": []},
    {"relations": [], "current_relations": [], "current_fleet_coverage_verified": True},
    _audited_fleet(complete=False),
    _audited_fleet(now=NOW - 901),
    {**_audited_fleet(), "current_roster_total": 1},
])
def test_unknown_or_stale_fleet_coverage_never_recommends(report):
    result = _rank(route_report=report)
    assert not result["recommendations"]
    assert "ocupacao_da_frota_a_confirmar" in result["candidates"][0]["pending"]
    assert "fleet_occupancy" not in result["candidates"][0]


def test_ranker_resolves_inverse_route_aliases_and_blocks_unresolved_candidate():
    report = _audited_fleet(({"code": "SLSA"}, {"id": "2926", "code": "XAP"}))
    rows = _rank(hubs=_inventory("2926"), scenarios=[
        _scenario("2926", "3139"),
        _scenario("2926", destination={"code": "ZZZ"}),
        _scenario("2926", destination={"id": "999999999999", "code": "SLSA"}),
    ], route_report=report)["candidates"]
    assert rows[0]["status"] == "rota_ocupada"
    assert rows[0]["fleet_occupancy"]["own_aircraft_count"] == 1
    assert all("ocupacao_da_frota_a_confirmar" in row["pending"] for row in rows[1:])


def test_game_route_count_conflicting_with_complete_fleet_blocks_recommendation():
    row = _rank(scenarios=[_scenario(observed_aircraft_on_route=1)])["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "contagem_rota_divergente" in row["pending"]
    assert row["fleet_occupancy"]["game_count_disagrees"] is True


def test_route_occupancy_needs_snapshot_and_positive_game_availability():
    without_routes = rank_next_aircraft(
        _inventory("123"), [_scenario()], cash=20000,
        cash_observed_at=NOW, now=NOW)
    assert without_routes["candidates"][0]["status"] == "dados_a_confirmar"
    assert "ocupacao_da_frota_a_confirmar" in without_routes["candidates"][0]["pending"]
    without_availability = _rank(scenarios=[_scenario(route_available=None)])
    assert not without_availability["recommendations"]
    assert "disponibilidade_da_rota_a_confirmar" in without_availability["candidates"][0]["pending"]


@pytest.mark.parametrize("change", [
    {"observed_at": NOW - MAX_AGE_SECONDS - 1},
    {"source": "manual"},
    {"demand_verified": False},
    {"range_verified": False},
    {"runway_verified": False},
    {"route_feasible": None},
    {"route_feasible": "true"},
    {"route_available": 1},
    {"route_available": "true"},
    {"model": ""},
    {"financial": {"source": "unknown", "observed_at": NOW, "profit_per_day": 2500}},
    {"financial": {"source": "route_optimizer", "observed_at": NOW + 1, "profit_per_day": 2500}},
    {"costs": {"source": "manual", "observed_at": NOW,
               "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0}},
    {"costs": {"source": "game_market", "observed_at": NOW,
               "aircraft_price": None, "route_fee": 1000, "hangar_price": 0}},
    {"costs": {"source": "game_market", "observed_at": NOW,
               "aircraft_price": 10000, "route_fee": False, "hangar_price": 0}},
    {"costs": {"source": "game_market", "observed_at": NOW,
               "aircraft_price": 1e308, "route_fee": 1e308, "hangar_price": 0}},
])
def test_missing_or_unverified_evidence_never_becomes_viable(change):
    row = _rank(scenarios=[_scenario(**change)])["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert row["pending"]


@pytest.mark.parametrize("change", [
    {"demand_remaining": 0},
    {"distance_km": 5000},
    {"runway_m": 1500},
    {"stopover": {"verified": True, "legs_km": [1000, 4000],
                  "airport_id": "999", "runway_m": 2500, "runway_verified": True}},
])
def test_verified_physical_limitations_make_route_infeasible(change):
    row = _rank(scenarios=[_scenario(**change)])["candidates"][0]
    assert row["status"] == "rota_inviavel"


def test_verified_stopover_can_make_long_distance_route_feasible():
    scenario = _scenario(distance_km=4200,
                         stopover={"verified": True, "airport_id": "999",
                                   "legs_km": [2100, 2200],
                                   "runway_m": 2600, "runway_verified": True})
    assert _rank(scenarios=[scenario])["recommendations"][0]["status"] == "viavel"
    scenario["stopover"]["verified"] = False
    pending = _rank(scenarios=[scenario])["candidates"][0]
    assert pending["status"] == "dados_a_confirmar"
    assert "escala_a_confirmar" in pending["pending"]


def test_stopover_without_intermediate_airport_is_unconfirmed():
    scenario = _scenario(distance_km=4200,
                         stopover={"verified": True, "legs_km": [2100, 2200],
                                   "runway_m": 2600, "runway_verified": True})
    result = _rank(scenarios=[scenario])
    assert result["recommendations"] == []
    assert "escala_a_confirmar" in result["candidates"][0]["pending"]


def test_explicit_route_rejection_is_reported_instead_of_recommended():
    assert _rank(scenarios=[_scenario(route_available=False)])["candidates"][0]["status"] == "rota_indisponivel"
    assert _rank(scenarios=[_scenario(route_feasible=False)])["candidates"][0]["status"] == "rota_inviavel"


def test_generator_input_and_integer_airport_ids_work():
    scenario = _scenario(origin={"id": 123}, destination={"id": 456})
    result = _rank(scenarios=(item for item in [scenario]))
    assert result["recommendations"][0]["route_key"] == route_key(endpoint("123"), endpoint("456"))


def test_unknown_hubs_and_non_base_routes_are_excluded_or_pending():
    result = _rank(scenarios=[_scenario("999"),
                              _scenario("123", origin=endpoint("987"))])
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["status"] == "dados_a_confirmar"
    assert "rota_da_base_a_confirmar" in result["candidates"][0]["pending"]


def test_model_filter_for_comparable_hub_rankings():
    result = _rank(scenarios=[_scenario(), _scenario("123", "789", model="B777")],
                   model="a320")
    assert [row["model"] for row in result["candidates"]] == ["A320"]
    assert len(result["recommendations"]) == 1


def test_only_explicit_current_observations_count_even_when_stale_prices_are_present():
    scenario = _scenario(costs={"source": "game_market",
                                "observed_at": NOW - MAX_AGE_SECONDS - 1,
                                "aircraft_price": 10000, "route_fee": 1000,
                                "hangar_price": 0})
    row = _rank(scenarios=[scenario])["candidates"][0]
    assert row["investment"] == 11000
    assert row["status"] == "dados_a_confirmar"
    assert row["payback_days"] is None


def test_historical_route_key_does_not_certify_current_occupancy_or_mutate_registry():
    candidate = _scenario()
    known = {"route_key": route_key(endpoint("123"), endpoint("456"))}
    snapshot = {"relations": [known], "partial": True}
    original = deepcopy(snapshot)
    result = rank_next_aircraft(_inventory("123"), [candidate],
                                route_report=snapshot, cash=20000,
                                cash_observed_at=NOW, now=NOW)
    assert result["candidates"][0]["status"] == "dados_a_confirmar"
    assert "ocupacao_da_frota_a_confirmar" in result["candidates"][0]["pending"]
    assert snapshot == original
