"""Evidence-driven research of aircraft engine variants without game mutations."""
import json
from configparser import ConfigParser
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine_catalog
import engine_selection
import game_observations
import paths
from settings_schema import AIRCRAFT_FIELDS, clamp_settings
from settings_schema import AIRCRAFT_SWITCHES

NOW = 1_900_000_000


def test_engine_collection_limit_is_configurable_and_clamped():
    defaults = ConfigParser(interpolation=None)
    defaults.read(Path(__file__).resolve().parents[1] / "config/defaults.ini", encoding="utf-8")
    assert defaults.getboolean("options", "collect_engine_catalog") is False
    assert defaults.getint("settings", "engine_models_per_cycle") == 2
    assert "engine_models_per_cycle" in dict(AIRCRAFT_FIELDS)
    assert "collect_engine_catalog" in dict(AIRCRAFT_SWITCHES)
    assert clamp_settings({"engine_models_per_cycle": 0}) == {"engine_models_per_cycle": 1}
    assert clamp_settings({"engine_models_per_cycle": 20}) == {"engine_models_per_cycle": 10}


def _groups(*, radio=False, invalid=False):
    return [{
        "type": "radio" if radio else "select", "name": "engine", "id": "" if radio else "acEngine",
        "selectedValue": "1",
        "options": [
            {"value": "1", "label": "Trent 970", "speed": 905, "fuel": 12.1,
             "selected": True, "disabled": False},
            {"value": "1" if invalid else "2", "label": "GP7270", "speed": 921,
             "fuel": 12.4, "selected": False, "disabled": True},
        ],
    }]


@pytest.mark.parametrize("radio", [False, True])
def test_registry_persists_only_verified_engine_variants(tmp_path, monkeypatch, radio):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    catalog = engine_selection.parse_engine_catalog(_groups(radio=radio))
    assert registry.record("11", "A320", catalog)
    result = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json").snapshot(now=NOW)
    model = result["models"]["11"]
    assert model["model"] == "A320"
    assert model["selector_type"] == ("radio" if radio else "select")
    assert model["selected_engine_id"] == "1"
    assert [item["engine_id"] for item in model["variants"]] == ["1", "2"]
    assert [item["available"] for item in model["variants"]] == [True, False]
    assert model["engine_prices_verified"] is False
    assert model["model_detail_identity_verified"] is False
    assert registry.record("11", "A320", object()) is False
    assert registry.snapshot(now=NOW)["models"]["11"] == model
    assert registry.snapshot(now=NOW + 3 * 86400 + 1)["models"] == {}
    assert registry.snapshot(now=NOW - 1)["models"] == {}


def test_registry_rejects_corruption_duplicate_engines_and_contradictions(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    assert registry.record("11", "A320", engine_selection.parse_engine_catalog(_groups()))
    raw = json.loads(registry.path.read_text(encoding="utf-8"))
    raw["catalogs"]["11"]["variants"][1]["engine_id"] = "1"
    registry.path.write_text(json.dumps(raw), encoding="utf-8")
    assert registry.snapshot(now=NOW)["models"] == {}
    raw["catalogs"]["11"]["variants"][1]["engine_id"] = "2"
    raw["catalogs"]["11"]["selected_engine_id"] = "2"
    registry.path.write_text(json.dumps(raw), encoding="utf-8")
    assert registry.snapshot(now=NOW)["models"] == {}
    registry.path.write_text("{broken", encoding="utf-8")
    assert registry.snapshot(now=NOW)["models"] == {}
    with pytest.raises(engine_selection.EngineSelectionError, match="duplicados"):
        engine_selection.parse_engine_catalog(_groups(invalid=True))


def test_round_robin_records_failures_and_keeps_prior_success(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    models = [{"id": "11", "name": "A320"}, {"id": "22", "name": "B737"},
              {"id": "33", "name": "A380"}]
    assert [m["id"] for m in registry.next_models(models, per_cycle=2)] == ["11", "22"]
    assert registry.record("11", "A320", engine_selection.parse_engine_catalog(_groups()))
    assert registry.record_attempt("22", "B737")
    assert [m["id"] for m in registry.next_models(models, per_cycle=2)] == ["33", "11"]
    assert registry.record_attempt("33", "A380")
    state = json.loads(registry.path.read_text(encoding="utf-8"))
    assert state["attempts"]["22"]["status"] == "inconclusive"
    assert state["catalogs"]["11"]["source"] == engine_catalog.SOURCE
    assert [m["id"] for m in registry.next_models(models, per_cycle=2)] == ["11", "22"]
    assert registry.next_models(models + [{"id": "22", "name": "Wrong"}], per_cycle=10) == [
        {"id": "11", "name": "A320"}, {"id": "33", "name": "A380"}]


def test_registry_is_separate_per_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    folder = [tmp_path / "principal"]
    monkeypatch.setattr(paths, "current", lambda: SimpleNamespace(data=folder[0]))
    assert engine_catalog.EngineCatalogRegistry().record(
        "11", "A320", engine_selection.parse_engine_catalog(_groups()))
    folder[0] = tmp_path / "segundo"
    assert engine_catalog.EngineCatalogRegistry().snapshot(now=NOW)["models"] == {}


def test_collector_reads_order_details_only_and_rotates_after_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)

    class Stop:
        def wait(self, _seconds):
            return False

    class Bot:
        stopping = False

        def __init__(self):
            self._stop = Stop()
            self.calls = []
            self.model_id = ""

        def open_popup(self, *args):
            self.calls.append(("open", args[0]))

        def close_popup(self, **kwargs):
            self.calls.append(("close", kwargs.get("quiet")))

        def ajax(self, url, target):
            self.calls.append(("ajax", url, target))
            if target == "acModel":
                self.model_id = url.split("id=")[1].split("&")[0]

        def js(self, script, *args):
            assert not args
            self.calls.append(("read", script))
            if script == game_observations._ENGINE_OPTIONS_JS:
                return _groups(invalid=self.model_id == "22")
            from fleet import _MODELS_JS
            assert script == _MODELS_JS
            return [{"id": "11", "name": "A320"}, {"id": "22", "name": "B737"},
                    {"id": "33", "name": "A380"}]

    first = Bot()
    assert game_observations.collect_aircraft_engine_catalog(first, per_cycle=2) == 1
    assert first.calls[0] == ("open", "routes_main.php")
    assert first.calls[-1] == ("close", True)
    assert [c[1] for c in first.calls if c[0] == "ajax"] == [
        "ac_orders.php?first=true", "ac_orders.php?mode=detail&id=11&charter=0",
        "ac_orders.php?mode=detail&id=22&charter=0"]
    assert len([c for c in first.calls if c[0] == "read"
                and c[1] == game_observations._ENGINE_OPTIONS_JS]) == 4
    assert registry.snapshot(now=NOW)["model_count"] == 1
    second = Bot()
    assert game_observations.collect_aircraft_engine_catalog(second, per_cycle=1) == 1
    assert [c[1] for c in second.calls if c[0] == "ajax"][-1] == (
        "ac_orders.php?mode=detail&id=33&charter=0")
    assert registry.snapshot(now=NOW)["model_count"] == 2
    assert json.loads(registry.path.read_text(encoding="utf-8"))["attempts"]["22"]["status"] == "inconclusive"


def test_collector_rejects_unstable_game_reads_without_overwriting_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)
    assert registry.record("11", "A320", engine_selection.parse_engine_catalog(_groups()))

    class Bot:
        stopping = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == game_observations._ENGINE_OPTIONS_JS:
                return []
            return [{"id": "11", "name": "A320"}]

    assert game_observations.collect_aircraft_engine_catalog(Bot(), per_cycle=1) == 0
    assert registry.snapshot(now=NOW)["model_count"] == 1
