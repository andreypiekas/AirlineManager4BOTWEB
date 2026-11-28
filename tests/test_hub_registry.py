"""Verified hub inventory, conservative aircraft attribution and stale estimates."""
from __future__ import annotations

import json
import time

import paths
from hub_registry import HubRegistry
from route_registry import HOME_HUB_EVIDENCE, RouteRegistry, endpoint


def _game_evidence(aircraft_id: str) -> dict:
    """Simulate explicit DOM evidence bound to exactly one aircraft ID."""
    return {"home_hub_evidence": HOME_HUB_EVIDENCE,
            "home_hub_evidence_aircraft_id": aircraft_id}


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
        {"aircraft_id": "1", "home_hub_id": 123, "home_hub_source": "game",
         "home_hub_verified_at": 100, **_game_evidence("1")},
    ]}, now=200)
    assert len(snapshot["hubs"]) == 1
    assert snapshot["hubs"][0]["id"] == "123"
    assert snapshot["hubs"][0]["name"] == "Chapecó"
    assert snapshot["hubs"][0]["code"] == "XAP"
    assert snapshot["hubs"][0]["aircraft_count"] == 1
    assert snapshot["hubs"][0]["aircraft"][0]["home_hub_verification"] == {
        "status": "confirmed", "reason": "confirmed", "home_hub_id": "123",
        "source": "game", "verified_at": 100, "evidence": HOME_HUB_EVIDENCE,
    }


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
        {"aircraft_id": "1", "home_hub_id": " 123 ", "home_hub_source": "game",
         "home_hub_verified_at": 100, **_game_evidence("1")},
    ]}, now=200)
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

    for profile, identity, registration in ((first, "101", "PP-FIRST"),
                                            (second, "202", "PP-SECOND")):
        route_path = profile.data / "routes_registry.json"
        route_registry = RouteRegistry(route_path)
        route_registry.record(identity, registration, "A320", endpoint("123"), endpoint("456"))
        saved = json.loads(route_path.read_text(encoding="utf-8"))
        saved["aircraft"][identity].update({"home_hub_id": "123", "home_hub_source": "game",
                                             "home_hub_verified_at": 100,
                                             **_game_evidence(identity)})
        route_path.write_text(json.dumps(saved), encoding="utf-8")

    monkeypatch.setattr(paths, "_current", second)
    first_report = first_hubs.snapshot(now=200)
    second_report = second_hubs.snapshot(now=200)
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
    assert snapshot["unconfirmed_aircraft"][0]["home_hub_verification"]["reason"] == "home_hub_not_observed"


def test_aircraft_home_hub_requires_individual_source_and_valid_timestamp(tmp_path):
    registry = HubRegistry(tmp_path / "hubs.json")
    assert registry.record_options([{"id": "123", "text": "Base A"}])
    now = 2_000_000_000
    observations = [
        {"aircraft_id": "1", "home_hub_id": "123", "home_hub_source": "game"},
        {"aircraft_id": "2", "home_hub_id": "123", "home_hub_source": "manual",
         "home_hub_verified_at": now - 30},
        {"aircraft_id": "3", "home_hub_id": "123", "home_hub_source": "game",
         "home_hub_verified_at": False},
        {"aircraft_id": "4", "home_hub_id": "123", "home_hub_source": "game",
         "home_hub_verified_at": now + 1},
        {"aircraft_id": "5", "home_hub_id": "999", "home_hub_source": "game",
         "home_hub_verified_at": now - 30, **_game_evidence("5")},
        {"aircraft_id": "6", "home_hub_id": "123", "home_hub_source": "game",
         "home_hub_verified_at": now - 30, **_game_evidence("6")},
        {"aircraft_id": "7", "home_hub_id": "123", "home_hub_source": "game",
         "home_hub_verified_at": now - 30},
        {"aircraft_id": "8", "home_hub_id": "123", "home_hub_source": "game",
         "home_hub_verified_at": now - 30, **_game_evidence("999")},
    ]
    original = json.loads(json.dumps(observations))
    result = registry.snapshot({"relations": observations}, now=now)
    assert observations == original  # snapshots cannot alter the route registry's rows
    assert [row["aircraft_id"] for row in result["hubs"][0]["aircraft"]] == ["6"]
    assert {row["aircraft_id"]: row["home_hub_verification"]["reason"]
            for row in result["unconfirmed_aircraft"]} == {
        "1": "timestamp_unverified", "2": "source_unverified",
        "3": "timestamp_unverified", "4": "timestamp_unverified",
        "5": "hub_not_in_owned_catalog", "7": "evidence_unverified",
        "8": "evidence_unverified",
    }
    manual = next(row for row in result["unconfirmed_aircraft"] if row["aircraft_id"] == "2")
    assert manual["home_hub_source"] == "manual"
    assert manual["home_hub_verified_at"] == now - 30
    assert manual["home_hub_verification"]["source"] == "manual"
    assert manual["home_hub_verification"]["verified_at"] == now - 30


def test_unproven_candidate_and_explicit_home_hub_proof_persist_across_restarts(tmp_path):
    registry = HubRegistry(tmp_path / "hubs_registry.json")
    routes = RouteRegistry(tmp_path / "routes_registry.json")
    assert registry.record_options([{"id": "123", "text": "Base A"}])
    routes.record_scan(1, 0, 1, route_observations=[
        {"aircraft_id": "101", "registration": "PP-101", "home_hub_id": "123"},
    ])
    saved = json.loads(routes.path.read_text(encoding="utf-8"))
    proof = saved["aircraft"]["101"]
    assert proof["home_hub_id"] == "123"
    assert proof["home_hub_source"] == "game"
    assert proof["home_hub_observed_at"] > 0
    assert "home_hub_verified_at" not in proof
    pending = HubRegistry(registry.path).snapshot()
    assert pending["hubs"][0]["aircraft_count"] == 0
    assert pending["unconfirmed_aircraft"][0]["home_hub_verification"]["status"] == "unknown"

    routes.record_scan(1, 0, 1, route_observations=[
        {"aircraft_id": "101", "registration": "PP-101", "home_hub_id": "123",
         **_game_evidence("101")},
    ])
    proof = json.loads(routes.path.read_text(encoding="utf-8"))["aircraft"]["101"]
    report = HubRegistry(registry.path).snapshot()
    aircraft = report["hubs"][0]["aircraft"][0]
    assert aircraft["aircraft_id"] == "101"
    assert aircraft["home_hub_verification"]["status"] == "confirmed"
    assert aircraft["home_hub_verification"]["verified_at"] == proof["home_hub_verified_at"]
    assert aircraft["home_hub_verification"]["source"] == proof["home_hub_source"]
    assert aircraft["home_hub_verification"]["evidence"] == HOME_HUB_EVIDENCE
    assert not aircraft.get("route_key")


def test_route_origin_and_unverified_candidate_never_prove_home_hub(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs_registry.json")
    routes = RouteRegistry(tmp_path / "routes_registry.json")
    assert hubs.record_options([{"id": "123", "text": "Base A"}])
    routes.record_scan(1, 1, 0, route_observations=[{
        "aircraft_id": "101", "registration": "PP-101",
        "origin": endpoint("123"), "destination": endpoint("456"),
        "at_base": True, "home_hub_id": "123",
    }])
    observed = routes.snapshot()["relations"][0]
    assert observed["home_hub_id"] == "123"
    assert observed["home_hub_observed_at"] > 0
    assert "home_hub_evidence" not in observed
    assert "home_hub_verified_at" not in observed
    report = hubs.snapshot()
    assert report["hubs"][0]["aircraft_count"] == 0
    assert report["unconfirmed_aircraft"][0]["home_hub_verification"]["status"] == "unknown"


def test_conflicting_home_hub_observation_keeps_original_proof_but_blocks_attribution(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs_registry.json")
    routes = RouteRegistry(tmp_path / "routes_registry.json")
    assert hubs.record_options([{"id": "123", "text": "A"}, {"id": "456", "text": "B"}])
    routes.record_scan(1, 0, 1, route_observations=[{
        "aircraft_id": "101", "home_hub_id": "123", **_game_evidence("101"),
    }])
    original = routes.snapshot()["relations"][0]
    routes.record_scan(1, 0, 1, route_observations=[{
        "aircraft_id": "101", "home_hub_id": "456", **_game_evidence("101"),
    }])
    current = RouteRegistry(routes.path).snapshot()["relations"][0]
    assert current["home_hub_id"] == original["home_hub_id"] == "123"
    assert current["home_hub_verified_at"] == original["home_hub_verified_at"]
    assert current["home_hub_conflict_id"] == "456"
    report = HubRegistry(hubs.path).snapshot()
    assert all(hub["aircraft_count"] == 0 for hub in report["hubs"])
    assert report["unconfirmed_aircraft"][0]["home_hub_verification"]["reason"] == (
        "conflicting_game_observations")


def test_evidence_for_another_aircraft_cannot_confirm_a_hub(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs_registry.json")
    routes = RouteRegistry(tmp_path / "routes_registry.json")
    assert hubs.record_options([{"id": "123", "text": "A"}])
    routes.record_scan(1, 0, 1, route_observations=[{
        "aircraft_id": "101", "home_hub_id": "123", **_game_evidence("102"),
    }])
    report = hubs.snapshot()
    assert report["hubs"][0]["aircraft_count"] == 0
    assert report["unconfirmed_aircraft"][0]["home_hub_verification"]["status"] == "unknown"


def test_legacy_source_without_timestamp_remains_unconfirmed(tmp_path):
    registry = HubRegistry(tmp_path / "hubs.json")
    assert registry.record_options([{"id": "123", "text": "Base A"}])
    row = {"aircraft_id": "101", "home_hub_id": "123", "home_hub_source": "game",
           "origin": endpoint("123"), "destination": endpoint("456"), "at_base": True}
    report = registry.snapshot({"relations": [row]})
    assert report["hubs"][0]["aircraft_count"] == 0
    assert report["unconfirmed_aircraft"][0]["home_hub_verification"]["reason"] == "timestamp_unverified"
    assert report["unconfirmed_aircraft"][0]["home_hub_id"] == "123"


def test_only_explicit_game_home_hub_counts_and_route_change_invalidates_profit(tmp_path):
    route_path = tmp_path / "routes.json"
    routes = RouteRegistry(route_path)
    hubs = HubRegistry(tmp_path / "hubs.json")
    hubs.record_options([{"id": "123", "text": "Base A"}])
    routes.record("100", "PP-1", "A320", endpoint("123"), endpoint("987"), profit_per_day=1250)
    state = json.loads(route_path.read_text(encoding="utf-8"))
    proof_at = int(time.time())
    state["aircraft"]["100"].update({"home_hub_id": "123", "home_hub_source": "game",
                                      "home_hub_verified_at": proof_at,
                                      **_game_evidence("100")})
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
    assert hub["aircraft"][0]["home_hub_verification"]["verified_at"] == proof_at
    assert hub["aircraft"][0]["home_hub_verification"]["source"] == "game"


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
                          "home_hub_source": "game", "home_hub_verified_at": now - 100,
                          **_game_evidence(str(index)),
                          "route_key": "id:1 ↔ id:2",
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


def test_hubs_report_preserves_historical_full_audit_without_claiming_current_coverage(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs.json")
    assert hubs.record_options([{"id": "123", "text": "Base A"}])
    historical_audit = {"at": 1_900_000_000, "audit_run_id": "run-123",
                        "expected_routes": 40, "total_pages": 2, "unique_aircraft": 40}
    report = hubs.snapshot({"relations": [],
                            "last_verified_full_audit": historical_audit})
    assert report["last_verified_full_audit"] == historical_audit
    assert report["partial_fleet"] is True
    assert report["known_aircraft"] == 0
    assert hubs.snapshot({"relations": []})["last_verified_full_audit"] is None


def test_hub_coverage_requires_current_fleet_and_every_permanent_assignment(tmp_path):
    hubs = HubRegistry(tmp_path / "hubs.json")
    assert hubs.record_options([{"id": "123", "text": "Base A"}])
    now = int(time.time())
    row = {"aircraft_id": "101", "home_hub_id": "123", "home_hub_source": "game",
           "home_hub_verified_at": now, **_game_evidence("101")}
    routes = {"current_roster_available": True, "current_fleet_coverage_verified": True,
              "fleet_coverage": {"total": 1, "source": "game_roster_and_route_audit"},
              "current_relations": [row],
              "relations": [{"aircraft_id": "999"}]}
    report = hubs.snapshot(routes, now=now)
    assert report["current_fleet_coverage_verified"] is True
    assert report["home_hub_coverage_verified"] is True
    assert report["partial_fleet"] is False
    assert report["known_aircraft"] == 1
    assert report["hubs"][0]["aircraft_count"] == 1
    unproven = hubs.snapshot({**routes, "current_relations": [{"aircraft_id": "101"}]}, now=now)
    assert unproven["current_fleet_coverage_verified"] is True
    assert unproven["partial_fleet"] is True
    assert unproven["home_hub_coverage_verified"] is False
    expired = hubs.snapshot(routes, now=now + 3 * 86400 + 1)
    assert expired["partial_fleet"] is True
    assert expired["hub_catalog_fresh"] is False
    duplicated = hubs.snapshot({**routes, "current_relations": [row, row],
                                "fleet_coverage": {**routes["fleet_coverage"], "total": 2}}, now=now)
    assert duplicated["current_fleet_coverage_verified"] is False
    assert duplicated["partial_fleet"] is True


def test_hubs_web_workspace_is_read_only():
    from conftest import ROOT

    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'id="hubsView" hidden' in page
    assert 'href="#hubs"' in page
    assert 'api("/api/hubs")' in page
    assert 'url.path == "/api/hubs"' in web
    assert 'elif path == "/api/hubs"' not in web
