"""Individual Fleet dispatch: native control discovery, gating and confirmation."""
from __future__ import annotations

from fleet_single_depart import choose_depart_control, fleet_dispatch
from route_registry import RouteRegistry, endpoint
from selective_depart import plan_dispatch, selective_dispatch


def control(label="Depart", action="departAircraft(101)", *, index=0, visible=True, disabled=False):
    return {"index": index, "label": label, "action": action,
            "visible": visible, "disabled": disabled}


def test_fleet_button_selection_is_unique_scoped_and_non_bulk():
    chosen = control()
    assert choose_depart_control("101", [chosen]) == chosen
    assert choose_depart_control("101", [control("Decolar", "")]) is None
    assert choose_depart_control("101", [control("Despegar", "departFlight(101)")]) is not None
    assert choose_depart_control("101", [control("Depart", "departAircraft()")]) is None
    assert choose_depart_control("101", [control("Depart All")]) is None
    assert choose_depart_control("101", [control(disabled=True)]) is None
    assert choose_depart_control("101", [control(visible=False)]) is None
    assert choose_depart_control("101", [chosen, control(index=1)]) is None
    assert choose_depart_control("101", [control("Ground", "fleet_ground.php?id=444")]) is None
    assert choose_depart_control("101", [
        control("Depart", "Ajax('route_depart.php?mode=all&ids=101','runme')"),
    ]) is None
    assert choose_depart_control("101", [
        control("Depart", "Ajax('route_depart.php?mode=single&ids=999','runme')"),
    ]) is None
    assert choose_depart_control("101", [
        control("", "Ajax('route_depart.php?mode=single&ids=101','runme')"),
    ]) is not None
    assert choose_depart_control("101", [
        control("Depart", "Ajax('route_depart.php?ac=101','runme')"),
    ]) is not None
    assert choose_depart_control("101", [
        control("Depart", "Ajax('route_depart.php?ids=x','runme')"),
    ]) is None
    assert choose_depart_control("101", [
        control("Depart", "Ajax('route_depart.php?ac=103','runme')"),
    ]) is None
    assert choose_depart_control("not-id", [chosen]) is None


def setup_registry(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    dac, osl, lax, pbm = (endpoint(code=x) for x in ("DAC", "OSL", "LAX", "PBM"))
    registry.record("101", "PP-A", "A320", dac, osl, source="game")
    registry.record("102", "PP-B", "A320", osl, dac, source="game")
    registry.record("103", "PP-C", "A320", lax, pbm, source="game")
    return registry


class Game:
    dry_run = False
    stopping = False

    def __init__(self, *, button=None, raise_click=False):
        self.landed = {"101", "102", "103"}
        self.inflight = set()
        self.button = button
        self.raise_click = raise_click
        self.chosen = ""
        self.ajax_calls = []
        self.clicked = []
        self.counted = 0
        self.driver = self

    def ajax(self, path, target, timeout=12):
        assert path.startswith("fleet_details.php?id=")
        assert target == "detailsAction"
        self.chosen = path.split("=")[-1]
        self.ajax_calls.append(self.chosen)

    def js(self, script, *args):
        if "#landedList [id^='flightStatus']" in script:
            return [{"id": aircraft_id, "native_actions": []}
                    for aircraft_id in sorted(self.landed)]
        if ".querySelectorAll(" in script and "detailsAction" in script and "return Array.from(root" in script:
            return [self.button or control(action=f"departAircraft({self.chosen})")]
        if "data-am4-fleet-depart" in script:
            assert args[0] == self.chosen
            assert args[1] == (self.button or control())["index"]
            return True
        raise AssertionError("Unrecognized game script")

    def find_element(self, by, locator):
        assert self.chosen in locator
        game = self

        class NativeButton:
            def click(self):
                if game.raise_click:
                    from selenium.common.exceptions import WebDriverException
                    raise WebDriverException("Lost response")
                game.clicked.append(game.chosen)
                game.landed.remove(game.chosen)
                game.inflight.add(game.chosen)
        return NativeButton()

    def execute_script(self, script, aircraft_id):
        assert "inflightList" in script
        return aircraft_id in self.inflight

    def count(self, name):
        assert name == "departures"
        self.counted += 1


def test_fleet_dispatch_only_clicks_approved_not_duplicate_reserved(tmp_path):
    registry = setup_registry(tmp_path)
    game = Game()
    eligible = [d for d in plan_dispatch(["101", "102", "103"], registry.snapshot())
                if d.approved]
    result = fleet_dispatch(game, registry, eligible)
    assert game.ajax_calls == ["101", "103"]
    assert game.clicked == ["101", "103"]
    assert game.counted == 2
    assert result["departed"] == 2
    assert result["status"] == "decolagens_confirmadas"


def test_missing_or_ambiguous_fleet_button_never_clicks(tmp_path):
    registry = setup_registry(tmp_path)
    game = Game(button=control("Depart All"))
    eligible = [d for d in plan_dispatch(["101"], registry.snapshot()) if d.approved]
    result = fleet_dispatch(game, registry, eligible)
    assert result["status"] == "controle_individual_nao_disponivel"
    assert result["departed"] == 0
    assert game.clicked == []


def test_uncertain_click_stops_other_aircraft_without_retry(tmp_path):
    registry = setup_registry(tmp_path)
    game = Game(raise_click=True)
    eligible = [d for d in plan_dispatch(["101", "103"], registry.snapshot()) if d.approved]
    result = fleet_dispatch(game, registry, eligible)
    assert result["status"] == "clique_individual_resultado_incerto"
    assert game.ajax_calls == ["101"]
    assert game.counted == 0


def test_selective_dispatch_uses_fleet_without_bulk_when_no_row_actions(tmp_path):
    registry = setup_registry(tmp_path)
    game = Game()
    summary = selective_dispatch(game, registry)
    assert summary["mode"] == "seletivo_fleet"
    assert summary["departed"] == 2
    assert summary["native_individual"] == 2
    assert summary["blocked"] == 1
    assert summary["status"] == "decolagens_confirmadas"
    assert game.clicked == ["101", "103"]
