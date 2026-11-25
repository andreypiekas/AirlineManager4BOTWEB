"""A6 reports use the same independent owned-coverage gate as the API."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from expansion_reporting import (
    CLAIM_LEASE_SECONDS,
    MAX_HTML_LENGTH,
    ExpansionAlertDeduplicator,
    build_expansion_report,
)
from investment_policy import InvestmentPolicy


NOW = 1_800_000_000
SNAPSHOT = "sha256:" + "a" * 64


def hub(hub_id="789", *, profit=500, price=10000, engine_id="engine-3",
        hub_price=5000, includes_engine=False):
    identity = {"model": "A320", "engine_id": engine_id,
                "model_id": "101", "stopover_id": None,
                "origin_id": hub_id, "destination_id": "999", "route": "XAP ↔ GRU <B>"}
    engine_extra = 0 if includes_engine else 400
    investment = hub_price + price + engine_extra + 1000 + 100 + 50
    costs = {**identity, "source": "game_market", "observed_at": NOW,
             "aircraft_price": price, "aircraft_price_includes_engine": includes_engine,
             "engine_delta_cost": None if includes_engine else 400,
             "route_fee": 1000, "hangar_price": 100, "other_fees": 50}
    financial = {**identity, "source": "route_optimizer", "observed_at": NOW,
                 "profit_per_day": profit}
    return {
        "id": hub_id, "code": f"H{hub_id}", "name": "Chapecó <Norte>",
        "source": "game_purchase_catalog", "hub_price": hub_price, "hub_points": 0,
        "hub_price_observed_at": NOW, "hub_points_observed_at": NOW,
        "observed_at": NOW, "status": "viavel", "pending": [],
        "ranking_conclusive": True, "purchase_evidence": True,
        "scenario": {**identity, "source": "game_research", "observed_at": NOW,
                     "engine_label": "CFM & Co <fast>", "engine_verified": True,
                     "external_demand_verified": True, "route_feasible": True,
                     "demand_verified": True, "costs": costs, "financial": financial,
                     "excluded_costs": []},
        "cost_breakdown": {
            "hub_price": hub_price, "hub_points": 0, "aircraft_price": price,
            "aircraft_price_includes_engine": includes_engine,
            "engine_delta_cost": None if includes_engine else 400,
            "engine_extra_charged": engine_extra, "route_fee": 1000,
            "hangar_price": 100, "other_fees": 50, "reserve": 2000,
            "cash_required": investment + 2000, "total": investment,
        },
        "investment": investment, "profit_per_day": profit,
        "payback_days": round(investment / profit, 1),
    }


def external(*rows, cash=100000, complete=True):
    return {"source": "game_purchase_catalog", "observed_at": NOW,
            "catalog_complete": complete, "available_cash": cash,
            "candidates": list(rows)}


def owned(*, eligible=0, complete=True):
    portfolio = {
        "status": "comparacao_concluida" if complete else "inconclusivo",
        "eligible_count": eligible, "best": {"hub_id": "123"} if eligible else None,
        "excluded": {"rota_ocupada": 1, "sem_lucro": 2},
        "blocking_reasons": [] if complete else ["cobertura_frota_a_confirmar"],
    }
    return {"portfolio": portfolio, "hubs": [{"code": "XAP", "status": "sem_lucro"}]}


def evidence():
    inventory = {"source": "game_hub_select", "observed_at": NOW,
                 "partial_fleet": False, "hubs": [{"id": "123"}, {"id": "456"}]}
    research = {"partial_fleet": False, "candidates": []}
    coverage = {
        "source": "game_hub_opportunity_scan", "complete": True, "observed_at": NOW,
        "hubs": [{"hub_id": item, "source": "game_hub_opportunity_scan",
                  "complete": True, "observed_at": NOW, "routes_complete": True,
                  "models_complete": True, "engines_complete": True,
                  "costs_complete": True, "demand_complete": True}
                 for item in ("123", "456")],
    }
    return inventory, research, coverage


def build(owned_data=None, external_data=None, *, profile="principal", snapshot=SNAPSHOT,
          inventory=None, research=None, coverage=None, **kwargs):
    default_inventory, default_research, default_coverage = evidence()
    return build_expansion_report(
        owned() if owned_data is None else owned_data,
        external(hub()) if external_data is None else external_data,
        profile_id=profile, snapshot_id=snapshot, now=NOW,
        owned_inventory=default_inventory if inventory is None else inventory,
        owned_research=default_research if research is None else research,
        opportunity_coverage=default_coverage if coverage is None else coverage,
        **kwargs,
    )


def set_profit(row, profit):
    row["scenario"]["financial"]["profit_per_day"] = profit
    row["profit_per_day"] = profit
    row["payback_days"] = round(row["investment"] / profit, 1)


def test_full_breakdown_and_proof_gate_yield_top_three():
    source = external(hub())
    original = deepcopy(source)
    report = build(external_data=source)
    message = report["html"]
    assert report["status"] == "recomendacoes_para_analise"
    assert report["alertable"] and report["read_only"]
    assert report["purchase_allowed"] is False and report["approved"] is False
    assert report["expansion_decision"]["status"] == "avaliacao_expansao"
    assert "XAP" in message and "sem lucro" in message and "rota ocupada" in message
    assert "H789" in message and "A320" in message
    assert "CFM &amp; Co &lt;fast&gt;" in message and "XAP ↔ GRU &lt;B&gt;" in message
    assert "Custos: hub $ 5.000,00" in message
    assert "aeronave $ 10.000,00" in message and "motor $ 400,00" in message
    assert "Rota $ 1.000,00" in message and "hangar $ 100,00" in message
    assert "taxas $ 50,00" in message and "Investimento <b>$ 16.550,00</b>" in message
    assert "reserva $ 2.000,00" in message and "Caixa necessário $ 18.550,00" in message
    assert "Lucro/dia projetado $ 500,00" in message and "retorno estimado 33.1 dias" in message
    assert "Pontos 0" in message and "Pendências: nenhuma identificada" in message
    assert "Nenhuma compra aprovada ou executada" in message
    assert source == original


def test_alert_preserves_recommendation_when_hub_limit_blocks_selection():
    report = build(policy=InvestmentPolicy(max_hub_investment=4999))
    assert report["alertable"] is True
    assert report["purchase_allowed"] is False
    assert report["expansion_decision"]["hub_limit_selection"]["eligible_count"] == 0
    assert "Hubs dentro dos limites individuais de capital e pontos: 0." in report["html"]
    eligible = build(policy=InvestmentPolicy(max_hub_investment=5000))
    assert eligible["alertable"] is True
    assert eligible["material"]["hub_limit_selection"]["selected_hub_id"] == "789"
    assert "Hubs dentro dos limites individuais de capital e pontos: 1." in eligible["html"]


def test_ranked_candidate_displays_independent_sources_and_observation_dates():
    report = build()
    candidate = report["candidates"][0]
    assert candidate["sources"] == {
        "catalog": "game_purchase_catalog", "research": "game_research",
        "prices": "game_market", "forecast": "route_optimizer",
    }
    assert candidate["observed_at"]["research"] == NOW
    assert candidate["observed_at"]["forecast"] == NOW
    assert "Fontes verificadas:" in report["html"]
    assert "game_purchase_catalog" in report["html"]
    assert "game_research" in report["html"]
    assert "route_optimizer" in report["html"]
    assert "UTC" in report["html"]
    assert "Critério do ranking: lucro diário por capital investido" in report["html"]


@pytest.mark.parametrize("invalidate", [
    lambda report: report.update(source="manual_guess"),
    lambda report: report["candidates"][0]["scenario"].update(source="manual_guess"),
    lambda report: report["candidates"][0]["scenario"]["costs"].update(source="manual_guess"),
    lambda report: report["candidates"][0]["scenario"]["financial"].update(source="manual_guess"),
])
def test_untrusted_provenance_cannot_generate_a_recommendation(invalidate, tmp_path):
    source = external(hub())
    invalidate(source)
    report = build(external_data=source)
    assert report["status"] == "pesquisa_externa_pendente"
    assert report["candidates"] == []
    assert report["alertable"] is False
    assert ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3").claim(report, now=NOW) is None


def test_ranking_uses_verified_return_per_capital_and_deduplicates_hubs():
    rows = [hub("789", profit=500), hub("888", profit=900), hub("777", profit=700),
            hub("666", profit=100)]
    report = build(external_data=external(*rows))
    assert [row["hub_id"] for row in report["candidates"]] == ["888", "777", "789"]
    assert "H666" not in report["html"]
    assert report["html"].count("Custos: hub") == 3


@pytest.mark.parametrize("section,field", [
    ("scenario", "profile_id"),
    ("costs", "profile_id"),
    ("financial", "snapshot_id"),
    ("cost_breakdown", "snapshot_id"),
])
def test_nested_foreign_evidence_is_filtered_before_top_three(section, field):
    corrupted = hub("888", profit=900)
    part = corrupted["scenario"].get(section) if section in ("costs", "financial") else corrupted[section]
    part[field] = "other" if field == "profile_id" else "sha256:" + "b" * 64
    report = build(external_data=external(
        corrupted, hub("777", profit=700), hub("789", profit=500), hub("666", profit=100),
    ))
    assert [row["hub_id"] for row in report["candidates"]] == ["777", "789", "666"]
    assert report["expansion_decision"]["external_pending_count"] == 1
    assert "H888" not in report["html"]


@pytest.mark.parametrize("change", [
    lambda row: row["scenario"].update(engine_id=None),
    lambda row: row["scenario"].update(engine_verified=False),
    lambda row: row["scenario"].update(external_demand_verified=False),
    lambda row: row["scenario"]["costs"].update(aircraft_price=7),
    lambda row: row["scenario"]["financial"].update(engine_id="wrong"),
    lambda row: row["cost_breakdown"].update(total="untrusted"),
    lambda row: row.update(pending=["motor_a_confirmar"]),
    lambda row: row.update(hub_points=10),
    lambda row: row.update(investment=12),
    lambda row: row.update(hub_price_observed_at=NOW - 259201),
])
def test_external_candidate_without_independent_proof_is_never_ranked(change):
    row = hub()
    change(row)
    report = build(external_data=external(row))
    assert report["candidates"] == []
    assert report["status"] == "pesquisa_externa_pendente"
    assert "Cenários externos com evidência pendente: 1" in report["html"]


@pytest.mark.parametrize("change", [
    lambda inv, research, coverage: inv.update(partial_fleet=True),
    lambda inv, research, coverage: research.update(partial_fleet=True),
    lambda inv, research, coverage: coverage.update(hubs=coverage["hubs"][:1]),
    lambda inv, research, coverage: coverage["hubs"][0].update(engines_complete=False),
    lambda inv, research, coverage: inv.update(observed_at=NOW - 259201),
])
def test_incomplete_owned_coverage_suppresses_alert_even_with_profitable_external(change):
    inventory, research, coverage = evidence()
    change(inventory, research, coverage)
    report = build(inventory=inventory, research=research, coverage=coverage)
    assert report["status"] == "inconclusivo"
    assert report["alertable"] is False
    assert report["candidates"] == []
    assert report["expansion_decision"]["blocking_reasons"]


def test_no_coverage_is_never_interpreted_as_no_owned_opportunities():
    inventory, research, _ = evidence()
    report = build_expansion_report(
        owned(), external(hub()), profile_id="principal", snapshot_id=SNAPSHOT,
        now=NOW, owned_inventory=inventory, owned_research=research,
    )
    assert report["status"] == "inconclusivo"
    assert report["alertable"] is False
    assert "varredura_completa_hubs_proprios_nao_comprovada" in report["expansion_decision"]["blocking_reasons"]


def test_finished_owned_scan_and_incomplete_external_catalog_have_distinct_statuses(tmp_path):
    report = build(external_data=external(hub(), complete=False))
    assert report["status"] == "pesquisa_externa_pendente"
    assert "nenhuma proposta elegível na comparação concluída" in report["html"]
    assert "catálogo externo incompleto" in report["html"].lower()
    assert "cobertura inconclusiva" not in report["html"]
    assert report["alertable"] is False
    assert ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3").claim(report, now=NOW) is None

    inventory, research, coverage = evidence()
    inventory["partial_fleet"] = True
    inconclusive = build(inventory=inventory, research=research, coverage=coverage,
                         external_data=external(hub(), complete=False))
    assert inconclusive["status"] == "inconclusivo"
    assert "cobertura inconclusiva" in inconclusive["html"]
    assert inconclusive["alertable"] is False


def test_unverified_external_research_reports_obstacles_without_telegram_alert(tmp_path):
    unverified = hub()
    unverified["scenario"]["external_demand_verified"] = False
    unverified["pending"] = ["demanda_pre_compra_a_confirmar"]
    report = build(external_data=external(unverified))
    assert report["status"] == "pesquisa_externa_pendente"
    assert report["candidates"] == []
    assert "demanda pre compra a confirmar" in report["html"]
    assert report["alertable"] is False
    assert ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3").claim(report, now=NOW) is None


def test_eligible_owned_hub_suppresses_alert_even_when_external_profit_is_higher():
    report = build(owned(eligible=1), compare_even_if_owned=True)
    assert report["status"] == "expansao_nao_indicada"
    assert report["alertable"] is False
    assert report["candidates"] == []
    assert "Comparação externa aguardando política" in report["html"]


def test_partial_catalog_or_missing_cash_prohibits_verified_ranking():
    assert build(external_data=external(hub(), complete=False))["status"] == "pesquisa_externa_pendente"
    report = build(external_data=external(hub(), cash=None))
    assert report["status"] == "pesquisa_externa_pendente"
    assert report["candidates"] == []


def test_report_supports_json_and_rejects_cross_profile_or_snapshot_evidence():
    inventory, research, coverage = evidence()
    report = build_expansion_report(
        json.dumps(owned()), json.dumps(external(hub())),
        profile_id="principal", snapshot_id=SNAPSHOT, now=NOW,
        owned_inventory=inventory, owned_research=research, opportunity_coverage=coverage,
    )
    assert report["status"] == "recomendacoes_para_analise"
    with pytest.raises(ValueError, match="perfil"):
        build(external_data={**external(hub()), "profile_id": "other"})
    with pytest.raises(ValueError, match="snapshot"):
        build(owned_data={**owned(), "snapshot_id": "sha256:" + "b" * 64})


def test_candidate_identity_mismatch_suppresses_only_that_candidate():
    mismatched = hub("789")
    mismatched["profile_id"] = "other"
    report = build(external_data=external(mismatched, hub("888")))
    assert [row["hub_id"] for row in report["candidates"]] == ["888"]


def test_included_engine_and_excluded_costs_are_explicit():
    row = hub(includes_engine=True)
    row["scenario"]["excluded_costs"] = ["A-check não comprovado"]
    report = build(external_data=external(row))
    assert report["status"] == "recomendacoes_condicionais"
    assert report["candidates"][0]["engine_included"] is True
    assert "motor incluído" in report["html"]
    assert "A-check não comprovado" in report["html"]


def test_html_escapes_untrusted_values_without_truncating_tags():
    rows = [hub(str(hub_id)) for hub_id in (789, 888, 777)]
    for row in rows:
        row["name"] = "<script>alert(1)</script>" * 20
        row["scenario"]["engine_label"] = "<dangerous> & <fast>" * 25
    report = build(external_data=external(*rows))
    assert "<script>" not in report["html"]
    assert "&lt;dangerous&gt;" in report["html"]
    assert len(report["html"]) <= MAX_HTML_LENGTH


def test_first_alert_and_cooldown_persist_across_restart(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    store = ExpansionAlertDeduplicator(path)
    initial = store.claim(build(), now=NOW)
    assert initial and initial["reason"] == "primeiro_alerta"
    assert store.claim(build(), now=NOW + 1) is None
    assert store.acknowledge(initial, delivered=True, now=NOW + 2)
    restarted = ExpansionAlertDeduplicator(path)
    assert restarted.claim(build(snapshot="sha256:" + "b" * 64), now=NOW + 11) is None
    reminder = restarted.claim(build(), now=NOW + 6 * 3600 + 3)
    assert reminder and reminder["reason"] == "cooldown_expirado"


def test_significant_material_change_bypasses_cooldown_but_small_profit_change_does_not(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    initial = store.claim(build(), now=NOW)
    assert store.acknowledge(initial, delivered=True, now=NOW)
    slight = hub()
    set_profit(slight, 510)
    assert store.claim(build(external_data=external(slight)), now=NOW + 60) is None
    changed = hub(engine_id="engine-4")
    update = store.claim(build(external_data=external(changed)), now=NOW + 61)
    assert update and update["reason"] == "mudanca_material"
    assert "Atualização relevante na expansão" in update["html"]
    assert store.acknowledge(update, delivered=True, now=NOW + 62)


def test_updated_provenance_is_material_but_refreshed_timestamps_are_not(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    first = store.claim(build(), now=NOW)
    assert store.acknowledge(first, delivered=True, now=NOW)
    renewed = hub()
    renewed["scenario"]["observed_at"] += 10
    renewed["scenario"]["costs"]["observed_at"] += 10
    renewed["scenario"]["financial"]["observed_at"] += 10
    assert store.claim(build(external_data=external(renewed)), now=NOW + 60) is None
    replaced = hub()
    replaced["scenario"]["financial"]["source"] = "game_research"
    alert = store.claim(build(external_data=external(replaced)), now=NOW + 61)
    assert alert and alert["reason"] == "mudanca_material"


def test_native_model_change_is_material_even_with_same_display_name(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    first = store.claim(build(), now=NOW)
    assert store.acknowledge(first, delivered=True, now=NOW)
    changed = hub()
    scenario = changed["scenario"]
    for proof in (scenario, scenario["costs"], scenario["financial"]):
        proof["model_id"] = "102"
    report = build(external_data=external(changed))
    assert report["candidates"][0]["model_id"] == "102"
    alert = store.claim(report, now=NOW + 60)
    assert alert and alert["reason"] == "mudanca_material"


def test_significant_cost_change_alerts_and_missing_proof_withholds_recommendation(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    first = store.claim(build(), now=NOW)
    assert store.acknowledge(first, delivered=True, now=NOW)
    cost = hub(price=12000)
    alert = store.claim(build(external_data=external(cost)), now=NOW + 60)
    assert alert and alert["reason"] == "mudanca_material"
    assert store.acknowledge(alert, delivered=True, now=NOW + 61)
    missing = hub(price=12000)
    missing["scenario"]["demand_verified"] = False
    report = build(external_data=external(missing))
    assert report["candidates"] == []
    assert report["status"] == "pesquisa_externa_pendente"


def test_failed_delivery_allows_retry_and_claim_token_is_unique(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    first = store.claim(build(), now=NOW)
    assert store.acknowledge(first, delivered=False, now=NOW + 1)
    assert not store.acknowledge(first, delivered=True, now=NOW + 2)
    retry = store.claim(build(), now=NOW + 3)
    assert retry and retry["claim_id"] != first["claim_id"]


def test_alerts_are_isolated_by_profile(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    primary = store.claim(build(), now=NOW)
    secondary = store.claim(build(profile="outro"), now=NOW)
    assert primary and secondary and primary["claim_id"] != secondary["claim_id"]
    assert not store.acknowledge({**primary, "profile_id": "outro"}, delivered=True, now=NOW)
    assert store.acknowledge(primary, delivered=True, now=NOW)
    assert store.acknowledge(secondary, delivered=True, now=NOW)


def test_lease_expiry_does_not_allow_old_acknowledgment(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    first = store.claim(build(), now=NOW)
    assert store.claim(build(), now=NOW + CLAIM_LEASE_SECONDS - 1) is None
    later = store.claim(build(), now=NOW + CLAIM_LEASE_SECONDS)
    assert later and later["claim_id"] != first["claim_id"]
    assert not store.acknowledge(first, delivered=True, now=NOW + CLAIM_LEASE_SECONDS)
    assert store.acknowledge(later, delivered=True, now=NOW + CLAIM_LEASE_SECONDS + 1)


def test_concurrent_claims_emit_once(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    stores = [ExpansionAlertDeduplicator(path), ExpansionAlertDeduplicator(path)]
    report = build()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda store: store.claim(report, now=NOW), stores))
    assert sum(claim is not None for claim in claims) == 1


def test_inconclusive_report_never_claims_and_inputs_are_validated(tmp_path):
    store = ExpansionAlertDeduplicator(tmp_path / "alerts.sqlite3")
    report = build(owned(complete=False))
    assert report["status"] == "inconclusivo"
    assert store.claim(report, now=NOW) is None
    with pytest.raises(ValueError):
        store.claim({**build(), "html": "X" * 4001}, now=NOW)
    with pytest.raises(ValueError):
        store.claim(build(), now=NOW, cooldown_seconds=-1)
    with pytest.raises(ValueError):
        store.acknowledge({"profile_id": "principal", "claim_id": "invalid"}, delivered=True)
