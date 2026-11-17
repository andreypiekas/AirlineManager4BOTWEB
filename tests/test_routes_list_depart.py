"""AM4 2026-11-17 HTML: individual Depart uses ROUTE ID, not aircraft ID."""
from __future__ import annotations

from html.parser import HTMLParser

from route_registry import RouteRegistry, endpoint
from routes_list_depart import native_route_button, route_list_dispatch
from selective_depart import plan_dispatch, selective_dispatch


def native_row(aircraft_id, route_id, **overrides):
    row = {
        "row_id": f"routeMainList{route_id}",
        "route_id": str(route_id),
        "aircraft_id": str(aircraft_id),
        "link_count": 1,
        "button_id": f"listDepart{route_id}",
        "label": "Depart", "visible": True, "disabled": False,
        "action": (
            f"$('#rList{aircraft_id}').hide();hideFlightInfo();"
            f"Ajax('route_depart.php?id={route_id}&ref=list&costIndex=200','runme',this);"
        ),
    }
    row.update(overrides)
    return row


def test_real_game_route_id_differs_from_aircraft_id():
    # Literal ID correspondence extracted from a row in the uploaded AM4 HTML.
    row = native_row("24265127", "36562620")
    assert native_route_button("24265127", row) == row
    assert native_route_button("36562620", row) is None


def test_raw_html_fixture_matches_native_contract():
    sample = """
    <div class="row listDepartable" id="routeMainList36562620">
      <a onclick="Ajax('fleet_details.php?id=24265127','detailsAction')">
        <span id="acRegList24265127">PP-141-4</span></a>
      <button id="listDepart36562620"
          onclick="$('#rList24265127').hide();hideFlightInfo();Ajax('route_depart.php?id=36562620&amp;ref=list&amp;costIndex=200','runme',this);">Depart</button>
    </div>"""
    class ReadFixture(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.aircraft_id = ""
            self.route_id = ""
            self.action = ""
            self.button_id = ""

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "div" and attrs.get("id", "").startswith("routeMainList"):
                self.route_id = attrs["id"].removeprefix("routeMainList")
            if tag == "a" and "fleet_details.php?id=" in attrs.get("onclick", ""):
                self.aircraft_id = attrs["onclick"].split("fleet_details.php?id=")[1].split("'")[0]
            if tag == "button" and attrs.get("id", "").startswith("listDepart"):
                self.button_id = attrs["id"]
                self.action = attrs.get("onclick", "")
    parser = ReadFixture()
    parser.feed(sample)
    row = native_row(parser.aircraft_id, parser.route_id,
                     button_id=parser.button_id, action=parser.action)
    assert native_route_button(parser.aircraft_id, row) == row


def test_invalid_bulk_wrong_route_or_unproven_row_are_blocked():
    correct = native_row("101", "890")
    assert native_route_button("101", correct)
    assert native_route_button("101", {**correct, "link_count": 2}) is None
    assert native_route_button("101", {**correct, "aircraft_id": "102"}) is None
    assert native_route_button("101", {**correct, "button_id": "listDepart101"}) is None
    assert native_route_button("101", {**correct, "row_id": "routeMainList101"}) is None
    assert native_route_button("101", {**correct, "visible": False}) is None
    assert native_route_button("101", {**correct, "disabled": True}) is None
    assert native_route_button("101", {**correct, "action": (
        "Ajax('route_depart.php?id=101&ref=list&costIndex=200','runme',this)"
    )}) is None  # aircraft ID instead of route ID
    assert native_route_button("101", {**correct, "action": (
        "Ajax('route_depart.php?mode=all&ids=x','runme',this)"
    )}) is None
    assert native_route_button("101", {**correct, "action": (
        "Ajax('route_depart.php?id=890&ref=list&costIndex=200&ids=x','runme',this)"
    )}) is None
    assert native_route_button("101", {**correct, "action": (
        "Ajax('route_depart.php?id=890&ref=list&costIndex=200&fbSig=secret','runme',this)"
    )}) is None
    assert native_route_button("101", {**correct, "action": (
        "Ajax('route_depart.php?id=890&ref=all&costIndex=200','runme',this)"
    )}) is None
    assert native_route_button("101", {**correct, "label": "Depart All"}) is None


def setup_registry(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    a, b, c, d = [endpoint(code=code) for code in ("DAC", "OSL", "LAX", "PBM")]
    registry.record("101", "PP-A", "A320", a, b, source="game")
    registry.record("102", "PP-B", "A320", b, a, source="game")
    registry.record("103", "PP-C", "A320", c, d, source="game")
    return registry


class NativeGame:
    stopping = False
    dry_run = False

    def __init__(self, *, uncertain=False, rejected_ids=(), inconclusive=False):
        self.landed = {"101", "102", "103"}
        self.inflight = set()
        self.rows = [native_row("101", "890"), native_row("102", "891"),
                     native_row("103", "892")]
        self.clicked = []
        self.uncertain = uncertain
        self.rejected_ids = set(rejected_ids)
        self.inconclusive = inconclusive
        self.attempted = []
        self.driver = self

    def js(self, script, *args):
        if 'const elements = [document.getElementById("runme")' in script:
            return {"fingerprint": "0:abcd", "reason": "nao_informado"}
        if "const aircraftId = String(arguments[0]), routeId = String(arguments[1]);" in script:
            aid, rid = args
            return {
                "inflight": aid in self.inflight,
                "landed": aid in self.landed and not self.inconclusive,
                "same_route": any(r["aircraft_id"] == aid and r["route_id"] == rid for r in self.rows),
                "button_ready": True,
                "response_reason": "nao_informado",
            }
        if "data-am4-safe-route-depart" in script:
            aircraft_id, route_id, action = args
            row = [r for r in self.rows
                   if r["aircraft_id"] == aircraft_id and r["route_id"] == route_id]
            return len(row) == 1 and row[0]["action"] == action
        if "routeMainList" in script and "routesContainer" in script:
            return self.rows
        if "#landedList [id^='flightStatus']" in script:
            return [{"id": i, "native_actions": []} for i in sorted(self.landed)]
        raise AssertionError("unexpected JS query")

    def execute_script(self, script, aircraft_id=None):
        if 'const elements = [document.getElementById("runme")' in script:
            return {"fingerprint": "0:abcd", "reason": "nao_informado"}
        assert "inflightList" in script
        return aircraft_id in self.inflight

    def find_element(self, by, locator):
        game = self
        rows = [r for r in game.rows if r["route_id"] in locator
                and r["aircraft_id"] in locator]
        assert len(rows) == 1
        row = rows[0]

        class Button:
            def click(self):
                if game.uncertain:
                    from selenium.common.exceptions import WebDriverException
                    raise WebDriverException("response uncertain")
                assert row["aircraft_id"] in game.landed
                game.attempted.append((row["aircraft_id"], row["route_id"]))
                if row["aircraft_id"] in game.rejected_ids:
                    return  # Game received the native click but refused to depart.
                game.clicked.append((row["aircraft_id"], row["route_id"]))
                game.landed.remove(row["aircraft_id"])
                game.inflight.add(row["aircraft_id"])
        return Button()

    def count(self, name):
        assert name == "departures"


def test_selective_dispatch_clicks_route_buttons_for_only_approved_planes(tmp_path):
    registry = setup_registry(tmp_path)
    game = NativeGame()
    result = selective_dispatch(game, registry)
    assert result["mode"] == "seletivo_rotas_fleet"
    assert result["status"] == "decolagens_confirmadas"
    assert result["ready_seen"] == 3
    assert result["approved"] == 2
    assert result["blocked"] == 1
    assert result["departed"] == 2
    assert game.clicked == [("101", "890"), ("103", "892")]


def test_uncertain_native_click_never_attempts_other_aircraft(tmp_path):
    registry = setup_registry(tmp_path)
    game = NativeGame(uncertain=True)
    approved = [d for d in plan_dispatch(["101", "102", "103"], registry.snapshot())
                if d.approved]
    result = route_list_dispatch(game, registry, approved)
    assert result["status"] == "clique_individual_resultado_incerto"
    assert result["departed"] == 0
    assert game.clicked == []


def test_refused_departure_still_landed_continues_other_approved_aircraft(tmp_path, monkeypatch):
    import routes_list_depart as module

    registry = setup_registry(tmp_path)
    game = NativeGame(rejected_ids={"101"})
    monkeypatch.setattr(
        module, "_confirm_inflight", lambda bot, aircraft_id, **kwargs: aircraft_id in bot.inflight
    )
    summary = selective_dispatch(game, registry)
    assert summary["mode"] == "seletivo_rotas_fleet"
    assert summary["rejected"] == 1
    assert summary["departed"] == 1
    assert summary["status"] == "decolagens_parciais_com_recusas"
    assert game.attempted == [("101", "890"), ("103", "892")]
    assert game.clicked == [("103", "892")]
    assert "101" in game.landed
    assert registry.snapshot()["last_dispatch"]["rejected"] == 1


def test_inconclusive_flight_state_stops_without_departing_next(tmp_path, monkeypatch):
    import routes_list_depart as module

    registry = setup_registry(tmp_path)
    game = NativeGame(rejected_ids={"101"}, inconclusive=True)
    monkeypatch.setattr(
        module, "_confirm_inflight", lambda bot, aircraft_id: aircraft_id in bot.inflight
    )
    approved = [d for d in plan_dispatch(["101", "102", "103"], registry.snapshot())
                if d.approved]
    result = route_list_dispatch(game, registry, approved)
    assert result["status"] == "decolagem_sem_confirmacao"
    assert result["rejected"] == 0
    assert result["departed"] == 0
    assert game.attempted == [("101", "890")]
    assert game.clicked == []


def test_failed_game_state_read_never_assumes_a_refusal(tmp_path, monkeypatch):
    import routes_list_depart as module

    registry = setup_registry(tmp_path)
    game = NativeGame(rejected_ids={"101"})
    monkeypatch.setattr(
        module, "_confirm_inflight", lambda bot, aircraft_id, **kwargs: False
    )
    monkeypatch.setattr(
        module, "reconcile_failed_confirmation", lambda bot, aid, rid: {}
    )
    approved = [d for d in plan_dispatch(["101", "102", "103"], registry.snapshot())
                if d.approved]
    result = route_list_dispatch(game, registry, approved)
    assert result["status"] == "decolagem_sem_confirmacao"
    assert game.attempted == [("101", "890")]
