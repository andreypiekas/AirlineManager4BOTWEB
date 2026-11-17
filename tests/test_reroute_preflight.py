"""Preflight reads fresh aircraft details without changing the live page or route."""
from __future__ import annotations

import pytest
from selenium.common.exceptions import WebDriverException

import reroute
from reroute_preflight import check_existing_route
from route_registry import endpoint


def record():
    return {
        "origin": endpoint(code="DAC"),
        "destination": endpoint(code="OSL"),
        "source": "game",
    }


class Bot:
    def __init__(self, result):
        self.result = result
        self.reads = []
        self.driver = self

    def ajax(self, uri, target):
        pytest.fail("Preflight must not call Ajax or mutate a live container")

    def js(self, script):
        pytest.fail("Preflight must not read a stale detailsAction container")

    def execute_async_script(self, script, path, read):
        assert script == reroute._GET
        assert read == "details"
        self.reads.append((path, read))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("codes", [("DAC", "OSL"), ("OSL", "DAC")])
def test_reroute_preflight_reads_real_route_id_with_bidirectional_airport_codes(codes):
    b = Bot({"id": "99123", "codes": codes, "paused": False, "landed": True})
    result = check_existing_route(b, "24133209", record())
    assert result.aircraft_id == "24133209"
    assert result.route_confirmed
    assert result.route_id == "99123"
    assert result.reason == "rota_confirmada"
    assert result.game_endpoints == codes
    assert b.reads == [("fleet_details.php?id=24133209", "details")]


def test_reroute_preflight_uses_detached_authenticated_fetch():
    b = Bot({"id": "99", "codes": ["DAC", "OSL"], "paused": False, "landed": True})
    assert check_existing_route(b, "24133209", record()).route_confirmed
    assert "fetch(url" in reroute._GET
    assert "url.searchParams.set('fbSig', fbSig)" in reroute._GET
    assert "cache:'no-store'" in reroute._GET
    assert "new DOMParser().parseFromString(html, 'text/html')" in reroute._GET
    assert "detailsAction" not in reroute._GET
    assert b.reads == [("fleet_details.php?id=24133209", "details")]


@pytest.mark.parametrize("route_id", ["", "99,100", "../oops", "1" * 15])
def test_reroute_preflight_never_confuses_aircraft_id_with_route_id(route_id):
    b = Bot({"id": route_id, "codes": ["DAC", "OSL"], "paused": False, "landed": True})
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.route_id == ""
    assert result.reason == "id_da_rota_ambigua_ou_ausente"


def test_reroute_preflight_reads_fresh_details_for_each_check():
    b = Bot({"id": "99", "codes": ["DAC", "OSL"], "paused": False, "landed": True})
    assert check_existing_route(b, "24133209", record()).route_confirmed
    b.result = {"id": "100", "codes": ["DAC", "GRU"], "paused": False, "landed": True}
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.reason == "rota_divergente_dos_detalhes"
    assert result.route_id == "100"
    assert result.game_endpoints == ("DAC", "GRU")
    assert b.reads == [("fleet_details.php?id=24133209", "details")] * 2


def test_reroute_preflight_refuses_aircraft_in_flight():
    b = Bot({"id": "99", "codes": ["DAC", "OSL"], "paused": False, "landed": False})
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.reason == "aeronave_ainda_em_voo"
    assert result.route_id == "99"


def test_reroute_preflight_refuses_paused_route():
    b = Bot({"id": "99", "codes": ["DAC", "OSL"], "paused": True, "landed": True})
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.reason == "rota_pausada"
    assert result.route_id == "99"


@pytest.mark.parametrize("details", [
    None,
    {},
    {"id": "99", "codes": [], "paused": False, "landed": True},
    {"id": "99", "codes": ["DAC", "?"], "paused": False, "landed": True},
])
def test_preflight_missing_or_unverifiable_details_do_not_write_or_crash(details):
    b = Bot(details)
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.route_id == ""
    assert result.reason == "painel_da_aeronave_vazio"
    assert b.reads == [("fleet_details.php?id=24133209", "details")]


@pytest.mark.parametrize("aircraft_id", [None, "", "../oops", "1" * 15])
def test_preflight_invalid_aircraft_id_does_not_read(aircraft_id):
    b = Bot(None)
    result = check_existing_route(b, aircraft_id, record())
    assert not result.route_confirmed
    assert result.reason == "id_aeronave_invalido"
    assert b.reads == []


def test_preflight_read_error_does_not_write_or_crash():
    b = Bot(WebDriverException("detached fetch unavailable"))
    result = check_existing_route(b, "24133209", record())
    assert not result.route_confirmed
    assert result.route_id == ""
    assert result.reason == "detalhes_do_jogo_indisponiveis"
    assert b.reads == [("fleet_details.php?id=24133209", "details")]
