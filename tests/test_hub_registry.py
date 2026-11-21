"""Verified hub inventory, conservative aircraft attribution and stale estimates."""
from __future__ import annotations

import json

import paths
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


def test_hub_ids_are_canonical_and_blank_selector_text_uses_title(tmp_path):
    registry = HubRegistry(tmp_path / "hubs.json")
    assert registry.record_options([
        {"id": "000123", "text": "  ", "title": "  Chapecó ", "code": " xap "},
        {"id": "123", "text": " ", "title": "Chapecó", "code": "XAP"},
    ])
    snapshot = registry.snapshot({"relations": [
        {"aircraft_id": "1", "home_hub_id": 123, "home_hub_source": "game"},
    ]})
    assert len(snapshot["hubs"]) == 1
    assert snapshot["hubs"][0]["id"] == "123"
    assert snapshot["hubs"][0]["name"] == "Chapecó"
    assert snapshot["hubs"][0]["code"] == "XAP"
    assert snapshot["hubs"][0]["aircraft_count"] == 1


def test_malformed_or_conflicting_selector_cannot_erase_verified_hubs(tmp_path):
    registry = HubRegistry(tmp_path / "hubs.json")
    assert registry.record_options([{"id": "123", "text": "Chapecó"},
                                    {"id": "456", "text": "Guarulhos"}])
    previous = registry.path.read_bytes()

    assert not registry.record_options([{"id": "789", "text": "Nova base"},
                                        {"id": "invalid", "text": "Erro"}])
    assert not registry.record_options([{"id": "789", "text": "Nova base"}, None])
    assert not registry.record_options([{"id": "789", "text": "Nova base"},
                                        {"id": "000789", "text": "Outra base"}])
    assert not registry.record_options([{"id": "789", "text": "Nova base"},
                                        {"id": False, "text": "Inválido"}])
    assert not registry.record_options([{"id": "789", "text": "Nova base"},
                                        {"id": [], "text": "Inválido"}])
    assert registry.path.read_bytes() == previous
    assert {hub["id"] for hub in registry.snapshot({"relations": []})["hubs"]} == {"123", "456"}


def test_legacy_hub_ids_are_read_without_rewriting_saved_data(tmp_path):
    filename = tmp_path / "hubs.json"
    legacy = {"source": "game_hub_select", "observed_at": 123456,
              "hubs": [{"id": "000123", "code": "XAP", "name": "Chapecó"}]}
    filename.write_text(json.dumps(legacy), encoding="utf-8")
    registry = HubRegistry(filename)
    report = registry.snapshot({"relations": [
        {"aircraft_id": "1", "home_hub_id": " 123 ", "home_hub_source": "game"},
    ]})
    assert report["hubs"][0]["id"] == "123"
    assert report["hubs"][0]["aircraft_count"] == 1
    assert json.loads(filename.read_text(encoding="utf-8")) == legacy


def test_snapshot_reads_routes_from_the_same_profile_as_its_hubs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = paths.Profile("first")
    second = paths.Profile("second")
    first_hubs = HubRegistry(first.data / "hubs_registry.json")
    second_hubs = HubRegistry(second.data / "hubs_registry.json")
    assert first_hubs.record_options([{"id": "123", "text": "A"}])
    assert second_hubs.record_options([{"id": "123", "text": "B"}])

    for profile, registration in ((first, "PP-FIRST"), (second, "PP-SECOND")):
        route_path = profile.data / "routes_registry.json"
        route_registry = RouteRegistry(route_path)
        route_registry.record(registration, registration, "A320", endpoint("123"), endpoint("456"))
        saved = json.loads(route_path.read_text(encoding="utf-8"))
        saved["aircraft"][registration].update({"home_hub_id": "123", "home_hub_source": "game"})
        route_path.write_text(json.dumps(saved), encoding="utf-8")

    monkeypatch.setattr(paths, "_current", second)
    first_report = first_hubs.snapshot()
    second_report = second_hubs.snapshot()
    assert [row["registration"] for row in first_report["hubs"][0]["aircraft"]] == ["PP-FIRST"]
    assert [row["registration"] for row in second_report["hubs"][0]["aircraft"]] == ["PP-SECOND"]


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


def test_undated_expired_and_invalid_route_profits_are_excluded(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs.json")
    hubs.record_options([{"id": "123", "text": "Base A"}])
    now = 2_000_000_000
    relations = []
    for index, value, stamp in (
        (1, 1000, now - 60),
        (2, 2000, now - 4 * 86400),
        (3, 3000, None),
        (4, float("inf"), now),
        (5, 5000, now + 60),
    ):
        relations.append({"aircraft_id": str(index), "home_hub_id": "123",
                          "home_hub_source": "game", "route_key": "id:1 ↔ id:2",
                          "profit_route_key": "id:1 ↔ id:2",
                          "profit_per_day": value, "profit_estimated_at": stamp})
    report = hubs.snapshot({"relations": relations}, now=now)
    hub = report["hubs"][0]
    assert hub["aircraft_count"] == 5
    assert hub["estimated_routes"] == 1
    assert hub["estimates_pending"] == 4
    assert hub["estimated_profit_per_day"] == 1000


def test_fleet_scan_is_reported_as_partial_evidence(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs.json")
    hubs.record_options([{"id": "123", "text": "Base A"}])
    scan = {"at": 1234567, "visible": 20, "identified": 17, "missing_airports": 3}
    report = hubs.snapshot({"relations": [{"aircraft_id": "1"}], "last_scan": scan})
    assert report["partial_fleet"] is True
    assert report["known_aircraft"] == 1
    assert report["last_fleet_scan"] == scan
    assert len(report["unconfirmed_aircraft"]) == 1


def test_hubs_web_workspace_is_read_only():
    from conftest import ROOT

    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'id="hubsView" hidden' in page
    assert 'href="#hubs"' in page
    assert 'api("/api/hubs")' in page
    assert 'url.path == "/api/hubs"' in web
    assert 'elif path == "/api/hubs"' not in web
