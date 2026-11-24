from types import SimpleNamespace

import pytest

import paths
from native_route_quotes import native_route_quotes, record_native_route_quote, reference_for_route


NOW = 1_900_000_000


def quote(bot, **overrides):
    values = dict(aircraft_id="101", origin_id="11", destination_id="12",
                  distance=1000, fee=2500, occupied=0, fares=(100, 200, 300), now=NOW)
    return record_native_route_quote(bot, **{**values, **overrides})


def test_scope_and_freshness_are_preserved(monkeypatch):
    bot = SimpleNamespace()
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("test-one"))
    assert quote(bot, stopover_id="13", total_demand=(500, 50, 10))
    rows = native_route_quotes(bot, now=NOW + 100)
    assert rows[0]["scope"] == "existing_aircraft_only"
    assert rows[0]["purchase_eligible"] is False
    assert rows[0]["daily_demand_residual"] is None
    assert rows[0]["daily_demand_total"] == {"y": 500, "j": 50, "f": 10}
    assert rows[0]["observed_at"] == NOW
    rows[0]["fares"]["y"] = 1
    assert native_route_quotes(bot, now=NOW)[0]["fares"]["y"] == 100
    assert native_route_quotes(bot, now=NOW + 901) == []
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("test-two"))
    assert native_route_quotes(bot, now=NOW) == []


@pytest.mark.parametrize("invalid", [
    {"origin_id": ""}, {"origin_id": "12"}, {"stopover_id": "12"},
    {"fee": True}, {"distance": 0}, {"occupied": -1},
    {"fares": (100, 200)}, {"fares": (0, 0, 0)}, {"total_demand": (1, None, 3)},
])
def test_invalid_quote_is_not_retained(invalid):
    bot = SimpleNamespace()
    assert not quote(bot, **invalid)
    assert native_route_quotes(bot, now=NOW) == []


def test_deduplication_keeps_aircraft_direction_and_stopover_distinct():
    bot = SimpleNamespace()
    assert quote(bot)
    assert quote(bot, fee=2600, now=NOW + 1)
    assert quote(bot, aircraft_id="102", now=NOW + 1)
    assert quote(bot, origin_id="12", destination_id="11", now=NOW + 1)
    assert quote(bot, stopover_id="13", now=NOW + 1)
    rows = native_route_quotes(bot, now=NOW + 1)
    assert len(rows) == 4
    assert rows[0]["route_fee"] == 2600
    assert rows[0]["daily_demand_total"] is None


def test_collection_is_bounded():
    bot = SimpleNamespace()
    for index in range(300):
        assert quote(bot, aircraft_id=str(1000 + index))
    rows = native_route_quotes(bot, now=NOW)
    assert len(rows) == 256
    assert rows[0]["aircraft_id"] == "1044"


def test_reference_filters_profile_clock_direction_and_stopover():
    bot = SimpleNamespace()
    assert quote(bot, aircraft_id="900001", stopover_id="13", now=NOW - 10)
    assert quote(bot, aircraft_id="900002", stopover_id="13", fee=3000,
                 fares=(120, 200, 400), occupied=2)
    assert quote(bot, aircraft_id="900003")
    rows = native_route_quotes(bot, now=NOW)
    original = rows[0]
    rows.extend([
        {**original, "profile_id": "other"},
        {**original, "observed_at": NOW - 901},
        {**original, "observed_at": NOW + 1},
        {**original, "origin_id": "12", "destination_id": "11"},
        {**original, "distance_km": 999},
        {**original, "purchase_eligible": True},
        {**original, "scope": "future_aircraft"},
        {**original, "route_fee": True},
        {**original, "fares": {"y": 100, "j": 200, "f": -1}},
        {**original, "aircraft_id": ""},
        None,
    ])
    args = dict(profile_id=paths.current().label, origin_id="11", destination_id="12",
                distance_km=1000, stopover_id="13", now=NOW)
    ref = reference_for_route(rows, **args)
    assert ref["quote_count"] == 2
    assert ref["route_fee_range"] == {"min": 2500, "max": 3000}
    assert ref["fare_ranges"] == {"y": {"min": 100, "max": 120},
                                  "j": {"min": 200, "max": 200},
                                  "f": {"min": 300, "max": 400}}
    assert ref["aircraft_on_route_range"] == {"min": 0, "max": 2}
    assert ref["oldest_observed_at"] == NOW - 10 and ref["newest_observed_at"] == NOW
    assert ref["expires_at"] == NOW + 890
    assert "aircraft_id" not in ref and "900001" not in str(ref) and "900002" not in str(ref)
    assert reference_for_route(rows, **{**args, "stopover_id": "14"}) is None
    assert reference_for_route(rows, **{**args, "profile_id": "unknown"}) is None
    assert reference_for_route(rows[:3], **{**args, "now": NOW + 901}) is None
