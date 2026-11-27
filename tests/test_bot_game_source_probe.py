"""Selenium diagnostics execute only in the bot worker between cycles."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from contextlib import contextmanager

from aircraft_order_preview import AircraftPreviewRequest
from bot import Bot, BotState


class Driver:
    def __init__(self):
        self.calls: list[int] = []
        self.history_calls: list[tuple[int, str]] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def execute_script(self, script):
        assert "document.querySelectorAll" in script
        self.calls.append(threading.get_ident())
        self.started.set()
        assert self.release.wait(3)
        return {"schema_version": 1, "sources": {}, "pagination": {}, "status_data": {}}

    def execute_async_script(self, script, aircraft_id):
        assert "fleet_details.php?id=" in script
        self.history_calls.append((threading.get_ident(), aircraft_id))
        self.started.set()
        assert self.release.wait(3)
        return {"schema_version": 1, "aircraft_id": aircraft_id, "status": "missing_history",
                "history_present": False, "password": "HIDDEN_SECRET"}


def make_bot():
    bot = Bot.__new__(Bot)
    bot.driver = Driver()
    bot.state = BotState.RUNNING
    bot._stop = threading.Event()
    bot._wake = threading.Event()
    bot._lifecycle_lock = threading.Lock()
    bot._probe_condition = threading.Condition()
    bot._probe_ready = False
    bot._probe_request = None
    bot._thread = None
    bot._next_event = None
    bot.next_cycle_at = None
    bot.cash_reads = 0
    bot.login_threads = []
    bot.login_valid = True

    def get_int(_section, key, _default=0):
        return {"cycle_min_minutes": 1, "cycle_max_minutes": 1,
                "cash_sync_seconds": 30}[key]

    bot.config = type("Config", (), {"get_int": staticmethod(get_int)})()
    bot._sync_cash_from_game = lambda: setattr(bot, "cash_reads", bot.cash_reads + 1)

    def logged_in(timeout):
        assert timeout == 0
        bot.login_threads.append(threading.get_ident())
        return bot.login_valid

    bot._is_logged_in = logged_in
    return bot


def wait_until_idle(bot):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with bot._probe_condition:
            if bot._probe_ready:
                return
        time.sleep(0.01)
    raise AssertionError("bot never entered the idle diagnostic window")


@contextmanager
def running_worker(bot, target=None):
    bot._thread = threading.Thread(target=target or bot._sleep_until_next_cycle, daemon=True)
    bot._thread.start()
    try:
        yield bot
    finally:
        bot.stop()
        bot.driver.release.set()
        bot._thread.join(timeout=3)
        assert not bot._thread.is_alive()


def test_probe_executes_on_worker_without_ending_sleep_early():
    bot = make_bot()
    with running_worker(bot):
        wait_until_idle(bot)
        next_cycle = bot.next_cycle_at
        caller = threading.get_ident()
        result, report = bot.request_game_source_probe(timeout=2)
        assert result == "ok"
        assert report["schema_version"] == 1
        assert bot.driver.calls == [bot._thread.ident]
        assert bot.login_threads == [bot._thread.ident]
        assert bot._thread.ident != caller
        assert bot.next_cycle_at == next_cycle
        assert bot.cash_reads == 0
        assert bot._thread.is_alive()


def test_flight_history_probe_uses_worker_and_returns_only_structural_data():
    bot = make_bot()
    with running_worker(bot):
        wait_until_idle(bot)
        scheduled = bot.next_cycle_at
        status, report = bot.request_flight_history_probe("42")
        assert status == "ok"
        assert bot.driver.history_calls == [(bot._thread.ident, "42")]
        assert bot.login_threads == [bot._thread.ident]
        assert report["aircraft_id"] == "42"
        assert report["complete_history_verified"] is False
        assert report["financial_ledger_verified"] is False
        assert "HIDDEN_SECRET" not in str(report)
        assert bot.next_cycle_at == scheduled
        assert bot.request_game_source_probe(timeout=2)[0] == "ok"


def test_aircraft_preview_runs_only_on_observation_worker_and_rechecks_company(monkeypatch):
    bot = make_bot()
    request = AircraftPreviewRequest("12", "24323457", "23", (3, 0, 0), 51000)
    assert bot.request_aircraft_order_preview(request) == ("unavailable", None)
    bot._observation_only = True
    monkeypatch.setattr("bot.requested_work", lambda _store: None)
    calls = []

    def verify(label):
        calls.append((label, threading.get_ident()))

    def quote(worker, payload):
        assert worker is bot and payload == request
        verify("quote")
        return {"status": "matched", "execution_available": False}

    pending = {"fleet_total": 224, "pending": {"total": 0}, "observed_at": 42,
               "company_id": "123", "fleet_ids": ["456"]}

    def read_pending(worker, *, baseline):
        assert worker is bot
        verify("baseline" if baseline else "pending")
        return pending

    def read_cash(worker, roster, checkout_amount):
        assert worker is bot and roster is pending and checkout_amount == 51000
        verify("cash evidence")
        return {"receipt_verified": False}

    bot._require_observation_session = lambda: verify("session")
    bot._verify_observation_company = lambda: verify("company")
    monkeypatch.setattr("bot.probe_aircraft_order", quote)
    monkeypatch.setattr("bot.read_pilot_pending", read_pending)
    monkeypatch.setattr("bot.read_aircraft_cash_observation", read_cash)
    with running_worker(bot):
        wait_until_idle(bot)
        status, report = bot.request_aircraft_order_preview(request, timeout=2)
        assert status == "ok" and report["status"] == "matched"
        assert report["fleet_baseline"] == {"status": "verified", "fleet_total": 224,
                                            "pending_total": 0, "observed_at": 42}
        assert report["order_and_debit_observation"] == {"receipt_verified": False}
        assert calls == [(label, bot._thread.ident) for label in
                         ("session", "company", "quote", "baseline", "cash evidence", "session", "company")]
        assert bot.cash_reads == 0

        monkeypatch.setattr("bot.read_pilot_pending", lambda worker, *, baseline=False: (
            None if baseline else read_pending(worker, baseline=False)
        ))
        calls.clear()
        status, report = bot.request_aircraft_order_preview(request, timeout=2)
        assert status == "ok" and report["fleet_baseline"] == {"status": "unverified"}
        assert report["order_and_debit_observation"] == {"receipt_verified": False}

        def changed_company():
            if calls[-1][0] == "session" and any(label == "quote" for label, _ in calls):
                raise RuntimeError("sensitive session detail")
            verify("company")

        bot._verify_observation_company = changed_company
        calls.clear()
        assert bot.request_aircraft_order_preview(request, timeout=2) == ("unavailable", None)
        assert any(label == "quote" for label, _ in calls)


def test_flight_history_probe_validates_id_and_recovers_after_timeout():
    bot = make_bot()
    for invalid in ("", "0", "1;2", " 123", "1" * 15):
        try:
            bot.request_flight_history_probe(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid aircraft ID was accepted")
    assert not bot.driver.history_calls
    bot.driver.release.clear()
    with running_worker(bot):
        wait_until_idle(bot)
        assert bot.request_flight_history_probe("77", timeout=0.1) == ("timeout", None)
        assert bot.driver.history_calls == [(bot._thread.ident, "77")]
        assert bot.request_game_source_probe(timeout=0.1) == ("busy", None)
        bot.driver.release.set()
        wait_until_idle(bot)
        assert bot.request_game_source_probe(timeout=2)[0] == "ok"


def test_flight_history_probe_and_game_source_probe_share_queue():
    bot = make_bot()
    bot.driver.release.clear()
    results = []
    with running_worker(bot):
        wait_until_idle(bot)
        caller = threading.Thread(target=lambda: results.append(
            bot.request_flight_history_probe("314", timeout=2)), daemon=True)
        caller.start()
        assert bot.driver.started.wait(2)
        assert bot.request_game_source_probe(timeout=0.1) == ("busy", None)
        assert bot.request_flight_history_probe("315", timeout=0.1) == ("busy", None)
        bot.driver.release.set()
        caller.join(timeout=3)
        assert not caller.is_alive()
        assert results[0][0] == "ok"
        assert bot.driver.history_calls == [(bot._thread.ident, "314")]


def test_request_during_active_cycle_rejects_without_touching_driver():
    bot = make_bot()
    active_cycle = threading.Event()
    release_cycle = threading.Event()

    def cycle_then_sleep():
        active_cycle.set()
        assert release_cycle.wait(3)
        bot._sleep_until_next_cycle()

    with running_worker(bot, cycle_then_sleep):
        assert active_cycle.wait(2)
        status, report = bot.request_game_source_probe(timeout=0.1)
        assert (status, report) == ("busy", None)
        assert not bot.driver.calls
        assert not bot.login_threads
        release_cycle.set()
        wait_until_idle(bot)
        assert bot.request_game_source_probe(timeout=2)[0] == "ok"


def test_second_request_rejects_while_first_probe_uses_driver():
    bot = make_bot()
    bot.driver.release.clear()
    outcomes = []
    with running_worker(bot):
        wait_until_idle(bot)
        requester = threading.Thread(
            target=lambda: outcomes.append(bot.request_game_source_probe(timeout=2)),
            daemon=True,
        )
        requester.start()
        assert bot.driver.started.wait(2)
        assert bot.request_game_source_probe(timeout=0.1) == ("busy", None)
        assert bot.driver.calls == [bot._thread.ident]
        bot.driver.release.set()
        requester.join(timeout=3)
        assert not requester.is_alive()
        assert outcomes[0][0] == "ok"


def test_timeout_returns_safely_and_worker_recovers_after_driver_finishes():
    bot = make_bot()
    bot.driver.release.clear()
    with running_worker(bot):
        wait_until_idle(bot)
        assert bot.request_game_source_probe(timeout=0.1) == ("timeout", None)
        assert bot.driver.calls == [bot._thread.ident]
        assert bot.request_game_source_probe(timeout=0.1) == ("busy", None)
        bot.driver.release.set()
        wait_until_idle(bot)
        assert bot.request_game_source_probe(timeout=2)[0] == "ok"
        assert bot.driver.calls == [bot._thread.ident, bot._thread.ident]


def test_cancelled_queued_request_does_not_read_driver():
    bot = make_bot()
    with running_worker(bot):
        wait_until_idle(bot)
        canceled = Future()
        assert canceled.cancel()
        with bot._probe_condition:
            bot._probe_request = canceled
            bot._probe_condition.notify_all()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with bot._probe_condition:
                if bot._probe_request is None:
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("worker did not discard canceled request")
        assert bot.driver.calls == []
        assert bot.login_threads == []
        assert bot.request_game_source_probe(timeout=2)[0] == "ok"


def test_probe_rejects_when_next_cycle_is_approaching(monkeypatch):
    bot = make_bot()
    monkeypatch.setattr("bot.random.uniform", lambda _minimum, _maximum: 1.0)
    with running_worker(bot):
        wait_until_idle(bot)
        status, report = bot.request_game_source_probe(timeout=0.5)
        assert (status, report) == ("busy", None)
        assert bot.driver.calls == []
        assert bot.next_cycle_at is not None
        bot._thread.join(timeout=2)
        assert not bot._thread.is_alive()
        assert bot.driver.calls == []


def test_run_now_and_stop_while_diagnostic_uses_driver():
    for action in ("run_now", "stop"):
        bot = make_bot()
        bot.driver.release.clear()
        outcome = []
        with running_worker(bot):
            wait_until_idle(bot)
            requester = threading.Thread(
                target=lambda bot=bot, outcome=outcome: outcome.append(
                    bot.request_game_source_probe(timeout=2)),
                daemon=True,
            )
            requester.start()
            assert bot.driver.started.wait(2)
            getattr(bot, action)()
            bot.driver.release.set()
            requester.join(timeout=3)
            bot._thread.join(timeout=2)
            assert not requester.is_alive()
            assert not bot._thread.is_alive()
            assert bot.driver.calls == [bot._thread.ident]
            assert outcome[0][0] == "ok"


def test_expired_login_stays_on_worker_and_never_runs_probe():
    bot = make_bot()
    bot.login_valid = False
    with running_worker(bot):
        wait_until_idle(bot)
        assert bot.request_game_source_probe(timeout=2) == ("unavailable", None)
        assert bot.login_threads == [bot._thread.ident]
        assert bot.driver.calls == []


def test_run_now_and_stop_interrupt_idle_wait():
    bot = make_bot()
    with running_worker(bot):
        wait_until_idle(bot)
        bot.run_now()
        bot._thread.join(timeout=1)
        assert not bot._thread.is_alive()
        assert bot.driver.calls == []

    bot = make_bot()
    with running_worker(bot):
        wait_until_idle(bot)
        bot.stop()
        bot._thread.join(timeout=1)
        assert not bot._thread.is_alive()
        assert bot.driver.calls == []
