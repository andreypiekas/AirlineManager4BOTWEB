"""Conservative global comparison of researched hub/route/engine scenarios."""
from __future__ import annotations

from copy import deepcopy

from portfolio_planner import compare_portfolio


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


def test_extreme_money_and_weights_cannot_overflow_portfolio_ranking():
    result = compare_complete(report(candidate(cost=1e300, profit=1e-300)),
                              profit_weight=1e308, efficiency_weight=1e308)
    assert result["best"] is None
    assert "criterios_planejamento_invalidos" in result["blocking_reasons"]
    assert result["excluded"]["economia_fora_do_intervalo"] == 1
