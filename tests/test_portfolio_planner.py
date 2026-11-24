"""Conservative global comparison of researched hub/route/engine scenarios."""
from __future__ import annotations

from copy import deepcopy

import pytest

from expansion_economics import (
    _SOURCES as A3_PROVENANCE_SOURCES,
    _SUBJECTS as A3_PROVENANCE_SUBJECTS,
)
from portfolio_planner import _audited_a3_cash, compare_audited_portfolio, compare_portfolio


NOW = 1_800_000_000


def candidate(hub="123", destination="456", engine="1", *, profit=100, cost=1000, **changes):
    row = {
        "hub_id": hub, "hub_code": f"H{hub}", "model": "A320",
        "engine_id": engine, "route_key": f"ids:{hub}|{destination}",
        "origin": {"id": hub}, "destination": {"id": destination},
        "investment": cost, "profit_per_day": profit,
        "status": "viavel", "pending": [],
    }
    row.update(changes)
    return row


def report(*rows, partial_fleet=False, cash=30000):
    return {"candidates": list(rows), "partial_fleet": partial_fleet,
            "available_cash": cash}


def compare_complete(data, **kwargs):
    return compare_portfolio(data, research_coverage_verified=True,
                             commitments_verified=True, committed_cash=0, **kwargs)


def evidenced_candidate(*, risk=0.5, confidence=0.5, diversification=0.5,
                        **changes):
    row = candidate(**changes)
    row["observed_at"] = NOW
    row["financial_source"] = "route_optimizer"
    route_identity = {key: row[key] for key in ("hub_id", "route_key", "model", "engine_id")}
    row["ranking_evidence"] = {
        "risk": {"value": risk, "source": "route_optimizer",
                 "observed_at": NOW, "verified": True, **route_identity},
        "confidence": {"value": confidence, "source": "route_optimizer",
                       "observed_at": NOW, "verified": True, **route_identity},
        "diversification": {"value": diversification, "source": "game_hub_select",
                            "observed_at": NOW, "verified": True, "hub_id": row["hub_id"]},
    }
    return row


def evidenced_report(*rows):
    return {**report(*rows), "source": "game_hub_select",
            "inventory_observed_at": NOW}


def test_best_global_balances_profit_and_return_on_capital_across_hubs_and_engines():
    efficient = candidate("123", "456", "1", profit=100, cost=1000)
    absolute = candidate("789", "999", "3", profit=200, cost=10000)
    alternate_engine = candidate("123", "456", "2", profit=120, cost=5000)
    data = report(absolute, efficient, alternate_engine)
    original = deepcopy(data)

    result = compare_complete(data)
    reversed_result = compare_complete(report(alternate_engine, efficient, absolute))

    assert result["status"] == "comparacao_concluida"
    assert result["best"]["hub_id"] == "123"
    assert result["best"]["engine_id"] == "1"
    assert result["best"]["score"] > result["alternatives"][1]["score"]
    assert result["criteria"]["profit_weight"] == 0.6
    assert result["criteria"]["capital_efficiency_weight"] == 0.4
    assert result["criteria"]["risk_weight"] == 0.0
    assert result["criteria"]["confidence_weight"] == 0.0
    assert result["criteria"]["diversification_weight"] == 0.0
    assert set(result["best"]["score_components"]) == {"profit", "capital_efficiency"}
    assert result == reversed_result
    assert data == original
    assert result["read_only"] and result["execution_available"] is False


def test_incomplete_fleet_research_and_commitments_never_yield_conclusive_no_opportunity():
    result = compare_portfolio(report(partial_fleet=True))
    assert result["best"] is None
    assert result["status"] == "inconclusivo"
    assert set(result["blocking_reasons"]) == {
        "cobertura_frota_a_confirmar", "cobertura_pesquisa_a_confirmar",
        "pedidos_pendentes_a_conciliar",
    }
    provisional = compare_portfolio(report(candidate(), partial_fleet=True))
    assert provisional["best"] is not None
    assert provisional["status"] == "inconclusivo"
    assert provisional["budget_after_commitments"] is None


def test_commitments_reserve_cash_and_single_purchase_limit():
    data = report(candidate(cost=7000), candidate("789", "999", "2", cost=2000))
    result = compare_portfolio(data, research_coverage_verified=True,
                               commitments_verified=True, committed_cash=25000,
                               max_single_investment=3000)
    assert result["budget_after_commitments"] == 5000
    assert result["eligible_count"] == 1
    assert result["best"]["hub_id"] == "789"
    assert result["excluded"]["limite_por_aquisicao"] == 1

    insufficient = compare_portfolio(data, research_coverage_verified=True,
                                     commitments_verified=True, committed_cash=29500)
    assert insufficient["eligible_count"] == 0
    assert insufficient["excluded"]["caixa_apos_compromissos_insuficiente"] == 2


def test_unknown_commitments_cannot_be_substituted_with_zero():
    result = compare_portfolio(report(candidate()),
                               research_coverage_verified=True,
                               commitments_verified=True)
    assert result["best"] is not None
    assert result["budget_after_commitments"] is None
    assert "compromissos_invalidos" in result["blocking_reasons"]
    assert result["status"] == "inconclusivo"


def test_known_local_reservations_restrict_budget_without_proving_global_commitments():
    data = report(candidate(cost=7000), candidate("789", "999", "2", cost=2000), cash=10000)
    result = compare_portfolio(data, known_local_commitments=8500)
    assert result["budget_after_commitments"] is None
    assert result["known_local_commitments"] == 8500
    assert result["budget_upper_bound"] == 1500
    assert result["best"] is None
    assert result["excluded"]["caixa_apos_reservas_locais_insuficiente"] == 2
    assert result["status"] == "inconclusivo"

    invalid = compare_portfolio(data, known_local_commitments="8500")
    assert invalid["budget_upper_bound"] is None
    assert "reservas_locais_invalidas" in invalid["blocking_reasons"]


def test_local_period_limits_filter_global_candidates_independently_of_cash():
    data = report(candidate(cost=7000), candidate("789", "999", "2", cost=2000), cash=30000)
    usage = {"source": "local_investment_journal", "since": NOW - 86400,
             "estimated_exposure": 8000, "acquisition_count": 2}
    args = {"known_local_commitments": 1000, "local_period_usage": usage,
            "max_daily_spend": 10000, "max_acquisitions_per_day": 3}
    result = compare_portfolio(data, **args)
    assert result["budget_upper_bound"] == 29000
    assert result["local_period_limits"]["remaining_spend"] == 2000
    assert result["local_period_limits"]["remaining_acquisitions"] == 1
    assert result["best"]["hub_id"] == "789"
    assert result["excluded"]["limite_de_24h"] == 1
    exhausted = compare_portfolio(data, **{**args, "max_acquisitions_per_day": 2})
    assert exhausted["best"] is None
    assert exhausted["excluded"]["limite_de_aquisicoes_em_24h"] == 1
    unknown = compare_portfolio(data, **{**args, "local_period_usage": None})
    assert "uso_periodo_a_confirmar" in unknown["blocking_reasons"]
    assert unknown["local_period_limits"]["remaining_spend"] is None
    invalid = compare_portfolio(data, **{**args, "local_period_usage": {**usage, "estimated_exposure": 999}})
    assert "uso_periodo_a_confirmar" in invalid["blocking_reasons"]


def test_unverified_engine_route_ids_and_invalid_financials_are_excluded():
    data = report(candidate(engine=None),
                  candidate("789", "999", "2", origin={"id": "unknown"}),
                  candidate("234", "567", "3", profit=float("nan")),
                  candidate("555", "666", "4", status="dados_a_confirmar"),
                  candidate("777", "888", "5", cost=0))
    result = compare_complete(data)
    assert result["best"] is None
    assert result["eligible_count"] == 0
    assert result["excluded"]["identidade_ou_custos_a_confirmar"] == 4
    assert result["excluded"]["cenario_nao_validado"] == 1
    assert result["status"] == "inconclusivo"
    assert "cenarios_proprios_pendentes" in result["blocking_reasons"]


def test_pending_owned_scenario_cannot_certify_no_opportunity_for_expansion():
    pending = candidate(status="dados_a_confirmar", pending=["demanda_a_confirmar"])
    result = compare_complete(report(pending))

    assert result["best"] is None
    assert result["eligible_count"] == 0
    assert result["status"] == "inconclusivo"
    assert "cenarios_proprios_pendentes" in result["blocking_reasons"]

    # Missing pending evidence is itself inconclusive, including a supposedly
    # viable row without the producer's explicit empty list.
    missing = candidate()
    del missing["pending"]
    result = compare_complete(report(missing))
    assert result["best"] is None
    assert result["status"] == "inconclusivo"


@pytest.mark.parametrize("status", [
    "saldo_insuficiente", "sem_lucro", "rota_inviavel",
    "rota_ocupada", "rota_indisponivel",
])
def test_conclusively_rejected_owned_routes_allow_no_viable_opportunity(status):
    result = compare_complete(report(candidate(status=status)))

    assert result["status"] == "comparacao_concluida"
    assert result["best"] is None
    assert result["eligible_count"] == 0
    assert result["excluded"]["cenario_nao_validado"] == 1


def test_contradictory_owned_research_never_claims_exhaustion():
    first = candidate(profit=120)
    conflict = candidate(profit=500)
    result = compare_complete(report(first, conflict))

    assert result["status"] == "inconclusivo"
    assert result["best"] is None
    assert "pesquisas_conflitantes" in result["blocking_reasons"]


def test_filters_minimum_profit_payback_and_deduplicates_exact_repeated_scenarios():
    efficient = candidate(profit=120, cost=1200)
    expensive = candidate("789", "999", "2", profit=300, cost=20000)
    result = compare_complete(report(efficient, deepcopy(efficient), expensive),
                              min_daily_profit=100, max_payback_days=20)
    assert result["evaluated_count"] == 3
    assert result["eligible_count"] == 1
    assert result["excluded"]["retorno_acima_do_limite"] == 1
    assert result["best"]["payback_days"] == 10


def test_contradictory_observations_do_not_depend_on_input_order():
    first = candidate(profit=120)
    conflict = candidate(profit=500)
    one = compare_complete(report(first, conflict))
    two = compare_complete(report(conflict, first))
    assert one == two
    assert one["best"] is None
    assert one["excluded"]["pesquisas_conflitantes"] == 2


def test_invalid_weights_fail_closed():
    result = compare_complete(report(candidate()), profit_weight=float("nan"))
    assert result["best"] is None
    assert result["status"] == "inconclusivo"
    assert "criterios_planejamento_invalidos" in result["blocking_reasons"]


def test_invalid_external_policy_keeps_read_only_comparison_inconclusive():
    result = compare_complete(report(candidate()), policy_valid=False)
    assert result["status"] == "inconclusivo"
    assert "politica_invalida" in result["blocking_reasons"]
    assert result["execution_available"] is False


def test_extreme_money_and_weights_cannot_overflow_portfolio_ranking():
    result = compare_complete(report(candidate(cost=1e300, profit=1e-300)),
                              profit_weight=1e308, efficiency_weight=1e308)
    assert result["best"] is None
    assert "criterios_planejamento_invalidos" in result["blocking_reasons"]
    assert result["excluded"]["economia_fora_do_intervalo"] == 1


def test_configurable_profit_and_efficiency_weights_change_the_global_winner():
    absolute = candidate("789", "999", profit=250, cost=10000)
    efficient = candidate("123", "456", profit=100, cost=1000)
    data = report(absolute, efficient)
    original = deepcopy(data)

    default = compare_complete(data)
    profit_only = compare_complete(data, profit_weight=1, efficiency_weight=0)
    efficient_only = compare_complete(data, profit_weight=0, efficiency_weight=1)
    roi_only = compare_complete(data, profit_weight=0, efficiency_weight=0, return_weight=1)
    scaled = compare_complete(data, profit_weight=6, efficiency_weight=4)

    assert default["best"]["hub_id"] == "789"
    assert profit_only["best"]["hub_id"] == "789"
    assert efficient_only["best"]["hub_id"] == "123"
    assert efficient_only["best"]["score_components"] == {"capital_efficiency": 1.0}
    assert roi_only["best"]["hub_id"] == efficient_only["best"]["hub_id"]
    assert roi_only["best"]["score_components"] == {"return": 1.0}
    assert roi_only["criteria"]["return_weight"] == 1
    assert scaled["alternatives"] == default["alternatives"]
    assert data == original


@pytest.mark.parametrize(("dimension", "weight"), [
    ("risk", "risk_weight"),
    ("confidence", "confidence_weight"),
    ("diversification", "diversification_weight"),
])
def test_optional_evidence_backed_weights_are_independent_and_reproducible(dimension, weight):
    absolute = evidenced_candidate(hub="789", destination="999", profit=250, cost=10000,
                                   risk=0.9, confidence=0.1, diversification=0.1)
    diversified = evidenced_candidate(hub="123", destination="456", profit=100, cost=1000,
                                      risk=0.1, confidence=0.9, diversification=0.9)
    data = evidenced_report(absolute, diversified)
    original = deepcopy(data)
    options = {"profit_weight": 0, "efficiency_weight": 0, weight: 1}

    ranked = compare_complete(data, **options)
    reversed_ranked = compare_complete(evidenced_report(diversified, absolute), **options)

    assert ranked == reversed_ranked
    assert ranked["status"] == "comparacao_concluida"
    assert ranked["best"]["hub_id"] == "123"
    assert ranked["best"][f"{dimension}_index"] == 0.9
    assert ranked["best"]["score_components"] == {dimension: 0.9}
    assert ranked["criteria"][weight] == 1
    assert data == original


def test_five_way_ranking_exposes_comparable_score_components():
    winner = evidenced_candidate(hub="123", destination="456", profit=100,
                                 risk=0.1, confidence=0.9, diversification=0.9)
    other = evidenced_candidate(hub="789", destination="999", profit=250,
                                cost=10000, risk=0.9, confidence=0.1,
                                diversification=0.1)
    options = {"profit_weight": 0.1, "efficiency_weight": 0.1,
               "risk_weight": 0.35, "confidence_weight": 0.3,
               "diversification_weight": 0.15}
    ranked = compare_complete(evidenced_report(other, winner), **options)

    assert ranked["best"]["hub_id"] == "123"
    assert len(ranked["alternatives"]) == 2
    assert ranked["best"]["score"] > ranked["alternatives"][1]["score"]
    assert set(ranked["best"]["score_components"]) == {
        "profit", "capital_efficiency", "risk", "confidence", "diversification",
    }
    assert sum(ranked["best"]["score_components"].values()) == pytest.approx(
        ranked["best"]["score"], abs=3e-6)


def test_missing_optional_evidence_makes_ranking_provisional_without_ignoring_gaps():
    verified = evidenced_candidate(hub="123", destination="456", risk=0.1)
    missing = candidate("789", "999", profit=250, cost=10000)
    ranked = compare_complete(evidenced_report(missing, verified), risk_weight=1)

    assert ranked["status"] == "inconclusivo"
    assert ranked["best"]["hub_id"] == "123"
    assert ranked["eligible_count"] == 1
    assert ranked["excluded"]["evidencia_ranking_incompleta"] == 1
    assert ranked["missing_ranking_evidence"] == {"risk": 1}
    assert "evidencia_risk_a_confirmar" in ranked["blocking_reasons"]
    assert ranked["execution_available"] is False


@pytest.mark.parametrize(("field", "value"), [
    ("verified", False),
    ("verified", 1),
    ("source", "unknown_market"),
    ("source", ["route_optimizer"]),
    ("value", None),
    ("value", True),
    ("value", -0.01),
    ("value", 1.01),
    ("value", float("nan")),
    ("observed_at", NOW - 259201),
    ("observed_at", NOW + 1),
])
def test_unverified_or_stale_risk_evidence_fails_closed(field, value):
    row = evidenced_candidate()
    row["ranking_evidence"]["risk"][field] = value
    ranked = compare_complete(evidenced_report(row), risk_weight=1)

    assert ranked["status"] == "inconclusivo"
    assert ranked["best"] is None
    assert ranked["eligible_count"] == 0
    assert ranked["missing_ranking_evidence"] == {"risk": 1}


def test_ranking_evidence_must_match_financial_and_hub_snapshot_sources():
    row = evidenced_candidate()
    data = evidenced_report(row)
    data["source"] = "not_the_hub_inventory"
    ranked = compare_complete(data, diversification_weight=1)
    assert ranked["best"] is None
    assert "evidencia_diversification_a_confirmar" in ranked["blocking_reasons"]

    row["financial_source"] = "game_research"
    ranked = compare_complete(evidenced_report(row), confidence_weight=1)
    assert ranked["best"] is None
    assert "evidencia_confidence_a_confirmar" in ranked["blocking_reasons"]


def test_ranking_evidence_cannot_be_reused_for_another_hub_route_or_engine():
    row = evidenced_candidate()
    row["ranking_evidence"]["risk"]["route_key"] = "ids:123|999"
    ranked = compare_complete(evidenced_report(row), risk_weight=1)
    assert ranked["best"] is None

    row = evidenced_candidate()
    row["ranking_evidence"]["confidence"]["engine_id"] = "other-engine"
    ranked = compare_complete(evidenced_report(row), confidence_weight=1)
    assert ranked["best"] is None

    row = evidenced_candidate()
    row["ranking_evidence"]["diversification"]["hub_id"] = "789"
    ranked = compare_complete(evidenced_report(row), diversification_weight=1)
    assert ranked["best"] is None


def test_conflicting_evidence_for_same_scenario_is_order_independent():
    first = evidenced_candidate(risk=0.1)
    conflicting = evidenced_candidate(risk=0.9)
    settings = {"risk_weight": 1}
    ranked = compare_complete(evidenced_report(first, conflicting), **settings)
    reversed_ranked = compare_complete(evidenced_report(conflicting, first), **settings)

    assert ranked == reversed_ranked
    assert ranked["best"] is None
    assert ranked["excluded"]["pesquisas_conflitantes"] == 2


@pytest.mark.parametrize("weights", [
    {"risk_weight": -0.1},
    {"confidence_weight": float("inf")},
    {"diversification_weight": float("nan")},
    {"risk_weight": True},
    {"profit_weight": 0, "efficiency_weight": 0},
    {"profit_weight": 0, "efficiency_weight": 0, "risk_weight": 0},
    {"risk_weight": 1e308, "confidence_weight": 1e308},
])
def test_invalid_optional_weight_configuration_fails_closed(weights):
    ranked = compare_complete(evidenced_report(evidenced_candidate()), **weights)
    assert ranked["status"] == "inconclusivo"
    assert ranked["best"] is None
    assert "criterios_planejamento_invalidos" in ranked["blocking_reasons"]


def test_zero_weight_does_not_require_or_invent_optional_evidence():
    row = candidate()
    row["ranking_evidence"] = {"risk": {"value": "unknown"}}
    row["score"] = 999
    row["risk_index"] = 1.0
    ranked = compare_complete(report(row), risk_weight=0, confidence_weight=0,
                              diversification_weight=0)
    assert ranked["status"] == "comparacao_concluida"
    assert ranked["best"]["score"] == 1.0
    assert "risk_index" not in ranked["best"]
    assert ranked["missing_ranking_evidence"] == {}


# A4 fixtures are synthetic A3 output contracts. They never claim to describe
# a real game observation or imply that the acquisition gates were homologated.
PROFILE = "synthetic-profile"
SNAPSHOT = "synthetic-snapshot"


def a4_proof(value, source, *, hub_id=None, economics_id=None, **changes):
    proof = {"value": value, "source": source, "verified": True,
             "profile_id": PROFILE, "snapshot_id": SNAPSHOT,
             "observed_at": NOW}
    if hub_id is not None:
        proof["hub_id"] = hub_id
    if economics_id is not None:
        proof["economics_id"] = economics_id
    proof.update(changes)
    return proof


def a4_evaluation(hub="123", destination="456", engine="engine-1", *,
                  profit=100, cost=1000, layout=None, cash=None):
    seats = layout or {"y": 100, "j": 10, "f": 0}
    money = cash or {"available": 25000, "committed": 1500, "reserve": 2000}
    economics_id = f"economics-v1-synthetic-{hub}-{destination}-{engine}-{seats['y']}"
    identity = {"hub_id": hub, "origin_id": hub, "destination_id": destination,
                "model_id": "model-a", "engine_id": engine}
    provenance = {
        name: a4_proof(money if name == "cash" else 1, source,
                       **{key: identity[key] for key in A3_PROVENANCE_SUBJECTS[name]})
        for name, source in A3_PROVENANCE_SOURCES.items()
    }
    return {
        "schema_version": 1,
        "economics_id": economics_id,
        "plan_id": f"plan-{hub}-{destination}-{engine}",
        "profile_id": PROFILE,
        "snapshot_id": SNAPSHOT,
        "status": "evaluated", "blocking_reasons": [],
        "evidence_confidence": "provenance_complete", "excluded_costs": [],
        "read_only": True, "execution_available": False,
        "identity": identity,
        "configuration_yjf": seats,
        "components": {"daily_net_profit_estimate": profit,
                       "payback_days": round(cost / profit, 2),
                       "roi_365d_percent": round(profit * 36500 / cost, 2)},
        "capital_costs": {"total_investment": cost},
        "cash_after_purchase": money["available"] - money["committed"] - cost,
        "cash_required_reserve": money["reserve"],
        "observed_at_oldest": NOW,
        "provenance": provenance,
        "sensitivity": {
            name: {"daily_net_profit_estimate": profit * fraction}
            for name, fraction in (("fuel_price", .8), ("co2_price", .9),
                                   ("occupancy", .7), ("demand", .6), ("combined", .5))
        },
    }


def a4_controls(**changes):
    values = {
        "pending_orders_incremental": (0, "investment_journal"),
        "future_commitments_incremental": (0, "investment_journal"),
        "unrouted_aircraft_count": (0, "game_fleet_scan"),
        "operational_reserve": (3000, "investment_policy"),
        "cycle_spent": (0, "investment_journal"),
        "cycle_limit": (10000, "investment_policy"),
        "period_spent": (0, "investment_journal"),
        "period_limit": (20000, "investment_policy"),
    }
    return {key: a4_proof(changes.get(key, value), source)
            for key, (value, source) in values.items()}


def a4_local_journal(*, exposure=0, count=0, since=NOW - 86400, cycle_confirmed=0):
    return {"profile_id": PROFILE, "estimated_exposure": 0, "count": 0,
            "cycle_usage": {"source": "local_investment_journal",
                            "cycle_id": "a" * 32 if cycle_confirmed else None,
                            "started_at": NOW - 90000 if cycle_confirmed else None,
                            "reserved_exposure": 0, "confirmed_estimated_cost": cycle_confirmed,
                            "estimated_exposure": cycle_confirmed},
            "period_usage": {"source": "local_investment_journal", "since": since,
                             "estimated_exposure": exposure, "acquisition_count": count}}


def a4_compare(*evaluations, controls=None, capacities=None, **changes):
    default_capacity = a4_proof(2, "game_hangar_and_fleet_status")
    settings = {"profile_id": PROFILE, "snapshot_id": SNAPSHOT,
                "controls": a4_controls() if controls is None else controls,
                "passenger_hangar": default_capacity if capacities is None else capacities,
                "fleet_coverage_verified": True, "research_coverage_verified": True,
                "commitments_verified": True, "max_single_investment": 9000,
                "current_cash_reserve": 0, "max_daily_spend": 30000,
                "max_cycle_spend": 20000,
                "max_acquisitions_per_day": 10, "local_journal": a4_local_journal(),
                "now": NOW}
    settings.update(changes)
    return compare_audited_portfolio(list(evaluations), **settings)


def test_a4_current_policy_caps_audited_budget_without_double_counting():
    cheap = a4_evaluation(cost=2000)
    expensive = a4_evaluation("789", "999", cost=7000, profit=350)
    result = a4_compare(cheap, expensive, max_daily_spend=9000,
                        local_journal=a4_local_journal(exposure=5000, count=1),
                        max_acquisitions_per_day=2)
    assert result["budget_after_reservations_and_limits"] == 4000
    assert result["best"]["economics_id"] == cheap["economics_id"]
    assert result["local_period_limits"]["remaining_acquisitions"] == 1

    reserved = a4_compare(cheap, expensive, current_cash_reserve=21000)
    assert reserved["budget_after_reservations_and_limits"] == 2500
    assert reserved["best"]["economics_id"] == cheap["economics_id"]


def test_a4_cycle_limit_uses_stricter_current_and_audited_caps():
    candidate = a4_evaluation(cost=2000)
    controls = a4_controls(cycle_spent=3000, cycle_limit=10000)
    result = a4_compare(candidate, controls=controls, max_cycle_spend=6000)
    assert result["remaining_cycle_spend"] == 3000
    assert result["budget_after_reservations_and_limits"] == 3000
    assert result["decision"] == "sugestao_para_analise"
    increased = a4_compare(candidate, controls=controls, max_cycle_spend=15000)
    assert increased["remaining_cycle_spend"] == 7000
    exhausted = a4_compare(candidate, controls=controls, max_cycle_spend=3000)
    assert exhausted["remaining_cycle_spend"] == 0
    assert "limite_ciclo_esgotado" in exhausted["blocking_reasons"]
    assert exhausted["best"] is None


def test_a4_persistent_cycle_usage_is_independent_of_rolling_period():
    candidate = a4_evaluation(cost=2000)
    controls = a4_controls(cycle_spent=3000, cycle_limit=10000)
    journal = a4_local_journal(cycle_confirmed=7000)
    result = a4_compare(candidate, controls=controls, max_cycle_spend=10000, local_journal=journal)
    assert result["remaining_cycle_spend"] == 3000
    assert result["budget_after_reservations_and_limits"] == 3000
    assert result["local_cycle_limits"]["estimated_exposure"] == 7000
    assert result["decision"] == "sugestao_para_analise"
    exhausted = a4_compare(candidate, controls=controls, max_cycle_spend=7000, local_journal=journal)
    assert exhausted["remaining_cycle_spend"] == 0
    assert exhausted["best"] is None


@pytest.mark.parametrize("changes, reason", [
    ({"max_cycle_spend": 0}, "limite_ciclo_nao_configurado"),
    ({"max_cycle_spend": -1}, "limite_ciclo_nao_configurado"),
    ({"max_daily_spend": 0}, "limites_periodo_invalidos"),
    ({"max_acquisitions_per_day": 0}, "limites_periodo_invalidos"),
    ({"current_cash_reserve": -1}, "limites_periodo_invalidos"),
    ({"local_journal": None}, "uso_periodo_a_confirmar"),
    ({"local_journal": {**a4_local_journal(), "cycle_usage": None}}, "uso_ciclo_a_confirmar"),
    ({"local_journal": {**a4_local_journal(), "cycle_usage": {
        **a4_local_journal()["cycle_usage"], "estimated_exposure": 1}}}, "uso_ciclo_a_confirmar"),
    ({"local_journal": a4_local_journal(since=NOW - 86399)}, "uso_periodo_a_confirmar"),
    ({"local_journal": a4_local_journal(since=NOW - 86500)}, "uso_periodo_a_confirmar"),
    ({"local_journal": {**a4_local_journal(), "profile_id": "other"}}, "uso_periodo_a_confirmar"),
    ({"max_daily_spend": 1000, "local_journal": a4_local_journal(exposure=1000, count=1)},
     "limite_periodo_esgotado"),
    ({"max_acquisitions_per_day": 1, "local_journal": a4_local_journal(exposure=1000, count=1)},
     "limite_de_aquisicoes_em_24h"),
])
def test_a4_current_limits_fail_closed(changes, reason):
    result = a4_compare(a4_evaluation(), **changes)
    assert result["decision"] == "nao_comprar"
    assert reason in result["blocking_reasons"]
    assert result["best"] is None


def test_a4_global_ranking_best_per_hub_and_explanation_is_deterministic():
    cheap = a4_evaluation("123", "456", "engine-economical", profit=200, cost=1000)
    fast = a4_evaluation("123", "456", "engine-fast", profit=300, cost=6000)
    outside = a4_evaluation("789", "999", "engine-2", profit=250, cost=5000)
    original = deepcopy([cheap, fast, outside])

    ranked = a4_compare(cheap, fast, outside)
    reversed_ranked = a4_compare(outside, fast, cheap)

    assert ranked == reversed_ranked
    assert ranked["status"] == "comparacao_concluida"
    assert ranked["best"]["economics_id"] == cheap["economics_id"]
    assert ranked["best"]["score"] > ranked["alternatives"][1]["score"]
    assert len(ranked["alternatives"]) == 3
    assert [group["hub_id"] for group in ranked["best_by_hub"]] == ["123", "789"]
    assert len(ranked["best_by_hub"][0]["alternatives"]) == 2
    assert ranked["why_best"]["runner_up_economics_id"] == fast["economics_id"]
    assert ranked["why_best"]["score_difference"] > 0
    assert set(ranked["best"]["score_components"]) == {"profit", "capital_efficiency"}
    assert ranked["decision"] == "sugestao_para_analise"
    assert ranked["execution_available"] is False and ranked["read_only"] is True
    assert [cheap, fast, outside] == original


def test_a4_preserves_multiple_yjf_layouts_for_same_hub_route_and_engine():
    first = a4_evaluation(layout={"y": 90, "j": 10, "f": 0})
    second = a4_evaluation(layout={"y": 100, "j": 10, "f": 0}, profit=110)
    ranked = a4_compare(first, second)
    assert ranked["eligible_count"] == 2
    assert len(ranked["best_by_hub"][0]["alternatives"]) == 2


def test_a4_missing_financial_evidence_and_coverage_are_no_buy():
    evaluated = a4_evaluation()
    no_controls = a4_compare(evaluated, controls={})
    assert no_controls["decision"] == "nao_comprar"
    assert no_controls["best"] is None
    assert no_controls["budget_after_reservations_and_limits"] is None
    assert "evidencia_pending_orders_incremental_a_confirmar" in no_controls["blocking_reasons"]

    partial = a4_compare(evaluated, commitments_verified=False)
    assert partial["status"] == "inconclusivo"
    assert partial["decision"] == "nao_comprar"
    assert partial["best"] is not None  # informational ranking only
    assert "compromissos_a_conciliar" in partial["blocking_reasons"]


@pytest.mark.parametrize("capital_costs", [None, [], "invalid", 123, {},
                                            {"total_investment": -1000}])
def test_a4_malformed_capital_costs_fail_closed(capital_costs):
    evaluated = a4_evaluation()
    evaluated["capital_costs"] = capital_costs

    assert _audited_a3_cash(evaluated, profile_id=PROFILE,
                            snapshot_id=SNAPSHOT, now=NOW) is None

    result = a4_compare(evaluated)

    assert result["status"] == "inconclusivo"
    assert result["decision"] == "nao_comprar"
    assert result["best"] is None
    assert result["eligible_count"] == 0
    assert result["excluded"]["avaliacao_a3_invalida_ou_conflitante"] == 1
    assert result["execution_available"] is False


def test_a4_missing_capital_costs_fail_closed():
    evaluated = a4_evaluation()
    del evaluated["capital_costs"]

    result = a4_compare(evaluated)

    assert result["decision"] == "nao_comprar"
    assert result["best"] is None
    assert "avaliacoes_a3_invalidas_ou_conflitantes" in result["blocking_reasons"]


def test_a4_reconciles_cash_and_spend_caps_before_ranking():
    low = a4_evaluation(cost=2000)
    high = a4_evaluation("789", "999", cost=7000, profit=350)
    controls = a4_controls(pending_orders_incremental=2000,
                           future_commitments_incremental=3000,
                           cycle_spent=6000, cycle_limit=10000,
                           period_spent=15000, period_limit=20000)
    ranked = a4_compare(low, high, controls=controls)
    assert ranked["budget_after_reservations_and_limits"] == 4000
    assert ranked["best"]["economics_id"] == low["economics_id"]
    assert ranked["excluded"]["orcamento_global_insuficiente_ou_desconhecido"] == 1

    exhausted = a4_controls(cycle_spent=10000)
    blocked = a4_compare(low, controls=exhausted)
    assert blocked["best"] is None
    assert blocked["decision"] == "nao_comprar"
    assert "limite_ciclo_esgotado" in blocked["blocking_reasons"]

    period_exhausted = a4_compare(low, controls=a4_controls(period_spent=20000))
    assert period_exhausted["best"] is None
    assert "limite_periodo_esgotado" in period_exhausted["blocking_reasons"]

    committed_excess = a4_compare(low, controls=a4_controls(future_commitments_incremental=24000))
    assert committed_excess["best"] is None
    assert "saldo_apos_compromissos_insuficiente" in committed_excess["blocking_reasons"]


def test_a4_hangar_unrouted_aircraft_and_per_purchase_limit_fail_closed():
    evaluated = a4_evaluation()
    missing = a4_compare(evaluated, capacities={})
    assert missing["best"] is None
    assert "vagas_hangar_a_confirmar" in missing["blocking_reasons"]
    assert missing["excluded"]["vagas_hangar_a_confirmar"] == 1

    no_space = a4_compare(evaluated, capacities=a4_proof(0, "game_hangar_and_fleet_status"))
    assert no_space["best"] is None
    assert no_space["excluded"]["hangar_sem_vaga"] == 1
    assert no_space["decision"] == "nao_comprar"

    parked = a4_compare(evaluated, controls=a4_controls(unrouted_aircraft_count=2))
    assert parked["status"] == "inconclusivo"
    assert parked["decision"] == "nao_comprar"
    assert "aeronaves_sem_rota_a_resolver" in parked["blocking_reasons"]

    capped = a4_compare(evaluated, max_single_investment=500)
    assert capped["best"] is None
    assert capped["excluded"]["limite_por_aquisicao"] == 1


def test_a4_a3_blocked_stale_conflicting_and_foreign_evaluations_are_excluded():
    evaluated = a4_evaluation()
    blocked = deepcopy(evaluated)
    blocked.update(status="blocked", blocking_reasons=[{"code": "EVIDENCE_MISSING"}])
    foreign = a4_evaluation("789", "999")
    foreign["profile_id"] = "other-profile"
    stale = a4_evaluation("111", "222")
    stale["observed_at_oldest"] = NOW - 86400
    response = a4_compare(evaluated, blocked, foreign, stale)
    assert response["decision"] == "nao_comprar"
    assert response["eligible_count"] == 1
    assert "avaliacoes_a3_invalidas_ou_conflitantes" in response["blocking_reasons"]
    assert "avaliacoes_a3_incompativeis" in response["blocking_reasons"]
    assert "saldo_a3_a_confirmar" in response["blocking_reasons"]

    conflicting = deepcopy(evaluated)
    conflicting["components"]["daily_net_profit_estimate"] = 300
    conflicting["components"]["payback_days"] = round(1000 / 300, 2)
    conflicting["components"]["roi_365d_percent"] = 10950.0
    conflict = a4_compare(evaluated, conflicting)
    assert conflict["best"] is None
    assert conflict["excluded"]["avaliacao_a3_invalida_ou_conflitante"] == 2


def test_a4_contradictory_game_cash_from_same_snapshot_blocks_decision():
    normal = a4_evaluation()
    mismatch = a4_evaluation("789", "999", cash={"available": 27000,
                                                "committed": 1500, "reserve": 2000})
    ranked = a4_compare(normal, mismatch)
    assert ranked["status"] == "inconclusivo"
    assert "saldos_a3_contraditorios" in ranked["blocking_reasons"]
    assert ranked["decision"] == "nao_comprar"
    assert ranked["budget_after_reservations_and_limits"] is None


def test_a4_risk_uses_a3_stress_and_optional_dimensions_require_fresh_evidence():
    fragile = a4_evaluation("123", "456", profit=200, cost=2000)
    robust = a4_evaluation("789", "999", profit=150, cost=2000)
    fragile["sensitivity"]["demand"]["daily_net_profit_estimate"] = 10
    robust["sensitivity"]["demand"]["daily_net_profit_estimate"] = 130
    fragile["sensitivity"]["combined"]["daily_net_profit_estimate"] = -20
    robust["sensitivity"]["combined"]["daily_net_profit_estimate"] = 60
    other_weights = {"profit_weight": 0, "efficiency_weight": 0,
                     "risk_weight": 1}
    risk_ranked = a4_compare(fragile, robust, **other_weights)
    assert risk_ranked["best"]["hub_id"] == "789"
    assert risk_ranked["best"]["risk_index"] == pytest.approx(.4)

    del robust["sensitivity"]["combined"]
    missing_stress = a4_compare(robust, **other_weights)
    assert missing_stress["best"] is None
    assert missing_stress["decision"] == "nao_comprar"
    robust["sensitivity"]["combined"] = {"daily_net_profit_estimate": 60}

    missing = a4_compare(fragile, robust, profit_weight=0, efficiency_weight=0,
                         diversification_weight=1)
    assert missing["best"] is None
    assert missing["decision"] == "nao_comprar"
    assert "evidencia_diversification_a_confirmar" in missing["blocking_reasons"]

    diversification = {
        fragile["economics_id"]: a4_proof(.95, "game_fleet_scan", hub_id="123",
                                           economics_id=fragile["economics_id"]),
        robust["economics_id"]: a4_proof(.05, "game_fleet_scan", hub_id="789",
                                          economics_id=robust["economics_id"]),
    }
    ranked = a4_compare(fragile, robust, profit_weight=0, efficiency_weight=0,
                        diversification_weight=1, diversification_evidence=diversification)
    assert ranked["best"]["hub_id"] == "123"
    assert ranked["best"]["score_components"] == {"diversification": .95}

    diversification[fragile["economics_id"]]["snapshot_id"] = "different-snapshot"
    invalid = a4_compare(fragile, robust, profit_weight=0, efficiency_weight=0,
                         diversification_weight=1, diversification_evidence=diversification)
    assert invalid["status"] == "inconclusivo"
    assert invalid["best"]["hub_id"] == "789"
    assert invalid["decision"] == "nao_comprar"


def test_a4_audits_full_provenance_sources_subjects_and_clock():
    evaluated = a4_evaluation()
    missing = deepcopy(evaluated)
    del missing["provenance"]["fares"]
    result = a4_compare(missing)
    assert result["best"] is None
    assert "saldo_a3_a_confirmar" in result["blocking_reasons"]

    wrong_subject = deepcopy(evaluated)
    wrong_subject["provenance"]["daily_demand"]["destination_id"] = "999"
    result = a4_compare(wrong_subject)
    assert result["best"] is None

    too_old = deepcopy(evaluated)
    too_old["provenance"]["fuel_units_per_day"]["observed_at"] = NOW - 999999
    too_old["observed_at_oldest"] = NOW - 999999
    result = a4_compare(too_old)
    assert result["best"] is None


def test_a4_control_evidence_must_match_profile_snapshot_and_source():
    evaluated = a4_evaluation()
    invalid = a4_controls()
    invalid["cycle_spent"]["snapshot_id"] = "another-snapshot"
    result = a4_compare(evaluated, controls=invalid)
    assert result["best"] is None
    assert result["decision"] == "nao_comprar"
    assert "evidencia_cycle_spent_a_confirmar" in result["blocking_reasons"]

    invalid = a4_controls()
    invalid["pending_orders_incremental"]["source"] = "unverified-estimate"
    result = a4_compare(evaluated, controls=invalid)
    assert "evidencia_pending_orders_incremental_a_confirmar" in result["blocking_reasons"]

    wrong_hub = {"123": a4_proof(2, "game_hub_select", hub_id="789")}
    result = a4_compare(evaluated, capacities=wrong_hub)
    assert "vagas_hangar_a_confirmar" in result["blocking_reasons"]


def test_a4_policy_and_profitability_thresholds_cannot_allow_purchase():
    evaluated = a4_evaluation()
    low_profit = a4_compare(evaluated, min_daily_profit=200)
    assert low_profit["best"] is None
    assert low_profit["excluded"]["lucro_abaixo_do_minimo"] == 1

    long_payback = a4_compare(evaluated, max_payback_days=5)
    assert long_payback["best"] is None
    assert long_payback["excluded"]["retorno_acima_do_limite"] == 1

    invalid_policy = a4_compare(evaluated, policy_valid=False)
    assert invalid_policy["decision"] == "nao_comprar"
    assert "politica_invalida" in invalid_policy["blocking_reasons"]
    assert invalid_policy["execution_available"] is False

    missing_single_limit = a4_compare(evaluated, max_single_investment=None)
    assert missing_single_limit["best"] is None
    assert missing_single_limit["decision"] == "nao_comprar"


def test_a4_missing_roi_or_invalid_evaluations_format_never_concludes():
    invalid_roi = a4_evaluation()
    invalid_roi["components"]["roi_365d_percent"] = None
    result = a4_compare(invalid_roi)
    assert result["best"] is None
    assert result["decision"] == "nao_comprar"
    assert "avaliacoes_a3_invalidas_ou_conflitantes" in result["blocking_reasons"]

    invalid = compare_audited_portfolio(
        {"not": "a sequence"}, profile_id=PROFILE, snapshot_id=SNAPSHOT,
        now=NOW,
    )
    assert invalid["status"] == "inconclusivo"
    assert invalid["decision"] == "nao_comprar"
    assert "formato_avaliacoes_a3_invalido" in invalid["blocking_reasons"]


def test_a4_return_and_confidence_weights_require_real_a3_or_snapshot_proof():
    profitable = a4_evaluation("123", "456", profit=250, cost=10000)
    efficient = a4_evaluation("789", "999", profit=100, cost=1000)
    with_roi = a4_compare(profitable, efficient, profit_weight=0,
                          efficiency_weight=0, return_weight=1,
                          max_single_investment=12000)
    assert with_roi["best"]["hub_id"] == "789"
    assert with_roi["best"]["score_components"] == {"return": 1.0}

    missing_confidence = a4_compare(profitable, efficient, profit_weight=0,
                                    efficiency_weight=0, confidence_weight=1)
    assert missing_confidence["best"] is None
    assert "evidencia_confidence_a_confirmar" in missing_confidence["blocking_reasons"]

    evidence = {
        profitable["economics_id"]: a4_proof(
            .9, "game_research", hub_id="123", economics_id=profitable["economics_id"]),
        efficient["economics_id"]: a4_proof(
            .1, "game_research", hub_id="789", economics_id=efficient["economics_id"]),
    }
    confidence = a4_compare(profitable, efficient, profit_weight=0, efficiency_weight=0,
                            confidence_weight=1, confidence_evidence=evidence,
                            max_single_investment=12000)
    assert confidence["best"]["hub_id"] == "123"
    assert confidence["execution_available"] is False
