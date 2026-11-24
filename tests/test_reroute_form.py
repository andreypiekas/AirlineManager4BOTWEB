"""Native price timers and range checks must finish before a route can be submitted."""
from types import SimpleNamespace

import pytest

import reroute
import fleet
from airport_catalog import by_code
from route_registry import endpoint


@pytest.mark.parametrize("distance,expected", [(1000, True), (6000, False), (None, False)])
def test_form_waits_for_all_classes_and_checks_native_range(distance, expected):
    button, auto = object(), object()
    reads, clicks = [], []

    def price_read(script):
        reads.append(True)
        return len(reads) > 1

    panel = SimpleNamespace(find_elements=lambda by, selector: [auto] if selector == "introAuto" else [button])
    bot = SimpleNamespace(
        ajax=lambda *_: panel,
        js=lambda *_: dict(codes=["LAX", "MIA"], bound=True, existing="0", fee="100",
                           range="5500", distance=distance),
        read_money=lambda: 1000,
        config=SimpleNamespace(get_int=lambda *_: 100),
        click_element=lambda element: clicks.append(element),
        driver=SimpleNamespace(execute_script=price_read),
    )
    result = reroute._prepare_form(bot, "5", endpoint(code="LAX"), endpoint(by_code("MIA").game_id, code="MIA"))
    assert bool(result) == expected
    assert clicks == ([auto] if expected else [])
    if expected:
        assert result == (button, 100)
        assert len(reads) >= 2


@pytest.mark.parametrize("changes", [
    {"bound": False}, {"codes": ["MIA", "LAX"]}, {"fee": "$ 100 / 200"},
    {"fee": "-$ 100"}, {"fee": "$ 100.00"}, {"fee": None},
    {"existing": None}, {"existing": "-0"}, {"existing": "1"},
    {"range": "5,50"}, {"distance": "1 km / 2"},
])
def test_direct_form_rejects_ambiguous_or_mismatched_evidence(changes):
    form = dict(codes=["LAX", "MIA"], bound=True, existing="0", fee="$ 1,000",
                range="5,500", distance="1,000")
    form.update(changes)
    bot = SimpleNamespace(js=lambda *_: form)
    origin = endpoint(code="LAX")
    destination = endpoint(by_code("MIA").game_id, code="MIA")
    assert reroute.read_direct_form(bot, "5", origin, destination) is None


@pytest.mark.parametrize("occupied,allowed,expected", [("0", False, (1000, 1000, 0)),
                                                     ("2", True, (1000, 1000, 2)),
                                                     (None, True, None)])
def test_direct_form_distinguishes_duplicate_policy_and_unknown(occupied, allowed, expected):
    bot = SimpleNamespace(js=lambda *_: dict(codes=["LAX", "MIA"], bound=True, existing=occupied,
                                             fee="$ 1,000", range="5,500", distance="1,000"))
    assert reroute.read_direct_form(bot, "5", endpoint(code="LAX"),
                                    endpoint(by_code("MIA").game_id, code="MIA"),
                                    allow_duplicates=allowed) == expected


@pytest.mark.parametrize("second,balance", [((1000, 1100, 0), 5000), (None, 5000),
                                           ((1000, 1000, 0), None), ((1000, 1000, 0), 999)])
def test_parked_direct_route_aborts_before_submit_when_form_or_cash_changes(monkeypatch, second, balance):
    quotes = iter([(1000, 1000, 0), second])
    monkeypatch.setattr(fleet, "read_direct_form", lambda *args, **kwargs: next(quotes))
    actions = []
    panel = SimpleNamespace(find_elements=lambda *_: ["autoprice"],
                            find_element=lambda *_: pytest.fail("Unexpected route submission"))

    def js(script, *_):
        if "'eSeat', 'bSeat', 'fSeat'" in script:
            return ["100", "200", "300"]
        return None

    bot = SimpleNamespace(js=js, ajax=lambda *_: panel, can_spend=lambda *a, **kw: True,
                          click_element=actions.append, pause=lambda *_: None, dry_run=False,
                          stopping=False, read_money=lambda: balance)
    aircraft = fleet.ParkedAircraft("5", "A320", "TEST", 180)
    candidate = fleet.RouteCandidate(by_code("MIA").game_id, "Miami", 1000, 500, 50, 20, 8000)
    assert fleet.create_route(bot, aircraft, candidate, origin_id=by_code("LAX").game_id,
                              allow_duplicates=False) == "stop"
    assert actions == ["autoprice"]
