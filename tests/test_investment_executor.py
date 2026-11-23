"""End-to-end fake purchase protocol, recovery, limits and profile isolation."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from investment_executor import SimulatedAircraftGateway, SimulatedInvestmentExecutor
from investment_journal import InvestmentJournal
from investment_policy import InvestmentPolicy


def plan(**changes):
    result = {
        "plan_id": "plan-1", "snapshot_id": "sha256:" + "a" * 64,
        "kind": "aircraft", "hub_id": "123", "origin_id": "123",
        "destination_id": "456", "model_id": "A320", "engine_id": "motor-2",
        "estimated_cost": 10000,
    }
    result.update(changes)
    return result


def checkout(*, profile="principal", **changes):
    result = {
        "source": "simulation_checkout", "simulated": True,
        "profile_id": profile, "snapshot_id": plan()["snapshot_id"],
        "observed_at": time.time(), "hub_selection_id": "123",
        "origin_id": "123", "destination_id": "456", "model_id": "A320",
        "engine_selected_id": "motor-2", "hub_selection_confirmed": True,
        "model_available": True, "engine_available": True,
        "route_available": True, "route_feasible": True, "demand_verified": True,
        "capacity_available": True, "price_includes_engine": True,
        "checkout_cost": 10000, "cash": 50000,
        "commitments_verified": True, "pending_commitments": 2000,
    }
    result.update(changes)
    return result


def executor(tmp_path, *, profile="principal", mode="autonomous", **policy_changes):
    policy = {"enabled": True, "mode": mode, "auto_buy_aircraft": True,
              "max_single_investment": 50000, "max_daily_spend": 50000}
    policy.update(policy_changes)
    ledger = InvestmentJournal(tmp_path / "simulation.sqlite3", profile_id=profile,
                               simulation=True)
    return SimulatedInvestmentExecutor(ledger, InvestmentPolicy(**policy))


def test_simulated_order_confirms_exact_model_engine_route_and_hub(tmp_path):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout())
    result = worker.run(plan(), gateway, reserve=5000)
    assert result["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 1
    assert worker.journal.history(result["intent_key"])[-1]["evidence"]["source"] == "simulation_order_list"
    assert worker.journal.unresolved()["count"] == 0
    assert not worker.journal.executor_busy()
    assert worker.run(plan(), gateway)["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1


def test_refusal_needs_independent_evidence_and_never_repeats_submission(tmp_path):
    worker = executor(tmp_path)
    order_store = tmp_path / "fake_order_book.sqlite3"
    gateway = SimulatedAircraftGateway(checkout(), outcome="refused",
                                       order_store=order_store)
    result = worker.run(plan(), gateway)
    assert result["state"] == "FAILED"
    assert worker.journal.unresolved()["count"] == 0
    assert worker.journal.history(result["intent_key"])[-1]["evidence"]["refusal_code"] == "SIMULATED_REFUSAL"
    assert worker.run(plan(), gateway)["state"] == "FAILED"
    assert gateway.submit_calls == 1
    independent_reader = SimulatedAircraftGateway(checkout(), order_store=order_store)
    evidence = independent_reader.read_order_result(worker.journal.get(result["intent_key"]))
    assert evidence["source"] == "simulation_order_rejection"
    assert evidence["order_absent"] is True


def test_timeout_blocks_new_purchase_until_reconciliation_without_resubmit(tmp_path):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout(), outcome="timeout")
    first = worker.run(plan(), gateway)
    assert first["state"] == "UNKNOWN"
    assert worker.run(plan(), gateway)["state"] == "UNKNOWN"
    next_plan = plan(plan_id="plan-2", destination_id="789")
    next_gateway = SimulatedAircraftGateway(checkout(destination_id="789"))
    blocked = worker.run(next_plan, next_gateway)
    assert blocked["state"] == "BLOCKED"
    assert "compra_anterior_sem_conciliacao" in blocked["reasons"]
    assert next_gateway.submit_calls == 0

    gateway.outcome = "confirmed"
    restarted = executor(tmp_path)
    assert restarted.reconcile(first["intent_key"], gateway)["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert restarted.journal.get(first["intent_key"])["submit_attempts"] == 1
    assert restarted.run(next_plan, next_gateway)["state"] == "CONFIRMED"


def test_timeout_can_be_reconciled_as_verified_refusal(tmp_path):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout(), outcome="timeout_rejected",
                                       order_store=tmp_path / "fake_order_book.sqlite3")
    first = worker.run(plan(), gateway)
    assert first["state"] == "UNKNOWN"
    independent_reader = SimulatedAircraftGateway(
        checkout(), order_store=tmp_path / "fake_order_book.sqlite3")
    assert executor(tmp_path).reconcile(first["intent_key"], independent_reader)["state"] == "FAILED"
    assert gateway.submit_calls == 1


def test_approved_checkout_can_be_revalidated_after_data_is_fixed(tmp_path):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout(engine_selected_id="wrong"))
    pending = worker.run(plan(), gateway)
    assert pending["state"] == "APPROVED"
    gateway.checkout = checkout()
    assert executor(tmp_path).run(plan(), gateway)["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert worker.journal.get(pending["intent_key"])["submit_attempts"] == 1


def test_crash_requires_explicit_guard_recovery_and_preserves_one_shot(tmp_path):
    worker = executor(tmp_path)
    order_store = tmp_path / "fake_order_book.sqlite3"
    gateway = SimulatedAircraftGateway(checkout(), outcome="crash",
                                       order_store=order_store)
    result = worker.run(plan(), gateway)
    assert result["state"] == "SUBMITTED"
    assert worker.journal.executor_busy()
    with pytest.raises(RuntimeError, match="executor"):
        worker.journal.recover_submitted()
    restarted = executor(tmp_path)
    assert restarted.run(plan(), gateway)["reasons"] == ["executor_ocupado"]
    assert restarted.reconcile(result["intent_key"], gateway,
                             stopped_owner_token="wrong-token")["state"] == "BLOCKED"

    independent_reader = SimulatedAircraftGateway(checkout(), outcome="confirmed",
                                                   order_store=order_store)
    assert restarted.reconcile(result["intent_key"], independent_reader,
                             stopped_owner_token=result["stopped_owner_token"])["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert independent_reader.submit_calls == 0
    assert restarted.journal.get(result["intent_key"])["submit_attempts"] == 1
    assert not restarted.journal.executor_busy()


@pytest.mark.parametrize(("policy_changes", "approved", "expected"), [
    ({"mode": "analyze"}, False, "somente_analise"),
    ({"mode": "approval"}, False, "aprovacao_explicita_pendente"),
    ({"enabled": False}, False, "politica_desabilitada_ou_invalida"),
    ({"auto_buy_aircraft": False}, False, "compra_automatica_desabilitada"),
    ({"max_single_investment": 9000}, False, "limite_por_compra"),
    ({"max_daily_spend": 0}, False, "limite_de_24h_nao_configurado"),
])
def test_disabled_modes_and_limits_do_not_write_simulated_orders(
        tmp_path, policy_changes, approved, expected):
    worker = executor(tmp_path, **policy_changes)
    gateway = SimulatedAircraftGateway(checkout())
    result = worker.run(plan(), gateway, approved=approved)
    assert result["state"] == "BLOCKED"
    assert expected in result["reasons"]
    assert gateway.submit_calls == 0
    assert worker.journal.unresolved()["count"] == 0


def test_explicit_approval_and_spending_cap_across_routes(tmp_path):
    worker = executor(tmp_path, mode="approval", max_daily_spend=15000)
    assert worker.run(plan(), SimulatedAircraftGateway(checkout()),
                      approved=True)["state"] == "CONFIRMED"
    second = worker.run(plan(plan_id="plan-2", destination_id="789"),
                        SimulatedAircraftGateway(checkout(destination_id="789")),
                        approved=True)
    assert second["state"] == "BLOCKED"
    assert second["reasons"] == ["limite_de_24h"]
    assert worker.journal.budget_exposure_since(time.time() - 86400) == 10000


@pytest.mark.parametrize("change", [
    {"engine_selected_id": "motor-3"},
    {"hub_selection_id": "789"},
    {"checkout_cost": 11000},
    {"cash": 9000},
    {"source": "game_checkout_dom", "simulated": False},
    {"observed_at": time.time() - 300},
])
def test_bad_checkout_blocks_any_submission(tmp_path, change):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout(**change))
    result = worker.run(plan(), gateway)
    assert result["state"] == "APPROVED"
    assert result["reasons"]
    assert gateway.submit_calls == 0
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 0


def test_invalid_order_proof_remains_unknown_and_cannot_be_swapped_between_modes(tmp_path):
    class WrongProof(SimulatedAircraftGateway):
        def read_order_result(self, intent):
            proof = super().read_order_result(intent)
            return {**proof, "engine_id": "motor-3"}

    worker = executor(tmp_path)
    gateway = WrongProof(checkout())
    result = worker.run(plan(), gateway)
    assert result["state"] == "UNKNOWN"
    assert gateway.submit_calls == 1
    with pytest.raises(ValueError, match="ambiente incompatível"):
        InvestmentJournal(tmp_path / "simulation.sqlite3", profile_id="principal")
    with pytest.raises(ValueError, match="simulação"):
        SimulatedInvestmentExecutor(
            InvestmentJournal(tmp_path / "game.sqlite3", profile_id="principal"),
            InvestmentPolicy(enabled=True))


def test_atomic_profile_guard_prevents_parallel_executors_but_isolates_profiles(tmp_path):
    journal = executor(tmp_path).journal

    def acquire(index):
        return InvestmentJournal(journal.path, profile_id="principal",
                                 simulation=True).acquire_executor(f"owner-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, range(16)))
    assert results.count(True) == 1
    assert results.count(False) == 15
    secondary = executor(tmp_path, profile="secondary")
    assert secondary.journal.acquire_executor("secondary-token")
    assert secondary.journal.release_executor("secondary-token")
    assert journal.executor_busy()


def test_submission_claim_requires_guard_and_blocks_other_uncertain_order(tmp_path):
    ledger = executor(tmp_path).journal
    keys = []
    for new_plan in (plan(), plan(plan_id="another", destination_id="789")):
        intent, _ = ledger.register(new_plan)
        key = intent["intent_key"]
        assert ledger.transition(key, "PROPOSED", "APPROVED")
        assert ledger.transition(key, "APPROVED", "PRECHECKED")
        keys.append(key)
    with pytest.raises(ValueError, match="exclusividade"):
        ledger.claim_submission(keys[0], "no-guard")
    assert ledger.acquire_executor("first-worker")
    assert ledger.claim_submission(keys[0], "first-worker")
    assert not ledger.claim_submission(keys[1], "first-worker")
    assert not ledger.claim_submission(keys[0], "first-worker")
    assert ledger.release_executor("first-worker")
    assert ledger.get(keys[0])["submit_attempts"] == 1
    assert ledger.get(keys[1])["submit_attempts"] == 0
