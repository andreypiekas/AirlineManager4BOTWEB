from types import SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

import native_route_quotes
import parked_route_quote as collector
import paths
from market import MarketQuote
from reroute import _FORM
from route_stopover import _FARES, _READ, parked_seat_layout


NOW = 1_900_000_000
AIRCRAFT = "101"
ORIGIN = "1780"
DESTINATION = "3950"
SAMPLE = {"origin_id": ORIGIN, "destination_id": DESTINATION, "distance_km": 9830.576,
          "destination_runway_ft": 11154}
DETAIL = {"codes": ["BCN", "SHA"], "runways": ["11,654 ft", "11,154 ft"],
          "occupied": "0", "occupancy_label": "A/C on route", "observed_capable_aircraft": "1",
          "capable_aircraft_ids": [AIRCRAFT], "observed_daily_demand": {"y": "1,991", "j": "376", "f": "176"},
          "observed_today_demand": {"y": "1,800", "j": "300", "f": "160"},
          "event_demand_boosted": True}
FORM = {"bound": True, "codes": ["BCN", "SHA"], "existing": "0", "distance": "9,831",
        "fee": "$996,630", "range": "14,500", "fuel_lbs_per_leg": "212,273", "co2_kg_per_pax_km": "0.16"}


class Bot:
    driver = object()
    stopping = False

    def __init__(self):
        self.events = []
        self.arrival = 17
        self.form_reads = iter([FORM, FORM])
        self.preview_aircraft = iter([AIRCRAFT])
        self.fuel_quote = None

    def stats(self):
        return SimpleNamespace(fuel_quote=self.fuel_quote)

    def ajax(self, url, target, *, timeout):
        self.preview_id = next(self.preview_aircraft)
        assert (url, target, timeout) == (f"new_route_info.php?id={self.preview_id}&airportId={DESTINATION}&mode=res",
                                         "newRouteInfo", 8)
        assert self.arrival == int(DESTINATION)
        self.events.append("preview")
        return self

    def find_elements(self, method, selector):
        if (method, selector) == (By.ID, "introAuto"):
            return [SimpleNamespace(click=lambda: self.events.append("autoprice"))]
        assert (method, selector) == (By.CSS_SELECTOR, "#btnCreateNewRoute:not(.not-active):not([disabled])")
        return ["create"]

    def js(self, script, *args):
        if script == _FORM:
            assert args == (self.preview_id, DESTINATION)
            return next(self.form_reads)
        if script == _FARES:
            assert self.events[-2:] == ["preview", "autoprice"]
            return [{"value": price, "disabled": False} for price in ("4103", "8425", "12998")]
        if script.startswith("const previous"):
            previous, self.arrival = self.arrival, args[0]
            return previous
        assert script == "$('#newRouteInfo').hide(); arrId = arguments[0];"
        self.events.append("close")
        self.arrival = args[0]


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("test-parked-quote"))
    monkeypatch.setattr(native_route_quotes, "time", SimpleNamespace(time=lambda: NOW))
    monkeypatch.setattr(collector, "HubRegistry", lambda: SimpleNamespace(snapshot=lambda: {
        "hub_catalog_fresh": True, "hubs": [{"id": ORIGIN, "code": "BCN"}],
    }))

    def demand(origins):
        assert origins == {ORIGIN}
        return {"samples": [SAMPLE]}

    monkeypatch.setattr(collector, "HubExpansionRegistry", lambda: SimpleNamespace(demand_research_snapshot=demand))
    monkeypatch.setattr(collector, "parked_specs", lambda bot, aircraft: {"id": ORIGIN, "range": "14,500"})
    monkeypatch.setattr(collector, "parked_seat_layout", lambda bot, aircraft: None)

    def sample(bot, *reads, refresh_demand=False, parked_ids=(AIRCRAFT,)):
        replies = iter(reads)

        def detail(owner, origin, dest):
            assert owner is bot and (origin, dest) == (ORIGIN, DESTINATION)
            bot.events.append("detail")
            return next(replies)

        monkeypatch.setattr(collector, "research_details", detail)
        return collector.collect_parked_route_quote(bot, parked_ids, refresh_demand=refresh_demand)

    return sample


@pytest.mark.parametrize("daily_stable", [True, False])
@pytest.mark.parametrize("today_stable", [True, False])
def test_existing_aircraft_quote_with_only_read_only_actions(setup, daily_stable, today_stable):
    bot = Bot()
    again = {**DETAIL, "event_demand_boosted": None}
    if not daily_stable:
        again["observed_daily_demand"] = {**DETAIL["observed_daily_demand"], "y": "1,990"}
    if not today_stable:
        again.pop("observed_today_demand")
    assert setup(bot, DETAIL, again)
    assert bot.events == ["detail", "preview", "autoprice", "close", "detail"]
    assert bot.arrival == 17
    rows = native_route_quotes.native_route_quotes(bot)
    row, = rows
    assert row.get("observed_today_demand") == ({"y": 1800, "j": 300, "f": 160} if today_stable else None)
    assert row["fares"] == {"y": 4103, "j": 8425, "f": 12998}
    assert row["route_fee"] == 996630 and row["distance_km"] == 9831
    assert row["fuel_lbs_per_leg"] == 212273 and row["co2_kg_per_pax_km"] == 0.16
    assert row["event_demand_boosted"] is True
    assert row["daily_demand_total"] == ({"y": 1991, "j": 376, "f": 176} if daily_stable else None)
    assert row["daily_demand_residual"] is None and row["purchase_eligible"] is False
    lookup = {"profile_id": "test-parked-quote", "origin_id": ORIGIN, "destination_id": DESTINATION, "now": NOW}
    reference = native_route_quotes.reference_for_route(rows, **lookup, distance_km=SAMPLE["distance_km"])
    assert reference["native_distance_range"] == {"min": 9831, "max": 9831}
    assert reference["fuel_lbs_per_leg_range"] == {"min": 212273, "max": 212273}
    assert reference["co2_kg_per_pax_km_range"] == {"min": 0.16, "max": 0.16}
    assert reference["event_demand_boosted"] is True
    assert reference["purchase_eligible"] is False
    assert native_route_quotes.reference_for_route(rows, **lookup, distance_km=9830.577) is None


@pytest.mark.parametrize(("after", "expected"), [
    ((465, 28, 26), {"y": 465, "j": 28, "f": 26}),
    ((464, 28, 26), None),
    (None, None),
])
def test_observation_preserves_only_a_stable_aircraft_layout(setup, monkeypatch, after, expected):
    bot = Bot()
    reads = iter([(465, 28, 26), after])

    def layout(owner, aircraft):
        assert owner is bot and aircraft == AIRCRAFT
        bot.events.append("layout")
        return next(reads)

    monkeypatch.setattr(collector, "parked_seat_layout", layout)
    assert setup(bot, DETAIL, DETAIL, refresh_demand=True)
    assert bot.events == ["detail", "layout", "preview", "autoprice", "close", "detail", "layout"]
    row, = native_route_quotes.native_route_quotes(bot)
    assert row.get("observed_seat_layout") == expected
    assert row["fuel_lbs_per_leg"] == 212273 and row["purchase_eligible"] is False


def test_observation_discards_preview_if_native_origin_changes(setup, monkeypatch):
    bot = Bot()
    specs = iter([{"id": ORIGIN, "range": "14,500"}, {"id": "2947", "range": "14,500"}])
    monkeypatch.setattr(collector, "parked_specs", lambda bot, aircraft: next(specs))
    assert not setup(bot, DETAIL, DETAIL, refresh_demand=True)
    assert bot.events[-2:] == ["close", "detail"]
    assert native_route_quotes.native_route_quotes(bot) == []


@pytest.mark.parametrize(("price", "market_at", "expires_at", "observation", "cost_cents"), [
    (2450, NOW - 5, NOW + 1, True, 52006885),
    (2455, NOW - 3, NOW + 1, True, 52113022),
    (2450, NOW - 5, NOW, True, None),
    (2450, NOW - 2, NOW + 1, True, None),
    (0, NOW - 5, NOW + 1, True, None),
    (2450, NOW - 5, NOW + 1, False, None),
])
def test_fuel_price_must_cover_the_entire_observed_preview(
    setup, monkeypatch, price, market_at, expires_at, observation, cost_cents,
):
    bot = Bot()
    bot.fuel_quote = MarketQuote(price, market_at, expires_at)
    monkeypatch.setattr(collector, "time", SimpleNamespace(time=lambda: NOW - 3))
    assert setup(bot, DETAIL, DETAIL, refresh_demand=observation)
    row, = native_route_quotes.native_route_quotes(bot)
    assert row["fuel_lbs_per_leg"] == 212273
    assert row["purchase_eligible"] is False
    assert row.get("fuel_replacement_cost_per_leg_cents") == cost_cents
    if cost_cents is None:
        assert "preview_started_at" not in row and "fuel_market_quote" not in row
    else:
        assert row["preview_started_at"] == NOW - 3
        assert row["fuel_market_quote"] == {"source": "game_market", "unit": "USD/1000",
                                           "price": price, "observed_at": market_at, "expires_at": expires_at}


@pytest.mark.parametrize(("raw", "expected"), [
    (["1,005", "0", "26"], (1005, 0, 26)),
    (["0", "0", "0"], None),
    (["92", None, "20"], None),
    (["92", "39 seats", "20"], None),
    (["92", "39"], None),
])
def test_native_seat_layout_parses_all_three_unsigned_counts(raw, expected):
    def read(script, url, aircraft):
        assert (script, url, aircraft) == (_READ, "fleet_details.php?id=101", AIRCRAFT)
        return raw

    bot = SimpleNamespace(driver=SimpleNamespace(execute_async_script=read))
    assert parked_seat_layout(bot, AIRCRAFT) == expected


@pytest.mark.parametrize("unverified", [
    {"capable_aircraft_ids": ["102"]}, {"observed_capable_aircraft": "2"}, {"occupied": "1"},
    {"capable_aircraft_ids": [AIRCRAFT, AIRCRAFT], "observed_capable_aircraft": "2"},
])
def test_preview_requires_native_eligibility(setup, unverified):
    bot = Bot()
    assert not setup(bot, {**DETAIL, **unverified})
    assert bot.events == ["detail"]
    assert native_route_quotes.native_route_quotes(bot) == []


def test_loss_of_eligibility_discards_preview(setup):
    bot = Bot()
    assert not setup(bot, DETAIL, {**DETAIL, "capable_aircraft_ids": ["102"]})
    assert bot.events[-2:] == ["close", "detail"]
    assert native_route_quotes.native_route_quotes(bot) == []


@pytest.mark.parametrize("first_origin_matches", [True, False])
def test_observation_records_only_the_next_aircraft_after_an_invalid_preview(setup, first_origin_matches):
    bot = Bot()
    bot.preview_aircraft = iter([AIRCRAFT, "102"])
    next_detail = {**DETAIL, "capable_aircraft_ids": ["102"]}
    if first_origin_matches:
        bot.form_reads = iter([FORM, FORM, FORM, FORM])
        reads = (DETAIL, next_detail, next_detail, next_detail)
        first_actions = ["detail", "preview", "autoprice", "close", "detail"]
    else:
        bot.form_reads = iter([{**FORM, "codes": ["FUK", "SHA"]}, FORM, FORM])
        reads = (DETAIL, next_detail, next_detail)
        first_actions = ["detail", "preview", "close"]

    assert setup(bot, *reads, refresh_demand=True, parked_ids={"103", "102", AIRCRAFT})
    assert bot.events == first_actions + ["detail", "preview", "autoprice", "close", "detail"]
    assert bot.arrival == 17
    saved, = native_route_quotes.native_route_quotes(bot)
    assert saved["aircraft_id"] == "102" and saved["purchase_eligible"] is False


@pytest.mark.parametrize(("refresh_demand", "expected"), [(True, ["101", "102", "103"]), (False, ["101"])])
def test_candidate_limit_and_one_refresh_per_origin(setup, monkeypatch, refresh_demand, expected):
    bot = Bot()
    checked, actions = [], []

    def specs(owner, aircraft):
        checked.append(aircraft)
        return {"id": ORIGIN, "range": "14,500"}

    def refresh(owner, *, origin_id):
        actions.append(("research", origin_id))
        raise TimeoutException()

    bot.open_popup = lambda url, title, selector: actions.append(("reopen", url))
    monkeypatch.setattr(collector, "parked_specs", specs)
    monkeypatch.setattr(collector, "HubExpansionRegistry", lambda: SimpleNamespace(
        demand_research_snapshot=lambda origins: {"samples": []}))
    monkeypatch.setattr("game_observations.collect_owned_hub_demand", refresh)

    assert not setup(bot, refresh_demand=refresh_demand, parked_ids={"103", AIRCRAFT, "102", "104"})
    assert checked == expected
    assert actions == ([("research", ORIGIN), ("reopen", "routes_main.php")] if refresh_demand else [])


def test_observation_refreshes_the_owned_parked_origin_without_cached_samples(setup, monkeypatch):
    sample_reads = iter([{"samples": []}, {"samples": [SAMPLE]}])
    bot = Bot()
    actions = []

    def refresh(owner, *, origin_id):
        assert owner is bot
        actions.append(("research", origin_id))
        return 1

    bot.open_popup = lambda url, title, selector: actions.append(("reopen", url))
    monkeypatch.setattr(collector, "HubExpansionRegistry", lambda: SimpleNamespace(
        demand_research_snapshot=lambda origins: next(sample_reads)))
    monkeypatch.setattr("game_observations.collect_owned_hub_demand", refresh)
    assert setup(bot, DETAIL, DETAIL, refresh_demand=True)
    assert actions == [("research", ORIGIN), ("reopen", "routes_main.php")]


@pytest.mark.parametrize("changed", [{"fee": "$996,631"}, {"fuel_lbs_per_leg": "212,274"}])
def test_changed_form_discards_preview(setup, changed):
    bot = Bot()
    bot.form_reads = iter([FORM, {**FORM, **changed}])
    assert not setup(bot, DETAIL)
    assert bot.events[-1] == "close" and bot.arrival == 17
    assert native_route_quotes.native_route_quotes(bot) == []


def test_preview_from_another_airport_is_closed_before_autoprice(setup):
    bot = Bot()
    bot.form_reads = iter([{**FORM, "codes": ["FUK", "SHA"]}])
    assert not setup(bot, DETAIL)
    assert bot.events == ["detail", "preview", "close"] and bot.arrival == 17
    assert native_route_quotes.native_route_quotes(bot) == []


def test_unknown_consumption_preserves_only_the_other_preview_fields(setup):
    bot = Bot()
    form = {**FORM, "fuel_lbs_per_leg": "212,273 / 2", "co2_kg_per_pax_km": None}
    bot.form_reads = iter([form, form])
    assert setup(bot, DETAIL, DETAIL)
    row, = native_route_quotes.native_route_quotes(bot)
    assert row["route_fee"] == 996630
    assert "fuel_lbs_per_leg" not in row and "co2_kg_per_pax_km" not in row


def test_timeout_restores_arrival(setup):
    class TimeoutBot(Bot):
        def ajax(self, *args, **kwargs):
            super().ajax(*args, **kwargs)
            raise TimeoutException()

    bot = TimeoutBot()
    assert not setup(bot, DETAIL)
    assert bot.events[-1] == "close" and bot.arrival == 17
    assert native_route_quotes.native_route_quotes(bot) == []
