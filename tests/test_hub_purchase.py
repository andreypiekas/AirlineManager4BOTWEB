"""End-to-end fake hub purchase, restart and two-stage safety checks."""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import investment_journal  # noqa: E402
from hub_purchase import (  # noqa: E402
    SimulatedHubExecutor,
    SimulatedHubGateway,
    validate_aircraft_after_hub,
    validate_hub_preflight,
)
from investment_journal import InvestmentJournal  # noqa: E402
from investment_policy import InvestmentPolicy  # noqa: E402


SNAPSHOT = "sha256:" + "a" * 64
NEW_SNAPSHOT = "sha256:" + "b" * 64


def _plan():
    return {"plan_id": "hub-proposal-1", "profile_id": "main", "kind": "hub",
            "hub_id": "123", "estimated_cost": 50000, "snapshot_id": SNAPSHOT}


def _checkout():
    return {"source": "simulation_hub_checkout", "verified": True,
            "observed_at": time.time(), "profile_id": "main", "snapshot_id": SNAPSHOT,
            "selected_hub_id": "123", "before_owned": False,
            "can_purchase": True, "final_price": 50000,
            "available_cash": 100000, "required_points": 200,
            "available_points": 250}


def _policy(*, mode="approval", auto_buy_hub=False):
    return InvestmentPolicy(enabled=True, valid=True, mode=mode,
                            auto_buy_hub=auto_buy_hub, max_single_investment=100000,
                            max_daily_spend=200000, max_acquisitions_per_day=2)


def _env(tmp_path, *, outcome="confirmed", mode="approval", auto_buy_hub=False):
    journal = InvestmentJournal(tmp_path / "journal.sqlite3", profile_id="main",
                                simulation=True)
    executor = SimulatedHubExecutor(journal, _policy(mode=mode,
                                                     auto_buy_hub=auto_buy_hub))
    gateway = SimulatedHubGateway(_checkout(), outcome=outcome,
                                  ownership_store=tmp_path / "owned.sqlite3")
    return journal, executor, gateway


def _aircraft_plan():
    return {"plan_id": "aircraft-1", "kind": "aircraft", "profile_id": "main",
            "snapshot_id": NEW_SNAPSHOT, "hub_id": "123", "origin_id": "123",
            "destination_id": "456", "model_id": "A380-800", "engine_id": "EA1",
            "estimated_cost": 150000}


def _ownership(intent):
    return {"source": "simulation_owned_hubs", "verified": True,
            "profile_id": "main", "snapshot_id": NEW_SNAPSHOT,
            "hub_id": "123", "after_owned": True, "coverage_complete": True,
            "observed_at": time.time()}


def test_simulated_hub_requires_explicit_approval_and_proven_ownership(tmp_path):
    journal, executor, gateway = _env(tmp_path)
    blocked = executor.run(_plan(), gateway)
    assert blocked["state"] == "BLOCKED"
    assert gateway.submit_calls == 0

    bought = executor.run(_plan(), gateway, approved=True)
    assert bought["state"] == "CONFIRMED"
    assert bought["simulated"] is True
    assert gateway.submit_calls == 1
    intent = journal.get(bought["intent_key"])
    assert intent["state"] == "CONFIRMED"

    phase_two = validate_aircraft_after_hub(intent, _aircraft_plan(), _ownership(intent))
    assert phase_two["ready"] is True
    assert executor.run(_plan(), gateway, approved=True)["state"] == "CONFIRMED"
    assert gateway.submit_calls == 1


def test_after_hub_requires_new_snapshot_and_independent_complete_scan(tmp_path):
    journal, executor, gateway = _env(tmp_path)
    result = executor.run(_plan(), gateway, approved=True)
    intent = journal.get(result["intent_key"])
    aircraft = _aircraft_plan()
    ownership = _ownership(intent)
    assert validate_aircraft_after_hub(intent, aircraft, ownership)["ready"]
    for change in ({"snapshot_id": SNAPSHOT}, {"hub_id": "999"},
                   {"profile_id": "other"}):
        assert not validate_aircraft_after_hub(intent, {**aircraft, **change},
                                               ownership)["ready"]
    for change in ({"source": "guess"}, {"verified": False},
                   {"coverage_complete": False}, {"snapshot_id": SNAPSHOT},
                   {"observed_at": intent["updated_at"] - 100},
                   {"after_owned": None}):
        assert not validate_aircraft_after_hub(intent, aircraft,
                                               {**ownership, **change})["ready"]


@pytest.mark.parametrize("outcome", ["timeout", "crash"])
def test_timeout_and_restart_never_repurchase_hub(tmp_path, outcome):
    journal, executor, gateway = _env(tmp_path, outcome=outcome)
    first = executor.run(_plan(), gateway, approved=True)
    assert first["state"] in ("UNKNOWN", "SUBMITTED")
    assert gateway.submit_calls == 1

    restarted = SimulatedHubExecutor(
        InvestmentJournal(tmp_path / "journal.sqlite3", profile_id="main",
                          simulation=True), _policy())
    reopened_gateway = SimulatedHubGateway(_checkout(), outcome="confirmed",
                                           ownership_store=tmp_path / "owned.sqlite3")
    retry = restarted.run(_plan(), reopened_gateway, approved=True)
    assert retry["state"] == ("BLOCKED" if outcome == "crash" else first["state"])
    assert reopened_gateway.submit_calls == 0
    reconciled = restarted.reconcile(first["intent_key"], reopened_gateway,
                                    stopped_owner_token=first.get("stopped_owner_token"))
    assert reconciled["state"] == "CONFIRMED"
    assert reopened_gateway.submit_calls == 0
    assert journal.get(first["intent_key"])["state"] == "CONFIRMED"


def test_hub_restart_reconciles_stale_guard_without_repeating_order(tmp_path, monkeypatch):
    journal, executor, gateway = _env(tmp_path, outcome="crash")
    first = executor.run(_plan(), gateway, approved=True)
    assert first["state"] == "SUBMITTED"

    restarted = SimulatedHubExecutor(
        InvestmentJournal(tmp_path / "journal.sqlite3", profile_id="main",
                          simulation=True), _policy())
    monkeypatch.setattr(investment_journal, "_process_is_running", lambda _pid: False)
    reader = SimulatedHubGateway(_checkout(), outcome="confirmed",
                                 ownership_store=tmp_path / "owned.sqlite3")
    result = restarted.reconcile(first["intent_key"], reader)

    assert result["state"] == "CONFIRMED"
    assert reader.submit_calls == 0
    assert journal.get(first["intent_key"])["submit_attempts"] == 1
    assert not journal.executor_busy()


def test_refused_hub_purchase_recorded_as_failure_without_repeat(tmp_path):
    _, executor, gateway = _env(tmp_path, outcome="refused")
    result = executor.run(_plan(), gateway, approved=True)
    assert result["state"] == "FAILED"
    assert executor.run(_plan(), gateway, approved=True)["state"] == "FAILED"
    assert gateway.submit_calls == 1


def test_policy_and_checkout_fail_closed(tmp_path):
    _, executor, gateway = _env(tmp_path, mode="analyze")
    assert executor.run(_plan(), gateway, approved=True)["state"] == "BLOCKED"
    assert gateway.submit_calls == 0
    _, executor, gateway = _env(tmp_path / "autonomous", mode="autonomous")
    assert executor.run(_plan(), gateway)["state"] == "BLOCKED"
    assert gateway.submit_calls == 0
    _, executor, gateway = _env(tmp_path / "autonomous-enabled", mode="autonomous",
                                auto_buy_hub=True)
    assert executor.run(_plan(), gateway)["state"] == "CONFIRMED"

    for update in ({"selected_hub_id": "999"}, {"final_price": 52000},
                   {"available_points": 0}, {"before_owned": True},
                   {"can_purchase": False}, {"profile_id": "other"},
                   {"snapshot_id": NEW_SNAPSHOT}, {"observed_at": time.time() - 901},
                   {"available_cash": 1}, {"required_points": None}):
        result = validate_hub_preflight({**_plan()}, {**_checkout(), **update})
        assert result["ready"] is False


def test_reserve_and_wrong_profile_cannot_submit(tmp_path):
    _, executor, gateway = _env(tmp_path)
    result = executor.run(_plan(), gateway, approved=True, reserve=80000)
    assert result["state"] == "APPROVED"
    assert "caixa_ou_reserva_insuficiente" in result["reasons"]
    assert gateway.submit_calls == 0
    gateway.checkout["profile_id"] = "other"
    result = executor.run(_plan(), gateway, approved=True)
    assert result["state"] == "APPROVED"
    assert gateway.submit_calls == 0


@pytest.mark.parametrize(
    ("outcome", "expected_first_state"),
    [("confirmed", "CONFIRMED"), ("timeout", "UNKNOWN"), ("crash", "SUBMITTED")],
)
def test_different_intent_cannot_repurchase_owned_hub_after_restart(
    tmp_path, outcome, expected_first_state
):
    _, first_executor, gateway = _env(tmp_path, outcome=outcome)
    first = first_executor.run(_plan(), gateway, approved=True)
    assert first["state"] == expected_first_state

    second_gateway = SimulatedHubGateway(
        _checkout(), ownership_store=tmp_path / "owned.sqlite3"
    )
    second_plan = {**_plan(), "plan_id": "hub-proposal-2"}
    checkout = second_gateway.read_checkout()
    assert checkout["before_owned"] is True
    assert checkout["can_purchase"] is False

    second_journal = InvestmentJournal(
        tmp_path / "second-journal.sqlite3", profile_id="main", simulation=True
    )
    second_executor = SimulatedHubExecutor(second_journal, _policy())
    second = second_executor.run(second_plan, second_gateway, approved=True)
    assert second["state"] == "APPROVED"
    assert "hub_ja_adquirido_ou_indisponivel" in second["reasons"]
    assert second_gateway.submit_calls == 0

    with pytest.raises(AssertionError, match="recompra"):
        second_gateway.submit_order({
            "profile_id": "main",
            "intent_key": "different-intent-key",
            "hub_id": "123",
        })
    assert second_gateway.submit_calls == 0


def test_refused_hub_does_not_mark_ownership_for_another_intent(tmp_path):
    _, _, gateway = _env(tmp_path, outcome="refused")
    gateway.submit_order({
        "profile_id": "main", "intent_key": "refused-intent", "hub_id": "123"
    })

    retry_gateway = SimulatedHubGateway(
        _checkout(), ownership_store=tmp_path / "owned.sqlite3"
    )
    checkout = retry_gateway.read_checkout()
    assert checkout["before_owned"] is False
    assert checkout["can_purchase"] is True
    retry_gateway.submit_order({
        "profile_id": "main", "intent_key": "retry-intent", "hub_id": "123"
    })
    assert retry_gateway.submit_calls == 1


def test_hub_ownership_is_isolated_by_profile(tmp_path):
    _, _, main_gateway = _env(tmp_path)
    main_gateway.submit_order({
        "profile_id": "main", "intent_key": "main-intent", "hub_id": "123"
    })

    other_checkout = {**_checkout(), "profile_id": "other"}
    other_gateway = SimulatedHubGateway(
        other_checkout, ownership_store=tmp_path / "owned.sqlite3"
    )
    assert other_gateway.read_checkout()["before_owned"] is False
    other_gateway.submit_order({
        "profile_id": "other", "intent_key": "other-intent", "hub_id": "123"
    })
    assert other_gateway.submit_calls == 1


def test_concurrent_intents_cannot_acquire_same_hub_twice(tmp_path):
    ownership_store = tmp_path / "owned.sqlite3"
    gateways = [
        SimulatedHubGateway(_checkout(), ownership_store=ownership_store)
        for _ in range(2)
    ]
    intents = [
        {"profile_id": "main", "intent_key": f"intent-{index}", "hub_id": "123"}
        for index in range(2)
    ]

    def submit(gateway, intent):
        try:
            gateway.submit_order(intent)
        except AssertionError:
            return "duplicate"
        return "submitted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, gateways, intents))

    assert results.count("submitted") == 1
    assert results.count("duplicate") == 1
    assert sum(gateway.submit_calls for gateway in gateways) == 1
