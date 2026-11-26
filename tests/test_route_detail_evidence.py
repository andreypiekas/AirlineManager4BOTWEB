import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import route_detail_evidence as evidence
from hub_expansion import HubExpansionRegistry
from owned_hub_research_feed import build_owned_hub_research_queue
from owned_hub_research_ingestion import OwnedHubResearchInputsRegistry
from route_stopover import _READ


NOW = 1_900_000_000
RAW = {"codes": ["XAP", "SBL"], "runways": ["6,749 ft", "5013ft"], "occupied": "0"}
SAMPLE = {"source": "game_route_search", "origin_id": "2926", "destination_id": "3139",
          "observed_at": NOW, "distance_km": 1992.763, "y": 120, "j": 106, "f": 40,
          "destination_runway_ft": 5013}


@pytest.mark.parametrize("changes", [
    {"codes": ["SBL", "XAP"]}, {"codes": ["XAP"]}, {"codes": ["XAP", "SBL", "FLN"]},
    {"runways": ["6749m", "5013ft"]}, {"runways": ["6,74 ft", "5013ft"]},
    {"runways": ["0 ft", "5013ft"]}, {"runways": ["6749 ft", "30001ft"]},
    {"runways": ["6749 ft", "5014ft"]},
])
def test_invalid_detail(changes):
    assert evidence.validated_detail({**RAW, **changes}, "2926", "3139", expected_runway=5013) is None


def test_ordered_identity_and_units_do_not_certify_occupancy():
    assert evidence.validated_detail(RAW, "2926", "3139", expected_runway=5013, hub_code="XAP") == {
        "origin_runway_ft": 6749, "destination_runway_ft": 5013, "occupied_aircraft": None,
    }
    assert evidence.validated_detail(RAW, "2926", "3139", hub_code="GRU") is None
    assert evidence.validated_detail({**RAW, "codes": ["SBCH", "SLSA"]}, "2926", "3139")


def test_failed_attempts_rotate_across_hubs_and_routes(tmp_path):
    registry = evidence.RouteDetailRegistry(tmp_path / "details.json")
    other_route = {**SAMPLE, "destination_id": "2941"}
    other_hub = {**SAMPLE, "origin_id": "2891", "destination_id": "3029"}
    samples = [SAMPLE, other_route, other_hub]
    attempted = [registry.reserve(samples, now=NOW + i)[0] for i in range(4)]
    assert [row["origin_id"] for row in attempted] == ["2891", "2926", "2891", "2926"]
    assert set(row["destination_id"] for row in attempted) == {"3139", "2941", "3029"}
    reopened = evidence.RouteDetailRegistry(registry.path)
    assert reopened.reserve(samples, now=NOW + 4)[0] == other_hub


def test_label_bound_count_does_not_certify_occupancy(tmp_path):
    registry = evidence.RouteDetailRegistry(tmp_path / "details.json")
    assert registry.reserve([SAMPLE], now=NOW)
    raw = {**RAW, "occupancy_label": "A/C on route", "occupied": "0"}
    detail = evidence.validated_detail(raw, "2926", "3139")
    assert detail["observed_aircraft_on_route"] == 0
    assert detail["occupied_aircraft"] is None
    assert registry.finish("2926", "3139", NOW, detail, observed_at=NOW)
    assert registry.enrich([SAMPLE], now=NOW)[0]["route_detail"]["observed_aircraft_on_route"] == 0
    for count in ("-1", "1 aircraft", True, None, ""):
        assert "observed_aircraft_on_route" not in evidence.validated_detail(
            {**raw, "occupied": count}, "2926", "3139")
    assert "observed_aircraft_on_route" not in evidence.validated_detail(
        {**raw, "occupancy_label": "A/C capable"}, "2926", "3139")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")
def test_read_binds_passenger_labels_to_the_passenger_section():
    js = r"""
const read = new Function(process.argv[1]);
const cells = (...texts) => ({cells: texts.map((text, index) => ({
  textContent: text, classList: {contains: name => index === 1 && name === 'text-right'},
}))});
global.location = {href: 'https://example.test/'};
global.fetch = async () => ({ok: true, text: async () => ''});
const readDetail = async (today, header = 'J class', duplicateDaily = false) => {
  const rows = [cells('', 'Y class', header, 'F class'), cells('Daily', '1,081', '510', '272')];
  if (duplicateDaily) rows.push(cells('Daily', '1,080', '510', '272'));
  if (today) rows.push(cells('Today', '1,054', '461', '249'));
  rows.push(cells('', 'Large', '', 'Heavy'), cells('Daily', '811,000 Lbs', '', '765,000 Lbs'),
    cells('Today', '541,000 Lbs', '', '510,000 Lbs'));
  const detail = {
    textContent: today ? '*Demand is currently boosted due to a special event' : '',
    querySelectorAll: selector => ({
      'table.table-bordered': [{rows}],
      'table.m-text:not(.table-bordered) tr': [cells('A/C on route', '1'), cells('A/C capable', '0')],
    })[selector] || [],
  };
  // Both a bare AJAX fragment and a wrapped detail are accepted.
  global.DOMParser = class {parseFromString() {return {body: detail, getElementById: () => today ? detail : null};}};
  return new Promise((resolve, reject) => read('read-only', '', data => data ? resolve(data) : reject()));
};
(async () => {
  const result = [await readDetail(true), await readDetail(false), await readDetail(true, 'Business'),
    await readDetail(true, 'J class', true)];
  process.stdout.write(JSON.stringify(result));
})();
"""
    output = subprocess.run(["node", "-e", js, _READ], capture_output=True, text=True, check=True, timeout=10)
    full, daily_only, unknown_header, duplicate = json.loads(output.stdout)
    assert full["observed_daily_demand"] == {"y": "1,081", "j": "510", "f": "272"}
    assert full["observed_today_demand"] == {"y": "1,054", "j": "461", "f": "249"}
    assert full["occupied"] == "1" and full["observed_capable_aircraft"] == "0"
    assert full["event_demand_boosted"] is True
    assert daily_only["observed_daily_demand"] == full["observed_daily_demand"]
    assert daily_only["observed_today_demand"] is None and daily_only["event_demand_boosted"] is None
    assert unknown_header["observed_daily_demand"] is None and unknown_header["observed_today_demand"] is None
    assert duplicate["observed_daily_demand"] is None


@pytest.mark.parametrize("today", [None, {"y": "1,00", "j": "4", "f": "0"},
                                   {"y": "9" * 5000, "j": "4", "f": "0"},
                                   {"y": False, "j": 4, "f": 0}, {"y": "27 Lbs", "j": "4", "f": "0"}])
def test_absent_or_malformed_today_stays_unknown(today):
    raw = {**RAW, "observed_daily_demand": {"y": "1,200", "j": "106", "f": "0"},
           "observed_today_demand": today, "observed_capable_aircraft": "0"}
    detail = evidence.validated_detail(raw, "2926", "3139")
    assert detail["observed_daily_demand"] == {"y": 1200, "j": 106, "f": 0}
    assert detail["observed_capable_aircraft"] == 0
    assert "observed_today_demand" not in detail


def test_warning_from_either_read_blocks_economics_with_changing_today(tmp_path, monkeypatch):
    daily = {"y": "120", "j": "106", "f": "40"}
    today = {"y": "70", "j": "101", "f": "0"}
    raw = {**RAW, "observed_daily_demand": daily, "observed_today_demand": today,
           "observed_capable_aircraft": "2"}
    changed = {**raw, "observed_today_demand": {**today, "y": "68"}, "observed_capable_aircraft": "1"}
    reads = iter([{**raw, "event_demand_boosted": True}, changed, changed,
                  {**changed, "event_demand_boosted": True}])
    registry = evidence.RouteDetailRegistry(tmp_path / "details.json")
    monkeypatch.setattr(evidence, "research_details", lambda *_: next(reads))
    monkeypatch.setattr(evidence.time, "time", lambda: NOW)
    bot = SimpleNamespace(stopping=False)
    for today_was_stable in (False, True):
        assert evidence.collect_route_details(bot, registry, [SAMPLE], {"2926": "XAP"}) == 1
        sample = registry.enrich([SAMPLE], now=NOW)[0]
        assert sample["event_demand_boosted"] is True
        detail = sample["route_detail"]
        assert detail["observed_daily_demand"] == {"y": 120, "j": 106, "f": 40}
        assert detail.get("observed_today_demand") == ({"y": 68, "j": 101, "f": 0} if today_was_stable else None)
        assert detail.get("observed_capable_aircraft") == (1 if today_was_stable else None)
        sample.pop("event_demand_boosted")
        inventory = {"source": "game_hub_select", "observed_at": NOW, "hubs": [{"id": "2926", "code": "XAP"}]}
        market = {"source": "bot_aircraft_market_cache", "fresh": True, "observed_at": NOW,
                  "models": [{"id": 11, "name": "A320", "range": 6000, "capacity": 180, "price": 1700000}]}
        item = build_owned_hub_research_queue(inventory, [sample], market, now=NOW)["items"][0]
        assert item["event_demand_boosted"] is True
        assert "demanda_evento_temporario" in item["pending"]
        assert item["economics_preview"] is None and item["purchase_eligible"] is False


def test_stable_observation_expires_and_failed_refresh_revokes_it(tmp_path, monkeypatch):
    registry = evidence.RouteDetailRegistry(tmp_path / "details.json")
    clock = [NOW]
    monkeypatch.setattr(evidence.time, "time", lambda: clock[0])
    monkeypatch.setattr(evidence, "research_details", lambda *_: RAW)
    bot = SimpleNamespace(stopping=False)
    assert evidence.collect_route_details(bot, registry, [SAMPLE], {"2926": "XAP"}) == 1
    assert registry.enrich([SAMPLE], now=NOW)[0]["route_detail"]["observed_at"] == NOW
    assert "route_detail" not in registry.enrich([SAMPLE], now=NOW + evidence.MAX_AGE + 1)[0]
    assert "route_detail" not in registry.enrich([{**SAMPLE, "destination_runway_ft": 5014}], now=NOW)[0]
    clock[0] += 1
    reads = iter([RAW, {**RAW, "runways": ["6749 ft", "5014 ft"]}])
    monkeypatch.setattr(evidence, "research_details", lambda *_: next(reads))
    assert evidence.collect_route_details(bot, registry, [SAMPLE], {"2926": "XAP"}) == 0
    assert "route_detail" not in registry.enrich([SAMPLE], now=clock[0])[0]


def test_registry_feed_and_materialized_rows_respect_independent_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence.time, "time", lambda: NOW)
    expansion = HubExpansionRegistry(tmp_path / "hub_expansion.json")
    assert expansion.record_demand("2926", [{"arr_id": "3139", "distance": 1992.763,
                                              "y": 120, "j": 106, "f": 40,
                                              "destination_runway_ft": 5013}], observed_at=NOW) == 1
    details = expansion.route_detail_registry()
    assert details.reserve([SAMPLE], now=NOW)
    assert details.finish("2926", "3139", NOW, evidence.validated_detail(RAW, "2926", "3139"), observed_at=NOW)
    inventory = {"source": "game_hub_select", "observed_at": NOW, "hubs": [{"id": "2926", "code": "XAP"}]}
    market = {"source": "bot_aircraft_market_cache", "fresh": True, "observed_at": NOW,
              "models": [{"id": 11, "name": "A320", "range": 6000, "capacity": 180, "price": 1700000}]}
    samples = expansion.demand_research_snapshot({"2926"}, now=NOW)["samples"]
    page = build_owned_hub_research_queue(inventory, samples, market, now=NOW)
    item = page["items"][0]
    assert item["route_detail"]["origin_runway_ft"] == 6749
    assert item["purchase_eligible"] is False
    assert "pista_a_confirmar" in item["pending"]
    registry = OwnedHubResearchInputsRegistry(tmp_path / "inputs.json")
    assert registry.record_queue(page, now=NOW) == 1
    row = registry.snapshot(now=NOW)[0]
    assert row["route_detail"]["occupied_aircraft"] is None
    assert row["demand_remaining"] is None and row["route_feasible"] is None
    assert "route_detail" not in registry.snapshot(now=NOW + evidence.MAX_AGE + 1)[0]
    details.reserve([SAMPLE], now=NOW + 1)
    assert "route_detail" not in registry.snapshot(now=NOW + 1)[0]


def test_external_details_use_isolated_registry_and_exclude_acquired_hubs(tmp_path, monkeypatch):
    import game_observations as observations

    monkeypatch.setattr(evidence.time, "time", lambda: NOW)
    expansion = HubExpansionRegistry(tmp_path / "hub_expansion.json")
    assert expansion.record_catalog([{"id": "3139", "code": "SBL", "name": "SBL",
                                      "purchasable": True, "hub_price": 1000, "hub_points": 0}])
    external = expansion.external_demand_registry()
    assert external.record_demand("3139", [{"arr_id": "2926", "distance": 1992.763,
                                             "y": 120, "j": 106, "f": 40,
                                             "destination_runway_ft": 6749}], observed_at=NOW) == 1
    inventory = {"source": "game_hub_select", "hub_catalog_fresh": True, "observed_at": NOW,
                 "hubs": [{"id": "2926", "code": "XAP"}]}
    monkeypatch.setattr(observations, "HubRegistry", lambda: SimpleNamespace(snapshot=lambda: inventory))
    monkeypatch.setattr(observations, "HubExpansionRegistry", lambda: expansion)
    monkeypatch.setattr(evidence, "research_details", lambda *_: {
        "codes": ["SBL", "XAP"], "runways": ["5013ft", "6749ft"],
        "occupancy_label": "A/C on route", "occupied": "0"})
    bot = SimpleNamespace(stopping=False, config=SimpleNamespace(get_bool=lambda *_: True))
    assert observations.collect_external_route_details(bot) == 1
    samples = expansion.external_demand_snapshot({"2926"}, now=NOW)["samples"]
    assert samples[0]["route_detail"]["origin_runway_ft"] == 5013
    assert samples[0]["route_detail"]["occupied_aircraft"] is None
    assert not expansion.route_detail_registry().path.exists()
    inventory["hubs"].append({"id": "3139", "code": "SBL"})
    assert observations.collect_external_route_details(bot) == 0
    assert not expansion.external_demand_snapshot({"2926", "3139"}, now=NOW)["samples"]
    inventory["hub_catalog_fresh"] = False
    assert observations.collect_external_route_details(bot) == 0
