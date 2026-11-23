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
    with pytest.raises(KeyError):
        ledger.transition("sha256:" + "f" * 64, "PROPOSED", "APPROVED")
    assert ledger.get("garbage") is None
    assert ledger.history("garbage") == []


def test_submitted_is_claimed_once_even_with_concurrent_workers(tmp_path):
    ledger = journal(tmp_path)
    key = ready(ledger)
    assert ledger.unresolved()["estimated_exposure"] == 10000

    def claim(_index):
        return journal(tmp_path).transition(key, "PRECHECKED", "SUBMITTED")

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
    assert ledger.transition(key, "PRECHECKED", "SUBMITTED")
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
    assert ledger.transition(key, "PRECHECKED", "SUBMITTED")
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
