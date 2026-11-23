"""A9 operating metrics use local evidence and preserve unknown game facts."""

from __future__ import annotations

import time

import pytest

from expansion_metrics import build_expansion_metrics
from investment_journal import InvestmentJournal


SNAPSHOT = "sha256:" + "a" * 64


def _journal(tmp_path, profile="principal", simulation=True):
    return InvestmentJournal(tmp_path / "audit.sqlite3", profile_id=profile,
                             simulation=simulation)


def _plan(destination="456", kind="aircraft"):
    plan = {"plan_id": "plan-" + destination, "snapshot_id": SNAPSHOT,
            "kind": kind, "hub_id": "123", "estimated_cost": 20000}
    if kind == "aircraft":
        plan.update(origin_id="123", destination_id=destination,
                    model_id="A320", engine_id="engine-1")
    return plan


def _confirmed(journal, destination="456", *, uncertain=False):
    intent, _ = journal.register(_plan(destination))
    key = intent["intent_key"]
    assert journal.transition(key, "PROPOSED", "APPROVED")
    assert journal.transition(key, "APPROVED", "PRECHECKED")
    assert journal.acquire_executor("worker")
    try:
        assert journal.claim_submission(key, "worker")
    finally:
        assert journal.release_executor("worker")
    if uncertain:
        assert journal.transition(key, "SUBMITTED", "UNKNOWN")
    proof = {"source": "simulation_order_list", "profile_id": journal.profile_id,
             "verified": True, "observed_at": time.time(), "purchase_id": "777",
             "hub_id": "123", "origin_id": "123", "destination_id": destination,
             "model_id": "A320", "engine_id": "engine-1"}
    assert journal.transition(key, "UNKNOWN" if uncertain else "SUBMITTED",
                              "CONFIRMED", confirmation=proof)


def test_empty_metrics_do_not_invent_game_purchase_or_profits(tmp_path):
    journal = _journal(tmp_path)
    report = build_expansion_metrics(journal, now=time.time())
    assert report["read_only"] is True
    assert report["environment"] == "simulation"
    assert report["journal"]["total_intents"] == 0
    assert report["journal"]["pending_planned_cost"] == 0
    assert report["journal"]["mean_recovery_seconds"] is None
    assert report["research_coverage"]["hubs_total"] is None
    assert report["opportunities"]["evaluated_count"] is None
    assert report["forecast"]["mean_absolute_daily_error"] is None
    assert report["actual_spend"] is None
    assert report["verified_deliveries"] is None
    assert report["verified_spend_avoided"] is None


def test_journal_events_are_scoped_and_persist_across_restart(tmp_path):
    first = _journal(tmp_path)
    _confirmed(first, uncertain=True)
    pending, _ = first.register(_plan("789"))
    assert first.transition(pending["intent_key"], "PROPOSED", "APPROVED")
    other = _journal(tmp_path, "segundo")
    _confirmed(other)

    audit = _journal(tmp_path).audit_metrics(time.time() - 3600)
    assert audit["profile_id"] == "principal"
    assert audit["source"] == "local_investment_journal"
    assert audit["total_intents"] == 2
    assert audit["by_state"]["CONFIRMED"] == 1
    assert audit["by_state"]["APPROVED"] == 1
    assert audit["pending_planned_cost"] == 20000
    assert audit["confirmed_planned_cost_in_window"] == 20000
    assert audit["reconciliations_from_unknown"] == 1
    assert audit["mean_recovery_seconds"] is not None
    assert audit["submit_attempts_total"] == 1

    second = other.audit_metrics(time.time() - 3600)
    assert second["total_intents"] == 1
    assert second["pending_planned_cost"] == 0
    assert second["reconciliations_from_unknown"] == 0


def test_metrics_window_counts_current_reservations_but_not_old_events(tmp_path):
    journal = _journal(tmp_path)
    _confirmed(journal)
    tomorrow = time.time() + 86400
    audit = journal.audit_metrics(tomorrow)
    assert audit["total_intents"] == 1
    assert audit["created_in_window"] == 0
    assert audit["confirmed_in_window"] == 0
    assert audit["confirmed_planned_cost_in_window"] == 0
    assert audit["last_event_at"] is None
    with pytest.raises(ValueError):
        journal.audit_metrics(float("nan"))
    with pytest.raises(ValueError):
        build_expansion_metrics(journal, now=True)
    with pytest.raises(ValueError):
        build_expansion_metrics(journal, window_days=366)


def test_partial_coverage_and_portfolio_are_evidence_labeled(tmp_path):
    research = {
        "research_queue": {"coverage": "partial", "has_more": True,
                           "hub_coverage": [
                               {"status": "pesquisa_iniciada", "coverage": "partial"},
                               {"status": "nao_pesquisado", "coverage": "partial"}],
                           "items": [{"hub_id": "123"}]},
        "portfolio": {"status": "inconclusivo", "evaluated_count": 5,
                      "eligible_count": 0},
    }
    report = build_expansion_metrics(_journal(tmp_path),
                                     opportunity_report=research)
    assert report["research_coverage"] == {
        "status": "partial", "hubs_total": 2, "hubs_pesquisados": 1,
        "research_tasks_shown": 1, "has_more_tasks": True,
    }
    assert report["opportunities"] == {
        "status": "inconclusivo", "source": "portfolio_planner",
        "evaluated_count": 5, "eligible_count": 0,
    }
    assert "pesquisa_incompleta" in report["blocking_reasons"]


def test_calibration_only_counts_conclusive_same_profile_unique_plans(tmp_path):
    journal = _journal(tmp_path)
    def row(plan, days, flights, error, **updates):
        data = {"status": "conclusivo", "profile_id": "principal",
                "plan_id": plan, "reasons": [],
                "metrics": {"complete_days": days, "independent_flights": flights,
                            "mean_absolute_daily_error": error}}
        data.update(updates)
        return data

    reports = [row("one", 3, 5, 12), row("two", 5, 6, 20),
               row("foreign", 4, 5, 999, profile_id="segundo"),
               row("three", 3, 4, 1), row("three", 3, 4, 1),
               row("three", 3, 4, 1)]
    result = build_expansion_metrics(journal, calibration_reports=reports)
    assert result["forecast"] == {
        "status": "calibracao_verificada", "plans": 2,
        "complete_days": 8, "independent_flights": 11,
        "mean_absolute_daily_error": 17.0,
    }
    assert result["actual_spend"] is None
    inconclusive = build_expansion_metrics(journal, calibration_reports=[
        row("bad", 3, 3, 10, status="inconclusivo"),
    ])
    assert inconclusive["forecast"]["mean_absolute_daily_error"] is None
