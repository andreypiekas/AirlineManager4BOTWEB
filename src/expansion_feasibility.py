"""Read-only gate between exhausted owned hubs and external-hub suggestions.

The opportunity search must explicitly certify full coverage for every owned
hub. An empty list of researched scenarios is never coverage evidence.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from collections.abc import Mapping

from hub_expansion import (MAX_AGE_SECONDS, MAX_FINANCIAL_VALUE, excluded_research_costs,
                           native_scenario_identity, scenario_scope_consistent)
from investment_policy import InvestmentPolicy


_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SNAPSHOT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONCLUSIVE_STATUSES = {
    "viavel", "saldo_insuficiente", "sem_lucro", "rota_inviavel",
    "rota_ocupada", "rota_indisponivel",
}


def _fresh(when: object, now: float, max_age_seconds: int) -> bool:
    """Require recent, finite game timestamps without truncating DOM precision."""
    if type(when) not in (int, float) or type(now) not in (int, float):
        return False
    try:
        observed, current = float(when), float(now)
    except (OverflowError, ValueError):
        return False
    return (math.isfinite(observed) and math.isfinite(current)
            and observed > 0 and 0 <= current - observed <= max_age_seconds)


def _nonnegative(value: object) -> bool:
    if type(value) not in (int, float) or not 0 <= value <= MAX_FINANCIAL_VALUE:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _bound_to_capture(proof: Mapping, profile_id: str | None,
                      snapshot_id: str | None) -> bool:
    return (isinstance(profile_id, str) and bool(profile_id.strip())
            and isinstance(snapshot_id, str) and _SNAPSHOT_ID.fullmatch(snapshot_id) is not None
            and proof.get("profile_id") == profile_id
            and proof.get("snapshot_id") == snapshot_id)


def _candidate_id(value: object) -> str | None:
    """Identify duplicate legacy integer IDs without approving malformed IDs."""
    if type(value) not in (int, str):
        return None
    value = str(value)
    return value if _GAME_ID.fullmatch(value) else None


def _valid_external(row: Mapping, external: Mapping, now: float, *,
                    max_age_seconds: int, profile_id: str | None,
                    snapshot_id: str | None, require_snapshot_scope: bool) -> bool:
    """Recheck a candidate's exact engine, route, cost and profit evidence."""
    if ((profile_id is not None and row.get("profile_id") not in (None, profile_id))
            or (snapshot_id is not None and row.get("snapshot_id") not in (None, snapshot_id))):
        return False
    scenario = row.get("scenario")
    if not isinstance(scenario, Mapping):
        return False
    costs = scenario.get("costs")
    financial = scenario.get("financial")
    breakdown = row.get("cost_breakdown")
    if not all(isinstance(part, Mapping) for part in (costs, financial, breakdown)):
        return False
    if not scenario_scope_consistent(external, row, scenario, costs, financial, breakdown,
                                     profile_id=profile_id, snapshot_id=snapshot_id):
        return False
    if require_snapshot_scope and not all(
        _bound_to_capture(proof, profile_id, snapshot_id)
        for proof in (external, scenario, costs, financial)
    ):
        return False
    origin = str(scenario.get("origin_id") or "")
    destination = str(scenario.get("destination_id") or "")
    model = scenario.get("model")
    engine = scenario.get("engine_id")
    route = scenario.get("route")
    excluded = excluded_research_costs(scenario)
    if excluded is None or (require_snapshot_scope and not any(
            "excluded_costs" in proof for proof in (scenario, financial))):
        return False
    verified = (row.get("status") == "viavel" and row.get("ranking_conclusive") is True
                and row.get("purchase_evidence") is True and row.get("pending") == [])
    conditional = (bool(excluded) and row.get("status") == "projecao_condicional"
                   and row.get("ranking_conclusive") is False and row.get("purchase_evidence") is False
                   and row.get("pending") == ["custos_recorrentes_excluidos"])
    if not ((verified or conditional)
            and row.get("hub_price_conflict_at") is None
            and row.get("hub_points_conflict_at") is None
            and isinstance(row.get("id"), str) and _GAME_ID.fullmatch(row["id"])
            and isinstance(model, str) and model.strip()
            and isinstance(engine, str) and _ENGINE_ID.fullmatch(engine)
            and isinstance(route, str) and route.strip()
            and _GAME_ID.fullmatch(origin) and _GAME_ID.fullmatch(destination)
            and origin == row["id"] and origin != destination
            and scenario.get("source") == "game_research"
            and scenario.get("engine_verified") is True
            and scenario.get("demand_verified") is True
            and scenario.get("event_demand_boosted") is not True
            and scenario.get("external_demand_verified") is True
            and scenario.get("route_feasible") is True
            and type(row.get("hub_points")) is int and row["hub_points"] == 0
            and type(breakdown.get("hub_points")) is int and breakdown["hub_points"] == row["hub_points"]
            and all(_fresh(item, now, max_age_seconds) for item in (
                row.get("observed_at"), row.get("hub_price_observed_at"), row.get("hub_points_observed_at"),
                scenario.get("observed_at"), costs.get("observed_at"),
                financial.get("observed_at")))
            and costs.get("source") in ("game_market", "game_research")
            and financial.get("source") in ("route_optimizer", "game_research")
            and type(costs.get("aircraft_price_includes_engine")) is bool
            and scenario.get("costs") == costs):
        return False
    identity = native_scenario_identity(scenario)
    if (identity is None or identity[-1] is not None
            or any(native_scenario_identity(proof) != identity for proof in (costs, financial))):
        return False
    cost_names = ("hub_price", "aircraft_price", "engine_extra_charged",
                  "route_fee", "hangar_price", "other_fees")
    if not all(_nonnegative(breakdown.get(key)) for key in cost_names):
        return False
    if (not _nonnegative(breakdown.get("reserve"))
            or not _nonnegative(breakdown.get("total"))
            or not _nonnegative(breakdown.get("cash_required"))
            or not _nonnegative(external.get("available_cash"))
            or not _nonnegative(row.get("investment")) or row["investment"] < 0.01
            or not _nonnegative(row.get("profit_per_day"))
            or not _nonnegative(row.get("payback_days"))):
        return False
    investment = round(sum(breakdown[key] for key in cost_names), 2)
    profit = financial.get("profit_per_day")
    if (not _nonnegative(profit) or profit < 0.01 or not _nonnegative(investment)
            or investment < 0.01 or not _nonnegative(investment + breakdown["reserve"])
            or not _nonnegative(investment / profit)):
        return False
    includes_engine = costs["aircraft_price_includes_engine"]
    engine_delta = costs.get("engine_delta_cost")
    if (costs.get("engine_delta_invalid") is True
            or (engine_delta is not None and not _nonnegative(engine_delta))
            or breakdown.get("aircraft_price_includes_engine") is not includes_engine
            or (includes_engine and engine_delta not in (None, 0))
            or (not includes_engine and not _nonnegative(engine_delta))):
        return False
    if (any(not _nonnegative(costs.get(key)) or costs[key] != breakdown[key]
            for key in ("aircraft_price", "route_fee", "hangar_price", "other_fees"))
            or row.get("hub_price") != breakdown["hub_price"]
            or costs.get("aircraft_price_includes_engine") is True
            and breakdown["engine_extra_charged"] != 0
            or costs.get("aircraft_price_includes_engine") is False
            and costs.get("engine_delta_cost") != breakdown["engine_extra_charged"]
            or investment != row["investment"]
            or investment != breakdown["total"]
            or round(investment + breakdown["reserve"], 2) != breakdown["cash_required"]
            or investment > external["available_cash"]
            or profit != row["profit_per_day"]
            or round(investment / profit, 1) != row["payback_days"]):
        return False
    if "cash" in external or "reserve" in external:
        cash, reserve = external.get("cash"), external.get("reserve")
        if (not _nonnegative(cash) or not _nonnegative(reserve)
                or reserve != breakdown["reserve"]
                or round(max(0, cash - reserve), 2) != external["available_cash"]):
            return False
    return True


def assess_expansion(
    owned_inventory: Mapping | None,
    owned_research: Mapping | None,
    owned_portfolio: Mapping | None,
    external_report: Mapping | None,
    *,
    coverage: Mapping | None = None,
    now: float | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
    profile_id: str | None = None,
    snapshot_id: str | None = None,
    require_snapshot_scope: bool = False,
    policy: InvestmentPolicy | None = None,
) -> dict:
    """Evaluate full owned-hub exhaustion before suggesting external hubs.

    ``coverage`` is a separate proof emitted by a complete opportunity scan.
    Its per-hub rows must cover routes, aircraft models, engine variants and
    financial research from the same scan. No current caller fabricates it.
    """
    now = time.time() if now is None else now
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ValueError("max_age_seconds inválido")
    inventory = owned_inventory if isinstance(owned_inventory, Mapping) else {}
    research = owned_research if isinstance(owned_research, Mapping) else {}
    portfolio = owned_portfolio if isinstance(owned_portfolio, Mapping) else {}
    external = external_report if isinstance(external_report, Mapping) else {}
    scan = coverage if isinstance(coverage, Mapping) else {}
    reasons = []

    # Historical reports may be inspected, but production decisions need an
    # independently captured identity on every source used to exhaust owned hubs.
    if not scenario_scope_consistent(inventory, research, portfolio, scan,
                                     profile_id=profile_id, snapshot_id=snapshot_id):
        reasons.append("escopo_hubs_proprios_divergente")
    if require_snapshot_scope and not all(
        _bound_to_capture(proof, profile_id, snapshot_id)
        for proof in (inventory, research, portfolio, scan)
    ):
        reasons.append("snapshot_produtivo_hubs_proprios_nao_comprovado")

    hubs = inventory.get("hubs")
    owned_ids = [row.get("id") for row in hubs if isinstance(row, Mapping)] if isinstance(hubs, list) else []
    valid_ids = (all(isinstance(item, str) and _GAME_ID.fullmatch(item) is not None
                     for item in owned_ids))
    if (not owned_ids or not valid_ids or (valid_ids and len(set(owned_ids)) != len(owned_ids))
            or inventory.get("source") != "game_hub_select"
            or not _fresh(inventory.get("observed_at"), now, max_age_seconds)):
        reasons.append("inventario_hubs_proprios_a_confirmar")
    if inventory.get("partial_fleet") is not False or research.get("partial_fleet") is not False:
        reasons.append("cobertura_frota_incompleta")

    if (portfolio.get("status") != "comparacao_concluida"
            or portfolio.get("blocking_reasons") != []):
        reasons.append("comparacao_hubs_proprios_inconclusiva")
    if (portfolio.get("eligible_count") is None
            or type(portfolio.get("eligible_count")) is not int
            or portfolio["eligible_count"] < 0):
        reasons.append("resultado_portfolio_invalido")

    scenarios = research.get("candidates")
    if not isinstance(scenarios, list) or any(
            not isinstance(row, Mapping)
            or row.get("status") not in _CONCLUSIVE_STATUSES
            or bool(row.get("pending")) for row in scenarios):
        reasons.append("cenarios_proprios_pendentes")

    scan_hubs = scan.get("hubs")
    if (scan.get("source") != "game_hub_opportunity_scan"
            or scan.get("complete") is not True
            or not _fresh(scan.get("observed_at"), now, max_age_seconds)
            or not isinstance(scan_hubs, list)
            or len(scan_hubs) != len(owned_ids)):
        reasons.append("varredura_completa_hubs_proprios_nao_comprovada")
    else:
        scan_ids = set()
        for item in scan_hubs:
            if (not isinstance(item, Mapping)
                    or item.get("hub_id") not in owned_ids
                    or not isinstance(item.get("hub_id"), str)
                    or item.get("hub_id") in scan_ids
                    or item.get("source") != "game_hub_opportunity_scan"
                    or item.get("complete") is not True
                    or not _fresh(item.get("observed_at"), now, max_age_seconds)
                    or item.get("routes_complete") is not True
                    or item.get("models_complete") is not True
                    or item.get("engines_complete") is not True
                    or item.get("costs_complete") is not True
                    or item.get("demand_complete") is not True
                    or not scenario_scope_consistent(item, scan, profile_id=profile_id,
                                                     snapshot_id=snapshot_id)
                    or (require_snapshot_scope and not _bound_to_capture(item, profile_id, snapshot_id))):
                reasons.append("varredura_completa_hubs_proprios_nao_comprovada")
                break
            scan_ids.add(item["hub_id"])

    status = "inconclusivo"
    if not reasons and portfolio["eligible_count"] > 0:
        status = "priorizar_hubs_proprios"
    if not reasons and portfolio["eligible_count"] == 0:
        if (external.get("catalog_complete") is not True
                or external.get("source") != "game_purchase_catalog"
                or not _fresh(external.get("observed_at"), now, max_age_seconds)):
            reasons.append("catalogo_expansao_incompleto_ou_vencido")
        elif require_snapshot_scope and not _bound_to_capture(external, profile_id, snapshot_id):
            reasons.append("snapshot_produtivo_catalogo_externo_nao_comprovado")
        else:
            status = "avaliacao_expansao"

    all_external = external.get("candidates")
    all_external = all_external if isinstance(all_external, list) else []
    external_ids = Counter(_candidate_id(row.get("id")) for row in all_external
                           if isinstance(row, Mapping))

    def valid(row: object) -> bool:
        return (isinstance(row, Mapping) and isinstance(row.get("id"), str)
                and row["id"] not in owned_ids and external_ids[row["id"]] == 1 and _valid_external(
            row, external, now, max_age_seconds=max_age_seconds,
            profile_id=profile_id, snapshot_id=snapshot_id,
            require_snapshot_scope=require_snapshot_scope,
        ))

    rankable = []
    for row in all_external:
        if not valid(row):
            continue
        candidate = dict(row)
        if excluded_research_costs(row["scenario"]):
            candidate.update(status="projecao_condicional", ranking_conclusive=False,
                             purchase_evidence=False, pending=["custos_recorrentes_excluidos"])
        rankable.append(candidate)
    pending_count = len(all_external) - len(rankable)
    rankable.sort(key=lambda row: (
        bool(excluded_research_costs(row["scenario"])),
        -row["profit_per_day"] / row["investment"],
        -row["profit_per_day"], row["investment"], row["id"],
    ))
    if status != "avaliacao_expansao":
        rankable = []

    # A6 remains useful in analysis mode. A8 filters the full evidence-backed
    # ranking before selecting a hub, including candidates below the top three.
    eligible = []
    excluded = []
    for row in rankable:
        vetoes = []
        if excluded_research_costs(row["scenario"]):
            vetoes.append("custos_recorrentes_excluidos")
        if policy is None or not policy.valid:
            vetoes.append("politica_invalida_ou_ausente")
        else:
            if (type(policy.max_hub_investment) is not int
                    or not 0 < policy.max_hub_investment <= 10**15
                    or not 0 < row["hub_price"] <= policy.max_hub_investment
                    or row["hub_price"] % 1 != 0):
                vetoes.append("limite_por_compra_de_hub")
            if (type(policy.max_hub_points) is not int
                    or not 0 <= policy.max_hub_points <= 10**9
                    or row["hub_points"] > policy.max_hub_points):
                vetoes.append("limite_de_pontos_de_hub")
        if vetoes:
            excluded.append({"hub_id": row["id"], "reasons": vetoes})
        else:
            eligible.append(row)

    return {
        "status": status,
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "owned_hubs_evaluated": len(owned_ids) if not reasons else None,
        "owned_eligible_count": portfolio.get("eligible_count"),
        "top_three": rankable[:3],
        "hub_limit_selection": {
            "eligible_count": len(eligible),
            "selected_hub_id": eligible[0]["id"] if eligible else None,
            "eligible_hub_ids": [row["id"] for row in eligible],
            "excluded": excluded,
            "execution_available": False,
        },
        "external_pending_count": pending_count,
        "read_only": True,
        "execution_available": False,
    }
