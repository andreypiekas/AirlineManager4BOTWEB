"""Profile storage and dashboard integration for next-aircraft scenarios."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import web
from hub_aircraft_research import HubAircraftResearchRegistry
from hub_recommendations import rank_next_aircraft


def _scenario(hub="123", destination="456"):
    return {
        "hub_id": hub, "model": "A320", "source": "game_research",
        "observed_at": 1_800_000_000,
        "origin": {"id": hub, "code": "XAP"},
        "destination": {"id": destination, "code": "GRU"},
        "distance_km": 1000, "range_km": 3000,
        "runway_m": 2700, "required_runway_m": 2000,
        "demand_verified": True, "demand_remaining": 300,
        "range_verified": True, "runway_verified": True,
        "route_available": True, "route_feasible": True,
        "financial": {"source": "route_optimizer", "observed_at": 1_800_000_000,
                      "profit_per_day": 2500},
        "costs": {"source": "game_market", "observed_at": 1_800_000_000,
                  "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0},
    }


def test_research_registry_is_isolated_and_idempotent(tmp_path):
    first = HubAircraftResearchRegistry(tmp_path / "company-a.json")
    second = HubAircraftResearchRegistry(tmp_path / "company-b.json")
    scenario = _scenario()
    assert not first.record({**scenario, "source": "manual"})
    assert not first.record({**scenario, "hub_id": "0"})
    assert first.record(scenario)
    assert first.record({**scenario, "origin": scenario["destination"],
                         "destination": scenario["origin"], "observed_at": 1_800_000_001})
    assert len(first.snapshot()) == 1
    assert first.snapshot()[0]["observed_at"] == 1_800_000_001
    assert second.snapshot() == []
    detached = first.snapshot()
    detached[0]["costs"]["aircraft_price"] = 0
    assert first.snapshot()[0]["costs"]["aircraft_price"] == 10000


def test_legacy_migration_keeps_unidentified_engine_alongside_explicit_variants(tmp_path):
    registry = HubAircraftResearchRegistry(tmp_path / "old-profile.json")
    legacy = _scenario()
    legacy["observed_at"] = 1_700_000_000
    legacy["financial"]["observed_at"] = 1_700_000_001
    legacy["costs"]["observed_at"] = 1_700_000_002
    registry.path.write_text(json.dumps({"scenarios": [legacy]}), encoding="utf-8")

    for engine_id in ("1", "2"):
        observation = _scenario()
        observation["engine_id"] = engine_id
        observation["observed_at"] = 1_800_000_000 + int(engine_id)
        observation["financial"]["observed_at"] += int(engine_id)
        observation["costs"]["observed_at"] += int(engine_id)
        assert registry.record(observation)

    rows = registry.snapshot()
    assert len(rows) == 3
    assert rows[0] == legacy
    assert "engine_id" not in rows[0]
    assert {row["engine_id"] for row in rows[1:]} == {"1", "2"}
    assert [row["observed_at"] for row in rows] == [1_700_000_000, 1_800_000_001, 1_800_000_002]
    assert {row["engine_id"]: row["financial"]["observed_at"] for row in rows[1:]} == {
        "1": 1_800_000_001, "2": 1_800_000_002}
    assert {row["engine_id"]: row["costs"]["observed_at"] for row in rows[1:]} == {
        "1": 1_800_000_001, "2": 1_800_000_002}

    newer_legacy = deepcopy(legacy)
    newer_legacy["observed_at"] += 10
    assert registry.record(newer_legacy)
    rows = registry.snapshot()
    assert len(rows) == 3
    assert [row for row in rows if "engine_id" not in row] == [newer_legacy]
    assert {row["engine_id"] for row in rows if "engine_id" in row} == {"1", "2"}


def test_engine_variants_deduplicate_by_id_with_reverse_routes(tmp_path):
    registry = HubAircraftResearchRegistry(tmp_path / "research.json")
    first = {**_scenario(), "engine_id": 1, "engine_name": "CFM56"}
    second = {**_scenario(), "engine_id": "2", "engine_name": "IAE V2500"}
    second["financial"] = {"source": "route_optimizer", "observed_at": 1_800_000_004,
                           "profit_per_day": 4000}
    assert registry.record(first)
    assert registry.record(second)

    refreshed = deepcopy(first)
    refreshed["engine_id"] = "1"
    refreshed["model"] = "a320"
    refreshed["origin"], refreshed["destination"] = first["destination"], first["origin"]
    refreshed["observed_at"] += 15
    refreshed["costs"]["observed_at"] += 15
    assert registry.record(refreshed)
    rows = registry.snapshot()
    assert len(rows) == 2
    assert {row["engine_id"] for row in rows} == {"1", "2"}
    assert next(row for row in rows if row["engine_id"] == "1") == refreshed
    assert next(row for row in rows if row["engine_id"] == "2") == second

    before = registry.path.read_bytes()
    assert registry.record(refreshed)
    assert registry.path.read_bytes() == before
    assert len(registry.snapshot()) == 2


@pytest.mark.parametrize("engine_id", [None, "", "   ", True, False, 1.5, -1,
                                      [], {}, "CFM 56", "motor/1", "é", "x" * 65])
def test_invalid_explicit_engine_id_is_rejected_without_mutating_storage(tmp_path, engine_id):
    registry = HubAircraftResearchRegistry(tmp_path / "research.json")
    assert registry.record(_scenario())
    before = registry.path.read_bytes()
    assert not registry.record({**_scenario(), "engine_id": engine_id})
    assert registry.path.read_bytes() == before


def test_engine_identifiers_are_explicit_and_preserve_distinct_values(tmp_path):
    registry = HubAircraftResearchRegistry(tmp_path / "research.json")
    for engine_id in ("0", "01", 1, "CFM56-5B", "cfm56-5b"):
        assert registry.record({**_scenario(), "engine_id": engine_id})
    assert {row["engine_id"] for row in registry.snapshot()} == {
        "0", "01", "1", "CFM56-5B", "cfm56-5b"}
    assert len(registry.snapshot()) == 5


def test_engine_variants_remain_isolated_across_profiles_hubs_models_and_routes(tmp_path):
    first = HubAircraftResearchRegistry(tmp_path / "first-profile.json")
    second = HubAircraftResearchRegistry(tmp_path / "second-profile.json")
    assert first.record({**_scenario(), "engine_id": "1"})
    assert first.record({**_scenario(), "engine_id": "2"})
    assert first.record({**_scenario(hub="789"), "engine_id": "1"})
    assert first.record({**_scenario(destination="789"), "engine_id": "1"})
    assert first.record({**_scenario(), "model": "B737", "engine_id": "1"})
    assert second.record({**_scenario(), "engine_id": "1", "observed_at": 1_700_000_000})

    assert len(first.snapshot()) == 5
    assert len(second.snapshot()) == 1
    assert second.snapshot()[0]["observed_at"] == 1_700_000_000
    assert first.record({**_scenario(), "engine_id": "2", "observed_at": 1_800_000_009})
    assert len(first.snapshot()) == 5
    assert second.snapshot()[0]["observed_at"] == 1_700_000_000


def test_corrupt_storage_and_missing_evidence_remain_pending(tmp_path):
    storage = HubAircraftResearchRegistry(tmp_path / "research.json")
    storage.path.write_text("{broken", encoding="utf-8")
    assert storage.snapshot() == []
    scenario = _scenario()
    scenario["costs"].pop("observed_at")
    assert storage.record(scenario)
    report = rank_next_aircraft(
        {"source": "game_hub_select", "observed_at": 1_800_000_000,
         "hubs": [{"id": "123", "code": "XAP"}]}, storage.snapshot(),
        route_report={"relations": []}, cash=20000,
        cash_observed_at=1_800_000_000, now=1_800_000_000)
    assert report["recommendations"] == []
    assert "custos_a_confirmar" in report["candidates"][0]["pending"]
    saved = json.loads(storage.path.read_text(encoding="utf-8"))
    assert "observed_at" not in saved["scenarios"][0]["costs"]


def test_dashboard_ranks_saved_scenarios_and_never_calls_game(monkeypatch):
    scenario = _scenario()
    monkeypatch.setattr(web, "RouteRegistry", lambda: SimpleNamespace(snapshot=lambda **_kw: {"relations": []}))
    monkeypatch.setattr(web, "HubRegistry", lambda: SimpleNamespace(snapshot=lambda _routes: {
        "source": "game_hub_select", "observed_at": 1_800_000_000,
        "hubs": [{"id": "123", "code": "XAP", "name": "Chapecó"}]}))
    monkeypatch.setattr(web, "HubAircraftResearchRegistry",
                        lambda: SimpleNamespace(snapshot=lambda: [scenario]))
    monkeypatch.setattr(web, "recent_verified_money", lambda *_args: (20000, 1_800_000_000))
    monkeypatch.setattr(web, "load_state", lambda: {})
    monkeypatch.setattr(web, "rank_next_aircraft", lambda *args, **kwargs: {
        "hubs": args[0]["hubs"], "scenarios": args[1], "routes": kwargs["route_report"],
        "cash": kwargs["cash"], "reserve": kwargs["reserve"]})
    dashboard = web.WebDashboard.__new__(web.WebDashboard)
    dashboard.bot = object()
    dashboard.cfg = SimpleNamespace(
        get_bool=lambda *_args: False,
        get_int=lambda _section, _key, _fallback=0: 2000,
    )
    result = dashboard.hub_recommendations()
    assert result["hubs"][0]["code"] == "XAP"
    assert result["scenarios"] == [scenario]
    assert result["routes"] == {"relations": []}
    assert result["cash"] == 20000
    assert result["reserve"] == 2000
    assert result["portfolio"]["status"] == "inconclusivo"
    assert result["portfolio"]["execution_available"] is False
    assert result["investment_policy"]["release_gate"] == "G0"


def test_recommendations_endpoint_is_authenticated_read_only():
    from conftest import ROOT

    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    source = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'api("/api/hubs/recommendations")' in html
    assert 'url.path == "/api/hubs/recommendations"' in source
    assert 'elif path == "/api/hubs/recommendations"' not in source
    assert 'id="hubRecommendationsGrid"' in html
