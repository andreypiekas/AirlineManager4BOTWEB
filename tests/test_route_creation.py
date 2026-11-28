"""A lost route response must survive restart without another purchase."""
import json
import threading
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import WebDriverException

import bot as bot_module
import fleet
import route_creation as creation
from airport_catalog import by_code
from bot import Bot, Stats
from route_registry import RouteRegistry, endpoint


@pytest.fixture
def journal(tmp_path, monkeypatch):
    path = tmp_path / "route_creation_pending.json"
    monkeypatch.setattr(creation, "pending_path", lambda: path)
    return path


def airport(code):
    return endpoint(by_code(code).game_id, code=code)


def stage(stopover=None):
    return creation.stage_creation(fleet.ParkedAircraft("5", "A320", "TEST", 180),
                                   airport("LAX"), airport("MIA"), stopover, 1000, None)


def make_bot(state_path, monkeypatch):
    monkeypatch.setattr(bot_module, "state_file", lambda: state_path)
    bot = Bot.__new__(Bot)
    bot._state = json.loads(state_path.read_text()) if state_path.exists() else {}
    bot._stats = Stats(money=5000)
    bot._stats_lock = threading.Lock()
    bot.read_money = lambda: 4000
    bot.notify = lambda *_args, **_kwargs: None
    return bot


@pytest.mark.parametrize("via", [None, "ANC"])
def test_uncertain_creation_is_recovered_without_second_submission(journal, tmp_path, monkeypatch, via):
    stop = airport(via) if via else None
    job = stage(stop)
    assert job and stage(stop) is None
    assert json.loads(journal.read_text()) == job
    registry = RouteRegistry(tmp_path / "routes.json")
    state_path = tmp_path / "state.json"
    bot = make_bot(state_path, monkeypatch)
    reads = []

    def confirm(*args):
        reads.append(args[1:])
        return len(reads) > 1

    monkeypatch.setattr(creation, "confirm_direct_route", confirm)
    monkeypatch.setattr(creation, "confirm_stopover", confirm)
    assert not creation.recover_pending_creation(bot, registry)
    assert journal.exists() and not state_path.exists()
    assert not registry.snapshot()["relations"]

    restarted = make_bot(state_path, monkeypatch)
    assert creation.recover_pending_creation(restarted, registry)
    assert not journal.exists()
    assert reads == [("5", job["origin"], job["destination"], stop) if via else
                     ("5", job["origin"], job["destination"])] * 2
    assert restarted._state["invested"] == 1000
    assert restarted._state["spent_total"] == 1000
    assert restarted._state["counters"]["routes"] == 1
    assert restarted.stats().money == 4000
    relation = registry.snapshot()["relations"][0]
    assert relation.get("stopover") == stop


def test_confirmed_journal_replays_accounting_only_once_after_restart(journal, tmp_path, monkeypatch):
    job = stage()
    registry = RouteRegistry(tmp_path / "routes.json")
    state_path = tmp_path / "state.json"
    bot = make_bot(state_path, monkeypatch)
    real_expense = bot.record_route_expense

    def crash_after_expense(*args):
        real_expense(*args)
        raise OSError("interrupted before journal cleanup")

    bot.record_route_expense = crash_after_expense
    with pytest.raises(OSError):
        creation.finish_creation(bot, registry, job)
    assert json.loads(journal.read_text())["phase"] == "confirmed"

    restarted = make_bot(state_path, monkeypatch)
    monkeypatch.setattr(creation, "confirm_direct_route", lambda *_: pytest.fail("already confirmed"))
    assert creation.recover_pending_creation(restarted, registry)
    assert restarted._state["spent_total"] == 1000
    assert restarted._state["invested"] == 1000
    assert restarted._state["counters"]["routes"] == 1
    assert not journal.exists()


def test_accounting_write_failure_preserves_journal_and_does_not_change_totals(journal, tmp_path, monkeypatch):
    job = stage()
    registry = RouteRegistry(tmp_path / "routes.json")
    bot = make_bot(tmp_path / "state.json", monkeypatch)
    original_write = bot_module.write_atomic

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(bot_module, "write_atomic", fail)
    with pytest.raises(OSError):
        creation.finish_creation(bot, registry, job)
    assert bot._state == {}
    assert json.loads(journal.read_text())["phase"] == "confirmed"
    monkeypatch.setattr(bot_module, "write_atomic", original_write)
    assert creation.recover_pending_creation(bot, registry)
    assert bot._state["counters"]["routes"] == 1


def test_corrupt_journal_blocks_new_routes_and_aircraft(journal):
    journal.write_text("{")
    assert stage() is None
    assert not creation.recover_pending_creation(object(), object())
    assert fleet.create_route(object(), object(), object()) == "stop"
    fleet.buy_aircraft(object())
    assert journal.read_text() == "{"


def test_webdriver_failure_leaves_unconfirmed_intent(journal, monkeypatch):
    stage()

    def disconnected(*_args):
        raise WebDriverException("disconnected")

    monkeypatch.setattr(creation, "confirm_direct_route", disconnected)
    assert not creation.recover_pending_creation(object(), object())
    assert json.loads(journal.read_text())["phase"] == "submitted"


def test_route_journal_is_profile_local(tmp_path, monkeypatch):
    monkeypatch.setattr(creation.paths, "current", lambda: SimpleNamespace(data=tmp_path / "first"))
    assert stage()
    monkeypatch.setattr(creation.paths, "current", lambda: SimpleNamespace(data=tmp_path / "second"))
    assert not creation.has_pending_creation()
    assert stage()
    assert (tmp_path / "first" / "route_creation_pending.json").exists()
    assert (tmp_path / "second" / "route_creation_pending.json").exists()
