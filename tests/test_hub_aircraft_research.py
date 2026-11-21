"""Profile storage and dashboard integration for next-aircraft scenarios."""
from __future__ import annotations

import json
from types import SimpleNamespace

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


def test_recommendations_endpoint_is_authenticated_read_only():
    from conftest import ROOT

    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    source = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'api("/api/hubs/recommendations")' in html
    assert 'url.path == "/api/hubs/recommendations"' in source
    assert 'elif path == "/api/hubs/recommendations"' not in source
    assert 'id="hubRecommendationsGrid"' in html
