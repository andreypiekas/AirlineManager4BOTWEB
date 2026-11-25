"""A6 exhaustive owned-hub gate and evidence-backed external suggestions."""
from copy import deepcopy
import time

import pytest

from expansion_feasibility import assess_expansion
from investment_policy import InvestmentPolicy
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
                    "model_id": "101", "stopover_id": None,
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


def test_hub_selection_filters_full_ranking_without_suppressing_analysis():
    data = inputs()
    # The fourth-ranked candidate fits the hub cap even when the entire
    # hub/aircraft/route investment exceeds it.
    row = data[3]["candidates"][-1]
    row["hub_price"] = row["cost_breakdown"]["hub_price"] = 1000
    row["investment"] -= 4000
    row["cost_breakdown"]["total"] -= 4000
    row["cost_breakdown"]["cash_required"] -= 4000
    row["payback_days"] = round(row["investment"] / row["profit_per_day"], 1)
    result = evaluate(data, policy=InvestmentPolicy(max_hub_investment=1000))
    assert [item["id"] for item in result["top_three"]] == ["888", "777", "789"]
    selection = result["hub_limit_selection"]
    assert selection["eligible_count"] == 1
    assert selection["selected_hub_id"] == "666"
    assert selection["eligible_hub_ids"] == ["666"]
    assert selection["execution_available"] is False
    assert all(item["reasons"] == ["limite_por_compra_de_hub"] for item in selection["excluded"])


def test_affordability_uses_cash_after_reserve_only_once():
    data = inputs()
    external = data[3]
    row = external["candidates"][0]
    external["candidates"] = [row]
    external["available_cash"] = row["investment"]
    row["cost_breakdown"]["reserve"] = 5000
    row["cost_breakdown"]["cash_required"] = row["investment"] + 5000
    assert [item["id"] for item in evaluate(data)["top_three"]] == ["789"]
    external["available_cash"] -= 1
    assert evaluate(data)["top_three"] == []


@pytest.mark.parametrize("changes", [
    {"aircraft_price_includes_engine": 1},
    {"engine_delta_cost": True},
    {"engine_delta_cost": 100},
    {"engine_delta_invalid": True},
])
def test_gate_rejects_invalid_engine_price_composition(changes):
    data = inputs()
    row = data[3]["candidates"][0]
    row["scenario"]["costs"].update(changes)
    assert all(item["id"] != "789" for item in evaluate(data)["top_three"])
    assert evaluate(data)["external_pending_count"] == 1


def test_external_report_scope_cannot_conflict_with_scenario():
    data = inputs()
    data[3]["profile_id"] = "other"
    assert evaluate(data, profile_id="principal")["top_three"] == []


@pytest.mark.parametrize("policy", [None, InvestmentPolicy(),
                                  InvestmentPolicy(valid=False, max_hub_investment=5000),
                                  InvestmentPolicy(max_hub_investment=5000, max_hub_points=-1)])
def test_hub_selection_defaults_and_invalid_limits_do_not_suppress_a6(policy):
    result = evaluate(inputs(), policy=policy)
    assert len(result["top_three"]) == 3
    assert result["hub_limit_selection"]["selected_hub_id"] is None
    assert len(result["hub_limit_selection"]["excluded"]) == 4


def test_hub_selection_preserves_evidence_gate_and_ranking():
    data = inputs()
    policy = InvestmentPolicy(max_hub_investment=5000, max_hub_points=0)
    result = evaluate(data, policy=policy)
    assert result["hub_limit_selection"]["eligible_hub_ids"] == ["888", "777", "789", "666"]
    data[4]["complete"] = False
    result = evaluate(data, policy=policy)
    assert result["hub_limit_selection"]["eligible_count"] == 0
    assert result["hub_limit_selection"]["selected_hub_id"] is None


def _timestamps(data):
    """Every independent timestamp used by the owned/external A6 gate."""
    inventory, _, _, external, coverage = data
    timestamps = [
        inventory,
        coverage,
        *coverage["hubs"],
        external,
    ]
    for candidate in external["candidates"]:
        timestamps.extend((
            (candidate, "hub_price_observed_at"),
            (candidate, "hub_points_observed_at"),
            candidate["scenario"],
            candidate["scenario"]["costs"],
            candidate["scenario"]["financial"],
        ))
    return [(item, "observed_at") if isinstance(item, dict) else item
            for item in timestamps]


def test_fractional_dom_timestamps_survive_all_owned_and_external_proofs():
    data = inputs()
    observed = NOW + 0.25
    for part, key in _timestamps(data):
        part[key] = observed
    result = assess_expansion(*data[:4], coverage=data[4], now=NOW + 0.75)
    assert result["status"] == "avaliacao_expansao"
    assert result["blocking_reasons"] == []
    assert len(result["top_three"]) == 3
    assert result["external_pending_count"] == 0


@pytest.mark.parametrize("invalid", [
    True, False, None, "1800000000", -1, 0, float("nan"),
    float("inf"), -float("inf"), 10 ** 500,
    NOW + 0.01, NOW - 259201,
])
@pytest.mark.parametrize("proof_index", range(2 + 2 + 1 + 5))
def test_invalid_stale_or_future_timestamp_never_qualifies_external(proof_index, invalid):
    data = inputs()
    # Inventory, scan, its two hubs, external catalog, and the first
    # candidate's two price proofs, scenario, costs and financial research.
    selected = _timestamps(data)
    part, key = selected[proof_index]
    part[key] = invalid
    result = evaluate(data)
    if proof_index < 4:
        assert result["status"] == "inconclusivo"
        assert result["top_three"] == []
    elif proof_index == 4:
        assert result["status"] == "inconclusivo"
        assert "catalogo_expansao_incompleto_ou_vencido" in result["blocking_reasons"]
    else:
        assert result["status"] == "avaliacao_expansao"
        assert result["external_pending_count"] == 1
        assert all(row["id"] != "789" for row in result["top_three"])


def test_default_clock_accepts_current_fractional_proof():
    data = inputs()
    observed = time.time() - 0.25
    for part, key in _timestamps(data):
        part[key] = observed
    result = assess_expansion(*data[:4], coverage=data[4])
    assert result["status"] == "avaliacao_expansao"
    assert len(result["top_three"]) == 3


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
    {"destination_id": "998"},
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
    lambda row: row["scenario"].pop("model_id"),
    lambda row: row["scenario"]["costs"].pop("stopover_id"),
    lambda row: row["scenario"]["financial"].update(model_id="102"),
    lambda row: row["scenario"]["costs"].update(stopover_id=False),
    lambda row: row["scenario"]["financial"].update(stopover_id="888"),
    lambda row: row["scenario"].update(stopover_id="888"),
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


def test_external_evidence_from_different_snapshots_is_rejected_by_gate():
    data = inputs()
    scenario = data[3]["candidates"][0]["scenario"]
    scenario["snapshot_id"] = "capture-a"
    scenario["costs"]["snapshot_id"] = "capture-b"
    result = evaluate(data)
    assert result["external_pending_count"] == 1
    assert all(row["id"] != "789" for row in result["top_three"])


def test_unhashable_hub_identifiers_fail_closed():
    data = inputs()
    data[0]["hubs"][0]["id"] = {"unknown": "value"}
    result = evaluate(data)
    assert result["status"] == "inconclusivo"
    assert "inventario_hubs_proprios_a_confirmar" in result["blocking_reasons"]
