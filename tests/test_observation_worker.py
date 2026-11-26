from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot as bot_module
import config
import main
import paths
import web
from bot import Bot


def test_observation_worker_uses_only_readers_and_local_capture(monkeypatch):
    worker = Bot.__new__(Bot)
    worker._observation_only = True
    worker._stop = Event()
    worker.config = Mock()
    worker.config.get_bool.return_value = True
    worker.telegram = Mock()
    worker._guard = lambda action, label: action()
    calls = []
    worker._ensure_session = Mock(side_effect=AssertionError("automatic login"))
    worker._require_observation_session = lambda: calls.append("session")
    worker._verify_observation_company = lambda: calls.append("company")
    worker._read_mode = lambda: calls.append("mode")
    worker._read_header = lambda: calls.append("header")
    worker._check_market = lambda *, observation_only: calls.append(("market", observation_only))

    def fleet(owner, *, observation_only):
        assert owner is worker
        calls.append(("fleet", observation_only))

    def read(label):
        def action(owner):
            assert owner is worker
            calls.append(label)

        return action

    monkeypatch.setattr(bot_module, "manage_fleet", fleet)
    monkeypatch.setattr("game_observations.collect_owned_hub_demand", read("demand"))
    monkeypatch.setattr("finance_observations.collect_finance_observations", read("finance"))
    monkeypatch.setattr("staff_observations.collect_staff_observations", read("staff"))
    monkeypatch.setattr("audited_game_snapshot.capture_game_snapshot", read("snapshot"))

    worker._cycle()
    assert calls == ["session", "company", "mode", "demand", ("market", True), ("fleet", True),
                     "finance", "staff", "header", "session", "snapshot"]
    assert worker.notify("test", category="status") is False
    assert not worker.telegram.mock_calls
    assert not worker.config.mock_calls


def test_observation_rejects_redirect_and_expired_session_before_collecting():
    worker = Bot.__new__(Bot)
    worker._observation_only = True
    worker.driver = SimpleNamespace(current_url="https://www.airlinemanager.com.example/")
    worker._is_logged_in = Mock(return_value=False)
    worker.update_stats = Mock()
    worker._verify_observation_company = Mock()
    worker._observation_cycle = Mock()
    worker._ensure_session = Mock()

    with pytest.raises(RuntimeError, match="Origem"):
        worker._cycle()
    worker._is_logged_in.assert_not_called()
    worker.driver.current_url = "https://www.airlinemanager.com/?gameType=web"
    with pytest.raises(RuntimeError, match="Sessão"):
        worker._cycle()

    worker.update_stats.assert_called_once_with(money_read_at=None)
    worker._ensure_session.assert_not_called()
    worker._verify_observation_company.assert_not_called()
    worker._observation_cycle.assert_not_called()


def test_observation_rejects_changed_native_company_id():
    worker = Bot.__new__(Bot)
    worker._observation_company_id = None
    worker._click = Mock()
    worker.close_popup = Mock()
    worker._text = Mock(side_effect=["User ID: 123", "User ID: 456"])

    worker._verify_observation_company()
    with pytest.raises(RuntimeError, match="Identidade"):
        worker._verify_observation_company()

    assert worker._observation_company_id == "123"
    assert worker.close_popup.call_count == 2


def test_worker_directory_lock_remains_exclusive_until_release(tmp_path):
    directory = tmp_path / "profile"
    alias = directory / ".." / "profile"
    with paths.worker_lock(directory):
        with pytest.raises(RuntimeError, match="Outro worker"), paths.worker_lock(alias):
            pytest.fail("Segundo worker ocupou o mesmo diretório")
        with paths.worker_lock(tmp_path / "other"):
            pass
    with paths.worker_lock(alias):
        pass


@pytest.mark.parametrize("owner, dashboard_bound", [("192.0.2.1", True), (None, False)])
def test_observation_cannot_open_chrome_if_profile_dashboard_is_busy(
        monkeypatch, owner, dashboard_bound):
    cfg = Mock()
    dashboard = Mock()
    dashboard.return_value.start.return_value = dashboard_bound
    worker = Mock()
    monkeypatch.setattr(config, "AppConfig", lambda: cfg)
    monkeypatch.setattr(web, "running_instance", lambda cfg: owner)
    monkeypatch.setattr(web, "WebDashboard", dashboard)
    monkeypatch.setattr(bot_module, "Bot", worker)
    monkeypatch.setattr("logsetup.setup_logging", Mock())
    monkeypatch.setattr("i18n.set_language", Mock())

    with pytest.raises(SystemExit):
        main.run_web_only(observation_only=True)
    worker.return_value.start.assert_not_called()
    if owner:
        worker.assert_not_called()
    else:
        worker.assert_called_once_with(cfg, observation_only=True)
