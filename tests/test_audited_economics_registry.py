"""A3 persisted game evidence is scoped, expiring and read-only in A4."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

import paths
from audited_economics_registry import AuditedEconomicsRegistry
from expansion_economics import rank_expansion_economics
from portfolio_planner import compare_audited_portfolio
from test_expansion_economics import NOW, fixture
from test_investment_policy_web import auth, request, served


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    return AuditedEconomicsRegistry(tmp_path / "audited_expansion.json")


def record_fixture(registry, **kwargs):
    data = fixture()
    assert registry.record(*data, now=NOW, **kwargs)
    return data


def proof(value, source, snapshot_id, *, hub_id=None):
    result = {
        "value": value, "source": source, "profile_id": "principal",
        "snapshot_id": snapshot_id, "observed_at": NOW - 20,
        "verified": True,
    }
    if hub_id is not None:
        result["hub_id"] = hub_id
    return result


def controls(snapshot_id):
    return {
        name: proof(value, source, snapshot_id)
        for name, value, source in (
            ("pending_orders_incremental", 0, "investment_journal"),
            ("future_commitments_incremental", 0, "investment_journal"),
            ("unrouted_aircraft_count", 0, "game_fleet_scan"),
            ("operational_reserve", 3000, "investment_policy"),
            ("cycle_spent", 0, "investment_journal"),
            ("cycle_limit", 30000, "investment_policy"),
            ("period_spent", 0, "investment_journal"),
            ("period_limit", 50000, "investment_policy"),
        )
    }


def compare_registry(registry):
    stored = registry.snapshot(now=NOW)
    evidence = stored["portfolio_evidence"]
    return compare_audited_portfolio(
        stored["evaluations"], profile_id="principal",
        snapshot_id=stored["snapshot_id"] or "",
        controls=evidence.get("controls"),
        hub_capacity=evidence.get("hub_capacity"),
        fleet_coverage_verified=evidence.get("fleet_coverage_verified") is True,
        research_coverage_verified=evidence.get("research_coverage_verified") is True,
        commitments_verified=evidence.get("commitments_verified") is True,
        max_single_investment=20000, now=NOW,
    )


def test_record_is_idempotent_and_recomputes_economics_from_evidence(registry):
    data = record_fixture(registry)
    assert registry.record(*deepcopy(data), now=NOW)
    result = registry.snapshot(now=NOW)
    assert result["status"] == "registrado"
    assert result["snapshot_id"] == data[0]["snapshot_id"]
    assert len(result["evaluations"]) == 1
    assert result["evaluations"][0]["status"] == "evaluated"
    assert result["evaluations"][0]["components"]["daily_net_profit_estimate"] == 6656.5
    assert result["read_only"] is True
    assert len(json.loads(registry.path.read_text(encoding="utf-8"))["cases"]) == 1


def test_expired_or_unsupported_evidence_cannot_be_refreshed_by_reading(registry):
    record_fixture(registry)
    expired = registry.snapshot(now=NOW + 100000)
    assert expired["evaluations"][0]["status"] == "blocked"
    assert rank_expansion_economics(expired["evaluations"])["best"] is None
    assert not registry.record(*fixture(), now=NOW + 100000)


def test_conflicting_source_observations_quarantine_the_same_route(registry):
    data = record_fixture(registry)
    assert registry.record(*data, now=NOW, safety_margin_fraction=0.20)
    results = registry.snapshot(now=NOW)["evaluations"]
    assert len(results) == 2
    ranked = rank_expansion_economics(results)
    assert ranked["best"] is None
    assert ranked["conflicting_identities"] == 1
    assert compare_registry(registry)["decision"] == "nao_comprar"


def test_invalid_storage_and_tampered_id_fail_closed(registry):
    record_fixture(registry)
    stored = json.loads(registry.path.read_text(encoding="utf-8"))
    for payload in ("corrupt", {**stored, "portfolio": ["invalid"]}):
        registry.path.write_text(json.dumps(payload), encoding="utf-8")
        assert registry.snapshot(now=NOW)["status"] == "registro_invalido"
    stored["cases"][0]["economics_id"] = "tampered"
    registry.path.write_text(json.dumps(stored), encoding="utf-8")
    assert registry.snapshot(now=NOW)["status"] == "registro_invalido"
    assert not registry.record(*fixture(), now=NOW)


def test_different_profile_never_reads_or_overwrites_a3_evidence(registry, monkeypatch):
    record_fixture(registry)
    monkeypatch.setattr(paths, "current", lambda: paths.Profile("second"))
    assert registry.snapshot(now=NOW)["status"] == "registro_invalido"
    assert not registry.record(*fixture(), now=NOW)


def test_a4_needs_snapshot_bound_controls_and_verified_coverage(registry):
    data = record_fixture(registry)
    snapshot_id = data[0]["snapshot_id"]
    assert not registry.record_portfolio_evidence(snapshot_id="wrong", controls={}, hub_capacity={})
    assert compare_registry(registry)["decision"] == "nao_comprar"
    assert registry.record_portfolio_evidence(
        snapshot_id=snapshot_id, controls=controls(snapshot_id),
        hub_capacity={"123": proof(2, "game_hub_select", snapshot_id, hub_id="123")},
        fleet_coverage_verified=True, research_coverage_verified=True,
        commitments_verified=True,
    )
    ranked = compare_registry(registry)
    assert ranked["decision"] == "sugestao_para_analise", ranked["blocking_reasons"]
    assert ranked["best"]["identity"]["engine_id"] == "engine-02"
    assert ranked["read_only"] is True and ranked["execution_available"] is False

    incompatible = controls(snapshot_id)
    incompatible["cycle_spent"]["snapshot_id"] = "foreign"
    assert registry.record_portfolio_evidence(
        snapshot_id=snapshot_id, controls=incompatible,
        hub_capacity={"123": proof(2, "game_hub_select", snapshot_id, hub_id="123")},
        fleet_coverage_verified=True, research_coverage_verified=True,
        commitments_verified=True,
    )
    assert compare_registry(registry)["decision"] == "nao_comprar"


def test_authenticated_a3_api_exposes_only_read_only_analysis(tmp_path, monkeypatch):
    empty = AuditedEconomicsRegistry(tmp_path / "audited_expansion.json")
    monkeypatch.setattr("web.AuditedEconomicsRegistry", lambda: empty)
    with served(tmp_path) as (port, _config):
        denied, _ = request(port, "GET", "/api/investment/audited-expansion")
        assert denied == 403
        status, result = request(port, "GET", "/api/investment/audited-expansion", headers=auth())
        assert status == 200
        assert result["status"] == "sem_avaliacoes"
        assert result["evaluation_count"] == 0
        assert result["portfolio"]["decision"] == "nao_comprar"
        assert result["read_only"] is True
        assert result["execution_available"] is False


def test_web_dashboard_fails_closed_for_invalid_a3_storage(registry, monkeypatch):
    registry.path.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr("web.AuditedEconomicsRegistry", lambda: registry)
    with served(registry.path.parent) as (port, _config):
        status, result = request(port, "GET", "/api/investment/audited-expansion", headers=auth())
        assert status == 200
        assert result["portfolio"]["decision"] == "nao_comprar"
        assert "registro_a3_invalido" in result["portfolio"]["blocking_reasons"]
