"""Crash-safe simulated acquisition intents. No game or Selenium calls."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from investment_journal import IntentConflict, InvestmentJournal


SNAPSHOT = "sha256:" + "a" * 64


def aircraft_plan(**changes):
    plan = {
        "plan_id": "candidate-123", "snapshot_id": SNAPSHOT,
        "kind": "aircraft", "hub_id": "123", "origin_id": "123",
        "destination_id": "456", "model_id": "A320", "engine_id": "motor-2",
        "estimated_cost": 10000,
    }
    plan.update(changes)
    return plan


def aircraft_proof(**changes):
    proof = {
        "source": "game_order_list", "profile_id": "principal",
        "verified": True, "observed_at": time.time(), "purchase_id": "98765",
        "hub_id": "123", "origin_id": "123", "destination_id": "456",
        "model_id": "A320", "engine_id": "motor-2",
    }
    proof.update(changes)
    return proof


def journal(tmp_path, profile="principal"):
    return InvestmentJournal(tmp_path / "intents.sqlite3", profile_id=profile)


def ready(journal_instance, plan=None):
    intent, created = journal_instance.register(plan or aircraft_plan())
    assert created
    key = intent["intent_key"]
    assert journal_instance.transition(key, "PROPOSED", "APPROVED")
    assert journal_instance.transition(key, "APPROVED", "PRECHECKED")
    return key


def test_registration_is_durable_idempotent_and_conflicts_on_replanned_route(tmp_path):
    first = journal(tmp_path)
    intent, created = first.register(aircraft_plan())
    assert created and intent["state"] == "PROPOSED"
    assert intent["submit_attempts"] == 0
    assert len(first.history(intent["intent_key"])) == 1
    assert first.history(intent["intent_key"])[0]["new_state"] == "PROPOSED"

    again, created = journal(tmp_path).register(aircraft_plan())
    assert not created and again == intent
    for modified in (aircraft_plan(engine_id="motor-3"),
                     aircraft_plan(model_id="B737"),
                     aircraft_plan(snapshot_id="sha256:" + "b" * 64)):
        with pytest.raises(IntentConflict):
            journal(tmp_path).register(modified)

    another_route, created = first.register(aircraft_plan(
        destination_id="789", plan_id="candidate-789"))
    assert created and another_route["intent_key"] != intent["intent_key"]
    isolated = journal(tmp_path, "secundario")
    own_intent, created = isolated.register(aircraft_plan())
    assert created and own_intent["profile_id"] == "secundario"
    assert isolated.get(intent["intent_key"]) is None
    assert first.get(own_intent["intent_key"]) is None
    assert isolated.history(own_intent["intent_key"])[0]["new_state"] == "PROPOSED"


def test_explicit_plan_profile_must_match_journal_profile(tmp_path):
    ledger = journal(tmp_path)
    with pytest.raises(ValueError, match="perfil"):
        ledger.register(aircraft_plan(profile_id="secundario"))
    assert ledger.unresolved()["count"] == 0
    intent, created = ledger.register(aircraft_plan(profile_id="principal"))
    assert created and intent["profile_id"] == "principal"
    assert len(ledger.history(intent["intent_key"])) == 1


def test_concurrent_registration_creates_one_intent_and_one_event(tmp_path):
    ledger = journal(tmp_path)

    def register(_index):
        return journal(tmp_path).register(aircraft_plan())

    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(register, range(16)))
    assert sum(created for _intent, created in attempts) == 1
    keys = {intent["intent_key"] for intent, _created in attempts}
    assert len(keys) == 1
    assert len(ledger.history(keys.pop())) == 1


def test_invalid_plans_and_unauthorized_transitions_fail_closed(tmp_path):
    ledger = journal(tmp_path)
    for changes in ({"hub_id": "unknown"}, {"origin_id": "987"},
                    {"destination_id": "123"}, {"engine_id": "default"},
                    {"model_id": None}, {"estimated_cost": -5},
                    {"estimated_cost": 1.2}, {"estimated_cost": True},
                    {"snapshot_id": "stale"}, {"kind": "unknown"}):
        with pytest.raises(ValueError):
            ledger.register(aircraft_plan(**changes))
    with pytest.raises(ValueError):
        ledger.register(None)
    intent, _ = ledger.register(aircraft_plan())
    with pytest.raises(ValueError):
        ledger.transition(intent["intent_key"], "PROPOSED", "SUBMITTED")
    key = ready(journal(tmp_path), aircraft_plan(destination_id="789"))
    with pytest.raises(ValueError, match="Transição inválida"):
        ledger.transition(key, "PRECHECKED", "SUBMITTED")
    with pytest.raises(KeyError):
        ledger.transition("sha256:" + "f" * 64, "PROPOSED", "APPROVED")
    assert ledger.get("garbage") is None
    assert ledger.history("garbage") == []


def test_submitted_is_claimed_once_even_with_concurrent_workers(tmp_path):
    ledger = journal(tmp_path)
    key = ready(ledger)
    assert ledger.unresolved()["estimated_exposure"] == 10000

    def claim(_index):
        worker = journal(tmp_path)
        owner = f"worker-{_index}"
        if not worker.acquire_executor(owner):
            return False
        try:
            return worker.claim_submission(key, owner)
        finally:
            worker.release_executor(owner)

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(16)))
    assert claims.count(True) == 1
    assert claims.count(False) == 15
    assert journal(tmp_path).get(key)["submit_attempts"] == 1
    assert [event["new_state"] for event in ledger.history(key)] == [
        "PROPOSED", "APPROVED", "PRECHECKED", "SUBMITTED",
    ]


def test_restart_quarantines_timeout_and_requires_plan_specific_game_proof(tmp_path):
    ledger = journal(tmp_path)
    key = ready(ledger)
    assert ledger.acquire_executor("original-worker")
    assert ledger.claim_submission(key, "original-worker")
    assert ledger.release_executor("original-worker")
    restarted = journal(tmp_path)
    assert restarted.recover_submitted() == 1
    assert restarted.recover_submitted() == 0
    assert restarted.get(key)["state"] == "UNKNOWN"
    assert restarted.get(key)["submit_attempts"] == 1
    assert not restarted.transition(key, "SUBMITTED", "CONFIRMED",
                                    confirmation=aircraft_proof())
    assert restarted.unresolved()["estimated_exposure"] == 10000

    invalid_proofs = (
        aircraft_proof(engine_id="motor-3"),
        aircraft_proof(model_id="B737"),
        aircraft_proof(hub_id="999"),
        aircraft_proof(origin_id="999"),
        aircraft_proof(destination_id="999"),
        aircraft_proof(profile_id="secundario"),
        aircraft_proof(purchase_id="unknown"),
        aircraft_proof(source="click_notification"),
        aircraft_proof(verified=False),
        aircraft_proof(observed_at=time.time() - 901),
        aircraft_proof(observed_at=time.time() + 901),
    )
    for proof in invalid_proofs:
        with pytest.raises(ValueError):
            restarted.transition(key, "UNKNOWN", "CONFIRMED", confirmation=proof)
    assert restarted.get(key)["state"] == "UNKNOWN"

    proof = aircraft_proof(session_secret="should-never-persist")
    assert restarted.transition(key, "UNKNOWN", "CONFIRMED", confirmation=proof)
    assert restarted.unresolved()["count"] == 0
    assert not restarted.transition(key, "UNKNOWN", "CONFIRMED", confirmation=proof)
    assert restarted.get(key)["submit_attempts"] == 1
    assert restarted.history(key)[-1]["evidence"]["purchase_id"] == "98765"
    assert "session_secret" not in restarted.history(key)[-1]["evidence"]


def test_recover_submitted_under_guard_requires_matching_owner(tmp_path):
    ledger = journal(tmp_path)
    key = ready(ledger)
    assert ledger.acquire_executor("active-worker")
    assert ledger.claim_submission(key, "active-worker")
    with pytest.raises(RuntimeError, match="exclusividade"):
        ledger.recover_submitted(owner_token="stranger")
    with pytest.raises(RuntimeError, match="executor registrado"):
        ledger.recover_submitted()
    assert ledger.get(key)["state"] == "SUBMITTED"
    assert ledger.recover_submitted(owner_token="active-worker") == 1
    assert ledger.get(key)["state"] == "UNKNOWN"
    assert ledger.get(key)["submit_attempts"] == 1
    assert ledger.release_executor("active-worker")


def test_failed_intent_releases_reservation_from_exposure(tmp_path):
    ledger = journal(tmp_path)
    key = ready(ledger)
    assert ledger.transition(key, "PRECHECKED", "FAILED")
    assert ledger.unresolved()["estimated_exposure"] == 0
    assert ledger.get(key)["state"] == "FAILED"
    with pytest.raises(ValueError):
        ledger.transition(key, "FAILED", "SUBMITTED")


def test_hub_purchase_requires_independent_ownership_transition(tmp_path):
    ledger = journal(tmp_path)
    plan = {"plan_id": "new-hub", "snapshot_id": SNAPSHOT, "kind": "hub",
            "hub_id": "777", "estimated_cost": 50000}
    key = ready(ledger, plan)
    assert ledger.acquire_executor("hub-worker")
    assert ledger.claim_submission(key, "hub-worker")
    assert ledger.release_executor("hub-worker")
    proof = {"source": "game_owned_hubs", "profile_id": "principal",
             "verified": True, "observed_at": time.time(), "hub_id": "777",
             "before_owned": False, "after_owned": True}
    with pytest.raises(ValueError):
        ledger.transition(key, "SUBMITTED", "CONFIRMED",
                          confirmation={**proof, "before_owned": True})
    with pytest.raises(ValueError):
        ledger.transition(key, "SUBMITTED", "CONFIRMED",
                          confirmation={**proof, "source": "game_order_list"})
    assert ledger.transition(key, "SUBMITTED", "CONFIRMED", confirmation=proof)
    assert ledger.unresolved()["count"] == 0


def test_confirmed_purchase_receipt_cannot_be_reused_after_restart(tmp_path):
    path = tmp_path / "simulated_intents.sqlite3"
    ledger = InvestmentJournal(path, profile_id="principal", simulation=True)
    first_key = ready(ledger)
    second_key = ready(ledger, aircraft_plan(
        plan_id="candidate-789", destination_id="789"))
    assert ledger.acquire_executor("worker")
    try:
        assert ledger.claim_submission(first_key, "worker")
        assert ledger.transition(first_key, "SUBMITTED", "CONFIRMED", confirmation={
            **aircraft_proof(), "source": "simulation_order_list",
        })
        assert ledger.claim_submission(second_key, "worker")
    finally:
        assert ledger.release_executor("worker")

    restarted = InvestmentJournal(path, profile_id="principal", simulation=True)
    reused_receipt = aircraft_proof(
        source="simulation_order_list", destination_id="789")
    with pytest.raises(ValueError, match="comprovante"):
        restarted.transition(second_key, "SUBMITTED", "CONFIRMED",
                             confirmation=reused_receipt)
    assert restarted.get(second_key)["state"] == "SUBMITTED"
    assert [event["new_state"] for event in restarted.history(second_key)] == [
        "PROPOSED", "APPROVED", "PRECHECKED", "SUBMITTED",
    ]
    assert restarted.recover_submitted() == 1
    with pytest.raises(ValueError, match="comprovante"):
        restarted.transition(second_key, "UNKNOWN", "CONFIRMED",
                             confirmation=reused_receipt)
    assert restarted.get(second_key)["state"] == "UNKNOWN"
    assert restarted.transition(second_key, "UNKNOWN", "CONFIRMED",
                                confirmation={**reused_receipt, "purchase_id": "98766"})
    assert restarted.get(second_key)["state"] == "CONFIRMED"
