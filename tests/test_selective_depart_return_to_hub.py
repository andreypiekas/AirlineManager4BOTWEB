"""Reserved duplicates may only fly a freshly proven return to their reroute hub."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from selenium.common.exceptions import WebDriverException

from route_registry import RouteRegistry, endpoint
from selective_depart import plan_dispatch, selective_dispatch


@pytest.fixture
def registry(tmp_path):
    registry = RouteRegistry(tmp_path / "registry.json")
    dac, osl = endpoint(code="DAC"), endpoint(code="OSL")
    registry.record("101", "PP-A", "A320", dac, osl, source="game")
    # Stored direction deliberately disagrees with the current NEXT leg.
    registry.record("102", "PP-B", "A320", dac, osl, source="game")
    registry.note("102", "troca_aeronave_fora_da_base_de_origem", proposal={
        "origin_code": "DAC", "destination_code": "SIN",
    })
    return registry


def live_route(**changes):
    # LiveRoute.id is a route ID, not the aircraft ID (102).
    return {"id": "891", "codes": ["ENGM", "DAC"], "landed": True,
            "paused": False, **changes}


class NativeGame:
    stopping = False
    dry_run = False

    def __init__(self, flow="landed", *, enabled=True, states=None):
        self.flow = flow
        self.options = {"reroute_duplicates": enabled}
        self.config = SimpleNamespace(get_bool=lambda section, key, default=False: self.options.get(key, default))
        self.driver = self
        self.landed = {"102"}
        self.inflight = set()
        self.clicked = []
        self.reads = []
        self.counted = 0
        self.states = [live_route()] if states is None else list(states)
        self.action = "Ajax('route_depart.php?mode=single&ids=102','runme',this)"
        self.route_row = {
            "row_id": "routeMainList891", "route_id": "891", "aircraft_id": "102",
            "link_count": 1, "button_id": "listDepart891", "label": "Depart",
            "visible": True, "disabled": False,
            "action": "Ajax('route_depart.php?id=891&ref=list&costIndex=200','runme',this)",
        }

    def execute_async_script(self, script, path, read):
        assert path == "fleet_details.php?id=102"
        assert read == "details"
        assert "cache:'no-store'" in script
        self.reads.append(path)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(state, Exception):
            raise state
        return state

    def js(self, script, *args):
        if "#landedList [id^='flightStatus']" in script:
            return [{"id": aid, "native_actions": (
                [{"value": self.action}] if self.flow == "landed" else []
            )} for aid in sorted(self.landed)]
        if "routeMainList" in script and "routesContainer" in script:
            return [self.route_row] if self.flow == "routes" else []
        if "data-am4-safe-route-depart" in script:
            assert args == ("102", "891", self.route_row["action"])
            return True
        if "data-am4-safe-depart" in script:
            assert args == ("102", self.action)
            return True
        if "data-am4-fleet-depart" in script:
            assert args == ("102", 0, "Depart", "departAircraft(102)")
            return True
        if "return Array.from(root" in script and "detailsAction" in script:
            return ([{"index": 0, "label": "Depart", "action": "departAircraft(102)",
                      "visible": True, "disabled": False}] if self.flow == "fleet" else [])
        if 'const elements = [document.getElementById("runme")' in script:
            return {"fingerprint": "0:abcd", "reason": "nao_informado"}
        if 'inflight: read("inflightList")' in script:
            return {"landed": sorted(self.landed), "inflight": sorted(self.inflight)}
        if "route_depart" in script and "mode=all&ids=x" in script:
            return True  # Read-only discovery of the global control.
        raise AssertionError("Unexpected game script")

    def execute_script(self, script, *args):
        if 'const elements = [document.getElementById("runme")' in script:
            return {"fingerprint": "0:abcd", "reason": "nao_informado"}
        assert "inflightList" in script
        assert args == ("102",)
        return "102" in self.inflight

    def ajax(self, path, target, timeout=12):
        assert path == "fleet_details.php?id=102"
        assert target == "detailsAction"

    def find_element(self, by, locator):
        expected = {"landed": 'data-am4-safe-depart="102"',
                    "routes": 'data-am4-safe-route-depart="102"',
                    "fleet": 'data-am4-fleet-depart="102"'}
        assert expected[self.flow] in locator
        game = self

        class Button:
            def click(self):
                game.clicked.append("102")
                game.landed.remove("102")
                game.inflight.add("102")

        return Button()

    def count(self, name):
        assert name == "departures"
        self.counted += 1


@pytest.mark.parametrize("flow,mode", [
    ("landed", "seletivo"), ("routes", "seletivo_rotas_fleet"), ("fleet", "seletivo_fleet"),
])
def test_duplicate_returns_via_each_native_flow_without_changing_registry(registry, flow, mode):
    game = NativeGame(flow)
    summary = selective_dispatch(game, registry)

    assert summary["mode"] == mode
    assert summary["approved"] == 1
    assert summary["blocked"] == 0
    assert summary["blocked_aircraft"] == []
    assert summary["departed"] == game.counted == 1
    assert game.clicked == ["102"]
    assert len(game.reads) >= 2  # Initial policy and fresh native authorization.
    snapshot = registry.snapshot()
    assert snapshot["duplicate_routes"] == 1
    assert plan_dispatch(["102"], snapshot)[0].reason == "rota_duplicada_reservada"
    assert snapshot["relations"][1]["proposal"]["origin_code"] == "DAC"


@pytest.mark.parametrize("state", [
    live_route(codes=["DAC", "OSL"]),  # At the hub: hold for reroute.
    live_route(codes=["VGZR", "ENGM"]),  # Hub alias is still the departure.
    live_route(codes=["VGZR", "DAC"]),  # Both codes identify the hub.
    live_route(codes=["OSL", "SIN"]),  # Away from hub, but flying elsewhere.
    live_route(landed=False),
    live_route(paused=True),
    None,
    WebDriverException("Native read failed"),
])
def test_unproven_or_outbound_duplicate_remains_held(registry, state):
    game = NativeGame(states=[state])
    game.dry_run = True
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 0
    assert summary["blocked"] == 1
    assert summary["blocked_aircraft"][0]["reason"] == "rota_duplicada_reservada"
    assert summary["departed"] == 0
    assert game.clicked == []
    assert len(game.reads) == 1


@pytest.mark.parametrize("hub,arrival", [("DAC", "VGZR"), ("VGZR", "DAC")])
def test_return_destination_and_proposal_hub_match_airport_aliases(registry, hub, arrival):
    registry.note("102", "aguardando_troca_automatica", proposal={"origin_code": hub})
    game = NativeGame(states=[live_route(codes=["OSL", arrival])])
    game.dry_run = True
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 1
    assert summary["blocked"] == 0
    assert summary["departed"] == 0
    assert game.clicked == []


@pytest.mark.parametrize("enabled,proposal", [
    (False, {"origin_code": "DAC"}),
    (True, None),
    (True, {"destination_code": "DAC"}),
    (True, {"origin_id": "3499"}),
    (True, {"origin_code": "invalid"}),
])
def test_return_requires_opt_in_and_explicit_proposal_hub(registry, enabled, proposal):
    registry.note("102", "aguardando_troca_automatica", proposal=proposal)
    game = NativeGame(enabled=enabled)
    game.dry_run = True
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 0
    assert summary["blocked"] == 1
    assert game.reads == []
    assert game.clicked == []


@pytest.mark.parametrize("flow", ["landed", "routes", "fleet"])
def test_return_proof_is_refreshed_at_final_native_authorization(registry, flow):
    states = [live_route()] * (1 if flow == "landed" else 2)
    states.append(live_route(codes=["DAC", "OSL"]))
    game = NativeGame(flow, states=states)
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 1  # The initial plan was valid.
    assert summary["departed"] == 0
    assert game.clicked == []
    assert len(game.reads) >= (2 if flow == "landed" else 3)


@pytest.mark.parametrize("flow", ["landed", "routes", "fleet"])
def test_planner_switching_proposal_to_current_airport_cancels_return(registry, flow, monkeypatch):
    game = NativeGame(flow)
    read_native = game.execute_async_script

    def replan_after_read(*args):
        result = read_native(*args)
        if len(game.reads) == 1:
            registry.note("102", "aguardando_troca_automatica", proposal={
                "origin_code": "OSL", "destination_code": "SIN",
            })
        return result

    monkeypatch.setattr(game, "execute_async_script", replan_after_read)
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 1
    assert summary["departed"] == 0
    assert game.clicked == []


def test_return_can_still_serve_existing_plan_when_local_planning_has_no_alternative(registry):
    registry.note("102", "sem_alternativa_lucrativa", proposal={
        "origin_code": "DAC", "destination_code": "SIN",
    })
    game = NativeGame()
    summary = selective_dispatch(game, registry)

    assert summary["departed"] == 1
    assert game.clicked == ["102"]


def test_return_targets_specific_proposal_origin_instead_of_assuming_original_hub(registry):
    registry.note("102", "aguardando_troca_automatica", proposal={
        "origin_code": "OSL", "destination_code": "SIN",
    })
    game = NativeGame(states=[live_route(codes=["DAC", "ENGM"])])
    summary = selective_dispatch(game, registry)

    assert summary["departed"] == 1
    assert game.clicked == ["102"]


def test_default_dispatch_does_not_read_native_routes_for_ordinary_aircraft(registry):
    game = NativeGame()
    game.landed = {"101"}
    game.dry_run = True
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 1
    assert summary["blocked"] == 0
    assert game.reads == []


@pytest.mark.parametrize("experimental", [False, True])
def test_return_exception_never_uses_global_depart_all(registry, experimental):
    game = NativeGame()
    game.action = "Ajax('route_depart.php?mode=all&ids=x','runme',this)"
    game.options["experimental_id_batch_depart"] = experimental
    summary = selective_dispatch(game, registry)

    assert summary["approved"] == 1
    assert summary["departed"] == 0
    assert summary["status"] == ("nenhuma_aeronave_aprovada_agora" if experimental
                                 else "controle_individual_nao_disponivel")
    assert game.clicked == []
