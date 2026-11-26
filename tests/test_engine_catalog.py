"""Evidence-driven research of aircraft engine variants without game mutations."""
import json
import shutil
import subprocess
from configparser import ConfigParser
from pathlib import Path
from types import SimpleNamespace

import pytest

import economy
import engine_catalog
import engine_selection
import game_observations
import paths
from settings_schema import AIRCRAFT_FIELDS, clamp_settings
from settings_schema import AIRCRAFT_SWITCHES

NOW = 1_900_000_000


def _roster(*models):
    return [{"id": mid, "name": name, "section": f"listSection{index}"}
            for index, (mid, name) in enumerate(models, 1)]


def test_roster_coverage_counts_exact_identities_and_available_variant_details(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    rows = _roster(("11", "A320"), ("22", "B737"))
    assert registry.record_roster(rows, observed_at=NOW) == rows
    catalog = engine_selection.parse_engine_catalog(_groups())
    details = {"1": {"observed_at": NOW, "metrics": {"speed_kph": 905}}}
    assert registry.record("11", "A320", catalog, observed_model_id="11", variant_details=details)
    assert registry.record("22", "Wrong name", catalog, observed_model_id="22", variant_details=details)
    assert registry.record("33", "A380", catalog, observed_model_id="33", variant_details=details)
    coverage = registry.snapshot(now=NOW)["order_list_coverage"]
    assert coverage == {"source": engine_catalog.ROSTER_SOURCE, "status": "partial",
                        "observed_at": NOW, "listed_model_count": 2, "verified_model_count": 1,
                        "available_variant_count": 1, "observed_variant_count": 1,
                        "models_with_all_variant_details": 1, "final_prices_verified": False,
                        "models_expires_at": None, "engines_expires_at": None}
    # A new valid observation can fill the missing identity, but cannot prove checkout prices.
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW + 1)
    details["1"]["observed_at"] = NOW + 1
    assert registry.record("22", "B737", catalog, observed_model_id="22", variant_details=details)
    snapshot = engine_catalog.EngineCatalogRegistry(registry.path).snapshot(now=NOW + 1)
    assert snapshot["coverage"] == "partial"
    assert snapshot["order_list_coverage"]["status"] == "details_observed"
    assert snapshot["order_list_coverage"]["models_expires_at"] == NOW + 900
    assert snapshot["order_list_coverage"]["engines_expires_at"] == NOW + 900
    assert snapshot["order_list_coverage"]["final_prices_verified"] is False
    assert registry.record_attempt("11", "A320")
    assert registry.snapshot(now=NOW + 1)["order_list_coverage"]["verified_model_count"] == 1
    assert registry.snapshot(now=NOW + 901)["order_list_coverage"]["status"] == "unverified"
    registry.revoke_roster()
    assert registry.snapshot(now=NOW + 1)["order_list_coverage"]["listed_model_count"] is None
    assert registry.snapshot(now=NOW + 1)["model_count"] == 3


@pytest.mark.parametrize("rows", [
    [], _roster(("11", "A320"), ("11", "A320")),
    [{"id": "11", "name": "A320", "section": "listSection2"}],
    [{"id": "11", "name": "A320"}],
    _roster(("invalid", "A320")),
])
def test_roster_rejects_invalid_native_list(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    assert registry.record_roster(rows, observed_at=NOW) is None
    assert registry.snapshot(now=NOW)["order_list_coverage"]["status"] == "unverified"


def test_roster_dom_contract_requires_idle_visible_native_cards(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required to exercise the native roster DOM snapshot")
    js = r"""
const card = (id, section, name) => ({
  id: section, offsetParent: {}, matches: selector => selector === '.acListItem',
  querySelector: selector => selector === 'b' ? {textContent: name} : null,
  getAttribute: () => `Ajax('ac_orders.php?mode=detail&id=${id}&charter=0','acModel',false);`
});
const list = {offsetParent: {}, children: [card('12','listSection1','Cessna 172'),
  card('5','listSection2','A320-200')], querySelector: () => null};
list.children[0].dataset = {range: '1289', capacity: '3', price: '43200'};
globalThis.document = {querySelectorAll: () => [list]};
globalThis.window = {jQuery: {active: 0}};
"""
    js += "\nconst read = new Function(" + json.dumps(engine_catalog.MODEL_ROSTER_JS) + ");\n"
    js += """
const original = read();
window.jQuery.active = 1; const busy = read(); window.jQuery.active = 0;
list.children[1].offsetParent = null; const hidden = read();
list.children[1].offsetParent = {};
list.children[1].getAttribute = () => "Ajax('ac_orders.php?mode=detail&id=5&charter=1','acModel',false);";
console.log(JSON.stringify({original, busy, hidden, wrong: read()}));
"""
    path = tmp_path / "model_roster.js"
    path.write_text(js, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    reads = json.loads(result.stdout)
    expected = _roster(("12", "Cessna 172"), ("5", "A320-200"))
    expected[0]["advertised"] = {"range": "1289", "capacity": "3", "price": "43200"}
    assert reads["original"] == expected
    assert reads["busy"] is None and reads["hidden"] is None
    assert reads["wrong"][1]["id"] is None


def test_native_order_list_supplies_research_without_a_purchase_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    market_path = tmp_path / "market.json"
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(economy, "market_file", lambda: market_path)
    monkeypatch.setattr(engine_catalog, "EngineCatalogRegistry", lambda: registry)
    rows = _roster(("11", "A320"), ("22", "B737"), ("33", "A380"))
    rows[0]["advertised"] = {"range": "6150", "capacity": "180", "price": "6000000"}
    rows[1]["advertised"] = {"range": "5600", "capacity": True, "price": "$8,000,000"}
    assert registry.record_roster(rows, observed_at=NOW - 0.25)

    evidence = economy.load_market_evidence(now=NOW)
    assert evidence == {"source": "bot_aircraft_market_cache", "listing_source": engine_catalog.ROSTER_SOURCE,
                        "observed_at": NOW - 0.25, "fresh": True, "engine_prices_verified": False,
                        "models": [{"id": "11", "name": "A320", "range": 6150, "capacity": 180, "price": 6000000},
                                   {"id": "22", "name": "B737", "range": 5600}]}
    assert economy.load_market() == []
    assert economy.load_market_evidence(now=NOW - 0.5)["fresh"] is False
    assert economy.load_market_evidence(now=NOW + 900)["fresh"] is False

    legacy = [{"id": "11", "name": "A320", "price": 5500000, "score": 0.1}]
    economy.save_market(legacy)
    assert economy.load_market() == legacy
    assert economy.load_market_evidence(now=NOW)["models"] == legacy
    registry.revoke_roster()
    assert registry.advertised_market(now=NOW) is None


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


def test_registry_requires_explicit_correlated_detail_for_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    catalog = engine_selection.parse_engine_catalog(_groups())
    assert not registry.record("11", "A320", catalog, observed_model_id="22")
    assert registry.snapshot(now=NOW)["models"] == {}
    assert registry.record("11", "A320", catalog)
    assert registry.snapshot(now=NOW)["models"]["11"]["model_detail_identity_verified"] is False
    assert registry.record("11", "A320", catalog, observed_model_id="11")
    row = registry.snapshot(now=NOW)["models"]["11"]
    assert row["model_detail_identity_verified"] is True
    assert row["observed_model_id"] == "11"
    raw = json.loads(registry.path.read_text(encoding="utf-8"))
    raw["catalogs"]["11"]["observed_model_id"] = "22"
    registry.path.write_text(json.dumps(raw), encoding="utf-8")
    assert registry.snapshot(now=NOW)["models"] == {}


def test_registry_rejects_delayed_catalogs_per_model_across_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    path = tmp_path / "engines.json"
    registry = engine_catalog.EngineCatalogRegistry(path)
    a320 = engine_selection.parse_engine_catalog(_groups())

    a380_groups = _groups()
    a380_groups[0]["options"].append({
        "value": "3", "label": "Engine X", "speed": 932, "fuel": 13.2,
        "selected": False, "disabled": False,
    })
    a380 = engine_selection.parse_engine_catalog(a380_groups)

    assert registry.record("11", "A320", a320, observed_at=NOW - 50.75,
                           observed_model_id="11")
    assert registry.record("22", "A380", a380, observed_at=NOW - 20.5,
                           observed_model_id="22")
    updated = _groups()
    updated[0]["options"][1]["label"] = "Upgraded engine"
    latest = engine_selection.parse_engine_catalog(updated)
    assert registry.record("11", "A320", latest, observed_at=NOW - 5.25,
                           observed_model_id="11")

    restarted = engine_catalog.EngineCatalogRegistry(path)
    before = restarted.snapshot(now=NOW)["models"]
    assert [v["engine_id"] for v in before["22"]["variants"]] == ["1", "2", "3"]
    assert before["11"]["variants"][1]["label"] == "Upgraded engine"
    assert before["11"]["observed_at"] == NOW - 5.25
    assert not restarted.record("11", "A320", a320, observed_at=NOW - 12.5,
                                observed_model_id="11")
    assert not restarted.record("22", "A380", a320, observed_at=NOW - 25,
                                observed_model_id="22")
    assert restarted.snapshot(now=NOW)["models"] == before


def test_registry_same_time_identity_priority_and_conflicting_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    path = tmp_path / "engines.json"
    registry = engine_catalog.EngineCatalogRegistry(path)
    a320 = engine_selection.parse_engine_catalog(_groups())
    observed_at = NOW - 0.25

    assert registry.record("11", "A320", a320, observed_at=observed_at)
    assert registry.record("11", "A320", a320, observed_at=observed_at,
                           observed_model_id="11")
    restarted = engine_catalog.EngineCatalogRegistry(path)
    verified = restarted.snapshot(now=NOW)["models"]["11"]
    assert verified["model_detail_identity_verified"] is True

    # Both the identity downgrade and a contradictory equally dated snapshot
    # lack enough chronology to replace the already verified engine variants.
    assert not restarted.record("11", "A320", a320, observed_at=observed_at)
    changed = _groups()
    changed[0]["options"][1]["label"] = "Other variant"
    assert not restarted.record("11", "A320",
                                engine_selection.parse_engine_catalog(changed),
                                observed_at=observed_at, observed_model_id="11")
    assert restarted.snapshot(now=NOW)["models"]["11"] == verified

    assert restarted.record("11", "A320",
                            engine_selection.parse_engine_catalog(changed),
                            observed_at=observed_at + 0.1, observed_model_id="11")
    assert restarted.snapshot(now=NOW)["models"]["11"]["variants"][1]["label"] == (
        "Other variant")


def test_registry_preserves_verified_identity_against_newer_unverified_read(
        tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    path = tmp_path / "engines.json"
    registry = engine_catalog.EngineCatalogRegistry(path)
    original = engine_selection.parse_engine_catalog(_groups())
    assert registry.record("11", "A320", original, observed_at=NOW - 20,
                           observed_model_id="11")

    verified = registry.snapshot(now=NOW)["models"]["11"]
    contents = path.read_bytes()
    changed = _groups()
    changed[0]["options"][1]["label"] = "Uncorrelated engine"
    unverified = engine_selection.parse_engine_catalog(changed)

    restarted = engine_catalog.EngineCatalogRegistry(path)
    assert not restarted.record("11", "A320", unverified, observed_at=NOW - 5)
    assert path.read_bytes() == contents
    assert restarted.snapshot(now=NOW)["models"]["11"] == verified

    assert restarted.record("11", "A320", unverified, observed_at=NOW - 5,
                            observed_model_id="11")
    latest = restarted.snapshot(now=NOW)["models"]["11"]
    assert latest["model_detail_identity_verified"] is True
    assert latest["variants"][1]["label"] == "Uncorrelated engine"


@pytest.mark.parametrize("invalid", [
    None, True, False, "1900000000", -1, 0,
    float("nan"), float("inf"), float("-inf"),
    NOW + 0.001, NOW - engine_catalog.MAX_AGE_SECONDS - 1,
    10 ** 500,
])
def test_registry_rejects_bad_and_out_of_window_observation_timestamps(
        tmp_path, monkeypatch, invalid):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    catalog = engine_selection.parse_engine_catalog(_groups())
    assert registry.record("11", "A320", catalog, observed_at=NOW - 5,
                           observed_model_id="11")
    baseline = registry.path.read_bytes()
    assert registry.record("11", "A320", catalog, observed_at=invalid,
                           observed_model_id="11") is False
    assert registry.path.read_bytes() == baseline
    assert registry.snapshot(now=NOW)["models"]["11"]["observed_at"] == NOW - 5


@pytest.mark.parametrize("invalid_now", [False, "now", float("nan"),
                                          float("inf"), 10 ** 500])
def test_registry_snapshot_rejects_invalid_query_times_without_errors(
        tmp_path, monkeypatch, invalid_now):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    assert registry.record("11", "A320",
                           engine_selection.parse_engine_catalog(_groups()))
    assert registry.snapshot(now=invalid_now)["models"] == {}


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
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                return {"detail": {"attribute_present": True, "model_id": self.model_id},
                        "groups": _groups(invalid=self.model_id == "22")}
            assert script == engine_catalog.MODEL_ROSTER_JS
            return _roster(("11", "A320"), ("22", "B737"), ("33", "A380"))

    first = Bot()
    assert game_observations.collect_aircraft_engine_catalog(first, per_cycle=2) == 1
    assert first.calls[0] == ("open", "routes_main.php")
    assert first.calls[-1] == ("close", True)
    assert [c[1] for c in first.calls if c[0] == "ajax"] == [
        "ac_orders.php?first=true", "ac_orders.php?mode=detail&id=11&charter=0",
        "ac_orders.php?mode=detail&id=22&charter=0"]
    assert len([c for c in first.calls if c[0] == "read"
                and c[1] == game_observations._ENGINE_DETAIL_SNAPSHOT_JS]) == 4
    assert registry.snapshot(now=NOW)["model_count"] == 1
    assert registry.snapshot(now=NOW)["models"]["11"]["model_detail_identity_verified"] is True
    second = Bot()
    assert game_observations.collect_aircraft_engine_catalog(second, per_cycle=1) == 1
    assert [c[1] for c in second.calls if c[0] == "ajax"][-1] == (
        "ac_orders.php?mode=detail&id=33&charter=0")
    assert registry.snapshot(now=NOW)["model_count"] == 2
    assert json.loads(registry.path.read_text(encoding="utf-8"))["attempts"]["22"]["status"] == "inconclusive"


def test_collector_preserves_second_dom_read_time_when_processing_is_delayed(
        tmp_path, monkeypatch):
    clock = [NOW - 40.375]
    monkeypatch.setattr(game_observations.time, "time", lambda: clock[0])
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)
    real_parser = engine_selection.parse_engine_catalog

    def parse_after_delay(groups):
        clock[0] = NOW
        return real_parser(groups)

    monkeypatch.setattr(game_observations, "parse_engine_catalog", parse_after_delay)

    class Bot:
        stopping = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                return {"detail": {"attribute_present": True, "model_id": "11"},
                        "groups": _groups()}
            assert script == engine_catalog.MODEL_ROSTER_JS
            return _roster(("11", "A320"))

    assert game_observations.collect_aircraft_engine_catalog(Bot(), per_cycle=1) == 1
    saved = engine_catalog.EngineCatalogRegistry(registry.path).snapshot(now=NOW)
    assert saved["models"]["11"]["observed_at"] == NOW - 40.375
    assert saved["models"]["11"]["model_detail_identity_verified"] is True


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
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                return {"detail": {"attribute_present": False, "model_id": None},
                        "groups": []}
            return _roster(("11", "A320"))

    assert game_observations.collect_aircraft_engine_catalog(Bot(), per_cycle=1) == 0
    assert registry.snapshot(now=NOW)["model_count"] == 1


def test_collector_discards_mismatched_detail_without_replacing_last_good(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)
    assert registry.record("11", "A320", engine_selection.parse_engine_catalog(_groups()),
                           observed_model_id="11")
    original = registry.snapshot(now=NOW)["models"]["11"]

    class Bot:
        stopping = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                return {"detail": {"attribute_present": True, "model_id": "22"},
                        "groups": _groups()}
            return _roster(("11", "A320"))

    assert game_observations.collect_aircraft_engine_catalog(Bot(), per_cycle=1) == 0
    assert registry.snapshot(now=NOW)["models"]["11"] == original


@pytest.mark.parametrize(("detail", "collected", "verified"), [
    ({"attribute_present": False, "model_id": None, "script_model_id": "2"}, 1, True),
    ({"attribute_present": False, "model_id": None, "script_model_id": "12"}, 0, False),
    ({"attribute_present": True, "model_id": "2", "script_model_id": "12"}, 0, False),
    ({"attribute_present": True, "model_id": "12", "script_model_id": "2"}, 0, False),
    ({"attribute_present": False, "model_id": None, "script_model_id": None}, 1, False),
])
def test_collector_correlates_response_script_id(tmp_path, monkeypatch, detail, collected, verified):
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)

    class Bot:
        stopping = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                return {"detail": detail, "groups": _groups()}
            return _roster(("2", "A380-800"))

    assert game_observations.collect_aircraft_engine_catalog(Bot(), per_cycle=1) == collected
    models = registry.snapshot(now=NOW)["models"]
    if collected:
        assert models["2"]["model_detail_identity_verified"] is verified
        assert models["2"]["engine_prices_verified"] is False
    else:
        assert not models


@pytest.mark.parametrize("change", ["model", "engine"])
def test_collector_rejects_ajax_panel_change_between_snapshots(tmp_path, monkeypatch, change):
    """An AJAX replacement cannot combine engines and identity from different forms."""
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    monkeypatch.setattr(game_observations, "EngineCatalogRegistry", lambda: registry)
    assert registry.record("11", "A320", engine_selection.parse_engine_catalog(_groups()),
                           observed_model_id="11")
    original = registry.snapshot(now=NOW)["models"]["11"]

    class Bot:
        stopping = False

        def __init__(self):
            self.snapshots = 0

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == game_observations._ENGINE_DETAIL_SNAPSHOT_JS:
                self.snapshots += 1
                groups = _groups()
                detail_id = "11"
                if self.snapshots == 2:
                    if change == "model":
                        detail_id = "22"
                    else:
                        groups[0]["options"][0]["label"] = "Different motor"
                return {"detail": {"attribute_present": True, "model_id": detail_id},
                        "groups": groups}
            assert script == engine_catalog.MODEL_ROSTER_JS
            return _roster(("11", "A320"))

    bot = Bot()
    assert game_observations.collect_aircraft_engine_catalog(bot, per_cycle=1) == 0
    assert bot.snapshots == 2
    assert registry.snapshot(now=NOW)["models"]["11"] == original


def test_combined_engine_snapshot_runs_against_dom_and_rejects_loading(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required to exercise the engine detail DOM snapshot")

    mock = r"""
const option = (value, label, selected) => ({
  value, textContent: label, selected,
  matches: () => false,
  getAttribute: name => name === 'data-speed' ? '905' : null
});
const select = {
  name: 'engine', id: 'acEngine', value: '1',
  options: [option('1', 'Trent 970', true), option('2', 'GP7270', false)],
  closest: () => null, matches: () => false,
  getAttribute: name => name === 'aria-label' ? 'Engine' : null
};
let modelId = '11';
let loading = false;
let scripts = [];
let stepShown = false;
let duplicateSeat = false;
const seat = textContent => ({textContent, getClientRects: () => stepShown ? [{}] : []});
const seats = {'#eSeats': seat('3'), '#bSeats': seat('0'), '#fSeats': seat('0')};
const step = {contains: el => Object.values(seats).includes(el),
  getClientRects: () => stepShown ? [{}] : []};
const requirementRows = [['Delivery time', '00:00:30'], ['Pilots', '1'], ['Crew', '0'],
  ['Engineers', '1'], ['Tech', '1']].map(row => ({children:row.map(textContent => ({textContent}))}));
const panel = {
  getAttribute: name => name === 'data-model-id' ? modelId : null,
  querySelector: () => loading ? {} : null,
  querySelectorAll: name => name === 'select' ? [select] : name === 'script' ? scripts :
    name === 'tr, .row' ? requirementRows : name === '#step2' ? [step] : name in seats ?
    (duplicateSeat && name === '#eSeats' ? [seats[name], seat('3')] : [seats[name]]) : []
};
globalThis.document = {
  querySelector: name => name === '#acModel' ? panel : null,
  querySelectorAll: name => name === '#acModel' ? [panel] : []
};
globalThis.window = {jQuery: {active: 0}, getComputedStyle: () => ({visibility: 'visible'})};
"""
    js = (mock + "\nconst snapshot = new Function(" +
          json.dumps(game_observations._ENGINE_DETAIL_SNAPSHOT_JS) +
          ");\nconst first = snapshot();\n" +
          "window.jQuery.active = 1; const ajax = snapshot();\n" +
          "window.jQuery.active = 0; loading = true; const loader = snapshot();\n" +
          "loading = false; modelId = '22'; const next = snapshot();\n" +
          "modelId = null; scripts = [{textContent: 'var acId = 2;'}]; const native = snapshot();\n" +
          "scripts.push({textContent: 'acId = 12;'}); const conflict = snapshot();\n" +
          "scripts = [{textContent: 'var acId = 2;'}]; modelId = '12'; const attrConflict = snapshot();\n" +
          "modelId = null; scripts = []; const missing = snapshot();\n" +
          "stepShown = true; const visibleSeats = snapshot();\n" +
          "duplicateSeat = true; const duplicateSeats = snapshot();\n" +
          "console.log(JSON.stringify({first, ajax, loader, next, native, conflict, attrConflict, missing, visibleSeats, duplicateSeats}));\n")
    path = tmp_path / "engine_snapshot.js"
    path.write_text(js, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    reads = json.loads(result.stdout)
    assert reads["first"]["detail"] == {"attribute_present": True, "model_id": "11",
                                       "script_model_id": None}
    catalog = engine_selection.parse_engine_catalog(reads["first"]["groups"])
    assert [item.engine_id for item in catalog.variants] == ["1", "2"]
    assert reads["ajax"] is None
    assert reads["loader"] is None
    assert reads["next"]["detail"]["model_id"] == "22"
    assert reads["native"]["detail"] == {"attribute_present": False, "model_id": None,
                                        "script_model_id": "2"}
    assert reads["conflict"] is None
    assert reads["attrConflict"] is None
    assert reads["missing"]["detail"]["script_model_id"] is None
    assert reads["first"]["seat_observation"] == {
        "source": "hidden_native_template", "y": "3", "j": "0", "f": "0"}
    assert reads["first"]["metrics"]["rows"] == [
        ["Delivery time", "00:00:30"], ["Pilots", "1"], ["Crew", "0"], ["Engineers", "1"], ["Tech", "1"]]
    assert reads["visibleSeats"]["seat_observation"] == {
        "source": "visible_native_form", "y": "3", "j": "0", "f": "0"}
    assert reads["duplicateSeats"]["seat_observation"] is None
