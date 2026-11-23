"""A6 exhaustive owned-hub gate and evidence-backed external suggestions."""
from copy import deepcopy

import pytest

from expansion_feasibility import assess_expansion
from portfolio_planner import compare_portfolio


NOW = 1_800_000_000


def inputs():
    inventory = {
        "source": "game_hub_select", "observed_at": NOW, "partial_fleet": False,
        "hubs": [{"id": "123"}, {"id": "456"}],
    }
    research = {"partial_fleet": False, "candidates": []}
    portfolio = compare_portfolio(
        {"candidates": [], "partial_fleet": False, "available_cash": 100000},
        research_coverage_verified=True, commitments_verified=True, committed_cash=0,
    )
    coverage = {
        "source": "game_hub_opportunity_scan", "complete": True,
        "observed_at": NOW,
        "hubs": [
            {"hub_id": hub, "source": "game_hub_opportunity_scan", "complete": True,
             "observed_at": NOW, "routes_complete": True, "models_complete": True,
             "engines_complete": True, "demand_complete": True, "costs_complete": True}
            for hub in ("123", "456")
        ],
    }
    candidates = []
    for hub, profit, price in (("789", 900, 20000), ("888", 1200, 15000),
                               ("777", 600, 10000), ("666", 100, 10000)):
        identity = {"model": "A320", "engine_id": "engine-1",
                    "origin_id": hub, "destination_id": "999", "route": "XAP ↔ GRU"}
        costs = {**identity, "source": "game_market", "observed_at": NOW,
                 "aircraft_price": price, "aircraft_price_includes_engine": True,
                 "route_fee": 1000, "hangar_price": 0, "other_fees": 0,
                 "engine_delta_cost": None}
        financial = {**identity, "source": "route_optimizer", "observed_at": NOW,
                     "profit_per_day": profit}
        investment = 5000 + price + 1000
        candidate = {
            "id": hub, "code": f"X{hub}", "hub_price": 5000,
            "hub_points": 0, "status": "viavel",
            "observed_at": NOW, "hub_price_observed_at": NOW,
            "hub_points_observed_at": NOW,
            "scenario": {**identity, "source": "game_research", "observed_at": NOW,
                         "engine_verified": True, "external_demand_verified": True,
                         "route_feasible": True, "demand_verified": True,
                         "costs": costs, "financial": financial},
            "ranking_conclusive": True, "purchase_evidence": True,
            "pending": [], "cost_breakdown": {
                "hub_price": 5000, "hub_points": 0, "aircraft_price": price,
                "aircraft_price_includes_engine": True, "engine_delta_cost": None,
                "engine_extra_charged": 0, "route_fee": 1000,
                "hangar_price": 0, "other_fees": 0,
                "reserve": 0, "cash_required": investment, "total": investment,
            },
            "investment": investment,
            "profit_per_day": profit,
            "payback_days": round(investment / profit, 1),
        }
        candidates.append(candidate)
    external = {
        "source": "game_purchase_catalog", "observed_at": NOW,
        "catalog_complete": True, "candidates": candidates, "available_cash": 100000,
    }
    return inventory, research, portfolio, external, coverage


def evaluate(data, **changes):
    inventory, research, portfolio, external, coverage = data
    return assess_expansion(inventory, research, portfolio, external,
                            coverage=coverage, now=NOW, **changes)


def test_only_after_complete_owned_sweep_rank_three_evidence_backed_external_options():
    data = inputs()
    original = deepcopy(data)
    result = evaluate(data)
    assert result["status"] == "avaliacao_expansao"
    assert result["blocking_reasons"] == []
    assert result["owned_hubs_evaluated"] == 2
    assert [row["id"] for row in result["top_three"]] == ["888", "777", "789"]
    assert result["read_only"] is True
    assert result["execution_available"] is False
    assert data == original


def test_inconclusive_owned_sweep_never_promotes_external_investment():
    data = inputs()
    data[0]["partial_fleet"] = True
    data[1]["candidates"] = [{"status": "dados_a_confirmar", "pending": ["demanda_a_confirmar"]}]
    data[4]["hubs"][1]["engines_complete"] = False
    result = evaluate(data)
    assert result["status"] == "inconclusivo"
    assert result["top_three"] == []
    assert "cobertura_frota_incompleta" in result["blocking_reasons"]
    assert "cenarios_proprios_pendentes" in result["blocking_reasons"]
    assert "varredura_completa_hubs_proprios_nao_comprovada" in result["blocking_reasons"]


@pytest.mark.parametrize("mutation", [
    lambda d: d[4].update(hubs=d[4]["hubs"][:1]),
    lambda d: d[4]["hubs"][0].update(hub_id="456"),
    lambda d: d[4]["hubs"][1].update(observed_at=NOW - 259201),
    lambda d: d[0].update(observed_at=NOW - 259201),
    lambda d: d[4].update(source="unknown"),
    lambda d: d[2].update(status="inconclusivo"),
    lambda d: d[0].update(hubs=[]),
])
def test_incomplete_or_stale_proof_cannot_claim_all_owned_hubs_exhausted(mutation):
    data = inputs()
    mutation(data)
    result = evaluate(data)
    assert result["status"] == "inconclusivo"
    assert result["top_three"] == []
    assert result["blocking_reasons"]


def test_owned_opportunity_retains_priority_even_with_external_profit():
    data = inputs()
    data[2]["eligible_count"] = 1
    result = evaluate(data)
    assert result["status"] == "priorizar_hubs_proprios"
    assert result["top_three"] == []


def test_incomplete_external_catalog_never_yields_ranked_expansion():
    data = inputs()
    data[3]["catalog_complete"] = False
    result = evaluate(data)
    assert result["status"] == "inconclusivo"
    assert result["blocking_reasons"] == ["catalogo_expansao_incompleto_ou_vencido"]


@pytest.mark.parametrize("change", [
    {"engine_id": None},
    {"route": "X789-GRU"},
    {"demand_verified": False},
    {"external_demand_verified": False},
])
def test_missing_engine_route_or_demand_is_not_rankable(change):
    data = inputs()
    data[3]["candidates"][0]["scenario"].update(change)
    result = evaluate(data)
    assert result["status"] == "avaliacao_expansao"
    assert result["external_pending_count"] == 1
    assert all(row["id"] != "789" for row in result["top_three"])


@pytest.mark.parametrize("alter", [
    lambda row: row["scenario"]["costs"].update(aircraft_price=1),
    lambda row: row["scenario"]["financial"].update(engine_id="unknown"),
    lambda row: row["cost_breakdown"].update(total=0),
    lambda row: row.update(pending=["preco_a_confirmar"]),
    lambda row: row.update(purchase_evidence=False),
    lambda row: row.update(hub_points=10),
    lambda row: row.update(hub_price_observed_at=NOW - 259201),
])
def test_contradictory_external_cost_engine_points_or_provenance_is_not_rankable(alter):
    data = inputs()
    alter(data[3]["candidates"][0])
    result = evaluate(data)
    assert result["status"] == "avaliacao_expansao"
    assert result["external_pending_count"] == 1
    assert all(row["id"] != "789" for row in result["top_three"])


def test_unknown_coverage_does_not_treat_zero_candidates_as_no_opportunity():
    inventory, research, portfolio, external, _ = inputs()
    result = assess_expansion(inventory, research, portfolio, external, now=NOW)
    assert result["status"] == "inconclusivo"
    assert "varredura_completa_hubs_proprios_nao_comprovada" in result["blocking_reasons"]
    assert result["top_three"] == []


def test_unhashable_hub_identifiers_fail_closed():
    data = inputs()
    data[0]["hubs"][0]["id"] = {"unknown": "value"}
    result = evaluate(data)
    assert result["status"] == "inconclusivo"
    assert "inventario_hubs_proprios_a_confirmar" in result["blocking_reasons"]
