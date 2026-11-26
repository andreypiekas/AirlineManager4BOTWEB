import json
import time
from types import SimpleNamespace

import pytest

import paths
from market import MarketQuote
from native_route_quotes import native_route_quotes, record_native_route_quote
from audited_game_snapshot import (
    FILENAME, capture_game_snapshot, compose_snapshot, replay_external_research_page, replay_research_page, snapshot_summary,
)
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
                                      "roster_observation_id": "test-roster",
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


@pytest.mark.parametrize(("other_selector", "status", "absent", "unexpected"), [
    (["11", "21", "22"], "matched", [], []),
    (["11", "21", "23"], "different", ["23"], ["22"]),
    (["11", "21"], "unverified", None, None),
    (None, "unverified", None, None),
])
def test_snapshot_compares_country_windows_only_in_confirmed_company_cycle(
        other_selector, status, absent, unexpected):
    selector = ["11", "21", "22"] if status != "different" else ["11", "21", "23"]
    wide = {"origin_id": "11", "country": "Brazil", "country_value": "Brazil",
            "started_at": NOW - 23, "observed_at": NOW - 20, "min_runway_ft": 1000,
            "selector_airport_ids": selector, "native_destination_ids": ["21"],
            "native_max_distance_km": 20_000, "native_limit_reached": True}
    narrow = {**wide, "started_at": NOW - 18, "observed_at": NOW - 15,
              "selector_airport_ids": other_selector, "native_destination_ids": ["21", "22"],
              "native_max_distance_km": 1250, "native_limit_reached": False}
    evidence = {"country_search_windows": [wide, narrow,
                {**narrow, "started_at": NOW - 40, "native_destination_ids": ["23"]},
                {**narrow, "observed_at": NOW, "native_destination_ids": ["24"]},
                {**narrow, "origin_id": "12"}]}
    snapshot = compose_snapshot(**observations(), read_only_window=(NOW - 30, NOW - 1),
                                operational_evidence=evidence)
    report, = snapshot["observations"]["route_search_partitions"]
    assert report["windows"] == [wide, narrow]
    assert report["selector_status"] == status
    assert report["origin_in_selector"] == (None if status == "unverified" else True)
    assert report["observed_destination_ids"] == ["21", "22"]
    assert report["absent_selector_ids"] == absent
    assert report["unexpected_destination_ids"] == unexpected
    assert snapshot["coverage"]["scopes"]["routes"] is False
    assert snapshot["snapshot_id"] == fingerprint_snapshot(snapshot)


@pytest.mark.parametrize(("case", "status"), [
    ("matching", "matched"), ("substituted_aircraft", "different"), ("delivery", "different"),
    ("unclassified", "incomplete"), ("old_roster", "incomplete"),
    ("wrong_itinerary", "different"), ("wrong_pending_observation", "incomplete"),
])
def test_snapshot_reconciles_native_hub_operations_by_aircraft_and_route(case, status):
    inputs = observations()
    inputs["inventory"]["hubs"] = [{"id": "2947", "code": "GRU"}, {"id": "455", "code": "EDDF"}]
    routed, pending = inputs["routes"]["current_relations"]
    # Route cards can have ICAO codes only. The native hub table shows IATA
    # and both hubs must report the same aircraft even when direction flips.
    routed.update(game_route_id=41, origin={"code": "SBGR"}, destination={"code": "EDDF"})
    pending["game_route_id"] = 0
    gru = {"management_id": "76500", "iata": "GRU", "icao": "SBGR", "rows": [
        {"aircraft_id": "101", "airports": ["GRU", "FRA"]},
        {"aircraft_id": "102", "airports": ["GRU", "PRY"]},
    ]}
    fra = {"management_id": "76501", "iata": "FRA", "icao": "EDDF", "rows": [
        {"aircraft_id": "101", "airports": ["FRA", "GRU"]},
    ]}
    hubs = {"started_at": NOW - 8, "observed_at": NOW - 4, "panels": [gru, fra],
            "enumerated": True, "managed_count": 2}
    pending_read = {"observation_id": "test-native", "observed_at": NOW - 14, "observed_until": NOW - 11,
                    "pending_ids": frozenset({"102"}), "maintenance_ids": frozenset({"102"}),
                    "unclassified_pending_ids": frozenset()}
    if case == "substituted_aircraft":
        fra["rows"][0]["aircraft_id"] = "103"
    if case in ("delivery", "unclassified"):
        pending_read["maintenance_ids"] = frozenset()
    if case == "unclassified":
        pending_read["unclassified_pending_ids"] = frozenset({"102"})
    if case == "wrong_itinerary":
        fra["rows"][0]["airports"] = ["FRA", "PRY"]
    if case == "wrong_pending_observation":
        pending_read["observation_id"] = "earlier-cycle"
    cycle_start = NOW - 25 if case == "old_roster" else NOW - 35

    result = compose_snapshot(**inputs, read_only_window=(cycle_start, NOW - 1),
                              operational_evidence={"hubs": hubs, "pending": pending_read})
    report = result["observations"]["hub_operations"]
    assert report["status"] == status
    assert result["snapshot_id"] == fingerprint_snapshot(result)
    json.dumps(result)
    assert result["coverage"]["scopes"]["routes"] is False
    if case == "matching":
        assert report["associated_maintenance_aircraft"] == ["102"]
        assert report["observed_links"] == 3
    if case == "substituted_aircraft":
        assert {row["kind"] for row in report["differences"]} == {"unexpected_aircraft", "missing_aircraft"}


def external_observations():
    return {"candidate_source": "game_purchase_catalog", "origin_scope": "external_catalog",
            "candidate_inventory": [{"id": "12", "code": "EXT", "observed_at": NOW - 10,
                                     "hub_price": 1000, "hub_price_observed_at": NOW - 20,
                                     "hub_points": 0, "hub_points_observed_at": NOW - 30}],
            "samples": [{"origin_id": "12", "destination_id": "11", "source": "game_route_search",
                         "observed_at": NOW - 15, "distance_km": 500, "y": 10, "j": 2, "f": 1}],
            "hub_progress": [{"hub_id": "12", "coverage": "partial", "last_attempt_at": NOW - 15}]}


def test_external_snapshot_has_independent_clocks_and_fingerprint(tmp_path, monkeypatch):
    external = external_observations()
    external["candidate_inventory"].append({"id": "11", "observed_at": NOW})
    snapshot = compose_snapshot(**observations(), external_demand=external)
    research = snapshot["observations"]["external_route_research"]
    assert [row["id"] for row in research["candidate_inventory"]] == ["12"]
    assert len(research["samples"]) == len(research["hub_progress"]) == 1
    assert research["candidate_inventory"][0]["hub_points"] == 0
    assert snapshot["coverage"]["scopes"]["routes"] is False
    assert snapshot["coverage"]["scopes"]["prices"] is False
    external["samples"][0]["y"] = 99
    assert research["samples"][0]["y"] == 10
    assert fingerprint_snapshot(snapshot) == snapshot["snapshot_id"]
    assert compose_snapshot(**observations(), external_demand=external)["snapshot_id"] != snapshot["snapshot_id"]
    path = tmp_path / FILENAME
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    summary = snapshot_summary(now=NOW, path=path)["external_route_research"]
    assert summary == {"coverage": "partial", "candidate_count": 1, "fresh_price_count": 1,
                       "fresh_points_count": 1, "fresh_sample_count": 1,
                       "read_only": True, "purchase_eligible": False}
    later = snapshot_summary(now=NOW + 875, path=path)["external_route_research"]
    assert later["candidate_count"] == later["fresh_price_count"] == 1
    assert later["fresh_points_count"] == 0
    assert snapshot_summary(now=NOW + 881, path=path)["external_route_research"]["candidate_count"] == 0
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("other"))
    assert snapshot_summary(now=NOW, path=path)["status"] == "registro_invalido"


def test_external_snapshot_rejects_wrong_sources_stale_ownership_and_duplicates():
    for field in ("candidate_source", "origin_scope"):
        external = external_observations()
        external[field] = "unverified"
        research = compose_snapshot(**observations(), external_demand=external)["observations"]["external_route_research"]
        assert research["candidate_inventory"] == research["samples"] == []
    for hubs in (None, [None], [{"id": "11"}, {"id": "11"}], [{"id": "11"}, {"id": "12"}]):
        evidence = observations()
        evidence["inventory"]["hubs"] = hubs
        research = compose_snapshot(**evidence, external_demand=external_observations())["observations"]["external_route_research"]
        assert research["candidate_inventory"] == research["samples"] == []
    evidence = observations()
    evidence["inventory"]["observed_at"] = NOW - 901
    assert not compose_snapshot(**evidence, external_demand=external_observations())["observations"]["external_route_research"]["samples"]
    external = external_observations()
    external["candidate_inventory"].extend([None, {"id": "12", "observed_at": NOW}, {"id": [], "observed_at": NOW}])
    assert not compose_snapshot(**observations(), external_demand=external)["observations"]["external_route_research"]["candidate_inventory"]
    external = external_observations()
    external["samples"].extend([None, {**external["samples"][0], "y": 999}])
    external["hub_progress"] = "invalid"
    research = compose_snapshot(**observations(), external_demand=external)["observations"]["external_route_research"]
    assert research["samples"] == research["hub_progress"] == []


def test_external_snapshot_rejects_stale_and_future_costs_and_samples():
    external = external_observations()
    candidate = external["candidate_inventory"][0]
    candidate.update(hub_price_observed_at=NOW - 901, hub_points_observed_at=NOW + 1)
    external["samples"][0]["observed_at"] = NOW - 901
    research = compose_snapshot(**observations(), external_demand=external)["observations"]["external_route_research"]
    assert research["candidate_inventory"] == [{"id": "12", "code": "EXT", "observed_at": NOW - 10}]
    assert research["samples"] == []


def test_external_replay_binds_cursor_to_capture_and_expires_costs(tmp_path, monkeypatch):
    from test_owned_hub_research_feed import _market, _preview_engines

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    evidence = observations()
    external = external_observations()
    external["samples"] = [{**external["samples"][0], "destination_id": str(i)} for i in range(100, 150)]
    evidence.update(market=_market(), engines=_preview_engines(), operational_reserve=100)
    path = tmp_path / FILENAME
    snapshot = compose_snapshot(**evidence, external_demand=external)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    first = replay_external_research_page(now=NOW, path=path)
    assert first["status"] == "parcial" and first["snapshot_id"] == snapshot["snapshot_id"]
    assert first["external_budget"]["available_before_commitments"] == 1100
    assert first["has_more"] and first["purchase_eligible"] is False
    assert first["items"] and all(item["external_cost_preview"]["hub_points"] == 0 for item in first["items"])
    cursor = first["snapshot_fingerprint"]
    second = replay_external_research_page(now=NOW, path=path, offset=first["next_offset"],
                                          expected_fingerprint=cursor)
    assert not second["cursor_reset"] and second["offset"] == first["next_offset"]
    later = replay_external_research_page(now=NOW + 875, path=path,
                                         offset=first["next_offset"], expected_fingerprint=cursor)
    assert later["items"] and later["cursor_reset"] and later["offset"] == 0
    assert all(item["external_cost_preview"]["hub_points"] is None for item in later["items"])
    assert all(item["external_cost_preview"]["hub_price"] == 1000 for item in later["items"])
    expired_ownership = replay_external_research_page(now=NOW + 881, path=path)
    assert expired_ownership["items"] == [] and expired_ownership["external_hubs"] == 0
    evidence["cash"] = 1201
    replacement = compose_snapshot(**evidence, external_demand=external)
    path.write_text(json.dumps(replacement), encoding="utf-8")
    changed = replay_external_research_page(now=NOW, path=path, offset=first["next_offset"],
                                           expected_fingerprint=cursor)
    assert changed["cursor_reset"] and changed["offset"] == 0
    assert replay_external_research_page(now=NOW + 901, path=path)["status"] == "expirado"
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("other"))
    assert replay_external_research_page(now=NOW, path=path)["status"] == "registro_invalido"


def test_external_replay_rejects_missing_legacy_and_tampered_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    path = tmp_path / FILENAME
    assert replay_external_research_page(now=NOW, path=path)["status"] == "sem_coleta"
    evidence = observations()
    evidence["policy_values"] = {"operational_reserve": 100}
    legacy = compose_snapshot(**evidence)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert replay_external_research_page(now=NOW, path=path)["status"] == "recoleta_necessaria"
    snapshot = compose_snapshot(**evidence, external_demand=external_observations())
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    report = replay_external_research_page(now=NOW, path=path)
    assert report["external_budget"]["available_before_commitments"] == 1100
    snapshot["observations"]["cash"]["available"] = 999999
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    invalid = replay_external_research_page(now=NOW, path=path)
    assert invalid["status"] == "registro_invalido" and invalid["items"] == []


def test_capture_reads_external_registry_for_current_profile(tmp_path, monkeypatch):
    from hub_expansion import HubExpansionRegistry
    from hub_registry import HubRegistry

    monkeypatch.setattr(paths, "current", lambda: paths.Profile("isolated"))
    monkeypatch.setattr(paths.Profile, "data", property(lambda self: tmp_path))
    monkeypatch.setattr(HubRegistry, "snapshot", lambda self, routes: {
        **observations()["inventory"], "observed_at": time.time() - 1})
    registry = HubExpansionRegistry()
    assert registry.record_catalog([{"id": "12", "code": "EXT", "name": "Fixture",
                                     "purchasable": True, "hub_price": 1000, "hub_points": 0}])
    assert registry.external_demand_registry().record_demand(
        "12", [{"arr_id": "11", "distance": 500, "y": 10, "j": 2, "f": 1}]) == 1
    bot = SimpleNamespace(stats=lambda: SimpleNamespace(money=2500, money_read_at=time.time() - 1))
    snapshot = capture_game_snapshot(bot)
    assert snapshot["profile_id"] == "isolated"
    assert snapshot["observations"]["external_route_research"]["samples"][0]["origin_id"] == "12"
    assert snapshot["observations"]["route_research"]["samples"] == []
    assert json.loads((tmp_path / FILENAME).read_text(encoding="utf-8")) == snapshot


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


def test_capture_records_native_partition_when_all_aircraft_are_unrouted():
    evidence = observations()
    evidence["routes"]["fleet_coverage"].update(routes=0, parked=1, pending=1)
    evidence["routes"]["scan_coverage"] = {}
    coverage = compose_snapshot(**evidence)["coverage"]
    assert coverage["verified"] is True
    assert coverage["observed_pages"] == coverage["expected_pages"] == 0
    assert coverage["routed_aircraft_count"] == 0
    assert coverage["unrouted_aircraft_count"] == 2
    assert coverage["native_unrouted_identity_verified"] is True
    evidence["routes"]["fleet_coverage"]["native_identity_status"] = "different"
    coverage = compose_snapshot(**evidence)["coverage"]
    assert coverage["verified"] is False
    assert coverage["native_unrouted_identity_verified"] is False


def test_cycle_capture_persists_real_cash_and_missing_registry_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("isolated"))
    monkeypatch.setattr(paths.Profile, "data", property(lambda self: tmp_path))
    cash_at = time.time() - 3
    started_at, confirmed_at = cash_at + 1, cash_at + 2
    fuel_quote = MarketQuote(2450, started_at, confirmed_at)
    bot = SimpleNamespace(stats=lambda: SimpleNamespace(money=2500, money_read_at=cash_at, fuel_quote=fuel_quote))
    preview_at, quote_at = started_at + 0.25, started_at + 0.5
    assert record_native_route_quote(bot, aircraft_id="101", origin_id="11", destination_id="12",
                                     distance=1000, fee=250, occupied=0, fares=(100, 200, 300),
                                     fuel_lbs_per_leg=21000, co2_kg_per_pax_km=0.16, now=quote_at,
                                     fuel_quote=fuel_quote, preview_started_at=preview_at)
    snapshot = capture_game_snapshot(bot, read_only_window=(started_at, confirmed_at))
    assert json.loads((tmp_path / FILENAME).read_text(encoding="utf-8")) == snapshot
    assert snapshot["profile_id"] == "isolated"
    assert snapshot["verified"] is False
    assert snapshot["observations"]["cash"]["available"] == 2500
    assert snapshot["observations"]["cash"]["observed_at"] == cash_at
    assert not any(snapshot["coverage"]["scopes"].values())
    quote, = snapshot["observations"]["native_route_quotes"]
    assert quote["observed_at"] == quote_at
    assert quote["fuel_lbs_per_leg"] == 21000 and quote["co2_kg_per_pax_km"] == 0.16
    assert quote["fuel_market_quote"] == fuel_quote.evidence(quote_at)
    assert quote["fuel_replacement_cost_per_leg_cents"] == 5145000
    assert snapshot["observations"]["market_quotes"]["fuel"] is None
    summary = snapshot_summary()
    assert summary["status"] == "parcial"
    assert summary["read_only_window"] == {"started_at": started_at, "company_confirmed_at": confirmed_at}
    assert summary["cash_control"]["observed_at"] < summary["read_only_window"]["started_at"]
    assert summary["native_route_quote_count"] == 1
    assert "native_route_quotes" not in summary


def test_summary_preserves_source_age_and_is_profile_bound(tmp_path, monkeypatch):
    snapshot = compose_snapshot(**observations())
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    summary = snapshot_summary(now=NOW, path=path)
    assert summary["status"] == "parcial" and summary["fleet_count"] == 2
    assert summary["unrouted_aircraft_control"] == {
        "source": "game_fleet_scan", "profile_id": "principal",
        "snapshot_id": snapshot["snapshot_id"], "verified": True,
        "observed_at": NOW - 30, "value": 1,
    }
    assert summary["cash_control"] == {
        "source": "game_snapshot", "profile_id": "principal",
        "snapshot_id": snapshot["snapshot_id"], "verified": True,
        "observed_at": NOW - 5, "value": 1200,
    }
    assert summary["owned_inventory"] == {
        "source": "game_hub_select", "profile_id": "principal",
        "snapshot_id": snapshot["snapshot_id"], "hubs": [{"id": "11"}],
        "observed_at": NOW - 20, "hub_catalog_fresh": True, "partial_fleet": True,
    }
    assert "observed_aircraft_ids" not in json.dumps(summary)
    summary = snapshot_summary(now=NOW + 875, path=path)
    assert not summary["scopes"]["fleet"] and summary["fleet_count"] is None
    assert summary["unrouted_aircraft_control"] is None
    assert summary["scopes"]["hubs"] and summary["cash_observed"]
    summary = snapshot_summary(now=NOW + 881, path=path)
    assert summary["status"] == "parcial"
    assert not summary["scopes"]["hubs"] and summary["owned_inventory"] is None
    assert snapshot_summary(now=NOW + 896, path=path)["cash_control"] is None
    assert snapshot_summary(now=NOW + 901, path=path)["status"] == "expirado"
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("other"))
    summary = snapshot_summary(now=NOW, path=path)
    assert summary["status"] == "registro_invalido" and "owned_inventory" not in summary
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    snapshot["coverage"]["scopes"]["prices"] = True
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert snapshot_summary(now=NOW, path=path)["status"] == "registro_invalido"


def test_summary_certifies_zero_unrouted_and_expires_older_route_scan(tmp_path, monkeypatch):
    evidence = observations()
    evidence["routes"]["fleet_coverage"].update(
        routes=2, parked=0, pending=0, observed_at=NOW - 40,
    )
    snapshot = compose_snapshot(**evidence)
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    summary = snapshot_summary(now=NOW, path=path)
    assert summary["unrouted_aircraft_control"]["value"] == 0
    assert summary["unrouted_aircraft_control"]["observed_at"] == NOW - 40
    summary = snapshot_summary(now=NOW + 861, path=path)
    assert summary["scopes"]["fleet"] is False
    assert summary["unrouted_aircraft_control"] is None


def test_summary_binds_global_passenger_hangar_to_capture_and_source_age(tmp_path, monkeypatch):
    from fleet_commitment_observations import SOURCE

    evidence = observations()
    commitments = {"status": "partial", "source": SOURCE, "observed_at": NOW - 100,
                   "passenger_hangar": {"capacity": 3, "occupied": 3, "free": 0}}
    evidence["inventory"]["fleet_commitment_observations"] = commitments
    path = tmp_path / "observed.json"
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))

    def save():
        snapshot = compose_snapshot(**evidence)
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        return snapshot["snapshot_id"]

    snapshot_id = save()
    assert snapshot_summary(now=NOW, path=path)["passenger_hangar_control"] == {
        "source": SOURCE, "profile_id": "principal", "snapshot_id": snapshot_id,
        "verified": True, "observed_at": NOW - 100, "value": 0,
    }
    assert snapshot_summary(now=NOW + 801, path=path)["passenger_hangar_control"] is None
    commitments["passenger_hangar"]["free"] = 1
    save()
    assert snapshot_summary(now=NOW, path=path)["passenger_hangar_control"] is None
    commitments["passenger_hangar"]["occupied"] = 2
    save()
    assert snapshot_summary(now=NOW, path=path)["passenger_hangar_control"]["value"] == 1
    commitments["source"] = "game_hub_select"
    save()
    assert snapshot_summary(now=NOW, path=path)["passenger_hangar_control"] is None


def test_replay_uses_captured_mode_quotes_and_paginates_same_snapshot(tmp_path, monkeypatch):
    from test_owned_hub_research_feed import _fleet_report, _inventory, _market, _preview_engines, _sample

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    evidence = observations()
    evidence.update(inventory={**_inventory(), "hub_catalog_fresh": True}, routes=_fleet_report(),
                    market=_market(), engines=_preview_engines(),
                    mode="realista", mode_at=NOW - 10, preview_margin=0.15,
                    configured_prices={"fuel": 650, "co2": 125},
                    quotes={kind: {"source": "game_market", "unit": "USD/1000",
                                   "price": price, "observed_at": NOW - 5, "expires_at": NOW + 60}
                            for kind, price in (("fuel", 600), ("co2", 100))})
    evidence["demand"]["samples"] = [_sample(dest=str(i)) for i in range(3139, 3160)]
    from fleet_commitment_observations import SOURCE

    evidence["inventory"]["fleet_commitment_observations"] = {
        "source": SOURCE, "status": "partial", "observed_at": NOW - 10,
        "passenger_hangar": {"capacity": 4, "occupied": 3, "free": 1},
    }
    bot = SimpleNamespace()
    for aircraft, origin, dest, distance, fee, fares in (
        ("900001", "2926", "3139", 2000, 1000, (900, 1800, 2700)),
        ("900002", "2926", "3139", 2000, 1500, (950, 1900, 2800)),
        ("900003", "3139", "2926", 2000, 9999, (1, 2, 3)),
        ("900004", "2926", "3140", 1999, 9999, (1, 2, 3)),
    ):
        assert record_native_route_quote(bot, aircraft_id=aircraft, origin_id=origin,
                                         destination_id=dest, distance=distance, fee=fee,
                                         occupied=1, fares=fares, seat_layout=(92, 39, 20), now=NOW - 10)
    evidence["native_quotes"] = native_route_quotes(bot, now=NOW)
    snapshot = compose_snapshot(**evidence)
    assert snapshot["observations"]["native_route_quotes"][0]["observed_seat_layout"] == {
        "y": 92, "j": 39, "f": 20,
    }
    path = tmp_path / FILENAME
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    first = replay_research_page(now=NOW, path=path)
    assert first["status"] == "parcial" and first["historical_replay"] is True
    assert first["snapshot_id"] == snapshot["snapshot_id"]
    assert first["has_more"] and first["next_offset"] == 40
    previews = [item["economics_preview"] for item in first["items"] if item["economics_preview"]]
    assert previews and all(p["safety_margin_fraction"] == 0.15 for p in previews)
    assert all(p["configured_price_assumptions"] == {
        "source": "configured_purchase_thresholds", "unit": "USD/1000", "verified": False,
        "fuel": 650, "co2": 125,
    } for p in previews)
    assert all("configured_price_scenarios" in row for p in previews for row in p["layouts"])
    occupied = [item for item in first["items"] if item["destination_id"] == "3139"]
    assert occupied and all(item["fleet_occupancy"]["own_aircraft_count"] == 1
                            and item["economics_preview"] is None for item in occupied)
    for item in occupied:
        gate = item["accounting_gate"]
        assert gate["status"] == "blocked" and gate["purchase_eligible"] is False
        assert gate["scope"] == "shared_layout_prerequisites"
        assert "ROUTE_OCCUPIED" in {reason["code"] for reason in gate["blocking_reasons"]}
        ref = item["native_route_quote_reference"]
        assert ref["quote_count"] == 2
        assert ref["route_fee_range"] == {"min": 1000, "max": 1500}
        assert ref["fare_ranges"]["y"] == {"min": 900, "max": 950}
        assert ref["scope"] == "existing_aircraft_only" and ref["purchase_eligible"] is False
        assert ref["daily_demand_residual"] is None and ref["expires_at"] == NOW + 890
        assert item["daily_net_profit"] is None and item["final_aircraft_price"] is None
    assert all("native_route_quote_reference" not in item for item in first["items"]
               if item["destination_id"] != "3139")
    assert not any(aircraft in json.dumps(first) for aircraft in ("900001", "900002", "900003", "900004"))
    assert all(item["purchase_eligible"] is False for item in first["items"])
    for item in first["items"]:
        gate = item["accounting_gate"]
        assert gate["status"] == "blocked" and gate["read_only"] is True
        assert gate["total_investment"] is None and gate["cash_after_purchase"] is None
        assert gate["verified_capital_costs"]["hangar_cost"] == {
            "source": SOURCE, "observed_at": NOW - 10, "value": 0,
        }
        assert not any(reason["field"] == "costs.hangar_cost" for reason in gate["blocking_reasons"])
        assert {"fuel_price_per_1000", "co2_price_per_1000"} <= set(gate["verified_accounting_inputs"])
        assert not {"layout", "daily_demand", "fares", "cash"} & set(gate["verified_accounting_inputs"])
        assert "DEMAND_UNVERIFIED" in {reason["code"] for reason in gate["blocking_reasons"]}
        assert {"maintenance", "a_check", "other"} == set(gate["excluded_costs"])
        layouts = (item.get("economics_preview") or {}).get("layouts", [])
        evaluations = gate["layout_evaluations"]
        assert [row["configuration_yjf"] for row in evaluations] == [row["layout"] for row in layouts]
        assert len({row["economics_id"] for row in evaluations}) == len(layouts)
        for row in evaluations:
            assert row["economics_id"] != gate["economics_id"]
            assert row["status"] == "blocked" and row["read_only"] is True
            assert row["configuration_verified"] is False and row["purchase_eligible"] is False
            assert {"code": "EVIDENCE_CONTRADICTORY", "field": "inputs.layout"} in row["blocking_reasons"]
    assert replay_research_page(now=NOW + 100, path=path) == first
    assert replay_research_page(offset=40, expected_snapshot="other", now=NOW, path=path)["status"] == "snapshot_alterado"
    second = replay_research_page(offset=40, expected_snapshot=snapshot["snapshot_id"],
                                  expected_fingerprint=first["snapshot_fingerprint"], now=NOW, path=path)
    assert second["offset"] == 40 and second["snapshot_fingerprint"] == first["snapshot_fingerprint"]
    assert second["items"] and not second["cursor_reset"]
    assert replay_research_page(now=NOW + 901, path=path)["status"] == "expirado"


def test_replay_rejects_legacy_or_modified_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    snapshot = compose_snapshot(**observations())
    path = tmp_path / FILENAME
    snapshot["observations"].pop("research_inputs")
    snapshot["snapshot_id"] = fingerprint_snapshot(snapshot)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert replay_research_page(now=NOW, path=path)["status"] == "recoleta_necessaria"
    snapshot["observations"]["captured_at"] += 1
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert replay_research_page(now=NOW, path=path)["status"] == "registro_invalido"


def test_replay_native_count_and_event_veto_preview(tmp_path, monkeypatch):
    from test_owned_hub_research_feed import _inventory, _market, _preview_engines, _sample

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    evidence = observations()
    evidence.update(inventory={**_inventory(), "hub_catalog_fresh": True}, routes={},
                    market=_market(), engines=_preview_engines(), mode="realista", mode_at=NOW - 10,
                    quotes={kind: {"source": "game_market", "unit": "USD/1000",
                                   "price": price, "observed_at": NOW - 5, "expires_at": NOW + 60}
                            for kind, price in (("fuel", 600), ("co2", 100))})
    samples = [_sample(dest=str(dest)) for dest in range(3140, 3145)]
    # A positive count in correlated route detail is also useful without a roster.
    samples[3]["route_detail"] = {"source": "game_route_detail", "observed_at": NOW - 5,
                                  "origin_id": "2926", "destination_id": "3143",
                                  "origin_runway_ft": 6500, "destination_runway_ft": 6500,
                                  "observed_aircraft_on_route": 2}
    samples[4]["distance_km"] = 1999.6
    evidence["demand"]["samples"] = samples
    bot = SimpleNamespace()
    for dest, distance, occupied in (("3140", 2000, 1), ("3141", 2000, 0), ("3142", 1999, 2)):
        assert record_native_route_quote(bot, aircraft_id="900001", origin_id="2926",
                                         destination_id=dest, distance=distance, fee=1000,
                                         occupied=occupied, fares=(900, 1800, 2700), now=NOW - 10)
    assert record_native_route_quote(bot, aircraft_id="900001", origin_id="2926",
                                     destination_id="3144", distance=2000, fee=1000,
                                     occupied=0, fares=(900, 1800, 2700), now=NOW - 10,
                                     research_distance_km=1999.6, event_demand_boosted=True)
    evidence["native_quotes"] = native_route_quotes(bot, now=NOW)
    path = tmp_path / FILENAME
    path.write_text(json.dumps(compose_snapshot(**evidence)), encoding="utf-8")
    result = replay_research_page(now=NOW, path=path)
    rows = {item["destination_id"]: item for item in result["items"] if item["engine_id"] == "1"}
    assert set(rows) == {"3140", "3141", "3142", "3143", "3144"}
    for dest, item in rows.items():
        assert item["fleet_occupancy"] is None
        gate = item["accounting_gate"]
        codes = {reason["code"] for reason in gate["blocking_reasons"]}
        assert "DEMAND_UNVERIFIED" in codes
        assert not {"fares", "daily_demand"} & set(gate["verified_accounting_inputs"])
        assert gate["total_investment"] is None and not gate["purchase_eligible"]
        if dest in ("3140", "3143"):
            assert "ROUTE_OCCUPIED" in codes
            assert item["economics_preview"] is None
        else:
            assert "ROUTE_OCCUPANCY_UNVERIFIED" in codes
            assert "ROUTE_OCCUPIED" not in codes
            assert (item["economics_preview"] is None) == (dest == "3144")
    assert all("rota_ocupada_frota_propria" in rows[dest]["pending"] for dest in ("3140", "3143"))
    assert "native_route_quote_reference" not in rows["3142"]
    assert rows["3144"]["event_demand_boosted"] is True
    assert "demanda_evento_temporario" in rows["3144"]["pending"]
    assert rows["3144"]["native_route_quote_reference"]["distance_km"] == 1999.6


def test_replay_accounting_gate_uses_only_current_correlated_detail(tmp_path, monkeypatch):
    from test_owned_hub_research_feed import _fleet_report, _inventory, _market, _preview_engines, _sample
    from test_staff_observations import STAFF

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    evidence = observations()
    engines = _preview_engines()
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"capacity_pax": 180, "range_km": 2000,
                                                "required_runway_ft": 6500},
              "seat_observation": {"source": "hidden_native_template", "y": 180, "j": 0, "f": 0},
              "operational_requirements": {"delivery_seconds": 600, "pilots": 2,
                                           "cabin_crew": 4, "engineers": 2, "technicians": 1}}}
    sample = _sample()
    sample["destination_runway_ft"] = 6499
    sample["route_detail"] = {"source": "game_route_detail", "observed_at": NOW,
                              "origin_id": "2926", "destination_id": "3139",
                              "origin_runway_ft": 6500, "destination_runway_ft": 6499,
                              "observed_aircraft_on_route": 0}
    evidence.update(inventory={**_inventory(), "hub_catalog_fresh": True,
                               "staff_observations": {"source": "game_staff_salary", "status": "observed",
                                                      "observed_at": NOW - 10, "staff": STAFF}}, routes=_fleet_report(),
                    market=_market(), engines=engines,
                    mode="realista", mode_at=NOW - 10,
                    quotes={"fuel": {"source": "game_market", "unit": "USD/1000", "price": 600,
                                     "observed_at": NOW - 10, "expires_at": NOW},
                            "co2": {"source": "game_market", "unit": "USD/1000", "price": 100,
                                    "observed_at": NOW - 5, "expires_at": NOW + 60}})
    evidence["demand"]["samples"] = [sample]
    path = tmp_path / FILENAME
    path.write_text(json.dumps(compose_snapshot(**evidence)), encoding="utf-8")
    page = replay_research_page(now=NOW, path=path)
    row = next(item for item in page["items"] if item["engine_id"] == "1")
    gate = row["accounting_gate"]
    assert row["engine_detail"]["seat_observation"] == {
        "source": "hidden_native_template", "y": 180, "j": 0, "f": 0}
    assert row["engine_detail"]["operational_requirements"] == {
        "delivery_seconds": 600, "pilots": 2, "cabin_crew": 4, "engineers": 2, "technicians": 1}
    assert row["staff_salary_reference"] == {"source": "game_staff_salary", "observed_at": NOW - 10,
                                             "expires_at": NOW + 890, "daily_salary_if_all_additional": 2000,
                                             "incremental_cost_verified": False}
    assert not row["purchase_eligible"]
    assert gate["verified_accounting_inputs"] == ["capacity", "co2_price_per_1000"]
    codes = {reason["code"] for reason in gate["blocking_reasons"]}
    assert "ROUTE_PHYSICALLY_INFEASIBLE" in codes
    assert "ROUTE_OCCUPANCY_UNVERIFIED" in codes and "ROUTE_OCCUPIED" not in codes
    assert row["economics_preview"] is None
    other = next(item for item in page["items"] if item["engine_id"] == "3")
    assert other["accounting_gate"]["verified_accounting_inputs"] == ["co2_price_per_1000"]
    assert "staff_salary_reference" not in other



def test_replay_retains_verified_direct_range_veto_without_runway_detail(tmp_path, monkeypatch):
    from test_owned_hub_research_feed import _fleet_report, _inventory, _market, _preview_engines, _sample

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    evidence = observations()
    engines = _preview_engines()
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"range_km": 1999, "required_runway_ft": 6500}}}
    evidence.update(inventory={**_inventory(), "hub_catalog_fresh": True}, routes=_fleet_report(),
                    market=_market(), engines=engines, mode="realista", mode_at=NOW)
    evidence["demand"]["samples"] = [_sample(distance=2000)]
    path = tmp_path / FILENAME
    path.write_text(json.dumps(compose_snapshot(**evidence)), encoding="utf-8")
    rows = replay_research_page(now=NOW, path=path)["items"]
    row = next(item for item in rows if item["engine_id"] == "1")
    assert row["physical_feasibility"]["checks"] == {
        "range": "short", "origin_runway": "unknown", "destination_runway": "unknown"}
    assert row["physical_feasibility"]["stopover_research_required"] is True
    assert row["economics_preview"] is None and row["purchase_eligible"] is False
    codes = {reason["code"] for reason in row["accounting_gate"]["blocking_reasons"]}
    assert {"ROUTE_PHYSICAL_DATA_UNKNOWN", "ROUTE_PHYSICALLY_INFEASIBLE"} <= codes
    other = next(item for item in rows if item["engine_id"] == "3")
    other_codes = {reason["code"] for reason in other["accounting_gate"]["blocking_reasons"]}
    assert "ROUTE_PHYSICALLY_INFEASIBLE" not in other_codes


def test_catalog_coverage_is_independent_and_expires_with_oldest_source(tmp_path, monkeypatch):
    import engine_catalog
    import engine_selection
    from test_engine_catalog import _groups, _roster

    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    registry = engine_catalog.EngineCatalogRegistry(tmp_path / "engines.json")
    detail_at = NOW - engine_catalog.MAX_AGE_SECONDS + 25
    monkeypatch.setattr(engine_catalog.time, "time", lambda: detail_at)
    catalog = engine_selection.parse_engine_catalog(_groups())
    assert registry.record("11", "A320", catalog, observed_model_id="11")
    monkeypatch.setattr(engine_catalog.time, "time", lambda: NOW)
    assert registry.record_roster(_roster(("11", "A320")), observed_at=NOW)
    inputs = observations()
    inputs["engines"] = registry.snapshot(now=NOW)
    snapshot = compose_snapshot(**inputs)
    assert snapshot["coverage"]["scopes"]["models"] is True
    assert snapshot["coverage"]["scopes"]["engines"] is False
    assert snapshot["coverage"]["scopes"]["prices"] is False
    assert snapshot["coverage"]["status"] == "partial"
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    assert snapshot_summary(now=NOW + 25, path=path)["scopes"]["models"] is True
    assert snapshot_summary(now=NOW + 26, path=path)["scopes"]["models"] is False

    details = {"1": {"observed_at": NOW, "metrics": {"speed_kph": 905}}}
    assert registry.record("11", "A320", catalog, observed_model_id="11", variant_details=details)
    inputs["engines"] = registry.snapshot(now=NOW)
    snapshot = compose_snapshot(**inputs)
    scopes = snapshot["coverage"]["scopes"]
    assert scopes["models"] and scopes["engines"]
    assert not scopes["prices"] and not scopes["routes"]
    assert snapshot["coverage"]["status"] == "partial"
    assert registry.record_attempt("11", "A320")
    inputs["engines"] = registry.snapshot(now=NOW)
    assert not compose_snapshot(**inputs)["coverage"]["scopes"]["models"]
