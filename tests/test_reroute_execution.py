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
    ("rejected", ["101", "101"], "rota_original_preservada"),
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
    assert journal.exists() == (outcome in ("unreadable", "unknown_old"))
    assert charges == ([100] if outcome == "created" else [])
    relation = next(x for x in registry.snapshot()["relations"] if x["aircraft_id"] == "5")
    assert relation["destination"]["code"] == ("MIA" if outcome == "created" else "PBM")
