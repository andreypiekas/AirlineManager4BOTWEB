"""The worker re-evaluates the expansion planner even with no clients polling."""
import json
import time
from types import SimpleNamespace

import pytest

import paths
import planning_cycle
from audited_game_snapshot import capture_game_snapshot, snapshot_summary
from config import AppConfig
from conftest import ROOT
from web import WebDashboard


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("isolated"))
    monkeypatch.setattr(paths.Profile, "data", property(lambda self: tmp_path))
    config = AppConfig(settings_file=tmp_path / "settings.ini",
                       secrets_file=tmp_path / "secrets.ini", defaults_file=ROOT / "config/defaults.ini")
    return SimpleNamespace(config=config, dry_run=False, start=lambda: None,
                           stats=lambda: SimpleNamespace(money=2500, money_read_at=time.time() - 2))


def test_worker_replans_after_capture_with_real_a4_and_no_game_mutations(worker, tmp_path):
    first = planning_cycle.capture_and_plan(worker)
    result = planning_cycle.planning_cycle_summary()
    assert result["snapshot_id"] == first["snapshot_id"]
    assert result["status"] == "concluido"
    assert result["decision"] == "nao_comprar"
    assert result["evaluated_count"] == result["eligible_count"] == 0
    assert result["research"]["examined_combinations"] == 0
    assert result["research"]["sample_sweep_complete"] is False
    assert result["research"]["queue_blocking_reasons"]
    assert result["read_only"] and result["historical_only"]
    assert result["blocking_reasons"]
    assert not (tmp_path / "investment_journal.sqlite3").exists()
    from audited_economics_registry import AuditedEconomicsRegistry

    registry = AuditedEconomicsRegistry().snapshot()
    assert registry["snapshot_id"] == first["snapshot_id"]
    assert registry["status"] == "sem_avaliacoes"
    assert registry["sweep_published"] is True
    assert registry["evaluations"] == []
    assert registry["portfolio_evidence"]["research_coverage_verified"] is False
    assert registry["portfolio_evidence"]["commitments_verified"] is False
    assert registry["portfolio_evidence"]["controls"] == snapshot_summary()["policy_controls"]

    # New observations must invalidate the preceding decision until re-evaluated.
    worker.stats = lambda: SimpleNamespace(money=200, money_read_at=time.time() - 2)
    second = capture_game_snapshot(worker)
    assert second["snapshot_id"] != first["snapshot_id"]
    assert planning_cycle.planning_cycle_summary()["status"] == "coleta_alterada"
    third = planning_cycle.capture_and_plan(worker)
    result = planning_cycle.planning_cycle_summary()
    assert result["snapshot_id"] == third["snapshot_id"]
    assert result["decision"] == "nao_comprar"
    assert AuditedEconomicsRegistry().snapshot()["snapshot_id"] == third["snapshot_id"]
    assert planning_cycle.planning_cycle_summary(now=time.time() + 901)["status"] == "expirado"


def test_worker_failure_revokes_previous_result_and_hides_exception_text(worker, monkeypatch, tmp_path, caplog):
    planning_cycle.capture_and_plan(worker)

    def broken(self):
        assert planning_cycle.planning_cycle_summary()["status"] == "em_execucao"
        raise ValueError("private-account-detail")

    monkeypatch.setattr(WebDashboard, "audited_expansion", broken)
    with pytest.raises(RuntimeError, match="Falha no planejamento de expansão"):
        planning_cycle.capture_and_plan(worker)
    report = planning_cycle.planning_cycle_summary()
    assert report["status"] == "falhou" and report["decision"] is None
    assert "private-account-detail" not in caplog.text
    assert "private-account-detail" not in (tmp_path / planning_cycle.FILENAME).read_text(encoding="utf-8")


def test_worker_dry_run_does_not_publish_or_call_a4(worker, monkeypatch, tmp_path):
    worker.dry_run = True

    def forbidden(self):
        pytest.fail("Simulation must not consult productive A4")

    monkeypatch.setattr(WebDashboard, "audited_expansion", forbidden)
    assert planning_cycle.capture_and_plan(worker)["profile_id"] == "isolated"
    assert not (tmp_path / planning_cycle.FILENAME).exists()
    assert planning_cycle.planning_cycle_summary()["status"] == "sem_execucao"


@pytest.mark.parametrize("case_mode", ["complete", "missing", "mismatched", "second_page_invalid",
                                       "two_pages", "all_blocked"])
def test_worker_registers_complete_economics_before_a4(worker, monkeypatch, case_mode):
    from copy import deepcopy

    from audited_economics_registry import AuditedEconomicsRegistry
    from expansion_economics import evaluate_expansion_economics
    from opportunity_models import fingerprint_snapshot
    from test_expansion_economics import NOW, fixture

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    monkeypatch.setattr(time, "time", lambda: NOW)
    snapshot, candidate, inputs = fixture()
    snapshot["observations"] = {"captured_at": NOW}
    sid = snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    for envelope in (candidate, candidate["route"], candidate["aircraft"],
                     candidate["financial"], *candidate["costs"].values(), *inputs.values()):
        envelope["snapshot_id"] = sid
    result = evaluate_expansion_economics(snapshot, candidate, inputs, now=NOW)
    assert result["status"] == "evaluated", result["blocking_reasons"]
    capture = {"status": "parcial", "snapshot_id": sid, "captured_at": NOW,
               "scopes": snapshot["coverage"]["scopes"]}
    monkeypatch.setattr(planning_cycle, "capture_game_snapshot", lambda bot: snapshot)
    monkeypatch.setattr(planning_cycle, "snapshot_summary", lambda **kwargs: capture)
    monkeypatch.setattr("web.snapshot_summary", lambda **kwargs: capture)

    multi_page = case_mode in ("second_page_invalid", "two_pages")
    second_inputs = deepcopy(inputs)
    second_inputs["cash"]["value"]["available"] += 100
    second_result = evaluate_expansion_economics(snapshot, candidate, second_inputs, now=NOW)
    assert second_result["status"] == "evaluated"
    assert second_result["economics_id"] != result["economics_id"]

    def replay(**kwargs):
        offset = kwargs["offset"]
        evaluation = second_result if offset else result
        supplied = deepcopy(second_inputs if offset else inputs)
        blocked = case_mode == "all_blocked"
        if case_mode not in ("missing", "all_blocked"):
            if case_mode == "mismatched" or (offset and case_mode == "second_page_invalid"):
                supplied["cash"]["value"]["available"] += 100
            kwargs["on_evaluated"](evaluation["economics_id"], candidate, supplied, 0.10)
        return {"status": "parcial", "snapshot_id": sid, "historical_replay": True,
                "read_only": True, "purchase_eligible": False, "offset": offset,
                "cursor_reset": False, "total_candidates": 2 if multi_page else 1,
                "next_offset": 1 if multi_page and not offset else None,
                "snapshot_fingerprint": "a" * 24, "layout_fingerprint": "b" * 24,
                "blocking_reasons": [], "items": [{"accounting_gate": {
                    "economics_id": evaluation["economics_id"],
                    "status": "blocked" if blocked else "evaluated",
                    "blocking_reasons": [{"code": "demanda_ausente", "field": "daily_demand"}] if blocked else [],
                    "read_only": True, "purchase_eligible": False,
                    "layout_evaluations": [],
                }}]}

    monkeypatch.setattr(planning_cycle, "replay_research_page", replay)
    if case_mode in ("missing", "mismatched", "second_page_invalid"):
        with pytest.raises(RuntimeError, match="Falha no planejamento de expansão"):
            planning_cycle.capture_and_plan(worker)
        assert planning_cycle.planning_cycle_summary()["status"] == "falhou"
        assert AuditedEconomicsRegistry().snapshot()["evaluations"] == []
        return

    planning_cycle.capture_and_plan(worker)
    stored = AuditedEconomicsRegistry().snapshot()
    expected_results = [] if case_mode == "all_blocked" else [result, second_result] if multi_page else [result]
    assert stored["evaluations"] == expected_results
    assert stored["portfolio_evidence"]["research_coverage_verified"] is False
    assert stored["portfolio_evidence"]["commitments_verified"] is False
    report = planning_cycle.planning_cycle_summary()
    assert report["evaluated_count"] == len(expected_results) and report["eligible_count"] == 0
    assert report["decision"] == "nao_comprar"
    assert report["research"]["sample_sweep_complete"] is True
    assert report["research"]["blocked_combinations"] == (1 if case_mode == "all_blocked" else 0)
    assert report["research"]["coverage"] == "partial"
    assert "research_audit" not in report
    planning_cycle.capture_and_plan(worker)
    assert AuditedEconomicsRegistry().snapshot()["evaluations"] == expected_results
    # The oldest underlying observation expires before the capture itself.
    if expected_results:
        assert planning_cycle.planning_cycle_summary(now=NOW + 890)["status"] == "expirado"


def test_worker_summary_rejects_wrong_profile_and_invalid_record(worker, tmp_path):
    planning_cycle.capture_and_plan(worker)
    path = tmp_path / planning_cycle.FILENAME
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**record, "profile_id": "other"}), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"
    path.write_text(json.dumps({**record, "eligible_count": 5}), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"


def test_worker_summary_rejects_unpublished_empty_sweep(worker, tmp_path):
    from audited_economics_registry import AuditedEconomicsRegistry

    planning_cycle.capture_and_plan(worker)
    registry = AuditedEconomicsRegistry()
    stored = json.loads(registry.path.read_text(encoding="utf-8"))
    stored.pop("sweep_published")
    stored["portfolio"] = None
    registry.path.write_text(json.dumps(stored), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"


def test_worker_evaluates_sampled_combinations_and_layouts_with_real_replay(worker, monkeypatch, tmp_path):
    from audited_game_snapshot import FILENAME, compose_snapshot
    from test_audited_game_snapshot import NOW, observations
    from test_owned_hub_research_feed import _fleet_report, _inventory, _market, _preview_engines, _sample

    evidence = observations()
    monkeypatch.setattr(time, "time", lambda: evidence["now"])
    evidence.update(profile_id="isolated", inventory={**_inventory(), "hub_catalog_fresh": True},
                    routes=_fleet_report(), market=_market(), engines=_preview_engines(),
                    mode="realista", mode_at=NOW - 10,
                    quotes={kind: {"source": "game_market", "unit": "USD/1000", "price": price,
                                   "observed_at": NOW - 5, "expires_at": NOW + 60}
                            for kind, price in (("fuel", 600), ("co2", 100))})
    evidence["demand"]["samples"] = [_sample(dest=str(i)) for i in range(3139, 3200)]
    snapshot = compose_snapshot(**evidence)

    def capture(bot):
        (tmp_path / FILENAME).write_text(json.dumps(snapshot), encoding="utf-8")
        return snapshot

    monkeypatch.setattr(planning_cycle, "capture_game_snapshot", capture)
    planning_cycle.capture_and_plan(worker)
    result = planning_cycle.planning_cycle_summary()
    research = result["research"]
    assert result["snapshot_id"] == snapshot["snapshot_id"]
    assert research["pages"] == 2
    assert research["first_offset"] == 0 and research["next_offset"] == 80
    assert research["examined_combinations"] == research["blocked_combinations"] == 80
    assert research["total_sampled_combinations"] > 80
    assert research["hypothetical_layouts"] > 0
    assert research["sample_sweep_complete"] is False
    assert research["coverage"] == "partial"
    assert research["accounting_blocker_counts"]["DEMAND_UNVERIFIED"] >= 80
    assert result["evaluated_count"] == result["eligible_count"] == 0
    assert result["decision"] == "nao_comprar"
    path = tmp_path / planning_cycle.FILENAME
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["research_cursor"]["next_offset"] == 80
    audit = record["research_audit"]
    assert audit["snapshot_id"] == snapshot["snapshot_id"]
    assert [row["offset"] for row in audit["rows"]] == list(range(80))
    assert sum(len(row["evaluations"]) - 1 for row in audit["rows"]) == research["hypothetical_layouts"]
    assert "research_audit" not in result
    assert all("economics_id" not in row for row in result["research"].values() if isinstance(row, dict))
    from audited_game_snapshot import replay_research_page

    page = replay_research_page(now=NOW, expected_snapshot=snapshot["snapshot_id"])
    first_gate = page["items"][0]["accounting_gate"]
    assert audit["rows"][0]["evaluations"] == [
        {"economics_id": item["economics_id"], "blocking_reasons": item["blocking_reasons"]}
        for item in [first_gate, *first_gate["layout_evaluations"]]
    ]
    # A changed trace or aggregate cannot be presented as the original sweep.
    original_record = path.read_text(encoding="utf-8")
    record["research_audit"]["rows"][0]["evaluations"][0]["economics_id"] = "invalid"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"
    path.write_text(original_record, encoding="utf-8")
    saved_cursor = record["research_cursor"]
    # A failed A4 run cannot advance the successfully committed cursor.
    with monkeypatch.context() as context:
        def fail(self):
            raise ValueError("test failure")

        context.setattr(WebDashboard, "audited_expansion", fail)
        with pytest.raises(RuntimeError):
            planning_cycle.capture_and_plan(worker)
    assert planning_cycle.planning_cycle_summary()["status"] == "falhou"
    assert json.loads(path.read_text(encoding="utf-8"))["research_cursor"] == saved_cursor
    # A temporary missing catalog must also preserve the scheduling position.
    market = evidence["market"]
    evidence["market"] = {}
    evidence["now"] += 1
    snapshot = compose_snapshot(**evidence)
    planning_cycle.capture_and_plan(worker)
    assert planning_cycle.planning_cycle_summary()["research"]["queue_blocking_reasons"]
    assert json.loads(path.read_text(encoding="utf-8"))["research_cursor"] == saved_cursor
    evidence["market"] = market
    # Capture fresh financial observations with the same ordered identities.
    evidence["cash"] = 1500
    evidence["now"] += 1
    snapshot = compose_snapshot(**evidence)
    planning_cycle.capture_and_plan(worker)
    resumed = planning_cycle.planning_cycle_summary()
    assert resumed["snapshot_id"] != result["snapshot_id"]
    assert resumed["research"]["first_offset"] == 80
    assert resumed["research"]["examined_combinations"] == min(80, research["total_sampled_combinations"] - 80)
    assert resumed["research"]["sample_sweep_complete"] is False
    # A changed set of routes resets the cursor rather than skipping new identities.
    evidence["demand"]["samples"].pop(0)
    evidence["now"] += 1
    snapshot = compose_snapshot(**evidence)
    planning_cycle.capture_and_plan(worker)
    reset = planning_cycle.planning_cycle_summary()
    assert reset["research"]["first_offset"] == 0
    # Finish the remaining identities and verify the next cycle starts over.
    batch = reset["research"]
    total = batch["total_sampled_combinations"]
    for expected_offset in range(80, total, 80):
        planning_cycle.capture_and_plan(worker)
        batch = planning_cycle.planning_cycle_summary()["research"]
        assert batch["first_offset"] == expected_offset
        assert batch["sample_sweep_complete"] is False
    assert batch["next_offset"] is None
    assert json.loads(path.read_text(encoding="utf-8"))["research_cursor"] is None
    planning_cycle.capture_and_plan(worker)
    assert planning_cycle.planning_cycle_summary()["research"]["first_offset"] == 0
    record = json.loads(path.read_text(encoding="utf-8"))
    record["research"]["examined_combinations"] += 1
    path.write_text(json.dumps(record), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"


def test_worker_captures_policy_controls_and_revokes_changed_limits(worker):
    worker.config.set("investment", "planning_enabled", "on")
    worker.config.set("investment", "max_cycle_spend", 1200)
    worker.config.set("investment", "max_daily_spend", 2400)
    worker.config.set("settings", "cash_reserve", 0)
    snapshot = planning_cycle.capture_and_plan(worker)
    controls = snapshot_summary()["policy_controls"]
    assert {name: proof["value"] for name, proof in controls.items()} == {
        "operational_reserve": 0, "cycle_limit": 1200, "period_limit": 2400,
    }
    assert all(proof["source"] == "investment_policy" and proof["verified"] is True
               and proof["profile_id"] == "isolated" and proof["snapshot_id"] == snapshot["snapshot_id"]
               for proof in controls.values())
    dashboard = WebDashboard(worker, worker.config, buffer=None)
    reasons = dashboard.audited_expansion()["purchase_plan_blockers"]
    assert all(f"evidencia_{name}_a_confirmar" not in reasons for name in controls)
    assert "evidencia_period_spent_a_confirmar" in reasons
    worker.config.set("investment", "max_cycle_spend", 1500)
    reasons = dashboard.audited_expansion()["purchase_plan_blockers"]
    assert "evidencia_cycle_limit_a_confirmar" in reasons
    planning_cycle.capture_and_plan(worker)
    assert snapshot_summary()["policy_controls"]["cycle_limit"]["value"] == 1500
    assert "evidencia_cycle_limit_a_confirmar" not in dashboard.audited_expansion()["purchase_plan_blockers"]


def test_worker_applies_native_historical_spending_without_certifying_period(worker, tmp_path):
    from finance_observations import FILENAME, SOURCE

    worker.config.set("investment", "planning_enabled", "on")
    worker.config.set("investment", "max_cycle_spend", 1200)
    worker.config.set("investment", "max_daily_spend", 2400)
    worker.config.set("settings", "cash_reserve", 0)
    finance = {"source": SOURCE, "profile_id": "isolated", "observed_at": int(time.time()) - 5,
               "summary": {"window_hours": 24, "expenses": 4000, "income": 5000,
                           "result": 1000, "fuel_expenses": 100, "quota_expenses": 100,
                           "aircraft_orders": 2000, "hubs": 500, "route_fees": 200,
                           "ticket_income": 5000}}
    path = tmp_path / FILENAME
    path.write_text(json.dumps(finance), encoding="utf-8")
    snapshot = planning_cycle.capture_and_plan(worker)
    proof = snapshot_summary()["historical_investment_spending"]
    assert proof == {"source": SOURCE, "profile_id": "isolated", "snapshot_id": snapshot["snapshot_id"],
                     "verified": True, "historical_only": True, "window_hours": 24,
                     "observed_at": finance["observed_at"], "value": 2700}
    reasons = planning_cycle.planning_cycle_summary()["blocking_reasons"]
    assert "limite_periodo_esgotado_na_observacao" in reasons
    assert "evidencia_period_spent_a_confirmar" in reasons
    assert "compromissos_a_conciliar" in reasons
    assert snapshot_summary(now=finance["observed_at"] + 901)["historical_investment_spending"] is None
    path.write_text(json.dumps({**finance, "profile_id": "other"}), encoding="utf-8")
    planning_cycle.capture_and_plan(worker)
    assert snapshot_summary()["historical_investment_spending"] is None
    assert "limite_periodo_esgotado_na_observacao" not in planning_cycle.planning_cycle_summary()["blocking_reasons"]
    path.write_text(json.dumps({**finance, "summary": {**finance["summary"], "result": 0}}), encoding="utf-8")
    planning_cycle.capture_and_plan(worker)
    assert snapshot_summary()["historical_investment_spending"] is None
    assert "limite_periodo_esgotado_na_observacao" not in planning_cycle.planning_cycle_summary()["blocking_reasons"]
