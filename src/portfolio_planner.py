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


def compare_portfolio(
    hub_report: Mapping[str, Any],
    *,
    research_coverage_verified: bool = False,
    commitments_verified: bool = False,
    committed_cash: object = None,
    max_single_investment: object = None,
    min_daily_profit: object = 0,
    max_payback_days: object = None,
    profit_weight: float = DEFAULT_PROFIT_WEIGHT,
    efficiency_weight: float = DEFAULT_EFFICIENCY_WEIGHT,
) -> dict:
    """Compare every eligible hub/route/model/engine, irrespective of hub.

    Unknown commitments cannot be silently treated as zero. A caller may
    display ranked alternatives with incomplete evidence, but the conclusion
    stays inconclusive and ``execution_available`` always remains false.
    """
    report = hub_report if isinstance(hub_report, Mapping) else {}
    candidates = report.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    blockers = []
    if report.get("partial_fleet") is not False:
        blockers.append("cobertura_frota_a_confirmar")
    if research_coverage_verified is not True:
        blockers.append("cobertura_pesquisa_a_confirmar")
    if commitments_verified is not True:
        blockers.append("pedidos_pendentes_a_conciliar")

    available_cash = _number(report.get("available_cash"))
    obligations = _number(committed_cash) if commitments_verified is True else None
    if available_cash is None:
        blockers.append("saldo_disponivel_a_confirmar")
    if commitments_verified is True and obligations is None:
        blockers.append("compromissos_invalidos")
    budget = (max(0.0, available_cash - obligations)
              if available_cash is not None and obligations is not None else None)

    single_limit = (_number(max_single_investment, positive=True)
                    if max_single_investment is not None else None)
    minimum_profit = _number(min_daily_profit)
    maximum_payback = (_number(max_payback_days, positive=True)
                       if max_payback_days is not None else None)
    weights = (_number(profit_weight), _number(efficiency_weight))
    if (minimum_profit is None
            or (max_single_investment is not None and single_limit is None)
            or (max_payback_days is not None and maximum_payback is None)
            or any(weight is None for weight in weights)
            or not math.isfinite(sum(weights)) or sum(weights) <= 0):
        blockers.append("criterios_planejamento_invalidos")

    excluded = Counter()
    unique = {}
    conflicting = set()
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

        identity = (hub_id, route_key, model.casefold(), engine_id)
        item = dict(row)
        item["investment"] = investment
        item["profit_per_day"] = profit
        item["payback_days"] = round(payback, 2)
        item["capital_efficiency_per_day"] = round(efficiency, 8)
        # Repeats do not increase a candidate's weight. Contradictory prices
        # or projections for one identity remove it pending fresh research.
        if identity in conflicting:
            excluded["pesquisas_conflitantes"] += 1
        elif identity in unique and (
            unique[identity]["investment"] != investment
            or unique[identity]["profit_per_day"] != profit
        ):
            conflicting.add(identity)
            del unique[identity]
            excluded["pesquisas_conflitantes"] += 2
        elif identity not in unique:
            unique[identity] = item

    alternatives = list(unique.values())
    if alternatives and "criterios_planejamento_invalidos" not in blockers:
        highest_profit = max(item["profit_per_day"] for item in alternatives)
        highest_efficiency = max(item["profit_per_day"] / item["investment"]
                                 for item in alternatives)
        total_weight = sum(weights)
        for item in alternatives:
            profit_index = item["profit_per_day"] / highest_profit
            efficiency_index = (item["profit_per_day"] / item["investment"]
                                / highest_efficiency)
            item["profit_index"] = round(profit_index, 6)
            item["efficiency_index"] = round(efficiency_index, 6)
            item["score"] = round((profit_index * weights[0] + efficiency_index * weights[1])
                                  / total_weight, 6)
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
        "budget_after_commitments": budget,
        "criteria": {
            "minimum_daily_profit": minimum_profit,
            "maximum_payback_days": maximum_payback,
            "max_single_investment": single_limit,
            "profit_weight": profit_weight,
            "capital_efficiency_weight": efficiency_weight,
        },
        "read_only": True,
        "execution_available": False,
    }
