"""End-to-end fake purchase protocol, recovery, limits and profile isolation."""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

import investment_journal
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
        "observed_at": time.time(), "hub_selection_id": "800001",
        "origin_id": "123", "destination_id": "456", "model_id": "A320",
        "engine_selected_id": "motor-2", "hub_selection_confirmed": True,
        "model_available": True, "engine_available": True,
        "route_available": True, "route_feasible": True, "demand_verified": True,
        "capacity_available": True, "price_includes_engine": True,
        "checkout_cost": 10000, "cash": 50000,
        "commitments_verified": True, "pending_commitments": 2000,
    }
    result["delivery_hub_mapping"] = {
        "source": "simulation_hub_crosswalk", "verified": True,
        "profile_id": profile, "snapshot_id": plan()["snapshot_id"],
        "observed_at": result["observed_at"],
        "pairs": [{"airport_id": "123", "delivery_hub_id": "800001"}],
    }
    result.update(changes)
    return result


def executor(tmp_path, *, profile="principal", mode="autonomous", **policy_changes):
    policy = {"enabled": True, "mode": mode, "auto_buy_aircraft": True,
              "max_single_investment": 50000, "max_daily_spend": 50000,
              "max_acquisitions_per_day": 5, "max_cycle_spend": 50000}
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
    next_gateway = SimulatedAircraftGateway(
        checkout(destination_id="789"), purchase_id="987654322",
    )
    blocked = worker.run(next_plan, next_gateway)
    assert blocked["state"] == "BLOCKED"
    assert "compra_anterior_sem_conciliacao" in blocked["reasons"]
    assert next_gateway.submit_calls == 0

    gateway.outcome = "confirmed"
    restarted = executor(tmp_path)
    assert restarted.reconcile(first["intent_key"], gateway)["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert restarted.journal.get(first["intent_key"])["submit_attempts"] == 1
    second = restarted.run(next_plan, next_gateway)
    assert second["state"] == "CONFIRMED"
    assert next_gateway.submit_calls == 1
    receipts = {
        restarted.journal.history(key)[-1]["evidence"]["purchase_id"]
        for key in (first["intent_key"], second["intent_key"])
    }
    assert receipts == {"987654321", "987654322"}


def test_checkout_timeout_keeps_approved_intent_without_submission(tmp_path):
    class UnavailableCheckout(SimulatedAircraftGateway):
        def read_checkout(self):
            raise TimeoutError("checkout reader timed out")

    worker = executor(tmp_path)
    gateway = UnavailableCheckout(checkout())
    result = worker.run(plan(), gateway)

    assert result["state"] == "APPROVED"
    assert result["reasons"] == ["checkout_indisponivel"]
    assert gateway.submit_calls == 0
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 0
    assert not worker.journal.executor_busy()


def test_submit_and_order_reader_timeouts_reconcile_without_resubmission(tmp_path):
    class SubmitTimeout(SimulatedAircraftGateway):
        def submit_order(self, intent):
            super().submit_order(intent)
            raise TimeoutError("submit response timed out")

    class ReaderTimeout(SimulatedAircraftGateway):
        def read_order_result(self, intent):
            raise TimeoutError("order list timed out")

    order_store = tmp_path / "timeout_order_book.sqlite3"
    worker = executor(tmp_path)
    gateway = SubmitTimeout(checkout(), order_store=order_store)
    result = worker.run(plan(), gateway)

    assert result["state"] == "UNKNOWN"
    assert gateway.submit_calls == 1
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 1
    assert not worker.journal.executor_busy()

    reader = ReaderTimeout(checkout(), order_store=order_store)
    still_unknown = executor(tmp_path).reconcile(result["intent_key"], reader)
    assert still_unknown["state"] == "UNKNOWN"
    assert reader.submit_calls == 0

    independent_reader = SimulatedAircraftGateway(checkout(), order_store=order_store)
    reconciled = executor(tmp_path).reconcile(result["intent_key"], independent_reader)
    assert reconciled["state"] == "CONFIRMED"
    assert independent_reader.submit_calls == 0
    assert gateway.submit_calls == 1
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 1


def test_malformed_order_reader_result_remains_unknown_without_resubmission(tmp_path):
    class MalformedReader(SimulatedAircraftGateway):
        def read_order_result(self, intent):
            return ["not", "evidence"]

    worker = executor(tmp_path)
    gateway = MalformedReader(checkout())

    result = worker.run(plan(), gateway)
    repeated = worker.run(plan(), gateway)

    assert result["state"] == "UNKNOWN"
    assert repeated["state"] == "UNKNOWN"
    assert gateway.submit_calls == 1
    assert worker.journal.get(result["intent_key"])["submit_attempts"] == 1


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


def test_crash_requires_explicit_guard_recovery_and_preserves_one_shot(tmp_path, monkeypatch):
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
    assert restarted.reconcile(result["intent_key"], gateway,
                             stopped_owner_token=result["stopped_owner_token"])["state"] == "BLOCKED"
    assert restarted.journal.executor_busy()

    independent_reader = SimulatedAircraftGateway(checkout(), outcome="confirmed",
                                                   order_store=order_store)
    monkeypatch.setattr(investment_journal, "_process_is_running", lambda _pid: False)
    assert restarted.reconcile(result["intent_key"], independent_reader,
                             stopped_owner_token=result["stopped_owner_token"])["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1
    assert independent_reader.submit_calls == 0
    assert restarted.journal.get(result["intent_key"])["submit_attempts"] == 1
    assert not restarted.journal.executor_busy()


def test_restart_reconciles_after_os_proves_previous_executor_exited(tmp_path, monkeypatch):
    order_store = tmp_path / "fake_order_book.sqlite3"
    worker = executor(tmp_path)
    crashed = worker.run(
        plan(), SimulatedAircraftGateway(checkout(), outcome="crash", order_store=order_store),
    )
    assert crashed["state"] == "SUBMITTED"

    restarted = executor(tmp_path)
    monkeypatch.setattr(investment_journal, "_process_is_running", lambda _pid: False)
    reader = SimulatedAircraftGateway(
        checkout(), outcome="confirmed", order_store=order_store,
    )
    reconciled = restarted.reconcile(crashed["intent_key"], reader)

    assert reconciled["state"] == "CONFIRMED"
    assert reader.submit_calls == 0
    assert restarted.journal.get(crashed["intent_key"])["submit_attempts"] == 1
    assert not restarted.journal.executor_busy()


@pytest.mark.parametrize(("policy_changes", "approved", "expected"), [
    ({"mode": "analyze"}, False, "somente_analise"),
    ({"mode": "approval"}, False, "aprovacao_explicita_pendente"),
    ({"enabled": False}, False, "politica_desabilitada_ou_invalida"),
    ({"auto_buy_aircraft": False}, False, "compra_automatica_desabilitada"),
    ({"max_single_investment": 9000}, False, "limite_por_compra"),
    ({"max_daily_spend": 0}, False, "limite_de_24h_nao_configurado"),
    ({"max_acquisitions_per_day": 0}, False, "maximo_de_aquisicoes_nao_configurado"),
    ({"max_cycle_spend": 0}, False, "limite_ciclo_nao_configurado"),
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


def test_cycle_limit_persists_after_restart_until_explicit_close(tmp_path):
    worker = executor(tmp_path, max_cycle_spend=15000)
    assert worker.run(plan(), SimulatedAircraftGateway(checkout()))["state"] == "CONFIRMED"
    cycle = worker.journal.active_cycle()
    restarted = executor(tmp_path, max_cycle_spend=15000)
    assert restarted.journal.active_cycle() == cycle
    second_plan = plan(plan_id="plan-2", destination_id="789")
    second_gateway = SimulatedAircraftGateway(checkout(destination_id="789"), purchase_id="987654322")
    assert restarted.run(second_plan, second_gateway)["reasons"] == ["limite_ciclo_esgotado"]
    assert second_gateway.submit_calls == 0
    with pytest.raises(ValueError, match="exclusividade"):
        restarted.journal.finish_cycle(cycle["cycle_id"], "unowned")
    assert restarted.journal.acquire_executor("coordinator")
    assert not restarted.journal.finish_cycle("wrong-cycle", "coordinator")
    assert restarted.journal.finish_cycle(cycle["cycle_id"], "coordinator")
    assert restarted.journal.release_executor("coordinator")
    assert restarted.journal.active_cycle() is None
    assert restarted.run(second_plan, second_gateway)["state"] == "CONFIRMED"
    assert restarted.journal.active_cycle()["cycle_id"] != cycle["cycle_id"]
    assert restarted.journal.budget_exposure_since(time.time() - 86400) == 20000


def test_cycle_cannot_close_with_unresolved_reservation(tmp_path):
    worker = executor(tmp_path, max_cycle_spend=15000)
    gateway = SimulatedAircraftGateway(checkout(engine_selected_id="other"))
    assert worker.run(plan(), gateway)["state"] == "APPROVED"
    cycle = worker.journal.active_cycle()
    assert worker.journal.acquire_executor("coordinator")
    assert not worker.journal.finish_cycle(cycle["cycle_id"], "coordinator")
    assert worker.journal.release_executor("coordinator")
    assert worker.journal.active_cycle() == cycle


def test_daily_count_blocks_second_simulated_acquisition_even_when_cash_allows(tmp_path):
    worker = executor(tmp_path, max_acquisitions_per_day=1)
    assert worker.run(plan(), SimulatedAircraftGateway(checkout()))["state"] == "CONFIRMED"
    assert worker.journal.acquisition_count_since(time.time() - 86400) == 1
    second_gateway = SimulatedAircraftGateway(checkout(destination_id="789"))
    second = worker.run(plan(plan_id="plan-2", destination_id="789"), second_gateway)
    assert second["state"] == "BLOCKED"
    assert second["reasons"] == ["limite_de_aquisicoes_em_24h"]
    assert second_gateway.submit_calls == 0


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


def test_different_ordered_cabin_remains_unknown_after_restart(tmp_path):
    class CheckoutChangedAfterPreflight(SimulatedAircraftGateway):
        def submit_order(self, intent):
            self.checkout["configuration_yjf"] = {"y": 102, "j": 9, "f": 1}
            super().submit_order(intent)

    seats = {"y": 100, "j": 10, "f": 1}
    candidate = plan(configuration_yjf=seats)
    observation = checkout(configuration_yjf=seats, price_includes_configuration=True)
    order_store = tmp_path / "orders.sqlite3"
    gateway = CheckoutChangedAfterPreflight(observation, order_store=order_store)
    result = executor(tmp_path).run(candidate, gateway)
    assert result["state"] == "UNKNOWN"
    assert gateway.submit_calls == 1

    restarted = executor(tmp_path)
    order_reader = SimulatedAircraftGateway(observation, order_store=order_store)
    key = result["intent_key"]
    stored = restarted.journal.get(key)
    assert stored["configuration_yjf"] == seats
    assert order_reader.read_order_result(stored)["configuration_yjf"] != seats
    assert restarted.reconcile(key, order_reader)["state"] == "UNKNOWN"
    assert restarted.run(candidate, order_reader)["state"] == "UNKNOWN"
    assert order_reader.submit_calls == 0


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


def test_concurrent_reconciliation_does_not_race_guard_acquisition(tmp_path):
    store = tmp_path / "orders.sqlite3"
    pending = executor(tmp_path).run(
        plan(), SimulatedAircraftGateway(checkout(), outcome="timeout", order_store=store),
    )
    first = executor(tmp_path)
    second = executor(tmp_path)
    second_ready = Event()
    first_reading = Event()
    release_first = Event()

    class PausedReader(SimulatedAircraftGateway):
        def read_order_result(self, intent):
            first_reading.set()
            assert release_first.wait(10)
            return super().read_order_result(intent)

    original_recover = second.journal.recover_submitted
    original_acquire = second.journal.acquire_executor

    def delayed_recovery(*args, **kwargs):
        second_ready.set()
        assert first_reading.wait(10)
        return original_recover(*args, **kwargs)

    def delayed_acquire(token):
        second_ready.set()
        assert first_reading.wait(10)
        return original_acquire(token)

    # Force an overlap between a stale guard check and a newly acquired guard.
    second.journal.recover_submitted = delayed_recovery
    second.journal.acquire_executor = delayed_acquire
    with ThreadPoolExecutor(max_workers=2) as pool:
        second_result = pool.submit(
            second.reconcile, pending["intent_key"],
            SimulatedAircraftGateway(checkout(), order_store=store),
        )
        assert second_ready.wait(10)
        first_result = pool.submit(
            first.reconcile, pending["intent_key"], PausedReader(checkout(), order_store=store),
        )
        assert first_reading.wait(10)
        try:
            assert second_result.result(timeout=10)["reasons"] == ["executor_ocupado"]
        finally:
            release_first.set()
        assert first_result.result(timeout=10)["state"] == "CONFIRMED"
    assert first.journal.get(pending["intent_key"])["submit_attempts"] == 1


def test_losing_confirmation_compare_and_set_reports_actual_terminal_state(tmp_path):
    store = tmp_path / "orders.sqlite3"
    pending = executor(tmp_path).run(
        plan(), SimulatedAircraftGateway(checkout(), outcome="timeout", order_store=store),
    )
    restarted = executor(tmp_path)

    class ConcurrentProof(SimulatedAircraftGateway):
        def read_order_result(self, intent):
            evidence = super().read_order_result(intent)
            assert restarted.journal.transition(
                intent["intent_key"], "UNKNOWN", "CONFIRMED", confirmation=evidence,
            )
            return evidence

    result = restarted.reconcile(
        pending["intent_key"], ConcurrentProof(checkout(), order_store=store),
    )
    assert result["state"] == "CONFIRMED"
    assert restarted.journal.get(pending["intent_key"])["state"] == "CONFIRMED"
    assert restarted.journal.get(pending["intent_key"])["submit_attempts"] == 1


def test_crash_restart_unknown_stays_blocked_through_multiple_reentries(tmp_path, monkeypatch):
    store = tmp_path / "orders.sqlite3"
    crashed = executor(tmp_path).run(
        plan(), SimulatedAircraftGateway(checkout(), outcome="crash", order_store=store),
    )
    restarted = executor(tmp_path)
    # The simulated crash leaves this pytest process alive. Model the OS
    # proving that the previous executor process has exited before recovery.
    monkeypatch.setattr(investment_journal, "_process_is_running", lambda _pid: False)
    missing_proof = SimulatedAircraftGateway(checkout(), outcome="timeout", order_store=store)
    assert restarted.reconcile(
        crashed["intent_key"], missing_proof,
        stopped_owner_token=crashed["stopped_owner_token"],
    )["state"] == "UNKNOWN"
    assert executor(tmp_path).reconcile(crashed["intent_key"], missing_proof)["state"] == "UNKNOWN"
    new_gateway = SimulatedAircraftGateway(checkout(destination_id="789"))
    assert restarted.run(plan(plan_id="plan-2", destination_id="789"), new_gateway)["state"] == "BLOCKED"
    assert new_gateway.submit_calls == 0
    assert restarted.journal.get(crashed["intent_key"])["submit_attempts"] == 1
    assert executor(tmp_path).reconcile(
        crashed["intent_key"], SimulatedAircraftGateway(checkout(), order_store=store),
    )["state"] == "CONFIRMED"
    assert restarted.journal.get(crashed["intent_key"])["submit_attempts"] == 1


def test_analyze_mode_does_not_write_intents_events_guards_or_orders(tmp_path):
    worker = executor(tmp_path, mode="analyze")
    gateway = SimulatedAircraftGateway(checkout(), order_store=tmp_path / "orders.sqlite3")

    def counts(db_path, tables):
        with sqlite3.connect(db_path) as conn:
            return [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in tables]

    journal_tables = ("intents", "events", "executor_guards")
    order_tables = ("fake_orders", "fake_rejections")
    before = counts(worker.journal.path, journal_tables)
    orders_before = counts(gateway.order_store, order_tables)
    assert worker.run(plan(), gateway)["state"] == "BLOCKED"
    assert counts(worker.journal.path, journal_tables) == before == [0, 0, 0]
    assert counts(gateway.order_store, order_tables) == orders_before == [0, 0]
    assert gateway.submit_calls == 0


def test_parallel_runs_only_one_checkout_per_profile_and_isolate_other_profiles(tmp_path):
    first = executor(tmp_path)
    competing = executor(tmp_path)
    other_profile = executor(tmp_path, profile="secondary")
    submitted = Event()
    allow_completion = Event()
    store = tmp_path / "shared_fake_orders.sqlite3"

    class PausedSubmission(SimulatedAircraftGateway):
        def submit_order(self, intent):
            super().submit_order(intent)
            submitted.set()
            assert allow_completion.wait(10)

    primary_gateway = PausedSubmission(checkout(), order_store=store)
    secondary_gateway = SimulatedAircraftGateway(
        checkout(profile="secondary"), order_store=store,
    )
    competing_gateway = SimulatedAircraftGateway(checkout(destination_id="789"), order_store=store)
    with ThreadPoolExecutor(max_workers=3) as pool:
        primary = pool.submit(first.run, plan(profile_id="principal"), primary_gateway)
        assert submitted.wait(10)
        blocked = pool.submit(
            competing.run, plan(plan_id="plan-2", destination_id="789"), competing_gateway,
        )
        secondary = pool.submit(
            other_profile.run, plan(profile_id="secondary"), secondary_gateway,
        )
        try:
            assert blocked.result(timeout=10)["reasons"] == ["executor_ocupado"]
            assert secondary.result(timeout=10)["state"] == "CONFIRMED"
        finally:
            allow_completion.set()
        assert primary.result(timeout=10)["state"] == "CONFIRMED"
    assert primary_gateway.submit_calls == 1
    assert competing_gateway.submit_calls == 0
    assert secondary_gateway.submit_calls == 1
    assert first.journal.unresolved()["count"] == 0
    assert other_profile.journal.unresolved()["count"] == 0


def test_cross_profile_plan_cannot_submit_or_leave_guard_held(tmp_path):
    worker = executor(tmp_path)
    gateway = SimulatedAircraftGateway(checkout())
    with pytest.raises(ValueError, match="perfil"):
        worker.run(plan(profile_id="secondary"), gateway)
    assert gateway.submit_calls == 0
    assert not worker.journal.executor_busy()
    with sqlite3.connect(worker.journal.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0


def test_reconcile_unknown_key_preserves_other_submitted_intents(tmp_path):
    worker = executor(tmp_path)
    intent, _ = worker.journal.register(plan())
    key = intent["intent_key"]
    assert worker.journal.transition(key, "PROPOSED", "APPROVED")
    assert worker.journal.transition(key, "APPROVED", "PRECHECKED")
    assert worker.journal.acquire_executor("first-owner")
    assert worker.journal.claim_submission(key, "first-owner")
    assert worker.journal.release_executor("first-owner")
    with pytest.raises(KeyError, match="Intenção"):
        worker.reconcile("sha256:" + "f" * 64, SimulatedAircraftGateway(checkout()))
    assert worker.journal.get(key)["state"] == "SUBMITTED"
    assert worker.journal.get(key)["submit_attempts"] == 1
