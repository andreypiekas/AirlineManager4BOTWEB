from types import SimpleNamespace

import pytest

import fleet
import reroute
import route_creation
import route_stopover
from fleet import ParkedAircraft, RouteCandidate
from gamemode import EASY
from route_registry import RouteRegistry, endpoint
from route_stopover import Stopover


@pytest.mark.parametrize("found", [True, False])
def test_plan_stopover_from_parked_base_before_direct_route(tmp_path, monkeypatch, found):
    origin = {"id": "3934", "range": "14,500", "runway": "9,680"}
    long_route = RouteCandidate("1440", "Los Angeles", 16000, 1200, 300, 100, 12000)
    direct_route = RouteCandidate("2891", "San Julian", 7000, 650, 100, 50, 6500)
    stop = Stopover("2601", 8000, 8200)
    calls = []
    registry = RouteRegistry(tmp_path / "routes.json")
    monkeypatch.setattr(fleet, "RouteRegistry", lambda: registry)
    monkeypatch.setattr(fleet, "read_parked", lambda bot: [ParkedAircraft("101", "A380", "PP-101", 600)])
    monkeypatch.setattr(fleet, "load_market", lambda: [])
    monkeypatch.setattr(fleet, "find_model", lambda *_: {
        "range": 14500, "speed": 1000, "fuel": 26, "capacity": 600,
    })
    monkeypatch.setattr(fleet, "parked_specs", lambda *_: origin)
    monkeypatch.setattr(fleet, "research_details", lambda *_: {"occupied": "0"})

    def search(bot, hub_id, distance, runway):
        assert hub_id == origin["id"]
        calls.append(distance)
        return [long_route] if distance == 21000 else [direct_route]

    def find(bot, specs, destination, reach, limit, runway):
        assert specs == origin and (destination, reach, limit) == ("1440", 14500, 21000)
        return stop if found else None

    def create(bot, aircraft, candidate, **kwargs):
        assert kwargs["origin_id"] == origin["id"]
        calls.append((candidate.arr_id, kwargs.get("stopover")))
        return "dry"

    monkeypatch.setattr(fleet, "search_routes", search)
    monkeypatch.setattr(fleet, "find_stopover", find)
    monkeypatch.setattr(fleet, "create_route", create)

    class Bot:
        config = SimpleNamespace(
            get_int=lambda section, name, default=0: 21000 if name == "route_max_distance_big" else default,
            get_bool=lambda section, name, default=False: name == "route_stopover",
        )
        mode = EASY
        stopping = False

        def js(self, script, *args):
            if script == fleet._HUB_OPTIONS_JS:
                return [{"id": "2926"}, {"id": "3934"}]
            if script == fleet._ON_ROUTE_JS:
                return "0"
            return "2926"  # The research screen initially shows a different base.

        def ajax(self, *_):
            return SimpleNamespace(find_elements=lambda *_: [True])

        def open_popup(self, *_):
            pass

        def load_factor(self):
            return 0.8

        def fuel_cost_basis(self):
            return 750

        def co2_cost_basis(self):
            return 150

    assert fleet.create_routes(Bot(), 1) == 1
    assert calls == ([21000, ("1440", stop)] if found else [21000, 14500, ("2891", None)])


def test_skip_stopover_with_short_runway(monkeypatch):
    origin = {"id": "2891", "range": "14,500", "runway": "9,680"}
    rows = [{"id": "3029", "first": 525, "second": 9994}, {"id": "2601", "first": 14500, "second": 3552}]
    details = {
        "3029": {"codes": ["ULA", "GXQ"], "runways": ["6562ft", "5072ft"]},
        "2601": {"codes": ["ULA", "ANC"], "runways": ["6562ft", "11584ft"]},
    }
    bot = SimpleNamespace(js=lambda *_: rows)
    monkeypatch.setattr(route_stopover, "research_details", lambda bot, origin, dest: details[dest])
    assert route_stopover.find_stopover(bot, origin, "1440", 14500, 21000, 5500) == Stopover("2601", 14500, 3552)


def test_form_requires_the_expected_stopover_and_total():
    form = {
        "codes": ["ULA", "LAX"], "via": "ANC", "bound": True, "ready": True,
        "distance": "18,052", "demand": ["438", "218", "193"], "fee": "$ 1,058,871", "occupied": "0",
    }
    bot = SimpleNamespace(js=lambda *_: form)
    stop = Stopover("2601", 14400, 3652)
    assert route_stopover.read_form(bot, "101", "2891", "1440", stop) == (18052, [438, 218, 193], 1058871, 0)
    form["distance"] = "10,010"
    assert route_stopover.read_form(bot, "101", "2891", "1440", stop) is None
    form.update(distance="18,052", via="GXQ")
    assert route_stopover.read_form(bot, "101", "2891", "1440", stop) is None
    form.update(via="ANC", bound=False)
    assert route_stopover.read_form(bot, "101", "2891", "1440", stop) is None


@pytest.mark.parametrize("via", ["ANC", ""])
def test_confirm_route_requires_readback_of_stopover(monkeypatch, via):
    live = reroute.LiveRoute("123", False, ("LAX", "ULA"), True, via)

    def check(bot, aircraft_id, condition):
        return live if condition(live) else None

    monkeypatch.setattr(reroute, "_check_route", check)
    assert reroute.confirm_stopover(
        object(), "101", endpoint("2891"), endpoint("1440"), endpoint("2601")
    ) is bool(via)


@pytest.mark.parametrize("confirmed", [True, False])
def test_submit_native_form_once_and_record_only_after_confirmation(tmp_path, monkeypatch, confirmed):
    registry = RouteRegistry(tmp_path / "routes.json")
    monkeypatch.setattr(route_creation, "pending_path", lambda: tmp_path / "route_creation_pending.json")
    monkeypatch.setattr(fleet, "RouteRegistry", lambda: registry)
    monkeypatch.setattr(fleet, "read_form", lambda *_: (18052, (900, 400, 150), 1058871, 0))
    monkeypatch.setattr(fleet, "confirm_stopover", lambda *_: confirmed)
    actions = []

    class Bot:
        dry_run = False
        stopping = False

        def js(self, script, *args):
            if "'eSeat', 'bSeat', 'fSeat'" in script:
                return [{"value": price, "disabled": False} for price in ("6000", "9000", "12500")]
            return None

        def ajax(self, url, target, timeout):
            assert url == "new_route_info.php?id=101&airportId=1440&stopoverId=2601&ferry=0"
            return SimpleNamespace(find_element=lambda _, path: path, find_elements=lambda *_: ["autoprice"])

        def can_spend(self, *_args, **_kwargs):
            return True

        def read_money(self):
            return 2000000

        def click_element(self, element):
            actions.append(element)

        def pause(self, *_args):
            pass

        def wait_text(self, xpath, timeout):
            return ""

        def record_route_expense(self, intent_id, fee):
            assert len(intent_id) == 32
            actions.append((fee, True))

        def notify(self, message, *, category):
            assert "via ANC" in message

    result = fleet.create_route(
        Bot(), ParkedAircraft("101", "A380", "PP-101", 600),
        RouteCandidate("1440", "Los Angeles", 15000, 0, 0, 0, 12000), origin_id="2891",
        stopover=Stopover("2601", 14400, 3652),
        stopover_economics=dict(seats=600, model={"capacity": 600, "speed": 1000, "fuel": 26},
                                mode=EASY, load_factor=0.8, fuel_price=750, co2_price=150, premium=False),
    )
    assert result == ("created" if confirmed else "stop")
    assert sum("btnCreateNewRoute" in action for action in actions if isinstance(action, str)) == 1
    assert ((1058871, True) in actions) is confirmed
    assert route_creation.has_pending_creation() is not confirmed
    records = registry.snapshot()["relations"]
    assert (records[0]["stopover"]["code"] if records else None) == ("ANC" if confirmed else None)
