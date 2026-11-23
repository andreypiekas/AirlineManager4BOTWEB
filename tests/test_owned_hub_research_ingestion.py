"""Observed research inputs reach the ranking without authorizing purchases."""
from __future__ import annotations

import time
import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import economy
import engine_catalog
import hub_expansion
import hub_registry
import owned_hub_research_ingestion as ingestion
import paths
import route_registry
from hub_recommendations import rank_next_aircraft
from owned_hub_research_feed import build_owned_hub_research_queue
from owned_hub_research_feed import MAX_EVIDENCE_AGE
from owned_hub_research_ingestion import (
    OwnedHubResearchInputsRegistry, ingest_owned_hub_research_inputs,
)


NOW = 1_900_000_000


def _inputs(now=NOW):
    inventory = {"source": "game_hub_select", "observed_at": now,
                 "hubs": [{"id": "2926", "code": "XAP"}]}
    routes = [{"source": "game_route_search", "observed_at": now,
               "origin_id": "2926", "destination_id": "3139",
               "distance_km": 2000, "y": 100, "j": 20, "f": 5}]
    market = {"source": "bot_aircraft_market_cache", "observed_at": now,
              "fresh": True, "models": [
                  {"id": 11, "name": "A320", "range": 6000,
                   "capacity": 180, "price": 1700000},
                  {"id": 22, "name": "B737", "range": 7000,
                   "capacity": 190, "price": 1900000},
              ]}
    return inventory, routes, market


def _queue(now=NOW):
    inventory, routes, market = _inputs(now)
    return build_owned_hub_research_queue(inventory, routes, market, now=now)


def test_observed_inputs_persist_and_remain_unpurchaseable(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    page = _queue()
    assert registry.record_queue(page, now=NOW) == 2
    stored = registry.snapshot(now=NOW)
    assert len(stored) == 2
    a320 = next(row for row in stored if row["model"] == "A320")
    assert a320["source"] == "derived_research_queue"
    assert a320["observed_demand"] == {"y": 100, "j": 20, "f": 5}
    assert a320["demand_remaining"] is None
    assert a320["costs"] == {}
    assert a320["financial"] == {}
    assert a320["research_evidence"]["route"]["observed_at"] == NOW
    assert "preco_final_motor_a_confirmar" in a320["research_pending"]

    report = rank_next_aircraft(
        _inputs()[0], stored, route_report={"relations": []},
        cash=10_000_000, cash_observed_at=NOW, now=NOW,
    )
    assert report["recommendations"] == []
    assert len(report["candidates"]) == 2
    assert all(candidate["status"] == "dados_a_confirmar"
               for candidate in report["candidates"])
    assert all("pesquisa_complementar_a_confirmar" in candidate["pending"]
               for candidate in report["candidates"])
    assert all(candidate["profit_per_day"] is None
               and candidate["investment"] is None for candidate in report["candidates"])


def test_persisted_inputs_are_isolated_idempotent_and_expire(tmp_path):
    first = OwnedHubResearchInputsRegistry(tmp_path / "company-a.json")
    other = OwnedHubResearchInputsRegistry(tmp_path / "company-b.json")
    page = _queue()
    assert first.record_queue(page, now=NOW) == 2
    original = first.path.read_bytes()
    assert first.record_queue(page, now=NOW) == 2
    assert first.path.read_bytes() == original
    assert other.snapshot(now=NOW) == []

    copied = first.snapshot(now=NOW)
    copied[0]["observed_demand"]["y"] = 10_000
    assert first.snapshot(now=NOW)[0]["observed_demand"]["y"] == 100
    assert first.snapshot(now=NOW + 3 * 86400 + 1) == []


def test_verified_scenarios_win_same_identity_without_erasing_other_models(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    assert registry.record_queue(_queue(), now=NOW) == 2
    verified = {"source": "game_research", "hub_id": "2926", "model": "A320",
                "origin": {"id": "2926"}, "destination": {"id": "3139"}}
    assert [row["model"] for row in registry.snapshot(verified=[verified], now=NOW)] == ["B737"]
    assert len(registry.snapshot(now=NOW)) == 2


def test_conflicting_or_unverified_input_never_grants_approval(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    initial = _queue()
    registry.record_queue(initial, now=NOW)
    conflicting = deepcopy(initial)
    conflicting["items"][0]["observed_demand"]["y"] = 999
    assert registry.record_queue(conflicting, now=NOW) == 2
    rows = registry.snapshot(now=NOW)
    assert any("pesquisas_conflitantes" in row["research_pending"] for row in rows)

    invalid = deepcopy(initial)
    invalid["items"][0]["evidence"]["route"]["source"] = "manual"
    assert registry.record_queue(invalid, now=NOW) == 1
    assert len(registry.snapshot(now=NOW)) == 2
    assert registry.record_queue({"source": "manual", "items": initial["items"]}, now=NOW) == 0


def test_cached_inputs_expire_when_one_independent_source_gets_old(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    page = _queue()
    page["items"][0]["evidence"]["model"]["observed_at"] = NOW - MAX_EVIDENCE_AGE + 10
    assert registry.record_queue(page, now=NOW) == 2
    assert len(registry.snapshot(now=NOW)) == 2
    assert [row["model"] for row in registry.snapshot(now=NOW + 11)] == ["B737"]
    assert registry.record_queue(_queue(), now=NOW + 11) == 2
    assert len(registry.snapshot(now=NOW + 11)) == 2


def test_cursor_state_can_read_legacy_cache_safely(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    page = build_owned_hub_research_queue(*_inputs(), now=NOW, max_items=1)
    assert registry.record_queue(page, now=NOW) == 1
    assert registry.cursor_state() == (1, page["snapshot_fingerprint"])
    legacy = json.loads(registry.path.read_text(encoding="utf-8"))
    del legacy["snapshot_fingerprint"]
    del legacy["layout_fingerprint"]
    legacy["version"] = 1
    registry.path.write_text(json.dumps(legacy), encoding="utf-8")
    assert registry.cursor_state() == (1, None)
    assert registry.pagination_state() == (1, None, None)


def test_cycle_ingestion_rotates_pages_and_persists_across_restart(tmp_path, monkeypatch):
    now = int(time.time())
    inventory, routes, market = _inputs(now)
    monkeypatch.setattr(paths, "current", lambda: SimpleNamespace(data=tmp_path))
    monkeypatch.setattr(route_registry, "RouteRegistry", lambda: SimpleNamespace(
        snapshot=lambda: {"relations": []}))
    monkeypatch.setattr(hub_registry, "HubRegistry", lambda: SimpleNamespace(
        snapshot=lambda _routes: inventory))
    monkeypatch.setattr(hub_expansion, "HubExpansionRegistry", lambda: SimpleNamespace(
        demand_research_snapshot=lambda _hubs: {"samples": routes, "hub_progress": []}))
    monkeypatch.setattr(engine_catalog, "EngineCatalogRegistry", lambda: SimpleNamespace(
        snapshot=lambda: {}))
    monkeypatch.setattr(economy, "load_market_evidence", lambda: market)

    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    restarted = OwnedHubResearchInputsRegistry()
    assert restarted.cursor() == 1
    old_fingerprint = restarted.cursor_state()[1]

    # A refreshed market changes its evidence fingerprint every cycle. Keep
    # rotating through candidates while their ordered identities are stable.
    market["models"][0]["price"] = 2_000_000
    market["observed_at"] = now + 0.001
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 0
    assert restarted.cursor_state()[1] != old_fingerprint
    assert {row["model"] for row in restarted.snapshot()} == {"A320", "B737"}

    # Adding a model changes the candidate order, so the old offset cannot
    # skip the new first candidate. A structural change resets the cursor.
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 1
    market["models"].append({"id": 33, "name": "A319", "range": 5000,
                             "capacity": 150, "price": 1_400_000})
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 1
    # The structural change invalidates old pages. The new catalogue is
    # repopulated incrementally instead of mixing incompatible generations.
    assert {row["model"] for row in restarted.snapshot()} == {"A319"}
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert {row["model"] for row in restarted.snapshot()} == {"A319", "A320", "B737"}

    # A partially corrupted state cannot resume solely from its layout hash.
    cached = json.loads(restarted.path.read_text(encoding="utf-8"))
    del cached["snapshot_fingerprint"]
    restarted.path.write_text(json.dumps(cached), encoding="utf-8")
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 1


def test_structural_change_removes_stale_research_candidates_without_waiting_for_ttl(tmp_path):
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    inventory, routes, market = _inputs()
    first = build_owned_hub_research_queue(inventory, routes, market, now=NOW, max_items=1)
    second = build_owned_hub_research_queue(
        inventory, routes, market, now=NOW, max_items=1,
        offset=1, expected_fingerprint=first["snapshot_fingerprint"],
    )
    assert registry.record_queue(first, now=NOW) == 1
    assert registry.record_queue(second, now=NOW) == 1
    assert {row["model"] for row in registry.snapshot(now=NOW)} == {"A320", "B737"}

    # Only a monetary input changed. Previously collected models remain
    # available for research until their own observations expire.
    market["models"][0]["price"] += 1000
    market["observed_at"] += 1
    price_refresh = build_owned_hub_research_queue(
        inventory, routes, market, now=NOW + 1, max_items=1,
    )
    assert price_refresh["layout_fingerprint"] == first["layout_fingerprint"]
    assert registry.record_queue(price_refresh, now=NOW + 1) == 1
    assert {row["model"] for row in registry.snapshot(now=NOW + 1)} == {"A320", "B737"}

    # The game stopped offering B737 and introduced A319. A previous
    # candidate must never survive a changed model/route/engine topology.
    market["models"] = [market["models"][0],
                        {"id": 33, "name": "A319", "range": 5000,
                         "capacity": 150, "price": 1_400_000}]
    replacement = build_owned_hub_research_queue(
        inventory, routes, market, now=NOW + 1, max_items=1,
    )
    assert replacement["layout_fingerprint"] != first["layout_fingerprint"]
    assert registry.record_queue(replacement, now=NOW + 1) == 1
    assert [row["model"] for row in registry.snapshot(now=NOW + 1)] == ["A319"]


def test_research_layout_tracks_hub_code_and_catalogue_labels():
    inventory, routes, market = _inputs()
    baseline = build_owned_hub_research_queue(inventory, routes, market, now=NOW)

    inventory["hubs"][0]["code"] = "NEW"
    renamed_hub = build_owned_hub_research_queue(inventory, routes, market, now=NOW)
    assert renamed_hub["layout_fingerprint"] != baseline["layout_fingerprint"]

    inventory["hubs"][0]["code"] = "XAP"
    market["models"][0]["name"] = "A320 Updated"
    renamed_model = build_owned_hub_research_queue(inventory, routes, market, now=NOW)
    assert renamed_model["layout_fingerprint"] != baseline["layout_fingerprint"]


def test_record_queue_rejects_page_from_superseded_pagination_state(tmp_path):
    inventory, routes, old_market = _inputs()
    new_market = deepcopy(old_market)
    new_market["models"][1] = {"id": 33, "name": "A319", "range": 5000,
                               "capacity": 150, "price": 1_400_000}
    new_market["observed_at"] += 10
    old_page = build_owned_hub_research_queue(
        inventory, routes, old_market, now=NOW + 10, max_items=1,
    )
    new_page = build_owned_hub_research_queue(
        inventory, routes, new_market, now=NOW + 10, max_items=1,
    )
    registry = OwnedHubResearchInputsRegistry(tmp_path / "research.json")
    initial_state = registry.pagination_state()

    assert registry.record_queue(new_page, now=NOW + 10, expected_state=initial_state) == 1
    assert registry.record_queue(old_page, now=NOW + 10, expected_state=initial_state) == 0
    assert registry.pagination_state() == (
        1, new_page["snapshot_fingerprint"], new_page["layout_fingerprint"],
    )
    assert [row["model"] for row in registry.snapshot(now=NOW + 10)] == ["A319"]


def test_inflight_old_ingestion_cannot_replace_newer_snapshot(tmp_path, monkeypatch):
    observed_at = int(time.time()) - 20
    old_inputs = _inputs(observed_at)
    new_inputs = deepcopy(old_inputs)
    new_inputs[2]["models"][1] = {"id": 33, "name": "A319", "range": 5000,
                                  "capacity": 150, "price": 1_400_000}
    new_inputs[2]["observed_at"] += 10

    def inputs():
        return old_inputs if threading.current_thread().name == "older-ingestion" else new_inputs

    monkeypatch.setattr(paths, "current", lambda: SimpleNamespace(data=tmp_path))
    monkeypatch.setattr(route_registry, "RouteRegistry", lambda: SimpleNamespace(
        snapshot=lambda: {"relations": []}))
    monkeypatch.setattr(hub_registry, "HubRegistry", lambda: SimpleNamespace(
        snapshot=lambda _routes: inputs()[0]))
    monkeypatch.setattr(hub_expansion, "HubExpansionRegistry", lambda: SimpleNamespace(
        demand_research_snapshot=lambda _hubs: {"samples": inputs()[1], "hub_progress": []}))
    monkeypatch.setattr(engine_catalog, "EngineCatalogRegistry", lambda: SimpleNamespace(
        snapshot=lambda: {}))
    monkeypatch.setattr(economy, "load_market_evidence", lambda: inputs()[2])

    older_ready = threading.Event()
    newer_committed = threading.Event()
    original_build = ingestion.build_owned_hub_research_queue

    def delayed_build(*args, **kwargs):
        if threading.current_thread().name == "older-ingestion" and not older_ready.is_set():
            older_ready.set()
            if not newer_committed.wait(5):
                raise TimeoutError("Newer ingestion did not finish")
        return original_build(*args, **kwargs)

    monkeypatch.setattr(ingestion, "build_owned_hub_research_queue", delayed_build)
    results = {}

    def run(name):
        try:
            results[name] = ingest_owned_hub_research_inputs(per_cycle=1)
        except Exception as exc:  # Ensure exceptions in worker threads fail this test.
            results[name] = exc
        finally:
            if name == "newer-ingestion":
                newer_committed.set()

    older = threading.Thread(target=run, args=("older-ingestion",), name="older-ingestion")
    newer = threading.Thread(target=run, args=("newer-ingestion",), name="newer-ingestion")
    older.start()
    assert older_ready.wait(5)
    newer.start()
    older.join(10)
    newer.join(10)

    assert not older.is_alive() and not newer.is_alive()
    assert results == {"newer-ingestion": 1, "older-ingestion": 0}
    saved = json.loads((tmp_path / "owned_hub_research_inputs.json").read_text(encoding="utf-8"))
    assert [row["model"] for row in saved["items"]] == ["A319"]
    assert saved["items"][0]["research_evidence"]["model"]["observed_at"] == observed_at + 10
