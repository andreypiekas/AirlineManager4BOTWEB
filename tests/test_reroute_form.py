"""Native price timers and range checks must finish before a route can be submitted."""
from types import SimpleNamespace

import pytest

import reroute
import fleet
from gamemode import EASY
from native_route_quotes import native_route_quotes
from route_stopover import read_route_fares
from airport_catalog import by_code
from route_registry import endpoint


@pytest.mark.parametrize("fields,expected", [
    ([{"value": "100", "disabled": False}, {"value": "200", "disabled": False},
      {"value": "300", "disabled": False}], (100, 200, 300)),
    ([{"value": "100", "disabled": False}, {"value": "", "disabled": True},
      {"value": "0", "disabled": True}], (100, 0, 0)),
    ([{"value": "100", "disabled": False}, {"value": "", "disabled": False},
      {"value": "300", "disabled": False}], None),
    ([{"value": "100", "disabled": False}, {"value": "-200", "disabled": False},
      {"value": "300", "disabled": False}], None),
    ([{"value": "100", "disabled": False}, None, {"value": "300", "disabled": False}], None),
    (None, None),
])
def test_native_route_fares_require_unambiguous_fields(fields, expected):
    assert read_route_fares(SimpleNamespace(js=lambda *_: fields)) == expected


@pytest.mark.parametrize("distance,expected", [(1000, True), (6000, False), (None, False)])
def test_form_waits_for_all_classes_and_checks_native_range(distance, expected):
    button, auto = object(), object()
    reads, clicks = [], []

    def form_read(script, *_):
        if "'eSeat', 'bSeat', 'fSeat'" in script:
            reads.append(True)
            return ([{"value": price, "disabled": False} for price in ("100", "200", "300")]
                    if len(reads) > 1 else None)
        return dict(codes=["LAX", "MIA"], bound=True, existing="0", fee="100",
                    range="5500", distance=distance)

    panel = SimpleNamespace(find_elements=lambda by, selector: [auto] if selector == "introAuto" else [button])
    bot = SimpleNamespace(
        ajax=lambda *_: panel,
        js=form_read,
        read_money=lambda: 1000,
        config=SimpleNamespace(get_int=lambda *_: 100),
        click_element=lambda element: clicks.append(element),
        driver=SimpleNamespace(),
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


@pytest.mark.parametrize("second,balance,second_fares", [
    ((1000, 1100, 0), 5000, (100, 200, 300)), (None, 5000, (100, 200, 300)),
    ((1000, 1000, 0), None, (100, 200, 300)), ((1000, 1000, 0), 999, (100, 200, 300)),
    ((1000, 1000, 0), 5000, (100, 201, 300)), ((1000, 1000, 0), 5000, None),
])
def test_parked_direct_route_aborts_before_submit_when_form_or_cash_changes(monkeypatch, second, balance, second_fares):
    quotes = iter([(1000, 1000, 0), second])
    monkeypatch.setattr(fleet, "read_direct_form", lambda *args, **kwargs: next(quotes))
    actions = []
    fares = iter([(100, 200, 300), second_fares])
    monkeypatch.setattr(fleet, "read_route_fares", lambda *_: next(fares))
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
                              profit_per_day=100, allow_duplicates=False) == "stop"
    assert actions == ["autoprice"]
    retained = native_route_quotes(bot)
    if second == (1000, 1000, 0) and second_fares == (100, 200, 300):
        assert len(retained) == 1
        assert retained[0]["route_fee"] == 1000
        assert retained[0]["daily_demand_total"] is None
    else:
        assert retained == []


def test_dry_run_collects_quote_without_submitting(monkeypatch):
    monkeypatch.setattr(fleet, "read_direct_form", lambda *args, **kwargs: (1000, 1000, 0))
    monkeypatch.setattr(fleet, "read_route_fares", lambda *_: (100, 200, 300))
    actions = []
    panel = SimpleNamespace(find_elements=lambda *_: ["autoprice"],
                            find_element=lambda *_: pytest.fail("Unexpected route submission"))
    bot = SimpleNamespace(js=lambda *_: None, ajax=lambda *_: panel, can_spend=lambda *a, **kw: True,
                          click_element=actions.append, pause=lambda *_: None, dry_run=True,
                          stopping=False, notify=lambda *a, **kw: None)
    aircraft = fleet.ParkedAircraft("5", "A320", "TEST", 180)
    candidate = fleet.RouteCandidate(by_code("MIA").game_id, "Miami", 1000, 500, 50, 20, 8000)
    assert fleet.create_route(bot, aircraft, candidate, origin_id=by_code("LAX").game_id) == "dry"
    assert actions == ["autoprice"]
    assert native_route_quotes(bot)[0]["purchase_eligible"] is False


def _prepare_live_direct_route(monkeypatch, *, fares=(1000, 1200, 1500), direct_form=(1004, 1000, 0)):
    actions = []
    staged = {}
    quotes = []
    panel = SimpleNamespace(
        find_elements=lambda *_: ["autoprice"],
        find_element=lambda *_: "create",
    )

    class Registry:
        def invalidate_fleet_coverage(self):
            pass

    def stage(_aircraft, _origin, _destination, _stopover, _fee, profit, **_kwargs):
        staged["profit_per_day"] = profit
        return {"intent_id": "test"}

    monkeypatch.setattr(fleet, "has_pending_creation", lambda: False)
    monkeypatch.setattr(fleet, "read_direct_form", lambda *_args, **_kwargs: direct_form)
    monkeypatch.setattr(fleet, "read_route_fares", lambda *_: fares)
    monkeypatch.setattr(fleet, "record_native_route_quote",
                        lambda *args, **kwargs: quotes.append((args, kwargs)))
    monkeypatch.setattr(fleet, "RouteRegistry", Registry)
    monkeypatch.setattr(fleet, "stage_creation", stage)
    monkeypatch.setattr(fleet, "finish_creation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(fleet, "confirm_direct_route", lambda *_: True)

    bot = SimpleNamespace(
        ajax=lambda *_args, **_kwargs: panel,
        js=lambda *_args, **_kwargs: None,
        click_element=actions.append,
        pause=lambda *_: None,
        can_spend=lambda *_args, **_kwargs: True,
        dry_run=False,
        stopping=False,
        read_money=lambda: 5000,
        config=SimpleNamespace(get_int=lambda *_: 0),
        wait_text=lambda *_args, **_kwargs: "Rota criada",
        notify=lambda *_args, **_kwargs: None,
    )
    return bot, actions, staged, quotes


def test_direct_route_recalculates_profit_with_live_form_fares(monkeypatch):
    fares = (1000, 1200, 1500)
    bot, actions, staged, quotes = _prepare_live_direct_route(monkeypatch, fares=fares)
    aircraft = fleet.ParkedAircraft("5", "A320", "TEST", 180)
    candidate = fleet.RouteCandidate(by_code("MIA").game_id, "Miami", 1000, 500, 50, 20, 8000)
    economics = dict(
        seats=180, model={"speed": 800, "fuel": 7, "capacity": 180}, mode=EASY,
        load_factor=0.8, fuel_price=650, co2_price=125, premium=False,
    )
    expected = fleet.estimate_route(
        fleet.RouteCandidate(candidate.arr_id, candidate.name, 1004, candidate.y,
                             candidate.j, candidate.f, candidate.runway, candidate.code),
        **economics, prices=fares,
    )

    result = fleet.create_route(
        bot, aircraft, candidate, origin_id=by_code("LAX").game_id,
        profit_per_day=123, route_economics=economics,
    )

    assert result == "created"
    assert staged["profit_per_day"] == pytest.approx(expected.profit_per_day)
    assert staged["profit_per_day"] != 123
    assert len(quotes) == 1
    assert actions == ["autoprice", "create"]


def test_direct_route_keeps_legacy_profit_when_economics_are_omitted(monkeypatch):
    bot, _actions, staged, _quotes = _prepare_live_direct_route(monkeypatch)
    aircraft = fleet.ParkedAircraft("5", "A320", "TEST", 180)
    candidate = fleet.RouteCandidate(by_code("MIA").game_id, "Miami", 1000, 500, 50, 20, 8000)

    result = fleet.create_route(
        bot, aircraft, candidate, origin_id=by_code("LAX").game_id, profit_per_day=123,
    )

    assert result == "created"
    assert staged["profit_per_day"] == 123


@pytest.mark.parametrize(
    "route_economics,initial_profit,actual_profit",
    [
        (None, None, None),
        ({"model": {"speed": 800, "fuel": 7}}, 250, None),
        ({"model": {"speed": 800, "fuel": 7}}, 250, 0),
        ({"model": {"speed": 800, "fuel": 7}}, 250, -1),
        ({"model": {"speed": 800, "fuel": 7}}, 250, float("nan")),
    ],
)
def test_direct_route_does_not_submit_when_live_profit_is_unknown_or_nonpositive(
    monkeypatch, route_economics, initial_profit, actual_profit,
):
    bot, actions, staged, quotes = _prepare_live_direct_route(monkeypatch)
    if route_economics is not None:
        estimate = (None if actual_profit is None
                    else SimpleNamespace(profit_per_day=actual_profit))
        monkeypatch.setattr(fleet, "estimate_route", lambda *_args, **_kwargs: estimate)
    bot.read_money = lambda: pytest.fail("Unknown-profit route reached the balance check")
    aircraft = fleet.ParkedAircraft("5", "A320", "TEST", 180)
    candidate = fleet.RouteCandidate(by_code("MIA").game_id, "Miami", 1000, 500, 50, 20, 8000)

    result = fleet.create_route(
        bot, aircraft, candidate, origin_id=by_code("LAX").game_id,
        profit_per_day=initial_profit, route_economics=route_economics,
    )

    assert result == "none"
    assert actions == ["autoprice"]
    assert staged == {}
    assert quotes == []


@pytest.mark.parametrize("codes,paused,via,expected", [
    (("LAX", "MIA"), False, "", True),
    (("MIA", "LAX"), False, "", True),
    (("LAX", "JFK"), False, "", False),
    (("LAX", "MIA"), True, "", False),
    (("LAX", "MIA"), False, "ANC", False),
])
def test_direct_confirmation_requires_independent_matching_active_route(monkeypatch, codes, paused, via, expected):
    live = reroute.LiveRoute("101", paused, codes, True, via)
    monkeypatch.setattr(reroute, "_check_route", lambda *_: live)
    assert reroute.confirm_direct_route(object(), "5", endpoint(code="LAX"), endpoint(code="MIA")) is expected


def test_direct_confirmation_requires_readback(monkeypatch):
    monkeypatch.setattr(reroute, "_check_route", lambda *_: None)
    assert not reroute.confirm_direct_route(object(), "5", endpoint(code="LAX"), endpoint(code="MIA"))
