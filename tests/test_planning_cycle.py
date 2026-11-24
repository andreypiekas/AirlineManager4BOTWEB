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
    assert result["read_only"] and result["historical_only"]
    assert result["blocking_reasons"]
    assert not (tmp_path / "investment_journal.sqlite3").exists()

    # New observations must invalidate the preceding decision until re-evaluated.
    worker.stats = lambda: SimpleNamespace(money=200, money_read_at=time.time() - 2)
    second = capture_game_snapshot(worker)
    assert second["snapshot_id"] != first["snapshot_id"]
    assert planning_cycle.planning_cycle_summary()["status"] == "coleta_alterada"
    third = planning_cycle.capture_and_plan(worker)
    result = planning_cycle.planning_cycle_summary()
    assert result["snapshot_id"] == third["snapshot_id"]
    assert result["decision"] == "nao_comprar"
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


def test_worker_summary_rejects_wrong_profile_and_invalid_record(worker, tmp_path):
    planning_cycle.capture_and_plan(worker)
    path = tmp_path / planning_cycle.FILENAME
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**record, "profile_id": "other"}), encoding="utf-8")
    assert planning_cycle.planning_cycle_summary()["status"] == "registro_invalido"
    path.write_text(json.dumps({**record, "eligible_count": 5}), encoding="utf-8")
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
    finance = {"source": SOURCE, "observed_at": int(time.time()) - 5,
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
    path.write_text(json.dumps({**finance, "summary": {**finance["summary"], "result": 0}}), encoding="utf-8")
    planning_cycle.capture_and_plan(worker)
    assert snapshot_summary()["historical_investment_spending"] is None
    assert "limite_periodo_esgotado_na_observacao" not in planning_cycle.planning_cycle_summary()["blocking_reasons"]
