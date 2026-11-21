"""Verified hub inventory, conservative aircraft attribution and stale estimates."""
from __future__ import annotations

import json

from hub_registry import HubRegistry
from route_registry import RouteRegistry, endpoint


def test_hub_selector_keeps_empty_hubs_and_rejects_placeholder(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs.json")
    assert hubs.record_options([
        {"id": "", "text": "Choose hub"},
        {"id": "0", "text": "Choose hub"},
        {"id": "123", "text": "Chapecó", "code": "XAP"},
        {"id": "456", "text": "Guarulhos", "code": "GRU"},
    ])
    report = hubs.snapshot({"relations": []})
    assert {item["id"] for item in report["hubs"]} == {"123", "456"}
    assert all(item["aircraft_count"] == 0 for item in report["hubs"])
    assert report["source"] == "game_hub_select"
    assert report["observed_at"]
    assert not hubs.record_options([])
    assert not hubs.record_options([{"id": "0"}])
    assert len(hubs.snapshot({"relations": []})["hubs"]) == 2


def test_route_endpoints_do_not_assign_an_aircraft_to_a_hub(tmp_path):
    routes = RouteRegistry(tmp_path / "routes.json")
    hubs = HubRegistry(tmp_path / "hubs.json")
    hubs.record_options([{"id": "123", "text": "Base A", "code": "XAP"}])
    routes.record("100", "PP-1", "A320", endpoint("123"), endpoint("987"),
                  source="game", at_base=True, profit_per_day=1250)
    snapshot = hubs.snapshot(routes.snapshot())
    assert snapshot["hubs"][0]["aircraft_count"] == 0
    assert snapshot["hubs"][0]["estimated_profit_per_day"] is None
    assert len(snapshot["unconfirmed_aircraft"]) == 1


def test_only_explicit_game_home_hub_counts_and_route_change_invalidates_profit(tmp_path):
    route_path = tmp_path / "routes.json"
    routes = RouteRegistry(route_path)
    hubs = HubRegistry(tmp_path / "hubs.json")
    hubs.record_options([{"id": "123", "text": "Base A"}])
    routes.record("100", "PP-1", "A320", endpoint("123"), endpoint("987"), profit_per_day=1250)
    state = json.loads(route_path.read_text(encoding="utf-8"))
    state["aircraft"]["100"].update({"home_hub_id": "123", "home_hub_source": "game"})
    route_path.write_text(json.dumps(state), encoding="utf-8")
    hub = hubs.snapshot(routes.snapshot())["hubs"][0]
    assert hub["aircraft_count"] == 1
    assert hub["estimated_profit_per_day"] == 1250
    assert hub["estimated_routes"] == 1
    routes.record("100", "PP-1", "A320", endpoint("123"), endpoint("456"))
    hub = hubs.snapshot(routes.snapshot())["hubs"][0]
    assert hub["aircraft_count"] == 1
    assert hub["estimated_profit_per_day"] is None
    assert hub["estimated_routes"] == 0


def test_hubs_web_workspace_is_read_only():
    from conftest import ROOT

    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'id="hubsView" hidden' in page
    assert 'href="#hubs"' in page
    assert 'api("/api/hubs")' in page
    assert 'url.path == "/api/hubs"' in web
    assert 'elif path == "/api/hubs"' not in web
