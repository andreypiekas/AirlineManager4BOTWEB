"""Observed research inputs reach the ranking without authorizing purchases."""
from __future__ import annotations

import time
import json
from copy import deepcopy
from types import SimpleNamespace

import economy
import engine_catalog
import hub_expansion
import hub_registry
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
    legacy["version"] = 1
    registry.path.write_text(json.dumps(legacy), encoding="utf-8")
    assert registry.cursor_state() == (1, None)


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

    # A changed market invalidates the saved offset: revisit the new first
    # combination before moving to the second, even after a process restart.
    market["models"][0]["price"] = 2_000_000
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 1
    assert restarted.cursor_state()[1] != old_fingerprint
    assert {row["model"] for row in restarted.snapshot()} == {"A320"}
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert restarted.cursor() == 0
    assert {row["model"] for row in restarted.snapshot()} == {"A320", "B737"}
    assert ingest_owned_hub_research_inputs(per_cycle=1) == 1
    assert len(restarted.snapshot()) == 2
