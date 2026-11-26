"""Game roster identity and flight-history enrichment are independently verified."""
import json
import shutil
import subprocess

import pytest

import route_registry
from fleet import _FLIGHT_HISTORY_JS, _GAME_ROSTER_JS
from route_registry import RouteRegistry, endpoint


def game_rows():
    return [
        {"aircraft_id": "101", "registration": "PP-101", "route_id": 801},
        {"aircraft_id": "102", "registration": "PP-102", "route_id": 802},
        {"aircraft_id": "103", "registration": "PP-103", "route_id": 0},
    ]


def observe_route(registry):
    return registry.record_scan(visible=1, identified=0, missing_airports=0,
                                route_observations=[{
                                    "aircraft_id": "101", "registration": "PP-101",
                                    "model": "A320", "observed_route_id": 801,
                                    "origin": endpoint(code="XAP"),
                                    "destination": endpoint(code="GRU"),
                                }])


def _audit_roster_routes(registry, run_id="a" * 32, *, native_next=None):
    rows = [{**row, "model": "A320", "observed_route_id": row["route_id"],
             "origin": endpoint(code="XAP"), "destination": endpoint(code="GRU"),
             "scan_has_next": native_next}
            for row in game_rows() if row["route_id"]]
    registry.record_scan(2, 2, 0, aircraft_ids=["101", "102"], page=1,
                         total_pages=1 if native_next is None else None,
                         expected_routes=2, audit_run_id=run_id,
                         route_observations=rows)


def test_correlated_fleet_requires_fresh_matching_roster_and_routes(tmp_path, monkeypatch):
    clock = [1900000000]
    monkeypatch.setattr(route_registry.time, "time", lambda: clock[0])
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])
    assert registry.snapshot()["current_fleet_coverage_verified"]
    registry.note("101", "troca_automatica_desativada")
    assert registry.snapshot()["current_fleet_coverage_verified"]
    clock[0] += 901
    assert not registry.snapshot()["current_fleet_coverage_verified"]


@pytest.mark.parametrize("native_ids,expected", [(frozenset({"103"}), "matched"),
                                                 (frozenset({"101"}), "different"),
                                                 (frozenset({"999"}), "different")])
def test_native_identity_proof_is_bound_to_audit_and_observation(tmp_path, monkeypatch, native_ids, expected):
    from fleet_commitment_observations import SOURCE, reconcile_route_coverage
    from portfolio_planner import compare_portfolio

    clock = [1900000000]
    monkeypatch.setattr(route_registry.time, "time", lambda: clock[0])
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 0, "pending": 1}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    clock[0] += 5
    evidence = {"observation_id": "b" * 32, "observed_at": clock[0] - 2, "observed_until": clock[0] - 1,
                "pending_ids": native_ids, "parked_ids": frozenset()}
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts, after_counts=counts,
                                           audited_pages=[1], native_identity_evidence=evidence)
    coverage = registry.snapshot()["fleet_coverage"]
    assert coverage["native_identity_status"] == expected
    assert "pending_ids" not in coverage and "parked_ids" not in coverage
    observation = {"source": SOURCE, "status": "observed", "observation_id": evidence["observation_id"],
                   "observed_at": evidence["observed_at"], "observed_until": evidence["observed_until"],
                   "parked_count": 0, "pending_fleet": {"total": 1, "maintenance": 1, "delivery": 0, "unclassified": 0}}
    result = reconcile_route_coverage(observation, coverage, now=clock[0])
    assert result["status"] == "matched" and result["identity_status"] == expected
    blockers = compare_portfolio({"fleet_route_reconciliation": result})["blocking_reasons"]
    assert ("identidades_frota_divergentes" in blockers) == (expected == "different")
    assert "pedidos_pendentes_a_conciliar" in blockers
    observation["observation_id"] = "c" * 32
    assert reconcile_route_coverage(observation, coverage, now=clock[0])["identity_status"] == "unverified"


def test_correlated_fleet_cannot_reuse_audit_from_same_second(tmp_path, monkeypatch):
    monkeypatch.setattr(route_registry.time, "time", lambda: 1900000000)
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.record_game_roster(game_rows(), 3)
    assert not registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                               after_counts=counts, audited_pages=[1])
    _audit_roster_routes(registry, "b" * 32)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])
    changed = game_rows()
    changed[0]["route_id"] = 999
    assert not registry.confirm_fleet_coverage(changed, before_counts=counts,
                                               after_counts=counts, audited_pages=[1])
    assert not registry.snapshot()["current_fleet_coverage_verified"]
    assert not registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                               after_counts={**counts, "parked": 0, "pending": 1},
                                               audited_pages=[1])


@pytest.mark.parametrize("native_next", [None, False])
def test_certified_coverage_survives_compatible_reads_but_not_mutation(tmp_path, native_next):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    registry.record("999", "PP-999", "A320", endpoint(code="DAC"), endpoint(code="OSL"))
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])
    proof = registry.snapshot()["fleet_coverage"]
    assert registry.unassign("103", "PP-103", "A320")
    historical = next(row for row in registry.snapshot()["relations"] if row["aircraft_id"] == "999")
    assert registry.retire_missing_assignment("999", expected_route=historical["route_key"])
    _audit_roster_routes(registry, None, native_next=native_next)
    assert registry.snapshot()["fleet_coverage"] == proof
    registry.record("101", "PP-101", "A320", endpoint(code="XAP"), endpoint(code="GRU"),
                    observed_route_id=801)
    assert registry.snapshot()["fleet_coverage"] == proof
    registry.invalidate_fleet_coverage()
    assert not registry.snapshot()["current_fleet_coverage_verified"]
    assert not registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                               after_counts=counts, audited_pages=[1])


def test_native_pager_next_revokes_coverage_for_a_previously_terminal_page(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])

    _audit_roster_routes(registry, None, native_next=True)

    assert not registry.snapshot()["current_fleet_coverage_verified"]


def test_certified_coverage_revoked_when_a_parked_read_contradicts_roster(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])
    registry.unassign("101", "PP-101", "A320")
    assert not registry.snapshot()["current_fleet_coverage_verified"]


def test_certified_coverage_revoked_when_detail_route_id_changes(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 2, "parked": 1, "pending": 0}
    assert registry.record_game_roster(game_rows(), 3)
    _audit_roster_routes(registry)
    assert registry.confirm_fleet_coverage(game_rows(), before_counts=counts,
                                           after_counts=counts, audited_pages=[1])
    registry.record("101", "PP-101", "A320", endpoint(code="XAP"), endpoint(code="GRU"),
                    observed_route_id=901)
    assert not registry.snapshot()["current_fleet_coverage_verified"]
    assert next(row for row in registry.snapshot()["current_relations"]
                if row["aircraft_id"] == "101")["route_data_stale"] is True


def test_zero_routes_cannot_be_certified_after_contradictory_scan(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 0, "parked": 1, "pending": 0}
    rows = [game_rows()[-1]]
    assert registry.record_game_roster(rows, 1)
    observe_route(registry)
    assert not registry.confirm_fleet_coverage(rows, before_counts=counts,
                                               after_counts=counts, audited_pages=[])


@pytest.mark.parametrize("rows", [[], [game_rows()[-1]]])
def test_correlated_fleet_without_routes(tmp_path, rows):
    registry = RouteRegistry(tmp_path / "routes.json")
    counts = {"routes": 0, "parked": len(rows), "pending": 0}
    assert registry.record_game_roster(rows, len(rows))
    assert registry.confirm_fleet_coverage(rows, before_counts=counts,
                                           after_counts=counts, audited_pages=[])
    assert registry.snapshot()["fleet_coverage"]["total"] == len(rows)
    registry.invalidate_fleet_coverage()
    assert not registry.snapshot()["current_fleet_coverage_verified"]


def test_current_screen_uses_only_exact_roster_and_keeps_history(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.record("999", "PP-999", "A320", endpoint(code="DAC"), endpoint(code="OSL"))
    assert registry.record_game_roster(game_rows(), 3)
    observe_route(registry)

    report = registry.snapshot()
    assert report["total"] == 2
    assert report["current_roster_total"] == 3
    assert report["current_roster_available"] is True
    assert report["current_roster_verified"] is True
    aircraft = {row["aircraft_id"]: row for row in report["current_relations"]}
    assert set(aircraft) == {"101", "102", "103"}
    assert aircraft["101"]["origin"]["code"] == "XAP"
    assert aircraft["101"]["destination"]["code"] == "GRU"
    assert aircraft["102"]["route_data_stale"] is True
    assert "origin" not in aircraft["102"]
    assert "destination" not in aircraft["103"]
    assert {row["aircraft_id"] for row in report["relations"]} == {"101", "999"}


def test_rejects_incomplete_duplicate_and_invalid_roster_without_overwriting(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    original = registry.path.read_bytes()
    assert not registry.record_game_roster(game_rows(), 218)
    assert not registry.record_game_roster(game_rows() + [game_rows()[0]], 4)
    assert not registry.record_game_roster([{"aircraft_id": "nope"}], 1)
    assert registry.path.read_bytes() == original


def test_route_reassignment_invalidates_old_endpoints_and_profit(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    observe_route(registry)
    registry.record("101", "PP-101", "A320", endpoint(code="XAP"),
                    endpoint(code="GRU"), profit_per_day=15000)
    assert registry.snapshot()["current_relations"][0]["origin"]["code"] == "XAP"

    changed = game_rows()
    changed[0]["route_id"] = 999
    assert registry.record_game_roster(changed, 3)
    current = {row["aircraft_id"]: row for row in registry.snapshot()["current_relations"]}
    assert current["101"]["route_data_stale"] is True
    assert "origin" not in current["101"]
    assert "destination" not in current["101"]
    assert "profit_per_day" not in current["101"]
    assert registry.snapshot()["relations"][0]["origin"]["code"] == "XAP"


def test_expired_roster_remains_visible_but_marked_unverified(tmp_path, monkeypatch):
    clock = [1900000000]
    monkeypatch.setattr(route_registry.time, "time", lambda: clock[0])
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    clock[0] += 901
    report = registry.snapshot()
    assert report["current_roster_available"] is True
    assert report["current_roster_verified"] is False
    assert len(report["current_relations"]) == 3
    assert all(row["route_data_stale"] for row in report["current_relations"])


def test_last_flight_value_and_margin_are_distinct_from_daily_profit(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    observe_route(registry)
    assert registry.next_flight_read_ids() == ["101", "102"]
    assert registry.record_flight_readings([{
        "aircraft_id": "101", "flight_route": "XAP-GRU", "flight_value": 2000,
        "fuel_lbs": 1000, "co2_quotas": 100,
        "recent_flights": [
            {"flight_route": "XAP-GRU", "flight_value": 2000, "fuel_lbs": 1000, "co2_quotas": 100, "age_hours": 1},
            {"flight_route": "GRU-XAP", "flight_value": 3000, "fuel_lbs": 2000, "co2_quotas": 100, "age_hours": 22},
            {"flight_route": "TAS-GRU", "flight_value": 9999, "fuel_lbs": 1000, "co2_quotas": 100, "age_hours": 2},
        ],
    }], fuel_price=800, co2_price=120) == 1
    snapshot = registry.snapshot()
    row = next(row for row in snapshot["current_relations"] if row["aircraft_id"] == "101")
    assert row["last_flight"]["value"] == 2000
    assert row["last_flight"]["game_route_id"] == 801
    assert row["last_flight"]["estimated_operating_margin"] == 1188
    assert row["last_flight"]["route"] == "XAP-GRU"
    assert row["last_flight"]["route_correlation"] == "observed_endpoints"
    assert row["last_24h"]["flight_count"] == 2
    assert row["last_24h"]["estimated_operating_margin"] == 2576
    assert row["last_24h"]["observed_revenue"] == 5000
    assert row["last_24h"]["fuel_lbs"] == 3000
    assert row["last_24h"]["co2_quotas"] == 200
    assert row["last_24h"]["coverage_complete"] is False
    assert "profit_per_day" not in row
    assert registry.next_flight_read_ids()[0] == "102"
    assert json.loads(registry.path.read_text(encoding="utf-8"))["aircraft"]["101"]["last_flight"]["source"] == "game_flight_history"


def test_reassigned_route_does_not_show_previous_flight_margin(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    observe_route(registry)
    assert registry.record_flight_readings([{
        "aircraft_id": "101", "flight_route": "XAP-GRU", "flight_value": 3000,
        "fuel_lbs": 1000, "co2_quotas": 100,
    }], fuel_price=800, co2_price=120) == 1
    rerouted = game_rows()
    rerouted[0]["route_id"] = 900
    assert registry.record_game_roster(rerouted, 3)
    aircraft = {row["aircraft_id"]: row for row in registry.snapshot()["current_relations"]}
    assert "last_flight" not in aircraft["101"]
    assert "last_flight" in registry.snapshot()["relations"][0]


def test_flight_history_requires_current_route_and_revokes_mismatched_sample(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    sample = {"aircraft_id": "101", "flight_route": "XAP-GRU", "flight_value": 3000,
              "fuel_lbs": 1000, "co2_quotas": 100}
    sample["recent_flights"] = [{**sample, "age_hours": 1}]
    assert registry.record_flight_readings([sample], fuel_price=800, co2_price=120) == 0
    observe_route(registry)
    assert registry.record_flight_readings([sample], fuel_price=800, co2_price=120) == 1
    assert registry.record_flight_readings([{**sample, "flight_route": "TAS-GRU"}],
                                           fuel_price=800, co2_price=120) == 0
    row = next(row for row in registry.snapshot()["current_relations"] if row["aircraft_id"] == "101")
    assert "last_flight" not in row
    assert "last_24h" not in row


def test_legacy_uncorrelated_finance_is_not_current_route_evidence(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record_game_roster(game_rows(), 3)
    observe_route(registry)
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["aircraft"]["101"]["last_24h"] = {
        "game_route_id": 801, "source": "game_flight_history", "estimated_operating_margin": 1000}
    registry.path.write_text(json.dumps(data), encoding="utf-8")
    row = next(row for row in registry.snapshot()["current_relations"] if row["aircraft_id"] == "101")
    assert "last_24h" not in row


def test_duplicate_panel_uses_verified_current_fleet_only(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    roster = game_rows()
    roster[1]["route_id"] = 900
    assert registry.record_game_roster(roster, 3)
    for aircraft_id, reg, route_id in (("101", "PP-101", 801), ("102", "PP-102", 900)):
        registry.record_scan(visible=1, identified=0, missing_airports=0,
                             route_observations=[{
                                 "aircraft_id": aircraft_id, "registration": reg,
                                 "observed_route_id": route_id,
                                 "origin": endpoint(code="XAP"),
                                 "destination": endpoint(code="GRU"),
                             }])
    registry.record("999", "PP-999", "A320", endpoint(code="XAP"), endpoint(code="GRU"))
    report = registry.snapshot()
    assert report["current_duplicate_routes"] == 1
    assert len(report["current_duplicates"][0]["aircraft"]) == 2
    assert {a["id"] for a in report["current_duplicates"][0]["aircraft"]} == {"101", "102"}
    assert report["affected_aircraft"] == 3


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js indisponível")
def test_statusdata_roster_js_reads_route_ids_and_registration():
    script = """
globalThis.window = {statusData: {
  '101': {reg: 'PP-101', routeId: 801},
  '102': {reg: 'PP-102', routeId: 0},
  '103': {reg: 'PP-103', routeId: null},
  '104': {reg: 'PP-104'},
  '105': {reg: 'PP-105', routeId: ''},
  '106': {reg: 'PP-106', routeId: false}
}};
console.log(JSON.stringify(new Function(process.argv[1])()));
"""
    result = subprocess.run(["node", "-e", script, _GAME_ROSTER_JS],
                            capture_output=True, text=True, check=True, timeout=8)
    rows = json.loads(result.stdout)
    assert rows == [
        {"aircraft_id": "101", "registration": "PP-101", "route_id": 801},
        {"aircraft_id": "102", "registration": "PP-102", "route_id": 0},
        {"aircraft_id": "103", "registration": "PP-103", "route_id": None},
        {"aircraft_id": "104", "registration": "PP-104", "route_id": None},
        {"aircraft_id": "105", "registration": "PP-105", "route_id": None},
        {"aircraft_id": "106", "registration": "PP-106", "route_id": None},
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js indisponível")
def test_live_flight_history_parses_money_and_recent_hours():
    script = """
globalThis.fetch = async () => ({ok: true, text: async () => '<html></html>'});
function flightRow(age, route, co2, fuel, money) {
  return {querySelectorAll: () => [
    {childNodes:[{textContent:age}], querySelector:()=>({textContent:route})},
    {querySelector:()=>({textContent:co2})},
    {querySelector:()=>({textContent:fuel})},
    {textContent:money}
  ]};
}
globalThis.DOMParser = class {
  parseFromString() {
    return {querySelectorAll: () => [
      flightRow('6 hours ago', 'TAS-GRU', '589,009 Quotas', '248,356 Lbs', '$1,277,380'),
      flightRow('1 day ago', 'GRU-TAS', '577,464 Quotas', '248,356 Lbs', '$1,252,350')
    ]};
  }
};
new Promise(done => new Function(process.argv[1])(['101'], done))
  .then(rows => console.log(JSON.stringify(rows)));
"""
    result = subprocess.run(["node", "-e", script, _FLIGHT_HISTORY_JS],
                            capture_output=True, text=True, check=True, timeout=8)
    readings = json.loads(result.stdout)
    assert readings[0]["aircraft_id"] == "101"
    assert readings[0]["flight_value"] == 1277380
    assert readings[0]["co2_quotas"] == 589009
    assert readings[0]["fuel_lbs"] == 248356
    assert len(readings[0]["recent_flights"]) == 1
    assert readings[0]["recent_flights"][0]["age_hours"] == 6
