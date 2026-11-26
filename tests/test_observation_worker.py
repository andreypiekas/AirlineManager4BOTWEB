from threading import Event
from time import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.webdriver.common.by import By

import bot as bot_module
import config
import main
import paths
import web
from bot import Bot


@pytest.mark.parametrize("company_changes", [False, True])
def test_observation_worker_uses_only_readers_and_local_capture(monkeypatch, company_changes):
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
    worker._read_mode = lambda: calls.append("mode")
    worker._read_header = lambda: calls.append("header")
    worker._check_market = lambda *, observation_only: calls.append(("market", observation_only))

    def verify_company():
        calls.append("company")
        if company_changes and calls.count("company") == 2:
            raise RuntimeError("Identidade mudou durante a coleta")

    worker._verify_observation_company = verify_company

    def fleet(owner, *, observation_only):
        assert owner is worker
        calls.append(("fleet", observation_only))
        return {"observation_id": "fleet"}

    def read(label):
        def action(owner):
            assert owner is worker
            calls.append(label)

        return action

    events_observed_at = None

    def demand_events(owner):
        nonlocal events_observed_at
        read("demand_events")(owner)
        events_observed_at = time()
        return [{"source": "game_route_events", "observed_at": events_observed_at,
                 "reported_count": 0, "events": []}]

    def demand(owner, *, country_windows):
        read("demand")(owner)
        country_windows.append({"origin_id": "11"})

    monkeypatch.setattr(bot_module, "manage_fleet", fleet)
    monkeypatch.setattr("demand_events.collect_demand_events", demand_events)
    monkeypatch.setattr("game_observations.collect_owned_hub_demand", demand)
    monkeypatch.setattr("hub_operations.collect_hub_operations", read("hub_operations"))
    monkeypatch.setattr("game_observations.collect_owned_route_details", read("route_details"))
    monkeypatch.setattr("game_observations.collect_aircraft_engine_catalog", read("aircraft_catalog"))
    monkeypatch.setattr("owned_delivery_coverage.collect_owned_delivery_coverage", read("delivery_hubs"))
    monkeypatch.setattr("finance_observations.collect_finance_observations", read("finance"))
    monkeypatch.setattr("staff_observations.collect_staff_observations", read("staff"))
    capture = Mock()
    monkeypatch.setattr("audited_game_snapshot.capture_game_snapshot", capture)

    if company_changes:
        with pytest.raises(RuntimeError, match="Identidade"):
            worker._cycle()
        capture.assert_not_called()
    else:
        worker._cycle()
        assert capture.call_count == 1 and capture.call_args.args == (worker,)
        started_at, confirmed_at = capture.call_args.kwargs["read_only_window"]
        assert 0 < started_at <= confirmed_at
        assert capture.call_args.kwargs["operational_evidence"] == {
            "pending": {"observation_id": "fleet"}, "hubs": None,
            "country_search_windows": [{"origin_id": "11"}],
            "demand_events": [{"source": "game_route_events", "observed_at": events_observed_at,
                               "reported_count": 0, "events": []}],
        }
    assert calls == ["session", "company", "mode", "demand_events", "demand", ("market", True), ("fleet", True),
                     "hub_operations", "route_details", "aircraft_catalog", "delivery_hubs", "finance", "staff", "header",
                     "session", "company"]
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


@pytest.mark.parametrize("wait_for_login", [False, True])
def test_observation_worker_startup_keeps_login_manual(tmp_path, monkeypatch, wait_for_login):
    worker = Bot.__new__(Bot)
    worker._observation_only = True
    worker._wait_for_login = wait_for_login
    worker._stop = Event()
    worker.config = Mock()
    worker.config.get.return_value = "https://www.airlinemanager.com/"
    worker.config.get_bool.return_value = True
    worker._login = Mock()
    worker._wait_for_observation_login = Mock(return_value=True)
    worker._require_observation_session = Mock()
    worker._cycle = Mock(side_effect=worker._stop.set)
    worker._quit_driver = Mock()
    create_driver = Mock()
    monkeypatch.setattr(bot_module, "current", lambda: SimpleNamespace(data=tmp_path / "data"))
    monkeypatch.setattr(bot_module, "chrome_session_path", lambda: tmp_path / "session")
    monkeypatch.setattr(bot_module, "create_driver", create_driver)

    worker._run()

    create_driver.assert_called_once_with(
        url="https://www.airlinemanager.com/", keep_session=True, headless=not wait_for_login,
    )
    assert worker._wait_for_observation_login.call_count == int(wait_for_login)
    worker._require_observation_session.assert_called_once_with()
    worker._cycle.assert_called_once_with()
    worker._quit_driver.assert_called_once_with()
    worker._login.assert_not_called()
    worker.config.reload_secrets.assert_not_called()


@pytest.mark.parametrize("outcome", ["authenticated", "redirect", "stop", "timeout"])
def test_observation_login_wait_checks_origin_and_is_bounded(monkeypatch, outcome):
    worker = Bot.__new__(Bot)
    url = "https://www.airlinemanager.com.example/" if outcome == "redirect" else "https://www.airlinemanager.com/"
    worker.driver = SimpleNamespace(current_url=url)
    worker._stop = Mock(wraps=Event())
    worker._stop.is_set.side_effect = [False, True] if outcome == "stop" else None
    worker._stop.wait.return_value = False
    worker._is_logged_in = Mock(side_effect=[False, outcome == "authenticated"])
    worker.update_stats = Mock()
    clock = Mock(side_effect=[0, 300 if outcome == "timeout" else 1])
    with monkeypatch.context() as patch:
        patch.setattr(bot_module, "time", SimpleNamespace(monotonic=clock))
        if outcome in {"redirect", "timeout"}:
            with pytest.raises(RuntimeError, match="Origem" if outcome == "redirect" else "Tempo limite"):
                worker._wait_for_observation_login()
        else:
            assert worker._wait_for_observation_login() is (outcome == "authenticated")

    if outcome in {"authenticated", "stop"}:
        worker._stop.wait.assert_called_once_with(1)
    else:
        worker._stop.wait.assert_not_called()
    if outcome == "redirect":
        worker._is_logged_in.assert_not_called()
    if outcome == "timeout":
        worker.update_stats.assert_called_once_with(money_read_at=None)
    else:
        worker.update_stats.assert_not_called()


def test_cli_rejects_manual_login_without_observation_before_profile_selection(monkeypatch):
    select = Mock()
    monkeypatch.setattr(main, "select_profile", select)
    monkeypatch.setattr(main.os, "chdir", Mock())
    monkeypatch.setattr(main.sys, "path", list(main.sys.path))
    monkeypatch.setattr(main.sys, "argv", ["src/main.py", "--web", "--wait-for-login"])

    with pytest.raises(SystemExit, match="requer --observe-game"):
        main.main()

    select.assert_not_called()


@pytest.mark.parametrize("label", ["User ID", "USER ID", "ID\xa0DO USUÁRIO"])
def test_observation_rejects_changed_native_company_id(label):
    worker = Bot.__new__(Bot)
    worker._observation_company_id = None
    worker.close_popup = Mock()
    worker.driver = Mock()
    worker.driver.find_element.return_value.is_displayed.return_value = True
    worker.driver.find_element.return_value.is_enabled.return_value = True
    first = Mock(text=f"{label}: 123")
    again = Mock(text=f"{label}: 123")
    changed = Mock(text=f"{label}: 456")
    worker.driver.find_elements.side_effect = [[], [first], [first], [again], [again], [changed]]

    worker._verify_observation_company()
    worker._verify_observation_company()
    with pytest.raises(RuntimeError, match="Identidade"):
        worker._verify_observation_company()

    assert worker._observation_company_id == "123"
    assert worker.close_popup.call_count == 3


def test_observation_waits_for_one_visible_company_id():
    worker = Bot.__new__(Bot)
    worker._observation_company_id = None
    worker.close_popup = Mock()
    worker.driver = Mock()
    worker.driver.find_element.return_value.is_displayed.return_value = True
    worker.driver.find_element.return_value.is_enabled.return_value = True
    hidden = Mock(text="User ID: 456")
    hidden.is_displayed.return_value = False
    old = Mock(text="User ID: 789")
    title = Mock(text="Company")
    field = Mock(text="USER ID: 123")
    worker.driver.find_elements.side_effect = [[old], [old, hidden, title], [field, field], [old, field]]

    worker._verify_observation_company()

    assert worker._observation_company_id == "123"
    assert worker.driver.find_elements.call_count == 4
    worker.driver.find_element.assert_called_once_with(By.CSS_SELECTOR, "#smallMainMenu #mapAcList")
    worker.driver.execute_script.assert_called_once_with("arguments[0].click();", worker.driver.find_element.return_value)
    worker.driver.find_elements.assert_called_with(By.CSS_SELECTOR, "#popup #companyAction .font-weight-bold")
    worker.close_popup.assert_called_once_with(quiet=True)


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
        worker.assert_called_once_with(cfg, observation_only=True, wait_for_login=False)
