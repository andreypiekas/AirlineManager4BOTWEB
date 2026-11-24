"""Read-only gate between exhausted owned hubs and external-hub suggestions.

The opportunity search must explicitly certify full coverage for every owned
hub. An empty list of researched scenarios is never coverage evidence.
"""
from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping

from hub_expansion import MAX_AGE_SECONDS


_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
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
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _valid_external(row: Mapping, external: Mapping, now: float, *,
                    max_age_seconds: int, profile_id: str | None,
                    snapshot_id: str | None) -> bool:
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
    origin = str(scenario.get("origin_id") or "")
    destination = str(scenario.get("destination_id") or "")
    model = scenario.get("model")
    engine = scenario.get("engine_id")
    route = scenario.get("route")
    if not (row.get("status") == "viavel"
            and row.get("ranking_conclusive") is True
            and row.get("purchase_evidence") is True
            and row.get("pending") == []
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
            and all(_fresh(item, now, max_age_seconds) for item in (
                row.get("hub_price_observed_at"), row.get("hub_points_observed_at"),
                scenario.get("observed_at"), costs.get("observed_at"),
                financial.get("observed_at")))
            and costs.get("source") in ("game_market", "game_research")
            and financial.get("source") in ("route_optimizer", "game_research")
            and costs.get("aircraft_price_includes_engine") in (True, False)
            and scenario.get("costs") == costs):
        return False
    identity = (model.casefold(), engine, origin, destination, route.casefold())
    for proof in (costs, financial):
        proof_model = proof.get("model")
        proof_route = proof.get("route")
        if (not isinstance(proof_model, str) or not isinstance(proof_route, str)
                or (proof_model.strip().casefold(), proof.get("engine_id"),
                    str(proof.get("origin_id") or ""),
                    str(proof.get("destination_id") or ""),
                    proof_route.strip().casefold()) != identity):
            return False
    cost_names = ("hub_price", "aircraft_price", "engine_extra_charged",
                  "route_fee", "hangar_price", "other_fees")
    if not all(_nonnegative(breakdown.get(key)) for key in cost_names):
        return False
    if (not _nonnegative(breakdown.get("reserve"))
            or not _nonnegative(breakdown.get("total"))
            or not _nonnegative(breakdown.get("cash_required"))
            or not _nonnegative(external.get("available_cash"))
            or not _nonnegative(row.get("investment"))
            or not _nonnegative(row.get("profit_per_day"))
            or not _nonnegative(row.get("payback_days"))):
        return False
    investment = sum(breakdown[key] for key in cost_names)
    profit = financial.get("profit_per_day")
    if not _nonnegative(profit) or profit <= 0 or investment <= 0:
        return False
    if (any(not _nonnegative(costs.get(key)) or costs[key] != breakdown[key]
            for key in ("aircraft_price", "route_fee", "hangar_price", "other_fees"))
            or row.get("hub_price") != breakdown["hub_price"]
            or costs.get("aircraft_price_includes_engine") is True
            and breakdown["engine_extra_charged"] != 0
            or costs.get("aircraft_price_includes_engine") is False
            and costs.get("engine_delta_cost") != breakdown["engine_extra_charged"]
            or abs(investment - row["investment"]) > 0.02
            or abs(investment - breakdown.get("total", float("inf"))) > 0.02
            or abs(investment + breakdown["reserve"] - breakdown["cash_required"]) > 0.02
            or breakdown["cash_required"] > external["available_cash"]
            or abs(profit - row["profit_per_day"]) > 0.02
            or abs(investment / profit - row["payback_days"]) > 0.06):
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
                    or item.get("demand_complete") is not True):
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
        else:
            status = "avaliacao_expansao"

    all_external = external.get("candidates")
    all_external = all_external if isinstance(all_external, list) else []
    def valid(row: object) -> bool:
        return isinstance(row, Mapping) and _valid_external(
            row, external, now, max_age_seconds=max_age_seconds,
            profile_id=profile_id, snapshot_id=snapshot_id,
        )

    rankable = [dict(row) for row in all_external if valid(row)]
    rankable.sort(key=lambda row: (
        -row["profit_per_day"] / row["investment"],
        -row["profit_per_day"], row["investment"], row["id"],
    ))
    if status != "avaliacao_expansao":
        rankable = []
    pending_count = sum(not valid(row) for row in all_external)

    return {
        "status": status,
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "owned_hubs_evaluated": len(owned_ids) if not reasons else None,
        "owned_eligible_count": portfolio.get("eligible_count"),
        "top_three": rankable[:3],
        "external_pending_count": pending_count,
        "read_only": True,
        "execution_available": False,
    }
