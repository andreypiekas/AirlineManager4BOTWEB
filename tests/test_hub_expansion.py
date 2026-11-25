"""Read-only financial scenarios require verified complete data."""
import json
import time
from copy import deepcopy

import pytest

from hub_expansion import MAX_AGE_SECONDS, HubExpansionRegistry


def _candidate(airport_id="123", price=5000):
    return {"id": airport_id, "code": "AAA", "name": "Airport fixture",
            "purchasable": True, "hub_price": price, "hub_points": 0}


def test_external_demand_isolated_and_excluded_after_hub_purchase(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate("123"), _candidate("456"), _candidate("789")])
    now = time.time()
    assert registry.external_research_origins({"123"}, now=now) == ["456", "789"]
    assert registry.external_research_origins(set(), now=now) == []
    assert registry.external_research_origins({"123", "invalid"}, now=now) == []
    assert registry.external_research_origins({"123"}, now=now + MAX_AGE_SECONDS + 1) == []
    external = registry.external_demand_registry()
    assert external.record_demand_attempt("456", search_scope="configured", max_distance=6000, min_runway=5000)
    assert external.record_demand("456", [{"arr_id": "789", "distance": 2000, "y": 100, "j": 20, "f": 5}]) == 1
    restarted = HubExpansionRegistry(registry.path)
    assert restarted.external_demand_registry().next_demand_origin(["456", "789"]) == "789"
    report = restarted.snapshot(owned_hub_ids={"123"})
    assert report["external_demand_fresh_samples"] == 1
    assert report["external_demand_attempted_hubs"] == 1
    assert report["demand_samples"] == 0
    assert report["external_demand_coverage"] == "partial"
    candidate = next(row for row in report["candidates"] if row["id"] == "456")
    assert candidate["route_research"]["fresh_sample_count"] == 1
    assert candidate["status"] == "dados_a_confirmar"
    assert restarted.snapshot(owned_hub_ids={"123"}, external_ownership_verified=False)["external_demand_fresh_samples"] == 0
    assert restarted.external_demand_snapshot({"123", "456"})["samples"] == []
    assert restarted.demand_observations({"456"}) == []


def test_external_catalog_costs_keep_independent_observation_times(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate("456", price=0)])
    initial = registry.external_demand_snapshot({"123"}, now=clock[0])["candidate_inventory"][0]
    assert initial["hub_price"] == initial["hub_points"] == 0
    assert initial["hub_price_observed_at"] == initial["hub_points_observed_at"] == clock[0]
    clock[0] += MAX_AGE_SECONDS + 1
    price_only = _candidate("456", price=1000)
    del price_only["hub_points"]
    assert registry.record_catalog([price_only], observed_at=clock[0])
    updated = registry.external_demand_snapshot({"123"}, now=clock[0])["candidate_inventory"][0]
    assert updated["hub_price"] == 1000 and updated["hub_price_observed_at"] == clock[0]
    assert "hub_points" not in updated and "hub_points_observed_at" not in updated
    assert registry.external_research_candidates({"123", "456"}, now=clock[0]) == []


def _research(*, airport_id="123", **overrides):
    observed_at = int(time.time())
    model = overrides.get("model", "model-fixture")
    engine_id = overrides.get("engine_id", "engine-fixture-1")
    origin_id = overrides.get("origin_id", airport_id)
    destination_id = overrides.get("destination_id", "789" if airport_id == "456" else "456")
    route = overrides.get("route", "fixture-route")
    evidence_identity = {"model": model, "engine_id": engine_id,
                         "model_id": overrides.get("model_id", "101"),
                         "stopover_id": overrides.get("stopover_id"),
                         "origin_id": origin_id, "destination_id": destination_id,
                         "route": route}
    data = {"source": "game_research", "observed_at": observed_at,
            **evidence_identity,
            "model": model, "engine_id": engine_id, "engine_verified": True,
            "engine_label": "variant fixture", "route": route,
            "origin_id": origin_id, "destination_id": destination_id,
            "route_feasible": True, "demand_verified": True,
            "external_demand_verified": True,
            "costs": {"source": "game_market", "observed_at": observed_at,
                      **evidence_identity, "aircraft_price": 10000,
                      "aircraft_price_includes_engine": True,
                      "route_fee": 1000, "hangar_price": 0, "other_fees": 0},
            "financial": {"source": "route_optimizer", "observed_at": observed_at,
                          **evidence_identity, "profit_per_day": 2000}}
    data.update(overrides)
    if "profit_per_day" in overrides:
        data["financial"] = {**data["financial"], "profit_per_day": overrides["profit_per_day"]}
    return data


def _legacy_research():
    return {"source": "game_research", "model": "model-legacy", "route": "route-legacy",
            "route_feasible": True, "demand_verified": True,
            "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0,
            "profit_per_day": 2000}


def test_unknown_catalog_and_invalid_input_do_not_create_recommendation(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.snapshot()["availability_pending"] is True
    assert not registry.record_catalog([{"id": "123", "hub_price": 5000}])
    assert not registry.record_catalog([_candidate("0")])
    assert registry.snapshot()["candidates"] == []


def test_full_verified_case_calculates_investment_and_payback(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    result = registry.snapshot(cash=20000, reserve=2000)
    row = result["candidates"][0]
    assert result["available_cash"] == 18000
    assert row["status"] == "viavel"
    assert row["investment"] == 16000
    assert row["payback_days"] == 8
    assert registry.snapshot(cash=15000, reserve=2000)["candidates"][0]["status"] == "saldo_insuficiente"
    assert registry.snapshot(cash=20000, reserve=2000, owned_hub_ids={"123"})["candidates"] == []


def test_point_cost_is_preserved_and_blocks_incomplete_financial_recommendation(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([{**_candidate(), "hub_points": 20}])
    assert registry.record_research("123", _research())
    candidate = registry.snapshot(cash=50000)["candidates"][0]
    assert candidate["hub_price"] == 5000
    assert candidate["hub_points"] == 20
    assert candidate["investment"] == 16000
    assert candidate["status"] == "dados_a_confirmar"

    assert not registry.record_catalog([{**_candidate(), "hub_points": "20"}])
    assert registry.snapshot(cash=50000)["candidates"][0]["hub_points"] == 20
    assert registry.record_catalog([{**_candidate(), "hub_points": 0}])
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "viavel"


def test_missing_prices_bad_demand_and_missing_cash_are_pending(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.record_catalog([_candidate(price=None)])
    registry.record_research("123", _research())
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "dados_a_confirmar"
    registry.record_catalog([_candidate(price=5000)])
    registry.record_research("123", _research(demand_verified=False))
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "dados_a_confirmar"
    registry.record_research("123", _research())
    assert registry.snapshot()["candidates"][0]["status"] == "dados_a_confirmar"
    assert registry.snapshot(cash=50000, now=9999999999)["candidates"][0]["status"] == "dados_a_confirmar"


def test_loss_and_partial_catalog_merge(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.record_catalog([_candidate(), _candidate("456", 4000)])
    registry.record_research("123", _research(profit_per_day=-300))
    statuses = {r["id"]: r["status"] for r in registry.snapshot(cash=50000)["candidates"]}
    assert statuses == {"123": "sem_lucro", "456": "dados_a_confirmar"}
    registry.record_catalog([_candidate("789", 3000)], complete=False)
    assert len(registry.snapshot(cash=50000)["candidates"]) == 3
    registry.record_catalog([_candidate("789", 3000)], complete=True)
    assert len(registry.snapshot(cash=50000)["candidates"]) == 1


def test_partial_refresh_ages_each_candidate_independently(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456", 3000)], complete=False)
    assert registry.record_research("123", _research())
    assert registry.record_research("456", _research(airport_id="456"))

    snapshot = registry.snapshot(cash=50000, now=clock[0])
    rows = {row["id"]: row for row in snapshot["candidates"]}
    assert snapshot["observed_at"] == clock[0]
    assert snapshot["catalog_complete"] is False
    assert rows["123"]["observed_at"] == clock[0] - MAX_AGE_SECONDS - 1
    assert rows["123"]["status"] == "dados_a_confirmar"
    assert rows["456"]["observed_at"] == clock[0]
    assert rows["456"]["status"] == "viavel"

    assert registry.record_catalog([_candidate("123", 6000)], complete=False)
    refreshed = {row["id"]: row for row in registry.snapshot(cash=50000, now=clock[0])["candidates"]}
    assert refreshed["123"]["observed_at"] == clock[0]
    assert refreshed["123"]["investment"] == 17000
    assert refreshed["123"]["status"] == "viavel"
    assert refreshed["456"]["observed_at"] == clock[0]


def test_legacy_catalog_timestamp_survives_partial_merge(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())

    legacy = json.loads(registry.path.read_text(encoding="utf-8"))
    del legacy["candidates"][0]["observed_at"]
    registry.path.write_text(json.dumps(legacy), encoding="utf-8")
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["observed_at"] == clock[0]

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456")], complete=False)
    assert registry.record_research("123", _research())
    rows = {row["id"]: row for row in registry.snapshot(cash=50000, now=clock[0])["candidates"]}
    assert rows["123"]["observed_at"] == legacy["observed_at"]
    assert rows["123"]["status"] == "dados_a_confirmar"
    assert rows["456"]["observed_at"] == clock[0]
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    assert {row["id"]: row["observed_at"] for row in persisted["candidates"]} == {
        "123": legacy["observed_at"], "456": clock[0]}


def test_complete_refresh_discards_unseen_and_updates_seen_candidate(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")])
    assert registry.record_research("456", _research(airport_id="456"))

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456", 7000)], complete=True)
    snapshot = registry.snapshot(cash=50000, now=clock[0])
    assert snapshot["catalog_complete"] is True
    assert len(snapshot["candidates"]) == 1
    row = snapshot["candidates"][0]
    assert row["id"] == "456"
    assert row["observed_at"] == clock[0]
    assert row["hub_price"] == 7000
    assert row["scenario"]["observed_at"] == clock[0] - MAX_AGE_SECONDS - 1
    assert row["status"] == "dados_a_confirmar"

    assert registry.record_research("456", _research(airport_id="456"))
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"


def test_conflicting_catalog_duplicates_cannot_replace_verified_evidence(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    original = registry.path.read_bytes()

    assert not registry.record_catalog([_candidate(price=8000), _candidate(price=9000)], complete=True)
    assert registry.path.read_bytes() == original

    assert registry.record_catalog([_candidate(price=8000), _candidate(price=8000)])
    rows = registry.snapshot(cash=50000)["candidates"]
    assert len(rows) == 1
    assert rows[0]["hub_price"] == 8000


@pytest.mark.parametrize("purchasability_order", [(True, False), (False, True)])
def test_conflicting_duplicate_purchasability_cannot_create_candidate(
        tmp_path, purchasability_order):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    options = [{**_candidate(), "purchasable": value}
               for value in purchasability_order]

    assert not registry.record_catalog(options, complete=True)
    assert registry.snapshot(cash=50000)["candidates"] == []
    assert not registry.path.exists()


def test_negative_purchase_evidence_survives_partial_pages_and_restart(
        tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    positive_at = clock[0] - 0.8
    denied_at = clock[0] - 0.5

    assert registry.record_catalog([_candidate(), _candidate("456")],
                                   observed_at=positive_at)
    assert registry.record_catalog([{**_candidate(), "purchasable": False}],
                                   observed_at=denied_at)
    restarted = HubExpansionRegistry(registry.path)
    assert {row["id"] for row in restarted.snapshot(now=clock[0])["candidates"]} == {"456"}

    # A page captured before the denial cannot restore the airport.
    assert restarted.record_catalog([_candidate(price=2000)],
                                    observed_at=clock[0] - 0.6)
    assert {row["id"] for row in restarted.snapshot(now=clock[0])["candidates"]} == {"456"}

    # A verified later positive reading restores it, even after restart.
    assert restarted.record_catalog([_candidate(price=7000)],
                                    observed_at=clock[0] - 0.1)
    rows = {row["id"]: row for row in registry.snapshot(now=clock[0])["candidates"]}
    assert set(rows) == {"123", "456"}
    assert rows["123"]["hub_price"] == 7000


def test_negative_evidence_at_equal_timestamp_wins_until_newer_read(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    stamp = clock[0] - 0.6

    assert registry.record_catalog([_candidate()], observed_at=stamp)
    assert registry.record_catalog([{**_candidate(), "purchasable": False}],
                                   observed_at=stamp)
    assert registry.record_catalog([_candidate()], observed_at=stamp)
    assert registry.snapshot(now=clock[0])["candidates"] == []
    assert registry.snapshot(now=clock[0])["availability_pending"] is True
    assert registry.record_catalog([_candidate()], observed_at=clock[0] - 0.1)
    assert len(registry.snapshot(now=clock[0])["candidates"]) == 1


def test_complete_catalog_with_only_unavailable_options_is_conclusive(
        tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()], observed_at=clock[0] - 0.8)
    assert registry.record_catalog([{**_candidate(), "purchasable": False}],
                                   complete=True, observed_at=clock[0] - 0.1)

    result = HubExpansionRegistry(registry.path).snapshot(now=clock[0])
    assert result["candidates"] == []
    assert result["catalog_complete"] is True
    assert result["availability_pending"] is False


def test_unavailable_option_without_valid_id_blocks_complete_coverage(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([
        _candidate(), {"id": "invalid", "purchasable": False}], complete=True)
    assert registry.snapshot()["catalog_complete"] is False


def test_unknown_purchasability_keeps_catalog_scan_incomplete(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")], complete=True)

    malformed = {**_candidate(), "purchasable": "false"}
    assert registry.record_catalog([_candidate("789"), malformed], complete=True)

    snapshot = registry.snapshot(cash=50000)
    assert {row["id"] for row in snapshot["candidates"]} == {"123", "456", "789"}
    assert snapshot["catalog_complete"] is False


def test_catalog_preserves_subsecond_read_time_and_rejects_delayed_replays(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(price=5000)], observed_at=clock[0] - 0.7)
    assert registry.record_catalog([_candidate(price=7000)], observed_at=clock[0] - 0.2)
    assert registry.record_catalog([_candidate(price=6000)], observed_at=clock[0] - 0.4)

    row = registry.snapshot(now=clock[0])["candidates"][0]
    assert row["hub_price"] == 7000
    assert row["observed_at"] == clock[0] - 0.2
    assert row["hub_price_observed_at"] == clock[0] - 0.2
    assert registry.snapshot(now=clock[0])["observed_at"] == clock[0] - 0.2
    assert HubExpansionRegistry(registry.path).snapshot(now=clock[0])["candidates"][0]["hub_price"] == 7000


def test_catalog_equal_time_price_and_points_conflicts_need_new_evidence(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    stamp = clock[0] - 0.6
    assert registry.record_catalog([{**_candidate(price=5000), "hub_points": 20}],
                                   observed_at=stamp)
    assert registry.record_research("123", _research())
    assert registry.record_catalog([{**_candidate(price=8000), "hub_points": 30}],
                                   observed_at=stamp)

    row = HubExpansionRegistry(registry.path).snapshot(cash=50000, now=clock[0])["candidates"][0]
    assert row["hub_price"] is None and row["hub_points"] is None
    assert row["status"] == "dados_a_confirmar"
    assert {"preco_hub_conflitante", "pontos_hub_conflitantes"} <= set(row["pending"])
    saved = json.loads(registry.path.read_text(encoding="utf-8"))["candidates"][0]
    assert saved["hub_price_conflict_at"] == stamp
    assert saved["hub_points_conflict_at"] == stamp
    assert registry.record_catalog([{**_candidate(price=8000), "hub_points": 30}],
                                   observed_at=stamp)
    assert registry.snapshot(now=clock[0])["candidates"][0]["hub_price"] is None

    assert registry.record_catalog([{**_candidate(price=8000), "hub_points": 0}],
                                   observed_at=clock[0] - 0.1)
    recovered = registry.snapshot(cash=50000, now=clock[0])["candidates"][0]
    assert recovered["hub_price"] == 8000 and recovered["hub_points"] == 0
    assert recovered["status"] == "viavel"
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))["candidates"][0]
    assert "hub_price_conflict_at" not in persisted
    assert "hub_points_conflict_at" not in persisted


def test_catalog_reconciles_price_and_points_using_independent_clocks(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    early = clock[0] - 0.8
    points_at = clock[0] - 0.1
    price_at = clock[0] - 0.3

    assert registry.record_catalog([{**_candidate(price=5000), "hub_points": 10}],
                                   observed_at=early)
    assert registry.record_catalog([{**_candidate(price=None), "hub_points": 20}],
                                   observed_at=points_at)
    price_only = _candidate(price=7000)
    del price_only["hub_points"]
    assert registry.record_catalog([price_only], observed_at=price_at)

    row = registry.snapshot(now=clock[0])["candidates"][0]
    assert row["hub_price"] == 7000
    assert row["hub_points"] == 20
    assert row["hub_price_observed_at"] == price_at
    assert row["hub_points_observed_at"] == points_at
    assert row["observed_at"] == points_at


def test_delayed_complete_hub_scan_keeps_newer_airports_and_completion(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()], complete=True,
                                   observed_at=clock[0] - 0.7)
    assert registry.record_catalog([_candidate("456", 8000)], observed_at=clock[0] - 0.2)
    assert registry.record_catalog([_candidate(price=4000)], complete=True,
                                   observed_at=clock[0] - 0.5)
    snapshot = registry.snapshot(now=clock[0])
    assert {row["id"] for row in snapshot["candidates"]} == {"123", "456"}
    assert snapshot["catalog_complete"] is False
    assert {row["id"]: row["hub_price"] for row in snapshot["candidates"]} == {
        "123": 4000, "456": 8000}
    assert snapshot["observed_at"] == clock[0] - 0.2

    assert registry.record_catalog([_candidate("456", 7000)], complete=True,
                                   observed_at=clock[0] - 0.1)
    after = registry.snapshot(now=clock[0])
    assert after["catalog_complete"] is True
    assert [(row["id"], row["hub_price"]) for row in after["candidates"]] == [("456", 7000)]


def test_stale_partial_page_cannot_restore_airport_removed_by_newer_complete_scan(tmp_path, monkeypatch):
    clock = [1_900_000_000.9]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")],
                                   observed_at=clock[0] - 0.7)
    assert registry.record_catalog([_candidate("456", 7000)], complete=True,
                                   observed_at=clock[0] - 0.2)
    before = registry.path.read_bytes()

    assert not registry.record_catalog([_candidate(price=9000)],
                                       observed_at=clock[0] - 0.4)
    assert registry.path.read_bytes() == before
    snapshot = registry.snapshot(now=clock[0])
    assert snapshot["catalog_complete"] is True
    assert [item["id"] for item in snapshot["candidates"]] == ["456"]


@pytest.mark.parametrize("stamp", [True, 0, -1, float("nan"), float("inf"),
                                      1_900_000_001, 1_900_000_000 - MAX_AGE_SECONDS - 1])
def test_catalog_rejects_invalid_or_outdated_read_timestamps(tmp_path, monkeypatch, stamp):
    monkeypatch.setattr("hub_expansion.time.time", lambda: 1_900_000_000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert not registry.record_catalog([_candidate()], observed_at=stamp)
    assert not registry.path.exists()


def test_partial_catalog_cannot_be_mistaken_for_complete_scan(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")], complete=True)

    # A malformed purchasable option means this is not a proven complete scan.
    assert registry.record_catalog([_candidate("789"), {"id": "INVALID", "purchasable": True}],
                                   complete=True)
    snapshot = registry.snapshot()
    assert {row["id"] for row in snapshot["candidates"]} == {"123", "456", "789"}
    assert snapshot["catalog_complete"] is False

    # Legacy callers must pass the literal boolean True to prune unseen rows.
    assert registry.record_catalog([_candidate("789")], complete="false")
    assert len(registry.snapshot()["candidates"]) == 3


def test_legacy_candidate_types_are_sanitized_and_merged(tmp_path, monkeypatch):
    monkeypatch.setattr("hub_expansion.time.time", lambda: 1800000000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.path.write_text(json.dumps({
        "source": "game_purchase_catalog", "observed_at": 1800000000,
        "candidates": [None, "broken", {"id": {"malformed": True}},
                       {"id": 123, "name": 123, "code": ["XAP"], "hub_price": "5000",
                        "scenario": {"source": "game_research", "observed_at": 1800000000,
                                     **{k: v for k, v in _legacy_research().items() if k != "source"}}}],
    }), encoding="utf-8")

    rows = registry.snapshot(cash=50000, now=1800000000)["candidates"]
    assert len(rows) == 1
    assert rows[0]["id"] == "123"
    assert isinstance(rows[0]["code"], str)
    assert rows[0]["status"] == "dados_a_confirmar"
    assert "motor_a_confirmar" in rows[0]["pending"]

    assert registry.record_research("123", _research())
    assert registry.record_catalog([_candidate("456")], complete=False)
    merged = registry.snapshot(cash=50000, now=1800000000)
    assert {row["id"] for row in merged["candidates"]} == {"123", "456"}
    assert next(row for row in merged["candidates"] if row["id"] == "123")["status"] == "dados_a_confirmar"

    registry.path.write_text(json.dumps({"candidates": None}), encoding="utf-8")
    assert registry.snapshot()["availability_pending"] is True
    assert not registry.record_research("123", _research())
    assert registry.record_catalog([_candidate()])


def test_legacy_boolean_research_timestamp_is_not_fresh(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.path.write_text(json.dumps({
        "observed_at": 1, "source": "game_purchase_catalog",
        "candidates": [{"id": "123", "name": "Chapecó", "code": "XAP", "hub_price": 5000,
                        "observed_at": 1,
                        "scenario": {"observed_at": True, **_legacy_research()}}],
    }), encoding="utf-8")
    assert registry.snapshot(cash=50000, now=1)["candidates"][0]["status"] == "dados_a_confirmar"


def test_lower_investment_breaks_equal_daily_profit_tie(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate("123", 9000), _candidate("456", 1000)])
    assert registry.record_research("123", _research())
    assert registry.record_research("456", _research(airport_id="456"))
    rows = registry.snapshot(cash=50000)["candidates"]
    assert [row["id"] for row in rows] == ["456", "123"]
    assert rows[0]["payback_days"] < rows[1]["payback_days"]


@pytest.mark.parametrize("invalid_timestamp", [None, True, "1800000000", 1800000001])
def test_invalid_or_future_candidate_timestamp_is_not_fresh(tmp_path, monkeypatch, invalid_timestamp):
    monkeypatch.setattr("hub_expansion.time.time", lambda: 1800000000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    saved["candidates"][0]["observed_at"] = invalid_timestamp
    registry.path.write_text(json.dumps(saved), encoding="utf-8")
    row = registry.snapshot(cash=50000, now=1800000000)["candidates"][0]
    assert row["observed_at"] == invalid_timestamp
    assert row["status"] == "dados_a_confirmar"


def test_legacy_research_is_readable_but_never_proves_a_purchase(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _legacy_research())

    legacy = registry.snapshot(cash=50000)["candidates"][0]
    assert legacy["scenario"]["aircraft_price"] == 10000
    assert legacy["profit_per_day"] == 2000
    assert legacy["engine_id"] is None
    assert legacy["status"] == "dados_a_confirmar"
    assert legacy["ranking_conclusive"] is False
    assert legacy["purchase_evidence"] is False
    assert "motor_a_confirmar" in legacy["pending"]

    assert registry.record_research("123", _research())
    verified = registry.snapshot(cash=50000)["candidates"][0]
    assert verified["status"] == "viavel"
    assert verified["ranking_conclusive"] is True
    assert verified["purchase_evidence"] is True
    assert len(verified["alternatives"]) == 2
    assert any(option["engine_id"] is None and not option["purchase_evidence"]
               for option in verified["alternatives"])


@pytest.mark.parametrize("invalid_id", [None, True, False, "", "has space", "#bad", {}, []])
def test_invalid_explicit_engine_id_is_rejected_without_erasing_research(tmp_path, invalid_id):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    original = registry.path.read_bytes()

    assert not registry.record_research("123", _research(engine_id=invalid_id))
    assert registry.path.read_bytes() == original
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "viavel"


def test_event_demand_blocks_otherwise_viable_external_research(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", {**_research(), "event_demand_boosted": True})
    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert "demanda_evento_temporario" in result["pending"]
    assert result["purchase_evidence"] is False


def test_distinct_engines_models_and_routes_have_independent_economics(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())

    other_engine = _research(engine_id="engine-fixture-2", model="model-fixture-2",
                             route="different-fixture-route", destination_id="789")
    other_engine["costs"].update({"aircraft_price": 11000,
                                  "aircraft_price_includes_engine": False,
                                  "engine_delta_cost": 1500, "route_fee": 200,
                                  "hangar_price": 300, "other_fees": 50})
    other_engine["financial"]["profit_per_day"] = 2500
    assert registry.record_research("123", other_engine)

    result = registry.snapshot(cash=30000, reserve=2000)["candidates"][0]
    assert len(result["alternatives"]) == 2
    assert {option["engine_id"] for option in result["alternatives"]} == {
        "engine-fixture-1", "engine-fixture-2"}
    assert result["engine_id"] == "engine-fixture-2"
    assert result["scenario"]["model"] == "model-fixture-2"
    assert result["status"] == "viavel"
    assert result["ranking_conclusive"] is True
    assert result["purchase_evidence"] is True
    assert result["investment"] == 18050
    assert result["payback_days"] == 7.2
    assert result["cost_breakdown"] == {
        "hub_price": 5000, "hub_points": 0, "aircraft_price": 11000,
        "aircraft_price_includes_engine": False, "engine_delta_cost": 1500,
        "engine_extra_charged": 1500, "route_fee": 200, "hangar_price": 300,
        "other_fees": 50, "reserve": 2000, "cash_required": 20050, "total": 18050}

    # A newer observation replaces only the same variant/route identity.
    assert registry.record_research("123", _research())
    assert len(registry.snapshot(cash=30000)["candidates"][0]["alternatives"]) == 2


def test_delayed_external_research_cannot_replace_latest_engine_route(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    latest = _research(observed_at=int(time.time()) - 10)
    assert registry.record_research("123", latest)
    original_bytes = registry.path.read_bytes()

    delayed = deepcopy(latest)
    delayed["observed_at"] -= 5
    delayed["financial"]["profit_per_day"] = -500
    assert registry.record_research("123", delayed)
    assert registry.path.read_bytes() == original_bytes

    reopened = HubExpansionRegistry(registry.path)
    row = reopened.snapshot(cash=50000)["candidates"][0]
    assert row["status"] == "viavel"
    assert row["profit_per_day"] == 2000
    assert len(row["alternatives"]) == 1


def test_equal_time_external_research_conflict_is_durable_and_requires_new_read(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    first = _research(observed_at=int(time.time()) - 15)
    contradictory = deepcopy(first)
    contradictory["financial"]["profit_per_day"] = 4000
    assert registry.record_research("123", first)
    assert registry.record_research("123", contradictory)

    reopened = HubExpansionRegistry(registry.path)
    quarantined = reopened.snapshot(cash=50000)["candidates"][0]
    assert quarantined["status"] == "dados_a_confirmar"
    assert len(quarantined["alternatives"]) == 2
    assert all("pesquisa_externa_conflitante" in option["pending"]
               and not option["ranking_conclusive"]
               and not option["purchase_evidence"]
               for option in quarantined["alternatives"])

    unchanged = registry.path.read_bytes()
    assert reopened.record_research("123", first)
    assert reopened.record_research("123", contradictory)
    assert registry.path.read_bytes() == unchanged

    repaired = deepcopy(contradictory)
    repaired["observed_at"] += 1
    assert reopened.record_research("123", repaired)
    resolved = reopened.snapshot(cash=50000)["candidates"][0]
    assert resolved["status"] == "viavel"
    assert resolved["profit_per_day"] == 4000
    assert len(resolved["alternatives"]) == 1
    assert "pesquisa_externa_conflitante" not in resolved["pending"]


def test_future_research_recovers_after_reopening_and_preserves_other_engine(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    valid = _research()
    assert registry.record_research("123", valid)
    assert registry.record_research("123", _research(engine_id="other-engine"))
    assert not registry.record_research("123", _research(observed_at=time.time() + 1000))
    for block in ("costs", "financial"):
        future = deepcopy(valid)
        future[block]["observed_at"] = time.time() + 1000
        assert not registry.record_research("123", future)
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    candidate = saved["candidates"][0]
    poisoned = deepcopy(candidate["scenarios"][0])
    poisoned["observed_at"] += 1000
    candidate["scenarios"].append(poisoned)
    candidate["scenario"] = poisoned
    registry.path.write_text(json.dumps(saved), encoding="utf-8")
    reopened = HubExpansionRegistry(registry.path)
    assert reopened.record_research("123", valid)
    row = reopened.snapshot(cash=50000)["candidates"][0]
    assert {option["engine_id"] for option in row["alternatives"]} == {
        "engine-fixture-1", "other-engine"}
    assert all(option["purchase_evidence"] for option in row["alternatives"])
    assert len(row["alternatives"]) == 2


def test_future_nested_proof_recovery_preserves_valid_conflicts(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    valid = _research()
    conflict = deepcopy(valid)
    conflict["financial"]["profit_per_day"] = 3000
    assert registry.record_research("123", valid)
    assert registry.record_research("123", conflict)
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    candidate = saved["candidates"][0]
    poisoned = deepcopy(candidate["scenarios"][0])
    poisoned["costs"]["observed_at"] += 1000
    candidate["scenarios"].append(poisoned)
    candidate["scenario"] = poisoned
    registry.path.write_text(json.dumps(saved), encoding="utf-8")
    reopened = HubExpansionRegistry(registry.path)
    assert reopened.record_research("123", valid)
    row = reopened.snapshot(cash=50000)["candidates"][0]
    assert len(row["alternatives"]) == 2
    assert all("pesquisa_externa_conflitante" in item["pending"]
               for item in row["alternatives"])


def test_excluded_costs_survive_reopening_and_block_purchase(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research(excluded_costs=["A-check"])
    research["costs"]["excluded_costs"] = ["Reparos"]
    research["financial"]["excluded_costs"] = ["A-check", "Manutenção"]
    assert registry.record_research("123", research)
    row = HubExpansionRegistry(registry.path).snapshot(cash=50000)["candidates"][0]
    assert row["status"] == "projecao_condicional"
    assert row["purchase_evidence"] is row["ranking_conclusive"] is False
    assert row["payback_days"] == 8
    assert row["scenario"]["costs"]["excluded_costs"] == ["Reparos"]
    assert row["scenario"]["financial"]["excluded_costs"] == ["A-check", "Manutenção"]
    research["financial"]["excluded_costs"] = "inválido"
    research["observed_at"] -= 10
    # A delayed malformed reading cannot replace newer evidence.
    assert registry.record_research("123", research)
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "projecao_condicional"


def test_malformed_excluded_costs_are_not_silently_discarded(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research["financial"]["excluded_costs"] = "inválido"
    assert registry.record_research("123", research)
    row = HubExpansionRegistry(registry.path).snapshot(cash=50000)["candidates"][0]
    assert row["status"] == "dados_a_confirmar"
    assert "custos_excluidos_invalidos" in row["pending"]
    assert row["scenario"]["financial"]["excluded_costs"] is None


def test_external_research_conflict_is_local_to_the_engine_route(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    first = _research(observed_at=int(time.time()) - 20)
    independent = _research(engine_id="engine-fixture-2",
                            observed_at=first["observed_at"])
    # The nested cost and profit evidence must refer to the alternate motor.
    independent["costs"]["engine_id"] = "engine-fixture-2"
    independent["financial"]["engine_id"] = "engine-fixture-2"
    assert registry.record_research("123", first)
    assert registry.record_research("123", independent)
    conflicting = deepcopy(first)
    conflicting["route_feasible"] = False
    assert registry.record_research("123", conflicting)

    row = registry.snapshot(cash=50000)["candidates"][0]
    assert row["status"] == "viavel"
    assert row["engine_id"] == "engine-fixture-2"
    assert len(row["alternatives"]) == 3
    assert sum("pesquisa_externa_conflitante" in option["pending"]
               for option in row["alternatives"]) == 2


def test_native_model_and_itinerary_are_independent_of_display_names(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    stamp = int(time.time()) - 20
    original = _research(observed_at=stamp)
    assert registry.record_research("123", original)
    before = registry.path.read_bytes()
    renamed = deepcopy(original)
    for proof in (renamed, renamed["costs"], renamed["financial"]):
        proof.update(model="updated name", route="updated display")
    assert registry.record_research("123", renamed)
    assert registry.path.read_bytes() == before
    renamed["observed_at"] += 1
    assert registry.record_research("123", renamed)
    assert registry.record_research("123", _research(model_id="102", observed_at=stamp))
    assert registry.record_research("123", _research(stopover_id="777", observed_at=stamp))
    assert registry.record_research("123", _research(stopover_id="888", observed_at=stamp))
    historical = deepcopy(original)
    for proof in (historical, historical["costs"], historical["financial"]):
        del proof["stopover_id"]
    assert registry.record_research("123", historical)

    row = HubExpansionRegistry(registry.path).snapshot(cash=50000)["candidates"][0]
    assert len(row["alternatives"]) == 5
    direct = [option for option in row["alternatives"] if option["purchase_evidence"]]
    assert {option["model_id"] for option in direct} == {"101", "102"}
    assert next(option for option in direct if option["model_id"] == "101")["model"] == "updated name"
    historical = next(option for option in row["alternatives"] if "stopover_id" not in option)
    assert "identidade_nativa_a_confirmar" in historical["pending"]
    for option in row["alternatives"]:
        if option.get("stopover_id") in ("777", "888"):
            assert option["pending"] == ["regras_escala_a_confirmar"]
            assert not option["purchase_evidence"]


@pytest.mark.parametrize("field,value", [
    ("model_id", None), ("model_id", True), ("model_id", "invalid"),
    ("stopover_id", True), ("stopover_id", ""), ("stopover_id", "123"),
    ("stopover_id", "456"),
])
def test_invalid_native_identity_does_not_replace_a_valid_scenario(tmp_path, field, value):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    before = registry.path.read_bytes()
    assert not registry.record_research("123", _research(**{field: value}))
    assert registry.path.read_bytes() == before


@pytest.mark.parametrize("block", ["costs", "financial"])
@pytest.mark.parametrize("field", ["model_id", "stopover_id"])
def test_missing_native_proof_field_blocks_ranking(tmp_path, block, field):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    del research[block][field]
    assert registry.record_research("123", research)
    row = registry.snapshot(cash=50000)["candidates"][0]
    assert not row["purchase_evidence"]


def test_invalid_nested_scale_does_not_become_direct_and_scope_is_preserved(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research["snapshot_id"] = "capture-a"
    research["costs"].update(stopover_id=False, snapshot_id="capture-b")
    assert registry.record_research("123", research)
    row = HubExpansionRegistry(registry.path).snapshot(cash=50000)["candidates"][0]
    assert not row["purchase_evidence"]
    assert row["scenario"]["costs"]["stopover_id"] is not None
    assert "custos_motor_rota_a_confirmar" in row["pending"]
    assert "escopo_pesquisa_divergente" in row["pending"]


def test_persisted_stale_variant_cannot_override_newer_incomplete_research(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research(observed_at=int(time.time()) - 20))
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    row = saved["candidates"][0]
    newer = deepcopy(row["scenarios"][0])
    newer["observed_at"] += 1
    newer["demand_verified"] = False
    row["scenarios"].append(newer)
    registry.path.write_text(json.dumps(saved), encoding="utf-8")

    evaluated = HubExpansionRegistry(registry.path).snapshot(cash=50000)["candidates"][0]
    assert len(evaluated["alternatives"]) == 1
    assert evaluated["status"] == "dados_a_confirmar"
    assert "demanda_externa_a_confirmar" in evaluated["pending"]
    assert evaluated["purchase_evidence"] is False


@pytest.mark.parametrize("field", ["aircraft_price", "route_fee", "hangar_price", "other_fees",
                                     "aircraft_price_includes_engine"])
def test_missing_cost_components_cannot_support_a_recommendation(tmp_path, field):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research["costs"].pop(field)
    assert registry.record_research("123", research)

    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert result["ranking_conclusive"] is False
    assert result["purchase_evidence"] is False
    assert "custos_motor_rota_a_confirmar" in result["pending"]


@pytest.mark.parametrize("engine_delta", [None, -1, "invalid"])
def test_engine_delta_required_when_price_does_not_include_engine(tmp_path, engine_delta):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research["costs"]["aircraft_price_includes_engine"] = False
    research["costs"]["engine_delta_cost"] = engine_delta
    assert registry.record_research("123", research)
    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["investment"] is None
    assert result["purchase_evidence"] is False
    assert "custos_motor_rota_a_confirmar" in result["pending"]


@pytest.mark.parametrize("invalid_delta", [100, -1, "invalid", True])
def test_inconsistent_included_engine_price_cannot_be_ranked(tmp_path, invalid_delta):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research["costs"]["engine_delta_cost"] = invalid_delta
    assert registry.record_research("123", research)
    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert result["purchase_evidence"] is False
    assert "custos_motor_rota_a_confirmar" in result["pending"]


def test_unbounded_total_cost_cannot_support_a_conclusive_ranking(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(price=1e308)])
    research = _research()
    research["costs"]["aircraft_price"] = 1e308
    assert registry.record_research("123", research)
    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["investment"] is None
    assert result["ranking_conclusive"] is False
    assert result["purchase_evidence"] is False


@pytest.mark.parametrize("block", ["costs", "financial"])
@pytest.mark.parametrize("identity_field,bad_value", [
    ("model_id", "102"), ("engine_id", "other-engine"),
    ("origin_id", "789"), ("destination_id", "999"),
    ("stopover_id", "999")])
def test_cost_and_profit_proofs_must_match_exact_scenario_identity(
        tmp_path, block, identity_field, bad_value):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    research[block][identity_field] = bad_value
    assert registry.record_research("123", research)

    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert result["ranking_conclusive"] is False
    assert result["purchase_evidence"] is False
    expected = "custos_motor_rota_a_confirmar" if block == "costs" else "lucro_motor_rota_a_confirmar"
    assert expected in result["pending"]


@pytest.mark.parametrize("expired_part,reason", [
    ("research", "pesquisa_desatualizada"),
    ("costs", "custos_motor_rota_a_confirmar"),
    ("financial", "lucro_motor_rota_a_confirmar")])
def test_expired_scenario_or_nested_evidence_blocks_purchase(
        tmp_path, monkeypatch, expired_part, reason):
    clock = 1800000000
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    research = _research()
    old = clock - MAX_AGE_SECONDS - 1
    if expired_part == "research":
        research["observed_at"] = old
    else:
        research[expired_part]["observed_at"] = old
    assert registry.record_research("123", research)

    result = registry.snapshot(cash=50000, now=clock)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert result["purchase_evidence"] is False
    assert reason in result["pending"]


def test_missing_points_and_expired_points_are_not_revalidated_by_price_only_scan(
        tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    no_points = _candidate()
    del no_points["hub_points"]
    assert registry.record_catalog([no_points])
    assert registry.record_research("123", _research())
    missing = registry.snapshot(cash=50000)["candidates"][0]
    assert missing["hub_points"] is None
    assert missing["purchase_evidence"] is False
    assert "pontos_a_confirmar" in missing["pending"]

    assert registry.record_catalog([_candidate()])
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "viavel"
    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([no_points])
    assert registry.record_research("123", _research())
    stale = registry.snapshot(cash=50000, now=clock[0])["candidates"][0]
    assert stale["hub_price"] == 5000
    assert stale["hub_points"] == 0
    assert stale["status"] == "dados_a_confirmar"
    assert "pontos_desatualizados" in stale["pending"]

    assert registry.record_catalog([_candidate()])
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"


def test_price_only_incomplete_refresh_preserves_old_catalog_price_and_age(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    clock[0] += MAX_AGE_SECONDS + 1

    assert registry.record_catalog([_candidate(price=None)])
    assert registry.record_research("123", _research())
    saved = registry.snapshot(cash=50000, now=clock[0])["candidates"][0]
    assert saved["hub_price"] == 5000
    assert saved["hub_price_observed_at"] == clock[0] - MAX_AGE_SECONDS - 1
    assert saved["status"] == "dados_a_confirmar"
    assert "preco_hub_a_confirmar" in saved["pending"]

    assert registry.record_catalog([_candidate()])
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"


def test_conflicting_persisted_duplicates_cannot_reuse_variant_proof(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    saved["candidates"].append(deepcopy(saved["candidates"][0]))
    registry.path.write_text(json.dumps(saved), encoding="utf-8")

    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert result["ranking_conclusive"] is False
    assert result["purchase_evidence"] is False
    assert result["alternatives"] == []


def test_conflicting_legacy_slot_cannot_hide_same_time_native_observation(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    row = saved["candidates"][0]
    row["scenario"]["financial"]["profit_per_day"] = 1234
    registry.path.write_text(json.dumps(saved), encoding="utf-8")

    result = registry.snapshot(cash=50000)["candidates"][0]
    assert result["status"] == "dados_a_confirmar"
    assert "pesquisa_externa_conflitante" in result["pending"]
    assert len(result["alternatives"]) == 2


def test_expansion_dashboard_is_only_a_get_endpoint():
    from conftest import ROOT
    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'api("/api/hubs/expansion")' in page
    assert 'url.path == "/api/hubs/expansion"' in web
    assert 'id="hubExpansionGrid"' in page
