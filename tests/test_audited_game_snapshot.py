import json
import time
from types import SimpleNamespace

import paths
from audited_game_snapshot import FILENAME, capture_game_snapshot, compose_snapshot, snapshot_summary
from opportunity_models import fingerprint_snapshot


NOW = 1_900_000_000


def observations():
    return {
        "profile_id": "principal", "now": NOW,
        "inventory": {"source": "game_hub_select", "hub_catalog_fresh": True,
                      "observed_at": NOW - 20, "hubs": [{"id": "11", "code": "TEST"}]},
        "routes": {"current_fleet_coverage_verified": True,
                   "fleet_coverage": {"source": "game_roster_and_route_audit",
                                      "observed_at": NOW - 10, "roster_observed_at": NOW - 30,
                                      "audit_run_id": "test-run", "total": 2, "routes": 1,
                                      "parked": 0, "pending": 1,
                                      "native_identity_status": "matched", "native_observation_id": "test-native"},
                   "current_relations": [{"aircraft_id": "101"}, {"aircraft_id": "102"}],
                   "scan_coverage": {"total_pages": 1, "pages": {"1": {}},
                                     "full_page_coverage_verified": True,
                                     "audit_run": {"id": "test-run", "invalidated": False}}},
        "demand": {"samples": [], "coverage": "partial"},
        "engines": {"order_list_coverage": {"status": "details_observed", "final_prices_verified": False}},
        "market": {}, "quotes": {}, "cash": 1200, "cash_at": NOW - 5,
    }


def test_snapshot_binds_verified_fleet_and_hubs_without_inventing_complete_coverage():
    snapshot = compose_snapshot(**observations())
    assert snapshot["snapshot_id"] == fingerprint_snapshot(snapshot)
    assert snapshot["observed_at"] == NOW - 30
    assert snapshot["coverage"]["observed_aircraft_ids"] == ["101", "102"]
    assert snapshot["coverage"]["expected_aircraft_count"] == 2
    assert snapshot["coverage"]["status"] == "partial"
    assert snapshot["coverage"]["scopes"] == {
        "hubs": True, "fleet": True, "routes": False,
        "models": False, "engines": False, "prices": False,
    }
    assert snapshot["observations"]["cash"]["committed"] is None


def test_missing_native_partition_or_revoked_page_audit_cannot_certify_fleet():
    for field in ("native_identity_status", "native_observation_id"):
        evidence = observations()
        evidence["routes"]["fleet_coverage"].pop(field)
        assert not compose_snapshot(**evidence)["coverage"]["scopes"]["fleet"]
    evidence = observations()
    evidence["routes"]["scan_coverage"]["audit_run"]["invalidated"] = True
    snapshot = compose_snapshot(**evidence)
    assert not snapshot["coverage"]["verified"]
    assert snapshot["coverage"]["observed_aircraft_ids"] == []


def test_cycle_capture_persists_real_cash_and_missing_registry_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("isolated"))
    monkeypatch.setattr(paths.Profile, "data", property(lambda self: tmp_path))
    cash_at = time.time() - 3
    bot = SimpleNamespace(stats=lambda: SimpleNamespace(money=2500, money_read_at=cash_at))
    snapshot = capture_game_snapshot(bot)
    assert json.loads((tmp_path / FILENAME).read_text(encoding="utf-8")) == snapshot
    assert snapshot["profile_id"] == "isolated"
    assert snapshot["verified"] is False
    assert snapshot["observations"]["cash"]["available"] == 2500
    assert snapshot["observations"]["cash"]["observed_at"] == cash_at
    assert not any(snapshot["coverage"]["scopes"].values())
    assert snapshot_summary()["status"] == "parcial"


def test_summary_preserves_source_age_and_is_profile_bound(tmp_path, monkeypatch):
    snapshot = compose_snapshot(**observations())
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    summary = snapshot_summary(now=NOW, path=path)
    assert summary["status"] == "parcial" and summary["fleet_count"] == 2
    assert "observed_aircraft_ids" not in json.dumps(summary)
    summary = snapshot_summary(now=NOW + 875, path=path)
    assert not summary["scopes"]["fleet"] and summary["fleet_count"] is None
    assert summary["scopes"]["hubs"] and summary["cash_observed"]
    assert snapshot_summary(now=NOW + 901, path=path)["status"] == "expirado"
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("other"))
    assert snapshot_summary(now=NOW, path=path)["status"] == "registro_invalido"
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    snapshot["coverage"]["scopes"]["prices"] = True
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert snapshot_summary(now=NOW, path=path)["status"] == "registro_invalido"
