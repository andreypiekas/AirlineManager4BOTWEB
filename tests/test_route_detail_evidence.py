from types import SimpleNamespace

import pytest

import route_detail_evidence as evidence
from hub_expansion import HubExpansionRegistry
from owned_hub_research_feed import build_owned_hub_research_queue
from owned_hub_research_ingestion import OwnedHubResearchInputsRegistry


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
