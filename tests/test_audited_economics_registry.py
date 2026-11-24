"""A3 persisted game evidence is scoped, expiring and read-only in A4."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

import paths
import investment_plan_bridge
from audited_economics_registry import AuditedEconomicsRegistry
from expansion_economics import rank_expansion_economics
from portfolio_planner import compare_audited_portfolio
from test_expansion_economics import NOW, fixture
from test_investment_policy_web import auth, request, served


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "current", lambda: paths.Profile(""))
    monkeypatch.setattr(paths.Profile, "data", property(lambda self: tmp_path))
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


def matching_capture(snapshot_id, *, unrouted=0, research=True, fleet=True):
    return {
        "status": "parcial", "snapshot_id": snapshot_id,
        "scopes": {"fleet": fleet, "hubs": True, "models": True, "engines": True,
                   "routes": research, "prices": research},
        "unrouted_aircraft_control": (proof(unrouted, "game_fleet_scan", snapshot_id)
                                      if fleet else None),
        "passenger_hangar_control": proof(2, "game_hangar_and_fleet_status", snapshot_id),
    }


def compare_registry(registry):
    stored = registry.snapshot(now=NOW)
    evidence = stored["portfolio_evidence"]
    return compare_audited_portfolio(
        stored["evaluations"], profile_id="principal",
        snapshot_id=stored["snapshot_id"] or "",
        controls=evidence.get("controls"),
        passenger_hangar=matching_capture(stored["snapshot_id"])["passenger_hangar_control"],
        fleet_coverage_verified=evidence.get("fleet_coverage_verified") is True,
        research_coverage_verified=evidence.get("research_coverage_verified") is True,
        commitments_verified=evidence.get("commitments_verified") is True,
        current_cash_reserve=0, max_daily_spend=50000, max_acquisitions_per_day=10,
        max_cycle_spend=30000,
        local_journal={"profile_id": "principal", "estimated_exposure": 0, "count": 0,
                       "period_usage": {"source": "local_investment_journal", "since": NOW - 86400,
                                        "estimated_exposure": 0, "acquisition_count": 0}},
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


@pytest.mark.parametrize("scenario,expected,absent", [
    ("empty", "aeronaves_sem_rota_a_resolver", "evidencia_unrouted_aircraft_count_a_confirmar"),
    ("positive", "aeronaves_sem_rota_a_resolver", "evidencia_unrouted_aircraft_count_a_confirmar"),
    ("partial", "cobertura_pesquisa_a_confirmar", "cobertura_frota_a_confirmar"),
    ("unverified", "evidencia_unrouted_aircraft_count_a_confirmar", "aeronaves_sem_rota_a_resolver"),
    ("different", "snapshot_a3_divergente_coleta", "aeronaves_sem_rota_a_resolver"),
    ("hangar_full", "hangar_sem_vaga", "vagas_hangar_a_confirmar"),
    ("hangar_missing", "vagas_hangar_a_confirmar", "hangar_sem_vaga"),
])
def test_a4_uses_current_capture_instead_of_stored_fleet_claims(
    registry, monkeypatch, scenario, expected, absent,
):
    if scenario == "empty":
        snapshot_id = "current-capture"
    else:
        data = record_fixture(registry)
        snapshot_id = data[0]["snapshot_id"]
        assert registry.record_portfolio_evidence(
            snapshot_id=snapshot_id, controls=controls(snapshot_id),
            hub_capacity={"123": proof(2, "game_hub_select", snapshot_id, hub_id="123")},
            fleet_coverage_verified=True, research_coverage_verified=True,
            commitments_verified=True,
        )
    record = registry.snapshot(now=NOW)
    capture = matching_capture(
        "different" if scenario == "different" else snapshot_id,
        unrouted=1 if scenario in ("empty", "positive", "different") else 0,
        research=False, fleet=scenario != "unverified",
    )
    if scenario == "hangar_full":
        capture["passenger_hangar_control"]["value"] = 0
    elif scenario == "hangar_missing":
        capture["passenger_hangar_control"] = None

    class SnapshotRegistry:
        def snapshot(self):
            return deepcopy(record)

    monkeypatch.setattr("web.AuditedEconomicsRegistry", SnapshotRegistry)
    monkeypatch.setattr("web.snapshot_summary", lambda: capture)
    monkeypatch.setattr("web.compare_audited_portfolio", lambda *args, **kwargs:
                        compare_audited_portfolio(*args, **kwargs, now=NOW))
    with served(registry.path.parent) as (port, _config):
        status, result = request(port, "GET", "/api/investment/audited-expansion", headers=auth())
    assert status == 200
    assert result["portfolio"]["decision"] == "nao_comprar"
    assert expected in result["purchase_plan_blockers"]
    assert absent not in result["purchase_plan_blockers"]
    assert result["purchase_plan_preview"] is None


def test_a4_api_enforces_live_policy_and_rolling_journal(registry, monkeypatch):
    data = record_fixture(registry)
    snapshot_id = data[0]["snapshot_id"]
    assert registry.record_portfolio_evidence(
        snapshot_id=snapshot_id, controls=controls(snapshot_id),
        hub_capacity={},
        fleet_coverage_verified=True, research_coverage_verified=True,
        commitments_verified=True,
    )
    record = registry.snapshot(now=NOW)

    class SnapshotRegistry:
        def snapshot(self):
            return deepcopy(record)

    journal = {"profile_id": "principal", "estimated_exposure": 0, "count": 0,
               "period_usage": {"source": "local_investment_journal", "since": NOW - 86400,
                                "estimated_exposure": 5000, "acquisition_count": 1,
                                "last_confirmed_at": None}}
    monkeypatch.setattr("web.AuditedEconomicsRegistry", SnapshotRegistry)
    monkeypatch.setattr("web.snapshot_summary", lambda: matching_capture(snapshot_id))
    monkeypatch.setattr("web._local_investment_snapshot", lambda: deepcopy(journal))
    monkeypatch.setattr("web.compare_audited_portfolio", lambda *args, **kwargs:
                        compare_audited_portfolio(*args, **kwargs, now=NOW))
    monkeypatch.setattr("web.recent_verified_money", lambda _bot: (40000, NOW))
    monkeypatch.setattr("web.build_aircraft_intent_plan", lambda portfolio, evaluation:
                        investment_plan_bridge.build_aircraft_intent_plan(portfolio, evaluation, now=NOW))
    endpoint = "/api/investment/audited-expansion"
    with served(registry.path.parent) as (port, cfg):
        for key, value in (("planning_enabled", "on"), ("max_single_investment", 20000),
                           ("max_daily_spend", 50000), ("max_cycle_spend", 30000),
                           ("max_acquisitions_per_day", 2)):
            cfg.set("investment", key, value)
        cfg.set("settings", "cash_reserve", 5000)
        status, result = request(port, "GET", endpoint, headers=auth())
        assert status == 200
        assert result["purchase_plan_preview"] is not None, result["purchase_plan_blockers"]
        assert result["portfolio"]["local_period_limits"]["remaining_acquisitions"] == 1

        cfg.set("investment", "max_cycle_spend", 10000)
        status, result = request(port, "GET", endpoint, headers=auth())
        assert status == 200
        assert result["portfolio"]["remaining_cycle_spend"] == 10000
        assert result["purchase_plan_preview"] is None
        cfg.set("investment", "max_cycle_spend", 30000)

        cfg.set("investment", "max_daily_spend", 15000)
        status, result = request(port, "GET", endpoint, headers=auth())
        assert status == 200
        assert result["portfolio"]["budget_after_reservations_and_limits"] == 10000
        assert result["portfolio"]["decision"] == "nao_comprar"
        assert result["purchase_plan_preview"] is None

        cfg.set("investment", "max_daily_spend", 50000)
        cfg.set("investment", "max_acquisitions_per_day", 1)
        status, result = request(port, "GET", endpoint, headers=auth())
        assert status == 200
        assert "limite_de_aquisicoes_em_24h" in result["purchase_plan_blockers"]
        assert result["purchase_plan_preview"] is None

        cfg.set("investment", "max_acquisitions_per_day", 2)
        cfg.set("settings", "cash_reserve", 35000)
        status, result = request(port, "GET", endpoint, headers=auth())
        assert status == 200
        assert result["portfolio"]["budget_after_reservations_and_limits"] == 4000
        assert result["purchase_plan_preview"] is None


def test_authenticated_snapshot_research_api_passes_pagination(tmp_path, monkeypatch):
    calls = []

    def replay(**kwargs):
        calls.append(kwargs)
        return {"items": [], "read_only": True, "purchase_eligible": False}

    monkeypatch.setattr("web.replay_research_page", replay)
    endpoint = "/api/investment/audited-expansion/research"
    with served(tmp_path) as (port, _config):
        assert request(port, "GET", endpoint)[0] == 403
        assert not calls
        status, result = request(port, "GET", endpoint +
                                 "?research_offset=40&snapshot_id=abc&research_snapshot=def", headers=auth())
        assert status == 200 and result["read_only"] and not result["purchase_eligible"]
        assert calls == [{"offset": 40, "expected_snapshot": "abc", "expected_fingerprint": "def"}]


def test_web_dashboard_fails_closed_for_invalid_a3_storage(registry, monkeypatch):
    registry.path.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr("web.AuditedEconomicsRegistry", lambda: registry)
    with served(registry.path.parent) as (port, _config):
        status, result = request(port, "GET", "/api/investment/audited-expansion", headers=auth())
        assert status == 200
        assert result["portfolio"]["decision"] == "nao_comprar"
        assert "registro_a3_invalido" in result["portfolio"]["blocking_reasons"]


@pytest.mark.parametrize("pending,blocker", [
    (None, None),
    ("cash_missing", "saldo_vivo_a_confirmar"),
    ("cash_old", "saldo_vivo_a_confirmar"),
    ("cash_changed", "saldo_vivo_divergente_a3"),
    ("confirmed_after", "snapshot_anterior_compra_confirmada"),
    ("snapshot_changed", "snapshot_a3_divergente_coleta"),
    ("snapshot_expired", "coleta_jogo_expirada"),
    ("snapshot_invalid", "coleta_jogo_invalida"),
    ("snapshot_missing", "coleta_jogo_ausente"),
    ("snapshot_matches", None),
    ("route_creation_pending.json", "criacao_rota_a_conciliar"),
    ("reroute_pending.json", "redirecionamento_a_conciliar"),
    ("investment", "intencoes_locais_a_conciliar"),
    ("corrupt", "diario_indisponivel"),
])
def test_authenticated_a4_api_exposes_read_only_a5_purchase_plan_preview(
    tmp_path, registry, monkeypatch, pending, blocker,
):
    data = record_fixture(registry)
    snapshot_id = data[0]["snapshot_id"]
    assert registry.record_portfolio_evidence(
        snapshot_id=snapshot_id, controls=controls(snapshot_id),
        hub_capacity={"123": proof(2, "game_hub_select", snapshot_id, hub_id="123")},
        fleet_coverage_verified=True, research_coverage_verified=True,
        commitments_verified=True,
    )
    portfolio = compare_registry(registry)
    record = registry.snapshot(now=NOW)

    class SnapshotRegistry:
        def snapshot(self):
            return deepcopy(record)

    monkeypatch.setattr("web.AuditedEconomicsRegistry", SnapshotRegistry)
    monkeypatch.setattr("web.compare_audited_portfolio", lambda *_args, **_kwargs: portfolio)
    live_cash = {"cash_missing": (None, None), "cash_old": (40000, NOW - 21),
                 "cash_changed": (39000, NOW)}.get(pending, (40000, NOW))
    monkeypatch.setattr("web.recent_verified_money", lambda _bot: live_cash)
    capture = {
        "snapshot_changed": {"status": "parcial", "snapshot_id": "different"},
        "snapshot_expired": {"status": "expirado", "snapshot_id": snapshot_id},
        "snapshot_invalid": {"status": "registro_invalido", "snapshot_id": None},
        "snapshot_missing": {"status": "sem_coleta", "snapshot_id": None},
    }.get(pending, matching_capture(snapshot_id))
    if capture is not None:
        monkeypatch.setattr("web.snapshot_summary", lambda: capture)
    monkeypatch.setattr(
        "web.build_aircraft_intent_plan",
        lambda current_portfolio, evaluation: investment_plan_bridge.build_aircraft_intent_plan(
            current_portfolio, evaluation, now=NOW,
        ),
    )

    if pending in ("investment", "confirmed_after"):
        from investment_journal import InvestmentJournal
        from test_investment_journal import ready, aircraft_proof
        from types import SimpleNamespace

        if pending == "confirmed_after":
            monkeypatch.setattr("investment_journal.time", SimpleNamespace(time=lambda: NOW - 10))

        ledger = InvestmentJournal()
        key = ready(ledger)
        assert ledger.acquire_executor("pending-test")
        assert ledger.claim_submission(key, "pending-test")
        assert ledger.release_executor("pending-test")
        if pending == "confirmed_after":
            assert ledger.transition(key, "SUBMITTED", "CONFIRMED",
                                     confirmation=aircraft_proof(observed_at=NOW - 10))
    elif pending == "corrupt":
        (tmp_path / "investment_journal.sqlite3").write_text("invalid", encoding="utf-8")
    elif pending and pending.endswith(".json"):
        (tmp_path / pending).write_text("invalid", encoding="utf-8")
    before = {file.name: file.read_bytes() for file in tmp_path.glob("*.sqlite3")}

    with served(tmp_path) as (port, _config):
        denied, _ = request(port, "GET", "/api/investment/audited-expansion")
        assert denied == 403
        status, result = request(
            port, "GET", "/api/investment/audited-expansion", headers=auth(),
        )

    assert status == 200
    assert {file.name: file.read_bytes() for file in tmp_path.glob("*.sqlite3")} == before
    if capture is not None:
        assert result["game_observation_snapshot"] == capture
        assert result["evaluation_count"] == 1
    if blocker:
        assert result["purchase_plan_preview"] is None
        assert result["portfolio"]["decision"] == "nao_comprar"
        assert result["portfolio"]["status"] == "inconclusivo"
        assert blocker in result["purchase_plan_blockers"]
        return
    assert result["purchase_plan_blockers"] == []
    assert result["purchase_plan_preview"]["plan_id"] == portfolio["best"]["plan_id"]
    assert result["purchase_plan_preview"]["engine_id"] == "engine-02"
    assert result["purchase_plan_preview"]["estimated_cost"] == 10700
    assert result["purchase_plan_preview"]["checkout_cost"] == 10500
    assert result["read_only"] is True
    assert result["execution_available"] is False
    assert not list(tmp_path.glob("*.sqlite3"))


@pytest.mark.parametrize("tamper,expected_blocker", [
    ("missing_costs", "Custos discriminados ausentes."),
    ("ambiguous_winner", "economia_a3_vencedora_ausente_ou_ambigua"),
])
def test_a5_preview_fails_closed_for_missing_or_ambiguous_a3_economics(
    tmp_path, registry, monkeypatch, tamper, expected_blocker,
):
    data = record_fixture(registry)
    snapshot_id = data[0]["snapshot_id"]
    assert registry.record_portfolio_evidence(
        snapshot_id=snapshot_id, controls=controls(snapshot_id),
        hub_capacity={"123": proof(2, "game_hub_select", snapshot_id, hub_id="123")},
        fleet_coverage_verified=True, research_coverage_verified=True,
        commitments_verified=True,
    )
    portfolio = compare_registry(registry)
    record = registry.snapshot(now=NOW)
    if tamper == "missing_costs":
        record["evaluations"][0].pop("capital_costs")
    else:
        record["evaluations"].append(deepcopy(record["evaluations"][0]))

    class SnapshotRegistry:
        def snapshot(self):
            return deepcopy(record)

    monkeypatch.setattr("web.AuditedEconomicsRegistry", SnapshotRegistry)
    monkeypatch.setattr("web.compare_audited_portfolio", lambda *_args, **_kwargs: portfolio)
    monkeypatch.setattr("web.recent_verified_money", lambda _bot: (40000, NOW))
    monkeypatch.setattr("web.snapshot_summary", lambda: matching_capture(snapshot_id))
    monkeypatch.setattr(
        "web.build_aircraft_intent_plan",
        lambda current_portfolio, evaluation: investment_plan_bridge.build_aircraft_intent_plan(
            current_portfolio, evaluation, now=NOW,
        ),
    )

    with served(tmp_path) as (port, _config):
        status, result = request(
            port, "GET", "/api/investment/audited-expansion", headers=auth(),
        )

    assert status == 200
    assert result["purchase_plan_preview"] is None
    assert expected_blocker in result["purchase_plan_blockers"]
    assert result["read_only"] is True
    assert result["execution_available"] is False
