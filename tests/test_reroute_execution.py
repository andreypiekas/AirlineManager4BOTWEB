"""Exercise the recovery boundaries of a route replacement."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import WebDriverException

import reroute
from airport_catalog import by_code
from route_registry import RouteRegistry, endpoint


@pytest.mark.parametrize("outcome,toggles,expected", [
    ("created", ["101"], "trocada"),
    ("rejected", ["101"], "troca_requer_verificacao"),
    ("unreadable", ["101"], "troca_requer_verificacao"),
    ("unknown_old", ["101"], "troca_requer_verificacao"),
])
def test_replace_verifies_the_assignment_or_restores_original(tmp_path, monkeypatch, outcome, toggles, expected):
    registry = RouteRegistry(tmp_path / "registry.json")
    origin, old, new = (endpoint(by_code(code).game_id, code) for code in ("LAX", "PBM", "MIA"))
    row = dict(aircraft_id="5", registration="AB-5", model="Aircraft", origin=origin, destination=old)
    registry.record("5", "AB-5", "Aircraft", origin, old)
    registry.record("6", "AB-6", "Aircraft", origin, old)
    live = reroute.LiveRoute("101", False, ("LAX", "PBM"), True)
    journal = tmp_path / "pending.json"
    actions = []
    charges = []
    submits = []

    def toggle(bot, route_id):
        nonlocal live
        assert journal.exists()
        actions.append(route_id)
        live = replace(live, paused=not live.paused)
        return True

    def game_request(script, *_):
        nonlocal live
        if script == reroute._GET:
            return True  # Maintenance confirms the aircraft is at a base.
        submits.append(True)
        if outcome == "rejected":
            return True  # The game's request finished, and the old route is still paused.
        if outcome == "created":
            live = reroute.LiveRoute("102", False, ("LAX", "MIA"), True)
        elif outcome == "unreadable":
            live = None
        # WebDriver may lose the response even if the request reached the game.
        raise WebDriverException("connection lost")

    bot = SimpleNamespace(
        dry_run=False, stopping=False, driver=SimpleNamespace(execute_async_script=game_request),
        spent=lambda fee, **_: charges.append(fee), count=lambda *_: None, notify=lambda *_, **__: None,
    )
    monkeypatch.setattr(reroute, "_transaction_path", lambda: journal)
    monkeypatch.setattr(reroute, "_live_route", lambda bot, aircraft: live if aircraft == "5" else
                        reroute.LiveRoute("103", False, ("PBM", "LAX"), False))
    monkeypatch.setattr(reroute, "_toggle", toggle)
    monkeypatch.setattr(reroute, "_prepare_form", lambda *_: (object(), 100))
    monkeypatch.setattr(reroute.time, "sleep", lambda *_: None)

    assert reroute.replace_route(bot, registry, row, origin, new, keeper_id="6",
                                 expected_id="101", profit=400) == expected
    assert actions == toggles
    assert submits == [True]
    assert journal.exists() == (outcome in ("rejected", "unreadable", "unknown_old"))
    assert charges == ([100] if outcome == "created" else [])
    relation = next(x for x in registry.snapshot()["relations"] if x["aircraft_id"] == "5")
    assert relation["destination"]["code"] == ("MIA" if outcome == "created" else "PBM")



def test_uncertain_create_waits_then_restores_the_verified_original(tmp_path, monkeypatch):
    """A lost AJAX reply must not hold all flights forever or cause a quick double click."""
    import json
    import time

    registry = RouteRegistry(tmp_path / "registry.json")
    original = {"origin": endpoint(code="DAC"), "destination": endpoint(code="OSL")}
    target = {"origin": endpoint(code="DAC"), "destination": endpoint(code="MIA")}
    job = {
        "aircraft_id": "5", "old_id": "101", "registration": "PP-5",
        "model": "A320", "old_route": original,
        **target, "phase": "creating", "phase_at": time.time(),
        "fee": 200, "profit": 400,
    }
    pending = tmp_path / "pending.json"
    pending.write_text(json.dumps(job), encoding="utf-8")
    route = reroute.LiveRoute("101", True, ("DAC", "OSL"), True)
    toggles = []
    bot = SimpleNamespace(dry_run=False)
    monkeypatch.setattr(reroute, "_transaction_path", lambda: pending)
    monkeypatch.setattr(reroute, "_live_route", lambda *_: route)
    monkeypatch.setattr(reroute.time, "sleep", lambda *_: None)

    def restore(_bot, route_id):
        nonlocal route
        toggles.append(route_id)
        route = replace(route, paused=False)
        return True

    monkeypatch.setattr(reroute, "_toggle", restore)
    assert not reroute.recover_pending(bot, registry)
    assert pending.exists() and toggles == []  # no premature undo while AJAX may still commit

    job["phase_at"] -= reroute._UNCONFIRMED_REQUEST_GRACE + 1
    pending.write_text(json.dumps(job), encoding="utf-8")
    assert reroute.recover_pending(bot, registry)
    assert toggles == ["101"]
    assert not pending.exists()


def test_uncertain_create_clears_stable_original_without_toggling(tmp_path, monkeypatch):
    import json
    import time

    registry = RouteRegistry(tmp_path / "routes.json")
    original = {"origin": endpoint(code="DAC"), "destination": endpoint(code="OSL")}
    job = {
        "aircraft_id": "5", "old_id": "101", "registration": "PP-5",
        "model": "A320", "old_route": original,
        "origin": endpoint(code="DAC"), "destination": endpoint(code="MIA"),
        "phase": "create_answered",
        "phase_at": time.time() - reroute._UNCONFIRMED_REQUEST_GRACE - 5,
        "fee": 200, "profit": 400,
    }
    pending = tmp_path / "pending.json"
    pending.write_text(json.dumps(job), encoding="utf-8")
    bot = SimpleNamespace(dry_run=False)
    monkeypatch.setattr(reroute, "_transaction_path", lambda: pending)
    monkeypatch.setattr(
        reroute, "_live_route",
        lambda *_: reroute.LiveRoute("101", False, ("DAC", "OSL"), True),
    )
    monkeypatch.setattr(
        reroute, "_toggle",
        lambda *_: (_ for _ in ()).throw(AssertionError("Cannot toggle an active original")),
    )
    monkeypatch.setattr(reroute.time, "sleep", lambda *_: None)

    assert reroute.recover_pending(bot, registry)
    assert not pending.exists()


def test_uncertain_restoration_is_retried_only_after_grace(tmp_path, monkeypatch):
    import json
    import time

    registry = RouteRegistry(tmp_path / "routes.json")
    original = {"origin": endpoint(code="DAC"), "destination": endpoint(code="OSL")}
    job = {
        "aircraft_id": "5", "old_id": "101", "registration": "PP-5",
        "model": "A320", "old_route": original,
        "origin": endpoint(code="DAC"), "destination": endpoint(code="MIA"),
        "phase": "restoring", "phase_at": time.time(),
        "fee": 200, "profit": 400,
    }
    pending = tmp_path / "pending.json"
    pending.write_text(json.dumps(job), encoding="utf-8")
    route = reroute.LiveRoute("101", True, ("DAC", "OSL"), True)
    toggles = []
    bot = SimpleNamespace(dry_run=False)
    monkeypatch.setattr(reroute, "_transaction_path", lambda: pending)
    monkeypatch.setattr(reroute, "_live_route", lambda *_: route)
    monkeypatch.setattr(reroute.time, "sleep", lambda *_: None)

    def restore(_bot, route_id):
        nonlocal route
        toggles.append(route_id)
        route = replace(route, paused=False)
        return True

    monkeypatch.setattr(reroute, "_toggle", restore)
    assert not reroute.recover_pending(bot, registry)
    assert not toggles
    job["phase_at"] -= reroute._UNCONFIRMED_REQUEST_GRACE + 1
    pending.write_text(json.dumps(job), encoding="utf-8")
    assert reroute.recover_pending(bot, registry)
    assert toggles == ["101"]


def test_route_change_with_reused_internal_id_is_confirmed(tmp_path, monkeypatch):
    import json
    import time

    registry = RouteRegistry(tmp_path / "routes.json")
    original = {"origin": endpoint(code="DAC"), "destination": endpoint(code="OSL")}
    target = {"origin": endpoint(code="DAC"), "destination": endpoint(code="MIA")}
    job = {
        "aircraft_id": "5", "old_id": "101", "registration": "PP-5",
        "model": "A320", "old_route": original, **target,
        "phase": "creating", "phase_at": time.time(),
        "fee": 200, "profit": 400,
    }
    pending = tmp_path / "pending.json"
    pending.write_text(json.dumps(job), encoding="utf-8")
    charges = []
    bot = SimpleNamespace(
        dry_run=False, spent=lambda amount, **_: charges.append(amount),
        count=lambda *_: None, notify=lambda *_, **__: None,
    )
    monkeypatch.setattr(reroute, "_transaction_path", lambda: pending)
    monkeypatch.setattr(
        reroute, "_live_route",
        lambda *_: reroute.LiveRoute("101", False, ("DAC", "MIA"), True),
    )
    assert reroute.recover_pending(bot, registry)
    assert charges == [200]
    assert not pending.exists()
    row = registry.snapshot()["relations"][0]
    assert row["destination"]["code"] == "MIA"
