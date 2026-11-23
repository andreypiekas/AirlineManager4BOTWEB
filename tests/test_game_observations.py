"""Live-read adapters must persist only game-correlated, non-destructive data."""
import json
import shutil
import subprocess

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
    now[0] += hub_expansion.MAX_AGE_SECONDS + 1
    expired = HubExpansionRegistry(registry.path).snapshot(
        now=now[0], owned_hub_ids={"2926", "2941"})
    assert expired["demand_fresh_samples"] == 0
    assert expired["demand_owned_hubs_fresh_samples"] == 0
    assert expired["demand_owned_hubs_attempted"] == 1
    assert expired["demand_coverage"] == "partial"


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
               'data-jclass': '106', 'data-fclass': '40'};
const row = {getAttribute: name => attrs[name] ?? null};
const result = {querySelector: () => null,
                querySelectorAll: () => [row]};
globalThis.document = {querySelector: () => result};
const observe = new Function(process.argv[1]);
const valid = observe();
delete attrs['data-yclass'];
const missing = observe();
console.log(JSON.stringify({valid, missing}));
"""
    response = subprocess.run(["node", "-e", js, game_observations._VERIFIED_ROUTE_DEMAND_JS],
                              capture_output=True, text=True, check=True, timeout=8)
    data = json.loads(response.stdout)
    assert data["valid"] == [{"dep_id": "2926", "arr_id": "3139", "distance": "1992.763",
                              "y": "120", "j": "106", "f": "40"}]
    assert data["missing"][0]["y"] is None


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

    def stable_read(bot, script):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            return bot.js(script)
        if not obtainable[bot.airport]:
            return None
        return {"id": bot.airport, "name": bot.airport, "code": "",
                "purchasable": True, "hub_price": 5000, "hub_points": 20}

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

    def read(_bot, script):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            return ["2966"]
        return next(price_reads)

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
    def observe(bot, script):
        if script == game_observations._HUB_AIRPORT_OPTIONS_JS:
            return bot.js(script)
        return ({"id": bot.airport, "name": f"Airport {bot.airport}", "code": "",
                 "hub_price": int(bot.airport) * 1000, "purchasable": True}
                if bot.airport != "2941" else None)

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
    assert bot.navigations == [1, 2, 3, 2]
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
