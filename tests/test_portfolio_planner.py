"""Conservative global comparison of researched hub/route/engine scenarios."""
from __future__ import annotations

from copy import deepcopy

import pytest

from portfolio_planner import compare_portfolio


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
    scaled = compare_complete(data, profit_weight=6, efficiency_weight=4)

    assert default["best"]["hub_id"] == "789"
    assert profit_only["best"]["hub_id"] == "789"
    assert efficient_only["best"]["hub_id"] == "123"
    assert efficient_only["best"]["score_components"] == {"capital_efficiency": 1.0}
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
