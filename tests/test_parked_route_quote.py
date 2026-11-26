from types import SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

import native_route_quotes
import parked_route_quote as collector
import paths
from reroute import _FORM
from route_stopover import _FARES


NOW = 1_900_000_000
AIRCRAFT = "101"
ORIGIN = "1780"
DESTINATION = "3950"
SAMPLE = {"origin_id": ORIGIN, "destination_id": DESTINATION, "distance_km": 9830.576,
          "destination_runway_ft": 11154}
DETAIL = {"codes": ["BCN", "SHA"], "runways": ["11,654 ft", "11,154 ft"],
          "occupied": "0", "occupancy_label": "A/C on route", "observed_capable_aircraft": "1",
          "capable_aircraft_ids": [AIRCRAFT], "observed_daily_demand": {"y": "1,991", "j": "376", "f": "176"},
          "event_demand_boosted": True}
FORM = {"bound": True, "codes": ["BCN", "SHA"], "existing": "0", "distance": "9,831",
        "fee": "$996,630", "range": "14,500"}


class Bot:
    driver = object()
    stopping = False

    def __init__(self):
        self.events = []
        self.arrival = 17
        self.form_reads = iter([FORM, FORM])

    def ajax(self, url, target, *, timeout):
        assert (url, target, timeout) == (f"new_route_info.php?id={AIRCRAFT}&airportId={DESTINATION}&mode=res",
                                         "newRouteInfo", 8)
        assert self.arrival == int(DESTINATION)
        self.events.append("preview")
        return self

    def find_elements(self, method, selector):
        if (method, selector) == (By.ID, "introAuto"):
            return ["autoprice"]
        assert (method, selector) == (By.CSS_SELECTOR, "#btnCreateNewRoute:not(.not-active):not([disabled])")
        return ["create"]

    def click_element(self, element):
        assert element == "autoprice"
        self.events.append(element)

    def js(self, script, *args):
        if script == _FORM:
            assert args == (AIRCRAFT, DESTINATION)
            return next(self.form_reads)
        if script == _FARES:
            assert self.events == ["detail", "preview", "autoprice"]
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

    def sample(bot, *reads):
        replies = iter(reads)

        def detail(owner, origin, dest):
            assert owner is bot and (origin, dest) == (ORIGIN, DESTINATION)
            bot.events.append("detail")
            return next(replies)

        monkeypatch.setattr(collector, "research_details", detail)
        return collector.collect_parked_route_quote(bot, {AIRCRAFT})

    return sample


@pytest.mark.parametrize("daily_stable", [True, False])
def test_existing_aircraft_quote_with_only_read_only_actions(setup, daily_stable):
    bot = Bot()
    again = {**DETAIL, "event_demand_boosted": None}
    if not daily_stable:
        again["observed_daily_demand"] = {**DETAIL["observed_daily_demand"], "y": "1,990"}
    assert setup(bot, DETAIL, again)
    assert bot.events == ["detail", "preview", "autoprice", "close", "detail"]
    assert bot.arrival == 17
    rows = native_route_quotes.native_route_quotes(bot)
    row, = rows
    assert row["fares"] == {"y": 4103, "j": 8425, "f": 12998}
    assert row["route_fee"] == 996630 and row["distance_km"] == 9831
    assert row["event_demand_boosted"] is True
    assert row["daily_demand_total"] == ({"y": 1991, "j": 376, "f": 176} if daily_stable else None)
    assert row["daily_demand_residual"] is None and row["purchase_eligible"] is False
    lookup = {"profile_id": "test-parked-quote", "origin_id": ORIGIN, "destination_id": DESTINATION, "now": NOW}
    reference = native_route_quotes.reference_for_route(rows, **lookup, distance_km=SAMPLE["distance_km"])
    assert reference["native_distance_range"] == {"min": 9831, "max": 9831}
    assert reference["event_demand_boosted"] is True
    assert reference["purchase_eligible"] is False
    assert native_route_quotes.reference_for_route(rows, **lookup, distance_km=9830.577) is None


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


def test_changed_form_discards_preview(setup):
    bot = Bot()
    bot.form_reads = iter([FORM, {**FORM, "fee": "$996,631"}])
    assert not setup(bot, DETAIL)
    assert bot.events[-1] == "close" and bot.arrival == 17
    assert native_route_quotes.native_route_quotes(bot) == []


def test_timeout_restores_arrival(setup):
    class TimeoutBot(Bot):
        def ajax(self, *args, **kwargs):
            super().ajax(*args, **kwargs)
            raise TimeoutException()

    bot = TimeoutBot()
    assert not setup(bot, DETAIL)
    assert bot.events[-1] == "close" and bot.arrival == 17
    assert native_route_quotes.native_route_quotes(bot) == []
