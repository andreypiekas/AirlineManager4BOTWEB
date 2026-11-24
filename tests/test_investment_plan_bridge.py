"""A3/A4 -> A5 uses full capital exposure and independently priced checkout."""
from __future__ import annotations

import time
from copy import deepcopy

import pytest

from investment_journal import InvestmentJournal
from investment_executor import SimulatedAircraftGateway, SimulatedInvestmentExecutor
from investment_plan_bridge import build_aircraft_intent_plan
from investment_policy import InvestmentPolicy
from investment_preflight import validate_aircraft_preflight
from portfolio_planner import A3_PROVENANCE_SOURCES, A3_PROVENANCE_SUBJECTS


NOW = 1_800_000_000
SNAPSHOT = "sha256:" + "d" * 64
IDENTITY = {"hub_id": "123", "origin_id": "123", "destination_id": "456",
            "model_id": "A320", "engine_id": "motor-2"}
COSTS = {"aircraft_cost": 10000.0, "engine_delta_cost": 500.0,
         "hub_cost": 0.0, "route_fee": 100.0, "hangar_cost": 50.0,
         "other_fees": 50.0, "total_investment": 10700.0}


def reports():
    provenance = {}
    for field, source in A3_PROVENANCE_SOURCES.items():
        provenance[field] = {
            "source": source, "verified": True, "profile_id": "principal",
            "snapshot_id": SNAPSHOT, "observed_at": NOW - 30,
            **{name: IDENTITY[name] for name in A3_PROVENANCE_SUBJECTS[field]},
        }
    provenance["cash"]["value"] = {
        "available": 50000, "committed": 2000, "reserve": 5000,
    }
    evaluation = {
        "status": "evaluated", "schema_version": 1,
        "evidence_confidence": "provenance_complete", "excluded_costs": [],
        "plan_id": "plan-1", "economics_id": "economics-1",
        "profile_id": "principal", "snapshot_id": SNAPSHOT,
        "identity": IDENTITY.copy(), "configuration_yjf": {"y": 100, "j": 0, "f": 0},
        "capital_costs": COSTS.copy(), "cash_after_purchase": 37300,
        "cash_required_reserve": 5000, "observed_at_oldest": NOW - 30,
        "provenance": provenance,
    }
    winner = {key: deepcopy(evaluation[key]) for key in
              ("plan_id", "economics_id", "profile_id", "snapshot_id",
               "identity", "configuration_yjf")}
    winner["investment"] = 10700.0
    portfolio = {
        "status": "comparacao_concluida", "decision": "sugestao_para_analise",
        "blocking_reasons": [], "best": winner,
        "read_only": True, "execution_available": False,
    }
    return portfolio, evaluation


def test_bridge_preserves_total_exposure_and_exact_checkout_through_restart(tmp_path):
    portfolio, evaluation = reports()
    plan = build_aircraft_intent_plan(portfolio, evaluation, now=NOW)
    assert plan["estimated_cost"] == 10700
    assert plan["checkout_cost"] == 10500
    assert plan["capital_costs"]["route_fee"] == 100

    database = tmp_path / "journal.sqlite3"
    ledger = InvestmentJournal(database, profile_id="principal")
    intent, created = ledger.register(plan)
    assert created
    assert ledger.transition(intent["intent_key"], "PROPOSED", "APPROVED")
    stored = InvestmentJournal(database, profile_id="principal").get(intent["intent_key"])
    assert stored["estimated_cost"] == 10700
    assert stored["checkout_cost"] == 10500
    assert ledger.budget_exposure_since(0) == 10700

    observation = {
        "source": "game_checkout_dom", "session_authenticated": True,
        "profile_id": stored["profile_id"], "snapshot_id": stored["snapshot_id"],
        "observed_at": NOW, "hub_selection_id": "800001",
        "delivery_hub_mapping": {
            "source": "game_owned_hub_crosswalk", "verified": True,
            "profile_id": stored["profile_id"], "snapshot_id": stored["snapshot_id"],
            "observed_at": NOW,
            "pairs": [{"airport_id": stored["hub_id"], "delivery_hub_id": "800001"}],
        },
        "origin_id": stored["origin_id"], "destination_id": stored["destination_id"],
        "model_id": stored["model_id"], "engine_selected_id": stored["engine_id"],
        "hub_selection_confirmed": True, "model_available": True,
        "engine_available": True, "route_available": True,
        "route_feasible": True, "demand_verified": True,
        "capacity_available": True, "price_includes_engine": True,
        "checkout_cost": 10500, "cash": 20000,
        "commitments_verified": True, "pending_commitments": 2000,
    }
    assert validate_aircraft_preflight(stored, observation, reserve=5000, now=NOW)["ready"]
    observation["checkout_cost"] = 10000
    assert "preco_divergente" in validate_aircraft_preflight(
        stored, observation, reserve=5000, now=NOW)["reasons"]
    observation["checkout_cost"] = 10500
    observation["cash"] = 17600  # Enough for checkout, not for full capex.
    assert "caixa_insuficiente_ou_nao_verificado" in validate_aircraft_preflight(
        stored, observation, reserve=5000, now=NOW)["reasons"]


@pytest.mark.parametrize("change", [
    lambda p, e: p.update(status="inconclusivo"),
    lambda p, e: p.update(blocking_reasons=["cobertura_incompleta"]),
    lambda p, e: p["best"].update(economics_id="outro"),
    lambda p, e: p["best"].update(investment=10500),
    lambda p, e: e.update(status="blocked"),
    lambda p, e: e["capital_costs"].update(engine_delta_cost=1000),
    lambda p, e: e["capital_costs"].update(other_fees=0.25),
    lambda p, e: e["capital_costs"].update(hub_cost=10),
    lambda p, e: e["provenance"]["cash"].update(profile_id="outro"),
])
def test_bridge_rejects_ambiguous_or_mismatched_audited_costs(change):
    portfolio, evaluation = reports()
    change(portfolio, evaluation)
    with pytest.raises(ValueError):
        build_aircraft_intent_plan(portfolio, evaluation, now=NOW)


def test_bridge_rejects_expired_evidence():
    portfolio, evaluation = reports()
    with pytest.raises(ValueError):
        build_aircraft_intent_plan(portfolio, evaluation, now=NOW + 90000)


def test_full_exposure_governs_simulated_acquisition_limits(tmp_path):
    portfolio, evaluation = reports()
    plan = build_aircraft_intent_plan(portfolio, evaluation, now=NOW)
    checkout = {
        "source": "simulation_checkout", "simulated": True,
        "profile_id": "principal", "snapshot_id": SNAPSHOT,
        "observed_at": time.time(),
        "hub_selection_id": "800001", "origin_id": "123", "destination_id": "456",
        "delivery_hub_mapping": {
            "source": "simulation_hub_crosswalk", "verified": True,
            "profile_id": "principal", "snapshot_id": SNAPSHOT,
            "observed_at": time.time(),
            "pairs": [{"airport_id": "123", "delivery_hub_id": "800001"}],
        },
        "model_id": "A320", "engine_selected_id": "motor-2",
        "hub_selection_confirmed": True, "model_available": True,
        "engine_available": True, "route_available": True,
        "route_feasible": True, "demand_verified": True,
        "capacity_available": True, "price_includes_engine": True,
        "checkout_cost": 10500, "cash": 20000,
        "commitments_verified": True, "pending_commitments": 2000,
    }
    journal = InvestmentJournal(tmp_path / "sim.sqlite3", profile_id="principal",
                                simulation=True)
    policy = InvestmentPolicy(enabled=True, mode="autonomous", auto_buy_aircraft=True,
                              max_single_investment=10600, max_daily_spend=20000,
                              max_acquisitions_per_day=2)
    gateway = SimulatedAircraftGateway(checkout)
    assert "limite_por_compra" in SimulatedInvestmentExecutor(journal, policy).run(
        plan, gateway)["reasons"]
    assert gateway.submit_calls == 0

    policy = InvestmentPolicy(enabled=True, mode="autonomous", auto_buy_aircraft=True,
                              max_single_investment=20000, max_daily_spend=20000,
                              max_acquisitions_per_day=2)
    executor = SimulatedInvestmentExecutor(journal, policy)
    gateway.checkout["cash"] = 17600
    blocked = executor.run(plan, gateway, reserve=5000)
    assert "caixa_insuficiente_ou_nao_verificado" in blocked["reasons"]
    assert gateway.submit_calls == 0

    gateway.checkout["cash"] = 20000
    confirmed = executor.run(plan, gateway, reserve=5000)
    assert confirmed["state"] == "CONFIRMED"
    assert journal.budget_exposure_since(0) == 10700
    assert gateway.submit_calls == 1

    second = {**plan, "plan_id": "plan-2", "destination_id": "789"}
    second_gateway = SimulatedAircraftGateway({**checkout, "destination_id": "789"})
    limited = executor.run(second, second_gateway, reserve=5000)
    assert "limite_de_24h" in limited["reasons"]
    assert second_gateway.submit_calls == 0


@pytest.mark.parametrize("bad", [
    {"checkout_cost": 10000},
    {"capital_costs": {**{k: int(v) for k, v in COSTS.items()}, "hub_cost": 1},
     "checkout_cost": 10500},
    {"capital_costs": {**{k: int(v) for k, v in COSTS.items()}, "other_fees": True},
     "checkout_cost": 10500},
])
def test_journal_refuses_unverified_breakdowns(tmp_path, bad):
    portfolio, evaluation = reports()
    plan = build_aircraft_intent_plan(portfolio, evaluation, now=NOW)
    plan.update(bad)
    with pytest.raises(ValueError):
        InvestmentJournal(tmp_path / "journal.sqlite3", profile_id="principal").register(plan)
