"""Read-only global comparison of researched aircraft opportunities.

Consumes the conservative output of ``rank_next_aircraft``. It never grants
purchase approval. Coverage of research and outstanding commitments require
independent verification before a comparison can be conclusive.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any


DEFAULT_PROFIT_WEIGHT = 0.6
DEFAULT_EFFICIENCY_WEIGHT = 0.4
DEFAULT_RISK_WEIGHT = 0.0
DEFAULT_CONFIDENCE_WEIGHT = 0.0
DEFAULT_DIVERSIFICATION_WEIGHT = 0.0
_OPTIONAL_DIMENSIONS = ("risk", "confidence", "diversification")
_EVIDENCE_SOURCES = {
    "risk": frozenset(("route_optimizer", "game_research")),
    "confidence": frozenset(("route_optimizer", "game_research")),
    "diversification": frozenset(("game_hub_select",)),
}
_MAX_EVIDENCE_AGE_SECONDS = 3 * 86400
_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")


def _number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or (positive and number <= 0):
        return None
    return number


def _evidence_index(row: Mapping[str, Any], report: Mapping[str, Any],
                    dimension: str) -> float | None:
    """Read only explicitly verified, snapshot-linked ranking evidence.

    ``risk.value`` represents exposure (zero is safer). Confidence and
    diversification values are benefits (one is better). All values must be
    normalized to [0, 1] by the evidence producer. This function never
    derives those metrics from price, hub size, or an invented market proxy.
    """
    evidence = row.get("ranking_evidence")
    metric = evidence.get(dimension) if isinstance(evidence, Mapping) else None
    if not isinstance(metric, Mapping) or metric.get("verified") is not True:
        return None

    value = _number(metric.get("value"))
    timestamp = _number(metric.get("observed_at"), positive=True)
    source = metric.get("source")
    reference_source = (row.get("financial_source")
                        if dimension != "diversification" else report.get("source"))
    reference_time = _number(
        row.get("observed_at") if dimension != "diversification"
        else report.get("inventory_observed_at"), positive=True)
    if (value is None or value > 1 or timestamp is None or reference_time is None
            or not isinstance(source, str)
            or source not in _EVIDENCE_SOURCES[dimension]
            or source != reference_source
            or not 0 <= reference_time - timestamp <= _MAX_EVIDENCE_AGE_SECONDS):
        return None
    if metric.get("hub_id") != row.get("hub_id"):
        return None
    if dimension != "diversification" and any(
        metric.get(field) != row.get(field)
        for field in ("route_key", "model", "engine_id")
    ):
        return None
    return 1 - value if dimension == "risk" else value


def compare_portfolio(
    hub_report: Mapping[str, Any],
    *,
    research_coverage_verified: bool = False,
    commitments_verified: bool = False,
    committed_cash: object = None,
    known_local_commitments: object = None,
    max_single_investment: object = None,
    min_daily_profit: object = 0,
    max_payback_days: object = None,
    profit_weight: float = DEFAULT_PROFIT_WEIGHT,
    efficiency_weight: float = DEFAULT_EFFICIENCY_WEIGHT,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
    diversification_weight: float = DEFAULT_DIVERSIFICATION_WEIGHT,
    policy_valid: bool = True,
) -> dict:
    """Compare every eligible hub/route/model/engine, irrespective of hub.

    Unknown commitments cannot be silently treated as zero. A caller may
    display ranked alternatives with incomplete evidence, but the conclusion
    stays inconclusive and ``execution_available`` always remains false.

    Optional ranking dimensions start disabled. When enabled, each candidate
    needs ``ranking_evidence[dimension]`` with normalized ``value`` in [0, 1],
    ``source``, ``observed_at``, ``verified=True`` and matching ``hub_id``.
    Risk/confidence evidence must also identify the route, model and engine.
    Risk is an exposure (lower is better); confidence and diversification are
    benefits (higher is better). Source/timestamp must match their snapshots.
    """
    report = hub_report if isinstance(hub_report, Mapping) else {}
    candidates = report.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    blockers = []
    if policy_valid is not True:
        blockers.append("politica_invalida")
    if report.get("partial_fleet") is not False:
        blockers.append("cobertura_frota_a_confirmar")
    if research_coverage_verified is not True:
        blockers.append("cobertura_pesquisa_a_confirmar")
    if commitments_verified is not True:
        blockers.append("pedidos_pendentes_a_conciliar")

    available_cash = _number(report.get("available_cash"))
    obligations = _number(committed_cash) if commitments_verified is True else None
    local_commitments = (_number(known_local_commitments)
                         if known_local_commitments is not None else None)
    if available_cash is None:
        blockers.append("saldo_disponivel_a_confirmar")
    if commitments_verified is True and obligations is None:
        blockers.append("compromissos_invalidos")
    if known_local_commitments is not None and local_commitments is None:
        blockers.append("reservas_locais_invalidas")
    budget = (max(0.0, available_cash - obligations)
              if available_cash is not None and obligations is not None else None)
    budget_upper_bound = (max(0.0, available_cash - local_commitments)
                          if available_cash is not None and local_commitments is not None else None)

    single_limit = (_number(max_single_investment, positive=True)
                    if max_single_investment is not None else None)
    minimum_profit = _number(min_daily_profit)
    maximum_payback = (_number(max_payback_days, positive=True)
                       if max_payback_days is not None else None)
    weights = {
        "profit": _number(profit_weight),
        "capital_efficiency": _number(efficiency_weight),
        "risk": _number(risk_weight),
        "confidence": _number(confidence_weight),
        "diversification": _number(diversification_weight),
    }
    total_weight = (sum(weights.values())
                    if all(weight is not None for weight in weights.values()) else None)
    valid_weights = (total_weight is not None and math.isfinite(total_weight)
                     and total_weight > 0)
    if (minimum_profit is None
            or (max_single_investment is not None and single_limit is None)
            or (max_payback_days is not None and maximum_payback is None)
            or not valid_weights):
        blockers.append("criterios_planejamento_invalidos")

    excluded = Counter()
    unique = {}
    conflicting = set()
    missing_evidence = Counter()
    for row in candidates:
        if not isinstance(row, Mapping) or row.get("status") != "viavel" or row.get("pending"):
            excluded["cenario_nao_validado"] += 1
            continue
        investment = _number(row.get("investment"), positive=True)
        profit = _number(row.get("profit_per_day"), positive=True)
        hub_id = row.get("hub_id")
        route_key = row.get("route_key")
        model = row.get("model")
        engine_id = row.get("engine_id")
        origin = row.get("origin")
        destination = row.get("destination")
        if (investment is None or profit is None
                or not all(isinstance(value, str) and value for value in
                           (hub_id, route_key, model, engine_id))
                or _GAME_ID.fullmatch(hub_id) is None
                or not isinstance(origin, Mapping) or not isinstance(destination, Mapping)
                or not isinstance(origin.get("id"), str)
                or not isinstance(destination.get("id"), str)
                or _GAME_ID.fullmatch(origin["id"]) is None
                or _GAME_ID.fullmatch(destination["id"]) is None):
            excluded["identidade_ou_custos_a_confirmar"] += 1
            continue
        if minimum_profit is None or profit < minimum_profit:
            excluded["lucro_abaixo_do_minimo"] += 1
            continue
        payback = investment / profit
        efficiency = profit / investment
        if not math.isfinite(payback) or not math.isfinite(efficiency) or efficiency <= 0:
            excluded["economia_fora_do_intervalo"] += 1
            continue
        if maximum_payback is not None and payback > maximum_payback:
            excluded["retorno_acima_do_limite"] += 1
            continue
        if single_limit is not None and investment > single_limit:
            excluded["limite_por_aquisicao"] += 1
            continue
        if budget is not None and investment > budget:
            excluded["caixa_apos_compromissos_insuficiente"] += 1
            continue
        if budget_upper_bound is not None and investment > budget_upper_bound:
            excluded["caixa_apos_reservas_locais_insuficiente"] += 1
            continue

        identity = (hub_id, route_key, model.casefold(), engine_id)
        item = dict(row)
        for key in ("profit_index", "efficiency_index", "risk_index",
                    "confidence_index", "diversification_index", "score",
                    "score_components"):
            item.pop(key, None)
        item["investment"] = investment
        item["profit_per_day"] = profit
        item["payback_days"] = round(payback, 2)
        item["capital_efficiency_per_day"] = round(efficiency, 8)
        if valid_weights:
            indexes = {}
            for dimension in _OPTIONAL_DIMENSIONS:
                if weights[dimension] > 0:
                    index = _evidence_index(row, report, dimension)
                    if index is None:
                        missing_evidence[dimension] += 1
                    else:
                        indexes[dimension] = index
            if len(indexes) != sum(weights[name] > 0 for name in _OPTIONAL_DIMENSIONS):
                excluded["evidencia_ranking_incompleta"] += 1
                continue
            for dimension, index in indexes.items():
                item[f"{dimension}_index"] = index
        # Repeats do not increase a candidate's weight. Contradictory prices
        # or evidence for one identity remove it pending fresh research.
        if identity in conflicting:
            excluded["pesquisas_conflitantes"] += 1
        elif identity in unique and unique[identity] != item:
            conflicting.add(identity)
            del unique[identity]
            excluded["pesquisas_conflitantes"] += 2
        elif identity not in unique:
            unique[identity] = item

    for dimension in _OPTIONAL_DIMENSIONS:
        if missing_evidence[dimension]:
            blockers.append(f"evidencia_{dimension}_a_confirmar")

    alternatives = list(unique.values())
    if alternatives and "criterios_planejamento_invalidos" not in blockers:
        highest_profit = max(item["profit_per_day"] for item in alternatives)
        highest_efficiency = max(item["profit_per_day"] / item["investment"]
                                 for item in alternatives)
        for item in alternatives:
            profit_index = item["profit_per_day"] / highest_profit
            efficiency_index = (item["profit_per_day"] / item["investment"]
                                / highest_efficiency)
            item["profit_index"] = round(profit_index, 6)
            item["efficiency_index"] = round(efficiency_index, 6)
            indexes = {"profit": profit_index, "capital_efficiency": efficiency_index}
            indexes.update((dimension, item[f"{dimension}_index"])
                           for dimension in _OPTIONAL_DIMENSIONS if weights[dimension] > 0)
            contributions = {name: indexes[name] * (weight / total_weight)
                             for name, weight in weights.items() if weight > 0}
            item["score_components"] = {name: round(amount, 6)
                                        for name, amount in contributions.items()}
            item["score"] = round(math.fsum(contributions.values()), 6)
            for dimension in _OPTIONAL_DIMENSIONS:
                if weights[dimension] > 0:
                    item[f"{dimension}_index"] = round(item[f"{dimension}_index"], 6)
        alternatives.sort(key=lambda item: (
            -item["score"], -item["profit_per_day"], item["payback_days"],
            item["investment"], item["hub_id"], item["model"].casefold(),
            item["engine_id"], item["route_key"],
        ))
    else:
        alternatives = []

    return {
        "status": "inconclusivo" if blockers else "comparacao_concluida",
        "blocking_reasons": blockers,
        "best": alternatives[0] if alternatives else None,
        "alternatives": alternatives,
        "evaluated_count": len(candidates),
        "eligible_count": len(alternatives),
        "excluded": dict(sorted(excluded.items())),
        "missing_ranking_evidence": dict(sorted(missing_evidence.items())),
        "budget_after_commitments": budget,
        "known_local_commitments": local_commitments,
        "budget_upper_bound": budget_upper_bound,
        "criteria": {
            "minimum_daily_profit": minimum_profit,
            "maximum_payback_days": maximum_payback,
            "max_single_investment": single_limit,
            "profit_weight": profit_weight,
            "capital_efficiency_weight": efficiency_weight,
            "risk_weight": risk_weight,
            "confidence_weight": confidence_weight,
            "diversification_weight": diversification_weight,
        },
        "read_only": True,
        "execution_available": False,
    }
