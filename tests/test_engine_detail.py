import json
from pathlib import Path

import pytest

import engine_catalog
import game_observations
from engine_detail import parse_displayed_metrics, parse_seat_observation, validate_seat_observation
from engine_selection import parse_engine_catalog


NOW = 1_900_000_000
FIXTURE = json.loads((Path(__file__).parent / "fixtures" /
                      "am4_selected_engine_details_20261123.json").read_text(encoding="utf-8"))


def _snapshot(engine_id):
    return {
        "detail": {"attribute_present": False, "model_id": None},
        "metrics": FIXTURE["variants"][engine_id],
        "groups": [{"type": "select", "id": "engSelection", "name": "",
                    "selectedValue": engine_id, "options": [
                        {"value": key, "label": value["label"], "speed": None,
                         "fuel": None, "selected": key == engine_id, "disabled": False}
                        for key, value in FIXTURE["variants"].items()]}],
    }


def test_observed_variant_metrics_are_distinct():
    first = parse_displayed_metrics(FIXTURE["variants"]["10"])
    second = parse_displayed_metrics(FIXTURE["variants"]["9"])
    assert first == {"speed_kph": 881, "capacity_pax": 164, "required_runway_ft": 6500,
                     "range_km": 5700, "fuel_lbs_per_km": 11.55, "a_check_cost_usd": 524690,
                     "maintenance_interval_hours": 360, "displayed_cost_usd": 6770196}
    assert second == {**first, "speed_kph": 798, "fuel_lbs_per_km": 10.67}


def test_passenger_emissions_use_exact_units():
    assert parse_displayed_metrics({"rows": [["CO2 Emission", "0.16 kg/pax/km"]]}) == {
        "co2_kg_per_pax_km": 0.16}
    assert parse_displayed_metrics({"rows": [["Emissão de CO₂", "0.14 kg/pax/km"]]}) == {
        "co2_kg_per_pax_km": 0.14}


def test_authenticated_emissions_fixture_preserves_every_selected_variant():
    emissions = json.loads((Path(__file__).parent / "fixtures" /
                            "am4_engine_emissions_20261124.json").read_text(encoding="utf-8"))
    for model_id, coefficient, expected_engines in (("5", .14, {"9", "10"}),
                                                     ("2", .16, {"5", "6", "7"})):
        variants = emissions["models"][model_id]["variants"]
        assert set(variants) == expected_engines
        parsed = [parse_displayed_metrics(value) for value in variants.values()]
        assert all(metrics["co2_kg_per_pax_km"] == coefficient for metrics in parsed)
        assert len({metrics["speed_kph"] for metrics in parsed}) == len(expected_engines)
        assert len({metrics["fuel_lbs_per_km"] for metrics in parsed}) == len(expected_engines)


@pytest.mark.parametrize("raw", [
    {"rows": [["Cruise speed", "881 mph"]]},
    {"rows": [["Cruise speed", "881 kph"], ["Cruise speed", "798 kph"]]},
    {"rows": [["Capacity", "164.5 pax"]]},
    {"rows": [], "costs": ["1,000", "2,000"]},
    {"rows": [["Runway required", "6,50 ft"]]},
    {"rows": [["CO2 Emission", "0.16 lbs/pax/km"]]},
    {"rows": [["CO2 Emission", "0.16 kg/pax/km"], ["CO2 Emission", "0.14 kg/pax/km"]]},
])
def test_bad_units_and_ambiguous_values_fail_closed(raw):
    assert parse_displayed_metrics(raw) is None


def test_observations_bound_to_selected_variant_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    initial = _snapshot("10")
    initial["seat_observation"] = {"source": "hidden_native_template", "y": "164", "j": "0", "f": "0"}
    catalog = parse_engine_catalog(initial["groups"])

    class Bot:
        stopping = False

        def js(self, script, *args):
            assert script == game_observations._SET_ENGINE_JS
            assert args == ("select", "engSelection", "9")
            return True

    monkeypatch.setattr(game_observations, "_stable_read",
                        lambda *_args, **_kwargs: (_snapshot("9"), NOW))
    result = game_observations._observe_variant_details(Bot(), initial, catalog, NOW - 1)
    assert result["10"]["metrics"]["speed_kph"] == 881
    assert result["10"]["seat_observation"] == {"source": "hidden_native_template", "y": 164, "j": 0, "f": 0}
    assert "seat_observation" not in result["9"]
    assert result["9"]["metrics"]["speed_kph"] == 798
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    assert registry.record("11", "A320-200", catalog, observed_at=NOW - 1,
                           variant_details=result)
    row = registry.snapshot(now=NOW)["models"]["11"]
    assert row["variant_details"] == result
    assert not row["model_detail_identity_verified"]
    assert not row["engine_prices_verified"]
    assert not registry.record("11", "A320-200", catalog, observed_at=NOW - 1,
                               variant_details={"unknown": result["9"]})


def test_changed_selector_without_refreshed_specs_is_not_attributed(monkeypatch):
    initial = _snapshot("10")
    catalog = parse_engine_catalog(initial["groups"])
    stale = _snapshot("9")
    stale["metrics"] = initial["metrics"]

    class Bot:
        stopping = False

        def js(self, *_args):
            return True

    class Stop:
        def wait(self, _seconds):
            return False

    bot = Bot()
    bot._stop = Stop()
    monkeypatch.setattr(game_observations, "_stable_read",
                        lambda *_args, **_kwargs: (stale, NOW))
    result = game_observations._observe_variant_details(bot, initial, catalog, NOW - 1)
    assert set(result) == {"10"}


@pytest.mark.parametrize("source", ["hidden_native_template", "visible_native_form"])
def test_native_seats_are_bounded_observations(source):
    raw = {"source": source, "y": "3", "j": "0", "f": "0"}
    parsed = parse_seat_observation(raw, 3)
    assert parsed == {"source": source, "y": 3, "j": 0, "f": 0}
    assert validate_seat_observation(parsed, 3) == parsed
    assert parse_seat_observation({**raw, "j": "1"}, 3) is None
    assert parse_seat_observation({**raw, "y": "3.0"}, 3) is None
    assert validate_seat_observation({**parsed, "y": True}, 3) is None
    assert validate_seat_observation({**parsed, "verified": True}, 3) is None
    assert validate_seat_observation({**parsed, "source": "confirmed"}, 3) is None
