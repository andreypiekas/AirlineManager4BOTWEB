"""Live-read adapters must persist only game-correlated, non-destructive data."""
import json
import shutil
import subprocess
import time

import pytest

import fleet
import game_observations
import hub_expansion
from fleet import (_HUB_OPTIONS_JS, _ROUTE_AUDIT_JS, _ROUTES_PAGER_LINKS_JS,
                   RouteCandidate, audit_routes, audit_routes_live_pages)
from hub_expansion import HubExpansionRegistry
from hub_registry import HubRegistry
from route_registry import HOME_HUB_EVIDENCE, RouteRegistry


def test_demand_is_persistent_per_origin_destination_and_survives_partial_queries(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand("2926", [
        {"arr_id": "3139", "distance": 1992.763, "y": 120, "j": 106, "f": 40},
        {"arr_id": "2941", "distance": 515, "y": 789, "j": 154, "f": 124},
    ]) == 2
    assert registry.record_demand("2926", [
        {"arr_id": "3139", "distance": 1992.763, "y": 125, "j": 106, "f": 40},
    ]) == 1
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    assert len(data["route_demand"]) == 2
    assert data["route_demand"]["2926:3139"]["y"] == 125
    assert data["route_demand"]["2926:2941"]["y"] == 789
    assert data["route_demand"]["2926:3139"]["source"] == "game_route_search"
    assert registry.snapshot()["demand_samples"] == 2


def test_demand_keeps_read_time_and_rejects_delayed_replay_per_route(tmp_path, monkeypatch):
    clock = [1_900_000_030.75]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 120, "j": 10, "f": 0}
    assert registry.record_demand("2926", [sample], observed_at=1_900_000_020.25) == 1
    assert registry.record_demand("2926", [
        {**sample, "y": 140},
        {**sample, "arr_id": "2941", "y": 900},
    ], observed_at=1_900_000_010.5) == 1
    rows = HubExpansionRegistry(registry.path).demand_observations({"2926"}, now=clock[0])
    assert [(row["destination_id"], row["y"], row["observed_at"]) for row in rows] == [
        ("2941", 900, 1_900_000_010.5), ("3139", 120, 1_900_000_020.25)]
    original = registry.path.read_bytes()
    assert registry.record_demand("2926", [{**sample, "y": 140}],
                                  observed_at=1_900_000_010.5) == 0
    assert registry.path.read_bytes() == original
    assert registry.snapshot(now=clock[0])["demand_observed_at"] == 1_900_000_020.25


def test_conflicting_simultaneous_demand_is_quarantined_until_newer_read(tmp_path, monkeypatch):
    clock = [1_900_000_040.5]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 120, "j": 10, "f": 0}
    stamp = 1_900_000_035.25
    assert registry.record_demand("2926", [sample], observed_at=stamp) == 1
    assert registry.record_demand("2926", [{**sample, "y": 121}], observed_at=stamp) == 0
    report = HubExpansionRegistry(registry.path).snapshot(
        now=clock[0], owned_hub_ids={"2926"})
    assert report["demand_samples"] == 0
    assert report["demand_conflicts"] == 1
    assert report["demand_hub_progress"][0]["conflict_count"] == 1
    assert registry.demand_observations({"2926"}, now=clock[0]) == []
    disputed = registry.path.read_bytes()
    assert registry.record_demand("2926", [sample], observed_at=stamp) == 0
    assert registry.path.read_bytes() == disputed
    assert registry.record_demand("2926", [sample], observed_at=stamp - 1) == 0
    assert registry.path.read_bytes() == disputed
    assert registry.record_demand("2926", [{**sample, "y": 123}],
                                  observed_at=stamp + 1) == 1
    confirmed = HubExpansionRegistry(registry.path).snapshot(now=clock[0])
    assert confirmed["demand_conflicts"] == 0
    assert confirmed["demand_samples"] == 1
    assert registry.demand_observations({"2926"}, now=clock[0])[0]["y"] == 123


def test_persisted_conflict_takes_precedence_over_same_time_legacy_sample(
        tmp_path, monkeypatch):
    clock = [1_900_000_050]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 120, "j": 10, "f": 0}
    assert registry.record_demand("2926", [sample], observed_at=clock[0] - 2) == 1
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    saved["route_demand_conflicts"] = {
        "2926:3139": {"observed_at": clock[0] - 2,
                      "source": "game_route_search"}}
    registry.path.write_text(json.dumps(saved), encoding="utf-8")
    assert registry.demand_observations({"2926"}, now=clock[0]) == []
    assert registry.snapshot(now=clock[0])["demand_conflicts"] == 1
    assert registry.record_demand("2926", [sample], observed_at=clock[0] - 1) == 1
    assert registry.snapshot(now=clock[0])["demand_conflicts"] == 0
    assert registry.demand_observations({"2926"}, now=clock[0])[0]["y"] == 120


@pytest.mark.parametrize("invalid", [None, True, "1900000000", float("nan"),
                                            float("inf"), -1, 1_900_000_002,
                                            1_900_000_000 - hub_expansion.MAX_AGE_SECONDS - 1])
def test_demand_rejects_invalid_read_timestamp_without_writes(tmp_path, monkeypatch, invalid):
    monkeypatch.setattr(hub_expansion.time, "time", lambda: 1_900_000_000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 120, "j": 10, "f": 0}
    assert registry.record_demand("2926", [sample], observed_at=invalid) == 0
    assert not registry.path.exists()


def test_demand_rejects_invalid_and_conflicting_evidence(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 1992, "y": 120, "j": 106, "f": 40}
    assert registry.record_demand("not-a-hub", [sample]) == 0
    assert registry.record_demand("2926", [{**sample, "y": -1}]) == 0
    assert registry.record_demand("2926", [{**sample, "y": True}]) == 0
    assert registry.record_demand("2926", [sample, {**sample, "y": 999}]) == 0
    assert not registry.path.exists()


def test_partly_invalid_demand_batch_preserves_previous_evidence(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    valid = {"arr_id": "3139", "distance": 1992.763, "y": 120, "j": 106, "f": 40}
    assert registry.record_demand("2926", [valid]) == 1
    original = registry.path.read_bytes()
    assert registry.record_demand("2926", [
        {**valid, "arr_id": "2941", "y": 180},
        {**valid, "arr_id": "2957", "distance": True},
    ]) == 0
    assert registry.path.read_bytes() == original
    assert registry.record_demand("2926", [
        {**valid, "arr_id": "2941", "distance": float("inf")},
    ]) == 0
    assert registry.path.read_bytes() == original


def test_stale_and_corrupt_demand_is_excluded_from_freshness(tmp_path, monkeypatch):
    clock = [1_900_000_000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 1}
    assert registry.record_demand("2926", [sample]) == 1
    assert registry.snapshot()["demand_samples"] == 1
    assert registry.snapshot()["demand_fresh_samples"] == 1
    clock[0] += hub_expansion.MAX_AGE_SECONDS + 1
    assert registry.snapshot()["demand_fresh_samples"] == 0
    assert registry.snapshot()["demand_samples"] == 1

    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    persisted["route_demand"]["2926:INVALID"] = {
        "origin_id": "2926", "destination_id": "INVALID", "observed_at": clock[0],
        "source": "game_route_search", "distance_km": 100, "y": 5, "j": 0, "f": 0,
    }
    persisted["route_demand"]["2926:2941"] = {
        "origin_id": "2926", "destination_id": "2941", "observed_at": True,
        "source": "game_route_search", "distance_km": 100, "y": 5, "j": 0, "f": 0,
    }
    registry.path.write_text(json.dumps(persisted), encoding="utf-8")
    assert registry.snapshot()["demand_samples"] == 1
    assert registry.snapshot()["demand_fresh_samples"] == 0
    assert registry.record_demand("2926", [{**sample, "arr_id": "2941"}]) == 1
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    assert set(saved["route_demand"]) == {"2926:3139", "2926:2941"}
    assert registry.snapshot()["demand_fresh_samples"] == 1


def test_future_demand_does_not_block_rotation(tmp_path, monkeypatch):
    clock = [1_900_000_000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand("2926", [{
        "arr_id": "3139", "distance": 2000, "y": 10, "j": 0, "f": 0,
    }]) == 1
    clock[0] -= 10
    assert registry.next_demand_origin(["2926", "2941"]) == "2926"
    assert registry.snapshot()["demand_fresh_samples"] == 0


def test_demand_rotates_to_least_recent_owned_hub(tmp_path, monkeypatch):
    now = [1900000000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: now[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.next_demand_origin(["2941", "2926"]) == "2926"
    assert registry.record_demand("2926", [
        {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 1}
    ]) == 1
    assert registry.next_demand_origin(["2941", "2926"]) == "2941"


def test_inconclusive_attempts_rotate_and_persist_across_restart(tmp_path, monkeypatch):
    now = [1900000000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: now[0])
    path = tmp_path / "expansion.json"
    registry = HubExpansionRegistry(path)
    hubs = ["2941", "2926", "3139"]
    assert registry.next_demand_origin(hubs) == "2926"
    assert registry.record_demand_attempt("2926")
    assert registry.next_demand_origin(hubs) == "2941"
    assert registry.record_demand_attempt("2941")
    assert HubExpansionRegistry(path).next_demand_origin(hubs) == "3139"
    assert registry.record_demand_attempt("3139")
    # Equal timestamps use a persistent sequence to avoid starving later hubs.
    assert HubExpansionRegistry(path).next_demand_origin(hubs) == "2926"
    assert registry.record_demand_attempt("2926")
    assert HubExpansionRegistry(path).next_demand_origin(hubs) == "2941"

    report = HubExpansionRegistry(path).snapshot(owned_hub_ids=set(hubs), now=now[0])
    assert report["demand_owned_hubs_total"] == 3
    assert report["demand_owned_hubs_attempted"] == 3
    assert report["demand_owned_hubs_inconclusive"] == 3
    assert report["demand_samples"] == 0
    assert report["demand_coverage"] == "partial"
    assert [row["hub_id"] for row in report["demand_hub_progress"]] == [
        "2926", "2941", "3139"]
    assert all(row["last_attempt_status"] == "inconclusive" and
               row["sample_count"] == 0 and row["coverage"] == "partial"
               for row in report["demand_hub_progress"])
    assert "route_demand" not in json.loads(path.read_text(encoding="utf-8"))


def test_verified_samples_survive_inconclusive_retry_and_expiry(tmp_path, monkeypatch):
    now = [1900000000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: now[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand_attempt("2926")
    assert registry.record_demand("2926", [{
        "arr_id": "3139", "distance": 2000, "y": 10, "j": 1, "f": 0,
    }]) == 1
    first = registry.snapshot(now=now[0], owned_hub_ids={"2926", "2941"})
    assert first["demand_owned_hubs_with_samples"] == 1
    assert first["demand_owned_hubs_fresh_samples"] == 1
    assert first["demand_owned_hubs_inconclusive"] == 0
    now[0] += 20
    assert registry.record_demand_attempt("2926")
    retry = registry.snapshot(now=now[0], owned_hub_ids={"2926", "2941"})
    assert retry["demand_samples"] == 1
    assert retry["demand_owned_hubs_inconclusive"] == 1
    assert retry["demand_owned_hubs_attempted"] == 1
    assert retry["demand_hub_progress"] == [
        {"hub_id": "2926", "last_attempt_at": now[0],
         "last_attempt_status": "inconclusive", "sample_count": 1,
         "fresh_sample_count": 1, "conflict_count": 0,
         "last_sample_at": 1900000000,
         "coverage": "partial"},
        {"hub_id": "2941", "last_attempt_at": None,
         "last_attempt_status": "unattempted", "sample_count": 0,
         "fresh_sample_count": 0, "conflict_count": 0,
         "last_sample_at": None,
         "coverage": "partial"},
    ]
    now[0] += hub_expansion.MAX_AGE_SECONDS + 1
    expired = HubExpansionRegistry(registry.path).snapshot(
        now=now[0], owned_hub_ids={"2926", "2941"})
    assert expired["demand_fresh_samples"] == 0
    assert expired["demand_owned_hubs_fresh_samples"] == 0
    assert expired["demand_owned_hubs_attempted"] == 1
    assert expired["demand_coverage"] == "partial"
    assert expired["demand_hub_progress"][0]["sample_count"] == 1
    assert expired["demand_hub_progress"][0]["fresh_sample_count"] == 0


def test_invalid_attempt_and_corrupt_legacy_cursor_do_not_claim_coverage(tmp_path):
    path = tmp_path / "expansion.json"
    registry = HubExpansionRegistry(path)
    assert not registry.record_demand_attempt("invalid")
    assert not path.exists()
    path.write_text(json.dumps({"route_demand_attempts": {
        "2926": {"attempted_at": True, "status": "samples_observed", "sequence": 1},
        "2941": {"attempted_at": 1900000000, "status": "complete", "sequence": 2},
    }}), encoding="utf-8")
    report = registry.snapshot(now=1900000000, owned_hub_ids={"2926", "2941"})
    assert report["demand_owned_hubs_attempted"] == 0
    assert report["demand_coverage"] == "partial"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js indisponível")
def test_price_script_requires_matching_selected_airport_and_explicit_dollars():
    js = r"""
const option = {value: '2941', disabled: false, textContent: 'Florianópolis (FLN)',
                dataset: {iata: 'FLN'}};
const select = {selectedOptions: [option]};
let detailId = null;
let costId = null;
const details = {textContent: 'Florianópolis FLN runway 7546',
                 getAttribute: () => detailId};
const cost = {textContent: '$ 11,472,000 + 20 points', getAttribute: () => costId};
globalThis.document = {querySelector: selector => ({
  '#hubAirportSelector': select, '#airportInfo': details, '#hubCostInfo': cost
})[selector]};
const observe = new Function(process.argv[1]);
const valid = observe();
detailId = '2957';
const mismatchedDetail = observe();
detailId = null;
costId = '2957';
const mismatchedCost = observe();
costId = null;
details.textContent = 'Joinville JOI';
const stale = observe();
details.textContent = 'Florianópolis FLN';
cost.textContent = '20 points';
const unknown = observe();
cost.textContent = '$ 1,234.56';
const fractional = observe();
cost.textContent = '$ 11.472.000';
const dotThousands = observe();
console.log(JSON.stringify({valid, mismatchedDetail, mismatchedCost,
                            stale, unknown, fractional, dotThousands}));
"""
    result = subprocess.run(["node", "-e", js, game_observations._SELECTED_HUB_PRICE_JS],
                            capture_output=True, text=True, check=True, timeout=8)
    parsed = json.loads(result.stdout)
    assert parsed["valid"]["id"] == "2941"
    assert parsed["valid"]["hub_price"] == 11472000
    assert parsed["valid"]["hub_points"] == 20
    assert parsed["stale"] is None
    assert parsed["unknown"] is None
    assert parsed["mismatchedDetail"] is None
    assert parsed["mismatchedCost"] is None
    assert parsed["fractional"] is None
    assert parsed["dotThousands"]["hub_price"] == 11472000


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js indisponível")
def test_live_hub_cost_row_keeps_dollars_and_points_separate():
    """The authenticated game puts cost and points in adjacent text nodes."""
    js = r"""
const option = {value: '2966', disabled: false, textContent: 'Almeirim', dataset: {}};
const select = {selectedOptions: [option]};
let currentId = '2966';
const details = {
  textContent: 'Almeirim Brazil MEU - SBMD Airport information Hub cost',
  getAttribute: () => null,
  querySelector: () => null,
  querySelectorAll: () => [{get textContent() {return 'arrId = ' + currentId + ';';}}],
};
const priceCell = {childNodes: [
  {textContent: '$ 11,520,000'},
  {textContent: ''},
  {textContent: '20 Points'}
]};
const cost = {
  textContent: '$ 11,520,00020 Points',
  querySelector: selector => selector === 'td:nth-child(2)' ? priceCell : null,
  getAttribute: () => null,
};
globalThis.document = {querySelector: selector => ({
  '#hubAirportSelector': select, '#airportInfo': details, '#hubCostInfo': cost
})[selector]};
globalThis.window = {jQuery: {active: 2}};
const read = new Function(process.argv[1]);
const valid = read();
currentId = '2914';
const previousAirport = read();
console.log(JSON.stringify({valid, previousAirport}));
"""
    result = subprocess.run(["node", "-e", js, game_observations._SELECTED_HUB_PRICE_JS],
                            capture_output=True, text=True, check=True, timeout=8)
    report = json.loads(result.stdout)
    assert report["valid"]["id"] == "2966"
    assert report["valid"]["hub_price"] == 11_520_000
    assert report["valid"]["hub_points"] == 20
    assert report["previousAirport"] is None


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js indisponível")
def test_demand_script_keeps_missing_attributes_visible_to_validator():
    js = r"""
const attrs = {onclick: 'route_research_route.php?dep=2926&arr=3139',
               'data-distance': '1992.763', 'data-yclass': '120',
               'data-jclass': '106', 'data-fclass': '40', 'data-rwy': '5013'};
const row = {getAttribute: name => attrs[name] ?? null, querySelector: () => null,
             dataset: {distance: '1992.763', yclass: '120', jclass: '106', fclass: '40', rwy: '5013'}};
const result = {querySelector: () => null,
                querySelectorAll: () => [row]};
globalThis.document = {querySelector: () => result, querySelectorAll: result.querySelectorAll};
const observe = new Function(process.argv[1]);
const search = new Function(process.argv[2]);
const valid = observe();
const ordinaryCandidate = search()[0];
row.textContent = '*Demand is currently boosted due to a special event';
const boosted = observe();
const boostedCandidate = search()[0];
delete attrs['data-yclass'];
const missing = observe();
console.log(JSON.stringify({valid, boosted, missing, ordinaryCandidate, boostedCandidate}));
"""
    response = subprocess.run(["node", "-e", js, game_observations._VERIFIED_ROUTE_DEMAND_JS,
                               fleet._CANDIDATES_JS],
                              capture_output=True, text=True, check=True, timeout=8)
    data = json.loads(response.stdout)
    assert data["valid"] == [{"dep_id": "2926", "arr_id": "3139", "distance": "1992.763",
                              "y": "120", "j": "106", "f": "40", "runway": "5013",
                              "event_demand_boosted": None}]
    assert data["boosted"][0]["event_demand_boosted"] is True
    assert data["missing"][0]["y"] is None
    assert data["ordinaryCandidate"]["event_demand_boosted"] is False
    assert data["boostedCandidate"]["event_demand_boosted"] is True


def test_price_collection_requires_identical_correlated_reads(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    observed = {"id": "2941", "name": "Florianópolis", "code": "FLN",
                "hub_price": 11472000, "purchasable": True}

    class Bot:
        def __init__(self, items):
            self.items = iter(items)

        def js(self, _script):
            return next(self.items)

    assert game_observations.collect_visible_hub_price(Bot([observed, dict(observed)]))
    assert registry.snapshot()["candidates"][0]["hub_price"] == 11472000
    assert not game_observations.collect_visible_hub_price(Bot([
        observed, {**observed, "hub_price": 999999}]))
    assert registry.snapshot()["candidates"][0]["hub_price"] == 11472000


def test_both_hub_price_collectors_preserve_dom_read_time(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    observed_at = clock[0] - 0.7
    old_price = {"id": "2941", "name": "Florianópolis", "code": "FLN",
                 "hub_price": 5000, "hub_points": 0, "purchasable": True}

    def read(_bot, script, *, with_timestamp=False):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            assert not with_timestamp
            return ["2941"]
        assert script == game_observations._SELECTED_HUB_PRICE_JS and with_timestamp
        return old_price, observed_at

    monkeypatch.setattr(game_observations, "_stable_read", read)
    assert game_observations.collect_visible_hub_price(object())
    first = registry.snapshot(now=clock[0])["candidates"][0]
    assert first["hub_price_observed_at"] == observed_at
    assert first["observed_at"] == observed_at

    assert registry.record_catalog([{**old_price, "hub_price": 7000}],
                                   observed_at=clock[0] - 0.2)

    class Bot:
        stopping = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def js(self, script, *args):
            if script == game_observations._HUB_COUNTRIES_JS:
                return ["Brazil"]
            if script in (game_observations._SELECT_MARKET_COUNTRY_JS,
                          game_observations._SELECT_MARKET_AIRPORT_JS):
                return True
            raise AssertionError("unexpected browser operation")

    assert game_observations.collect_hub_market_prices(Bot(), per_cycle=1) == 1
    after = registry.snapshot(now=clock[0])["candidates"][0]
    assert after["hub_price"] == 7000
    assert after["hub_price_observed_at"] == clock[0] - 0.2


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js indisponível")
def test_country_change_does_not_reuse_stale_airports_from_previous_country():
    js = r"""
const country = {
  value: 'Brazil',
  options: [{value: 'Brazil', disabled: false}, {value: 'Chile', disabled: false}],
  dispatchEvent: () => true
};
const airport = {options: [{value: '2941', disabled: false}]};
globalThis.window = {jQuery: {active: 0}};
globalThis.document = {querySelector: selector => ({
  '#hubcountrySelector': country, '#hubAirportSelector': airport
})[selector]};
globalThis.Event = class {constructor(type) {this.type = type;}};
const change = new Function(process.argv[1]);
const read = new Function(process.argv[2]);
const previous = read();
const changed = change('Chile');
const stale = read();
airport.options = [{value: '3101', disabled: false}];
const fresh = read();
const stable = read();
console.log(JSON.stringify({previous, changed, stale, fresh, stable}));
"""
    result = subprocess.run([
        "node", "-e", js, game_observations._SELECT_MARKET_COUNTRY_JS,
        game_observations._HUB_AIRPORT_OPTIONS_JS],
        capture_output=True, text=True, check=True, timeout=8)
    data = json.loads(result.stdout)
    assert data == {"previous": ["2941"], "changed": True, "stale": None,
                    "fresh": ["3101"], "stable": ["3101"]}


def test_failed_hub_price_is_retried_without_repeating_every_airport(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    now = [1_900_000_000]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: now[0])
    obtainable = {"2941": False, "2957": True, "3101": True}

    class Bot:
        stopping = False

        def __init__(self):
            self.country = "Brazil"
            self.airport = None
            self.airports_visited = []

        def open_popup(self, *args):
            pass

        def close_popup(self, **kwargs):
            pass

        def js(self, script, *args):
            if script == game_observations._HUB_COUNTRIES_JS:
                return ["Brazil", "Chile"]
            if script == game_observations._SELECT_MARKET_COUNTRY_JS:
                self.country = args[0]
                return True
            if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
                return {"Brazil": ["2941", "2957"], "Chile": ["3101"]}[self.country]
            if script == game_observations._SELECT_MARKET_AIRPORT_JS:
                self.airport = args[0]
                self.airports_visited.append(args[0])
                return True
            raise AssertionError("unexpected browser operation")

    def stable_read(bot, script, *, with_timestamp=False):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            assert not with_timestamp
            return bot.js(script)
        assert with_timestamp
        if not obtainable[bot.airport]:
            return None
        return ({"id": bot.airport, "name": bot.airport, "code": "",
                 "purchasable": True, "hub_price": 5000, "hub_points": 20},
                now[0])

    monkeypatch.setattr(game_observations, "_stable_read", stable_read)
    first = Bot()
    assert game_observations.collect_hub_market_prices(first, per_cycle=2) == 1
    assert first.airports_visited == ["2941", "2957"]
    assert registry.due_catalog_retries() == []
    assert registry.catalog_scan_position() == {"country": "Brazil", "airport_id": "2957"}

    obtainable["2941"] = True
    now[0] += 31
    second = Bot()
    assert game_observations.collect_hub_market_prices(second, per_cycle=2) == 2
    assert second.airports_visited == ["2941", "3101"]
    assert registry.due_catalog_retries() == []
    assert {row["id"] for row in registry.snapshot()["candidates"]} == {
        "2941", "2957", "3101"}


def test_hub_price_waits_for_ajax_before_advancing_airport(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    price_reads = iter([None, None, {"id": "2966", "name": "Almeirim", "code": "MEU",
                                    "purchasable": True, "hub_price": 11_520_000,
                                    "hub_points": 20}])

    class Stop:
        delays = []

        def wait(self, seconds):
            self.delays.append(seconds)
            return False

    class Bot:
        stopping = False

        def __init__(self):
            self._stop = Stop()
            self.selected = []

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def js(self, script, *args):
            if script == game_observations._HUB_COUNTRIES_JS:
                return ["Brazil"]
            if script == game_observations._SELECT_MARKET_COUNTRY_JS:
                return True
            if script == game_observations._SELECT_MARKET_AIRPORT_JS:
                self.selected.append(args[0])
                return True
            raise AssertionError("Unrecognized game operation")

    def read(_bot, script, *, with_timestamp=False):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            assert not with_timestamp
            return ["2966"]
        assert with_timestamp
        observed = next(price_reads)
        return (observed, time.time()) if observed is not None else None

    monkeypatch.setattr(game_observations, "_stable_read", read)
    bot = Bot()
    assert game_observations.collect_hub_market_prices(bot, per_cycle=1) == 1
    assert bot.selected == ["2966"]
    assert bot._stop.delays == [0.2, 0.2]
    assert registry.snapshot()["candidates"][0]["hub_price"] == 11_520_000


def test_price_read_failure_cannot_refresh_stored_observation(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    observed = {"id": "2941", "name": "Florianópolis", "code": "FLN",
                "hub_price": 11472000, "purchasable": True}

    class Bot:
        def __init__(self):
            self.calls = 0

        def js(self, _script):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("transient browser error")
            return observed

    bot = Bot()
    assert not game_observations.collect_visible_hub_price(bot)
    assert bot.calls == 2
    assert not registry.path.exists()


def test_market_price_scan_resumes_per_profile_and_never_purchases(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    def observe(bot, script, *, with_timestamp=False):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            assert not with_timestamp
            return bot.js(script)
        assert with_timestamp
        if bot.airport == "2941":
            return None
        return ({"id": bot.airport, "name": f"Airport {bot.airport}", "code": "",
                 "hub_price": int(bot.airport) * 1000, "purchasable": True}, time.time())

    monkeypatch.setattr(game_observations, "_stable_read", observe)

    class Bot:
        stopping = False
        _stop = None

        def __init__(self):
            self.country = None
            self.airport = None
            self.commands = []

        def open_popup(self, *args):
            self.commands.append(("popup", args[0]))

        def close_popup(self, **kwargs):
            self.commands.append(("close", kwargs.get("quiet")))

        def js(self, script, *args):
            if script == game_observations._HUB_COUNTRIES_JS:
                return ["Brazil", "Chile"]
            if script == game_observations._SELECT_MARKET_COUNTRY_JS:
                self.country = args[0]
                self.commands.append(("country", args[0]))
                return True
            if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
                return {"Brazil": ["2941", "2957"], "Chile": ["3101"]}[self.country]
            if script == game_observations._SELECT_MARKET_AIRPORT_JS:
                self.airport = args[0]
                self.commands.append(("airport", args[0]))
                return True
            raise AssertionError("Unexpected game interaction")

    first = Bot()
    assert game_observations.collect_hub_market_prices(first, per_cycle=2) == 1
    assert registry.catalog_scan_position() == {"country": "Brazil", "airport_id": "2957"}
    assert [row["id"] for row in registry.snapshot()["candidates"]] == ["2957"]
    assert first.commands == [("popup", "hubs_new.php"), ("country", "Brazil"),
                              ("airport", "2941"), ("airport", "2957"), ("close", True)]

    second = Bot()
    assert game_observations.collect_hub_market_prices(second, per_cycle=1) == 1
    assert registry.catalog_scan_position() == {"country": "Chile", "airport_id": "3101"}
    assert second.commands == [("popup", "hubs_new.php"), ("country", "Brazil"),
                               ("country", "Chile"), ("airport", "3101"), ("close", True)]
    assert {row["id"] for row in registry.snapshot()["candidates"]} == {"2957", "3101"}


def test_market_scan_does_not_overwrite_catalog_when_country_list_is_missing(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)

    class Bot:
        stopping = False
        closed = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            self.closed = True

        def js(self, script, *_args):
            assert script == game_observations._HUB_COUNTRIES_JS
            return []

    bot = Bot()
    assert game_observations.collect_hub_market_prices(bot) == 0
    assert bot.closed
    assert not registry.path.exists()


@pytest.mark.parametrize("raw_change", [
    {"y": None}, {"j": "n/a"}, {"distance": "?"}, {"y": "999"},
    {"arr_id": "2957"}, {"distance": "0"}, {"dep_id": "2941"},
])
def test_demand_collection_rejects_partial_or_unmatched_search(tmp_path, monkeypatch, raw_change):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)

    class Hubs:
        def record_options(self, options):
            return options == [{"id": "2926", "text": "Chapecó"}]

    monkeypatch.setattr(game_observations, "HubRegistry", Hubs)
    requested = []

    def search(bot, origin, distance, runway, *, persist_demand):
        requested.append((origin, distance, runway, persist_demand))
        return [RouteCandidate("3139", "SBL", 1992.763, 120, 106, 40, 5013)]

    monkeypatch.setattr(fleet, "search_routes", search)
    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "1992.763", "y": "120", "j": "106", "f": "40"}

    class Config:
        def get_int(self, _section, key, default):
            return default

    class Bot:
        stopping = False
        config = Config()

        def __init__(self, rows):
            self.reads = iter(rows)
            self.closed = False

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            self.closed = True

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == _HUB_OPTIONS_JS:
                return [{"id": "2926", "text": "Chapecó"}]
            if script == game_observations._VERIFIED_ROUTE_DEMAND_JS:
                return next(self.reads)
            raise AssertionError("unexpected browser query")

    verified = Bot([[raw], [dict(raw)]])
    assert game_observations.collect_owned_hub_demand(verified) == 1
    assert requested == [("2926", 6000, 5000, False)]
    assert verified.closed
    original = json.loads(registry.path.read_text(encoding="utf-8"))["route_demand"]
    changed = Bot([[{**raw, **raw_change}], [{**raw, **raw_change}]])
    assert game_observations.collect_owned_hub_demand(changed) == 0
    assert changed.closed
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    assert persisted["route_demand"] == original
    assert persisted["route_demand_attempts"]["2926"]["status"] == "inconclusive"


def test_planning_rotates_configured_and_broad_search_per_hub(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    options = [{"id": "2926"}, {"id": "2941"}]
    monkeypatch.setattr(game_observations, "HubRegistry", lambda: type("Hubs", (), {
        "record_options": lambda self, value: value == options})())
    clock = [1_900_000_000.0]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    requested = []
    rows = []

    def search(_bot, origin, distance, runway, *, persist_demand):
        requested.append((origin, distance, runway, persist_demand))
        candidate = (RouteCandidate("2957", "LONG", 9000, 100, 20, 5, 4000)
                     if distance == 20000 else RouteCandidate("3139", "SBL", 2000, 100, 20, 5, 5013))
        rows[:] = [{"dep_id": origin, "arr_id": candidate.arr_id,
                    "distance": str(candidate.distance), "runway": str(candidate.runway),
                    "y": "100", "j": "20", "f": "5"}]
        return [candidate]

    monkeypatch.setattr(fleet, "search_routes", search)
    monkeypatch.setattr(game_observations, "_stable_read", lambda *_args, **_kwargs: (rows, clock[0]))

    class Bot:
        stopping = False

        class config:
            @staticmethod
            def get_int(_section, _key, default):
                return default

            @staticmethod
            def get_bool(section, key):
                return (section, key) == ("investment", "planning_enabled")

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            assert script == _HUB_OPTIONS_JS
            return options

    for _ in range(4):
        assert game_observations.collect_owned_hub_demand(Bot()) == 1
        clock[0] += 10
    assert requested == [("2926", 6000, 5000, False), ("2941", 6000, 5000, False),
                         ("2926", 20000, 0, False), ("2941", 20000, 0, False)]
    reopened = HubExpansionRegistry(registry.path)
    snapshot = reopened.demand_research_snapshot({"2926", "2941"}, now=clock[0])
    assert snapshot["coverage"] == "partial"
    assert len(snapshot["samples"]) == 4
    assert {row["destination_runway_ft"] for row in snapshot["samples"]} == {4000, 5013}
    for row in snapshot["hub_progress"]:
        assert row["last_search_scope"] == "broad"
        assert row["last_requested_max_distance_km"] == 20000
        assert row["last_requested_min_runway_ft"] == 0
        assert reopened.next_demand_scope(row["hub_id"]) == "configured"


def test_dedicated_search_cursor_survives_unrelated_samples_and_failed_attempt(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand_attempt("2926", search_scope="configured", max_distance=6000, min_runway=5000)
    assert registry.record_demand("2926", [{"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 5}]) == 1
    snapshot = registry.demand_research_snapshot({"2926"})
    assert snapshot["hub_progress"][0]["last_attempt_status"] == "inconclusive"
    assert registry.next_demand_scope("2926") == "broad"
    assert registry.record_demand_attempt("2926", search_scope="broad", max_distance=20000, min_runway=0)
    assert HubExpansionRegistry(registry.path).next_demand_scope("2926") == "configured"


def test_demand_runway_is_only_retained_when_correlated():
    candidates = [RouteCandidate("3139", "SBL", 2000, 100, 20, 5, 5013)]
    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "2000", "y": "100", "j": "20", "f": "5"}
    for unknown in (None, "0", "n/a", True):
        samples = game_observations._verified_demand(candidates, [{**raw, "runway": unknown}], "2926")
        assert len(samples) == 1
        assert "destination_runway_ft" not in samples[0]
    assert game_observations._verified_demand(candidates, [{**raw, "runway": "5013"}], "2926")[0]["destination_runway_ft"] == 5013
    assert game_observations._verified_demand(candidates, [{**raw, "runway": "5014"}], "2926") == []


def test_event_demand_retains_only_explicit_positive_observation():
    candidates = [RouteCandidate("3139", "SBL", 2000, 100, 20, 5, 5013)]
    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "2000", "y": "100", "j": "20", "f": "5"}
    for flag in (None, False, "true", 1, True):
        row = game_observations._verified_demand(candidates, [{**raw, "event_demand_boosted": flag}], "2926")[0]
        assert row.get("event_demand_boosted") is (True if flag is True else None)


def test_search_keeps_event_warning_when_followup_dom_read_loses_it(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(fleet, "HubExpansionRegistry", lambda: registry)

    class Bot:
        def ajax(self, *_args):
            pass

        def js(self, _script):
            return [{"arr": "3139", "name": "SBL", "distance": "2000",
                     "y": "100", "j": "20", "f": "5", "rwy": "5013", "event_demand_boosted": True}]

    candidates = fleet.search_routes(Bot(), "2926", 3000, 1000, persist_demand=True)
    assert registry.demand_research_snapshot({"2926"})["samples"][0]["event_demand_boosted"] is True

    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "2000",
           "y": "100", "j": "20", "f": "5", "runway": "5013"}
    samples = game_observations._verified_demand(candidates, [raw], "2926")
    assert samples[0]["event_demand_boosted"] is True


def test_demand_collector_persists_dom_read_time_even_when_processing_is_late(
        tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)

    class Hubs:
        def record_options(self, options):
            return options == [{"id": "2926"}]

    monkeypatch.setattr(game_observations, "HubRegistry", Hubs)
    monkeypatch.setattr(fleet, "search_routes", lambda *_args, **_kwargs: [
        RouteCandidate("3139", "SBL", 2000, 120, 10, 0, 5000)])
    read_at = 1_900_000_010.125
    clock = [read_at + 30]
    monkeypatch.setattr(hub_expansion.time, "time", lambda: clock[0])
    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "2000",
           "y": "120", "j": "10", "f": "0"}

    def stable_read(_bot, script, *, with_timestamp=False):
        assert script == game_observations._VERIFIED_ROUTE_DEMAND_JS
        assert with_timestamp
        return ([raw], read_at)

    monkeypatch.setattr(game_observations, "_stable_read", stable_read)

    class Bot:
        stopping = False

        class config:
            @staticmethod
            def get_int(_section, _key, default):
                return default

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            assert script == _HUB_OPTIONS_JS
            return [{"id": "2926"}]

    assert game_observations.collect_owned_hub_demand(Bot()) == 1
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    assert saved["route_demand"]["2926:3139"]["observed_at"] == read_at
    assert saved["route_demand_attempts"]["2926"]["status"] == "inconclusive"


def test_demand_collection_discards_unstable_reads_and_invalid_hub_selector(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)

    class Hubs:
        def record_options(self, options):
            return bool(options) and options[0].get("id") == "2926"

    monkeypatch.setattr(game_observations, "HubRegistry", Hubs)
    monkeypatch.setattr(fleet, "search_routes", lambda *args, **kwargs: [
        RouteCandidate("3139", "SBL", 2000, 1, 2, 3, 5000)])

    class Config:
        def get_int(self, _section, _key, default):
            return default

    class Bot:
        stopping = False
        config = Config()

        def __init__(self, options, responses):
            self.options = options
            self.responses = iter(responses)

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            pass

        def ajax(self, *_args):
            pass

        def js(self, script):
            if script == _HUB_OPTIONS_JS:
                return self.options
            return next(self.responses)

    raw = {"dep_id": "2926", "arr_id": "3139", "distance": "2000", "y": "1", "j": "2", "f": "3"}
    assert game_observations.collect_owned_hub_demand(Bot(
        [{"id": "2926"}], [[raw], [{**raw, "y": "4"}]])) == 0
    assert game_observations.collect_owned_hub_demand(Bot(
        [{"id": "INVALID"}], [[raw], [raw]])) == 0
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    assert "route_demand" not in persisted
    assert set(persisted["route_demand_attempts"]) == {"2926"}
    assert persisted["route_demand_attempts"]["2926"]["status"] == "inconclusive"


@pytest.mark.parametrize("failure", [None, "wrong_origin", "changed_ownership", "missing_ownership"])
def test_external_demand_requires_current_ownership_and_matching_results(tmp_path, monkeypatch, failure):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([{"id": "3139", "purchasable": True, "hub_price": 5000}])
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)
    monkeypatch.setattr(game_observations, "HubRegistry", lambda: HubRegistry(tmp_path / "hubs.json"))
    options = [{"id": "0", "text": "Select hub"},
               {"id": "2926", "text": "XAP - Chapeco", "code": "XAP", "title": ""}]
    raw = {"dep_id": "2926" if failure == "wrong_origin" else "3139", "arr_id": "2926",
           "distance": "2000", "y": "100", "j": "20", "f": "5", "runway": "5013",
           "event_demand_boosted": True}
    ownership_reads = iter([None if failure == "missing_ownership" else options,
                            options + [{"id": "3139"}] if failure == "changed_ownership" else options])

    def stable_read(_bot, script, *, with_timestamp=False):
        if script == _HUB_OPTIONS_JS:
            return next(ownership_reads)
        assert with_timestamp
        return [raw], time.time()

    monkeypatch.setattr(game_observations, "_stable_read", stable_read)
    searched = []

    def search(_bot, origin, distance, runway, *, persist_demand):
        searched.append((origin, distance, runway, persist_demand))
        return [RouteCandidate("2926", "XAP", 2000, 100, 20, 5, 5013)]

    monkeypatch.setattr(fleet, "search_routes", search)

    class Config:
        def get_bool(self, _section, _key):
            return True

        def get_int(self, _section, _key, default):
            return default

    class Bot:
        stopping = False
        config = Config()

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            self.closed = True

        def ajax(self, *_args):
            pass

    bot = Bot()
    assert game_observations.collect_external_hub_demand(bot) == (1 if failure is None else 0)
    assert bot.closed
    assert searched == ([] if failure == "missing_ownership" else [("3139", 6000, 5000, False)])
    assert registry.demand_observations({"3139"}) == []
    external = registry.external_demand_snapshot({"2926"})
    assert len(external["samples"]) == (1 if failure is None else 0)
    if failure is None:
        assert external["samples"][0]["event_demand_boosted"] is True
    else:
        assert external["hub_progress"][0]["last_attempt_status"] == (
            "unattempted" if failure == "missing_ownership" else "inconclusive")


def test_demand_search_interruption_rotates_to_next_owned_hub(tmp_path, monkeypatch):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    monkeypatch.setattr(game_observations, "HubExpansionRegistry", lambda: registry)

    class Hubs:
        def record_options(self, options):
            return options == [{"id": "2926"}, {"id": "2941"}]

    monkeypatch.setattr(game_observations, "HubRegistry", Hubs)

    def interrupted_search(*_args, **_kwargs):
        raise RuntimeError("research interrupted")

    monkeypatch.setattr(fleet, "search_routes", interrupted_search)

    class Bot:
        stopping = False
        closed = False

        class config:
            @staticmethod
            def get_int(_section, _key, default):
                return default

        def open_popup(self, *_args):
            pass

        def close_popup(self, **_kwargs):
            self.closed = True

        def ajax(self, *_args):
            pass

        def js(self, script):
            assert script == _HUB_OPTIONS_JS
            return [{"id": "2926"}, {"id": "2941"}]

    bot = Bot()
    with pytest.raises(RuntimeError, match="research interrupted"):
        game_observations.collect_owned_hub_demand(bot)

    assert bot.closed
    assert registry.next_demand_origin(["2926", "2941"]) == "2941"
    report = registry.snapshot(owned_hub_ids={"2926", "2941"})
    assert report["demand_owned_hubs_attempted"] == 1
    assert report["demand_owned_hubs_inconclusive"] == 1
    assert report["demand_coverage"] == "partial"
    assert "route_demand" not in json.loads(registry.path.read_text(encoding="utf-8"))


class PaginatedBot:
    def __init__(self, *, invalid=False, links=None):
        self.page = 2
        self.invalid = invalid
        self.links = links
        self.navigations = []

    def js(self, script):
        if script == _ROUTES_PAGER_LINKS_JS:
            if self.links is not None:
                return self.links
            return [{"offset": 20 * (page - 1),
                     "url": f"routes.php?start={20 * (page - 1)}&sort=",
                     "target": "routeAction"}
                    for page in (self.page - 1, self.page + 1) if 1 <= page <= 3]
        if script == _ROUTE_AUDIT_JS:
            effective_page = 2 if self.invalid else self.page
            return [{"aircraft_id": str(900 + self.page), "registration": f"PP-{self.page}",
                     "model": "A320", "scan_page": effective_page,
                     "scan_total_pages": 3, "origin_code": "XAP", "destination_code": "GRU",
                     "home_hub_id": "2926" if self.page == 2 else None}]
        return None

    def ajax(self, url, target):
        assert target == "routeAction"
        self.page = int(url.split("start=")[1].split("&")[0]) // 20 + 1
        self.navigations.append(self.page)


def test_live_page_loader_verifies_each_page_and_restores_initial_view(tmp_path):
    bot = PaginatedBot()
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == [1, 3, 2]
    assert bot.page == 2
    assert bot.navigations == [1, 2, 3, 2, 1, 2, 3, 2]
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 3
    assert coverage["unique_aircraft"] == 3
    confirmed = next(r for r in registry.snapshot()["relations"] if r["aircraft_id"] == "902")
    assert confirmed["home_hub_id"] == "2926"
    assert confirmed["home_hub_source"] == "game"
    assert confirmed["home_hub_evidence"] == HOME_HUB_EVIDENCE
    assert confirmed["home_hub_evidence_aircraft_id"] == "902"
    assert confirmed["home_hub_verified_at"] > 0
    hubs = HubRegistry(tmp_path / "hubs.json")
    assert hubs.record_options([{"id": "2926", "text": "Chapecó"}])
    report = hubs.snapshot(registry.snapshot())
    assert report["hubs"][0]["aircraft_count"] == 1
    assert report["hubs"][0]["aircraft"][0]["aircraft_id"] == "902"
    assert len(report["unconfirmed_aircraft"]) == 2
    assert "home_hub_id" not in next(r for r in registry.snapshot()["relations"]
                                if r["aircraft_id"] == "901")


def test_loader_rejects_unknown_target_and_page_mismatch(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    bot = PaginatedBot(links=[{"offset": 40, "target": "unknown"}])
    assert audit_routes_live_pages(bot, registry) == []
    assert bot.navigations == []

    bot = PaginatedBot(invalid=True)
    assert audit_routes_live_pages(bot, registry) == []
    assert bot.page == 2
    assert registry.snapshot()["scan_coverage"] is None
