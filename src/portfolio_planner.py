"""Read-only global comparison of researched aircraft opportunities.

Consumes the conservative output of ``rank_next_aircraft``. It never grants
purchase approval. Coverage of research and outstanding commitments require
independent verification before a comparison can be conclusive.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from expansion_economics import (
    _SOURCES as A3_PROVENANCE_SOURCES,
    _SUBJECTS as A3_PROVENANCE_SUBJECTS,
    rank_expansion_economics,
)
from opportunity_models import DEFAULT_MAX_AGE_SECONDS


DEFAULT_PROFIT_WEIGHT = 0.6
DEFAULT_EFFICIENCY_WEIGHT = 0.4
DEFAULT_RISK_WEIGHT = 0.0
DEFAULT_CONFIDENCE_WEIGHT = 0.0
DEFAULT_DIVERSIFICATION_WEIGHT = 0.0
_OPTIONAL_DIMENSIONS = ("risk", "confidence", "diversification")
_CONCLUSIVE_REJECTED_STATUSES = frozenset((
    "saldo_insuficiente", "sem_lucro", "rota_inviavel",
    "rota_ocupada", "rota_indisponivel",
))
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
    if "fleet_commitment_observations" in report:
        observations = report.get("fleet_commitment_observations")
        hangar = (observations.get("passenger_hangar") if isinstance(observations, Mapping)
                  and observations.get("status") in ("observed", "partial") else None)
        if (not isinstance(hangar, Mapping) or type(hangar.get("free")) is not int
                or hangar["free"] < 0):
            blockers.append("vagas_hangar_a_confirmar")
        elif hangar["free"] == 0:
            blockers.append("hangar_sem_vaga")

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
        if not isinstance(row, Mapping):
            excluded["cenario_nao_validado"] += 1
            blockers.append("cenarios_proprios_pendentes")
            continue
        if row.get("status") != "viavel" or row.get("pending") != []:
            excluded["cenario_nao_validado"] += 1
            if (row.get("pending") != []
                    or row.get("status") not in _CONCLUSIVE_REJECTED_STATUSES):
                blockers.append("cenarios_proprios_pendentes")
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
            blockers.append("cenarios_proprios_pendentes")
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
            blockers.append("pesquisas_conflitantes")
        elif identity in unique and unique[identity] != item:
            conflicting.add(identity)
            del unique[identity]
            excluded["pesquisas_conflitantes"] += 2
            blockers.append("pesquisas_conflitantes")
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


# A4 consumes completed A3 evaluations. The separate entry point leaves the
# legacy dashboard comparison, including its input and output contract, intact.
_A4_CONTROL_SOURCES = {
    "pending_orders_incremental": "investment_journal",
    "future_commitments_incremental": "investment_journal",
    "unrouted_aircraft_count": "game_fleet_scan",
    "operational_reserve": "investment_policy",
    "cycle_spent": "investment_journal",
    "cycle_limit": "investment_policy",
    "period_spent": "investment_journal",
    "period_limit": "investment_policy",
}


def _audited_value(
    proof: object, *, source: str, profile_id: str, snapshot_id: str,
    now: float, hub_id: str | None = None, economics_id: str | None = None,
) -> float | None:
    """Accept only a current, identity-bound numeric observation."""
    if not isinstance(proof, Mapping):
        return None
    stamp = _number(proof.get("observed_at"), positive=True)
    value = _number(proof.get("value"))
    if (proof.get("verified") is not True or proof.get("source") != source
            or proof.get("profile_id") != profile_id
            or proof.get("snapshot_id") != snapshot_id
            or stamp is None or value is None
            or not 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS):
        return None
    if hub_id is not None and proof.get("hub_id") != hub_id:
        return None
    if economics_id is not None and proof.get("economics_id") != economics_id:
        return None
    return value


def _audited_a3_cash(
    row: Mapping[str, Any], *, profile_id: str, snapshot_id: str, now: float,
) -> tuple[float, float, float] | None:
    """Reconcile the same A3 cash snapshot across competing alternatives."""
    provenance = row.get("provenance")
    identity = row.get("identity")
    if (not isinstance(provenance, Mapping)
            or set(provenance) != set(A3_PROVENANCE_SOURCES)
            or not isinstance(identity, Mapping)):
        return None
    # A3 has not exported a public provenance validator. Verify its v1 field,
    # source, subject, time and isolation contracts at this read-only boundary.
    for name, source in A3_PROVENANCE_SOURCES.items():
        proof = provenance.get(name)
        if not isinstance(proof, Mapping):
            return None
        stamp = _number(proof.get("observed_at"), positive=True)
        if (proof.get("verified") is not True or proof.get("source") != source
                or proof.get("profile_id") != profile_id
                or proof.get("snapshot_id") != snapshot_id
                or stamp is None or not 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS
                or any(proof.get(field) != identity.get(field)
                       for field in A3_PROVENANCE_SUBJECTS[name])):
            return None
    cash = provenance.get("cash")
    if not isinstance(cash, Mapping) or not isinstance(cash.get("value"), Mapping):
        return None
    if (cash.get("source") != "game_snapshot" or cash.get("verified") is not True
            or cash.get("profile_id") != profile_id
            or cash.get("snapshot_id") != snapshot_id):
        return None
    stamp = _number(cash.get("observed_at"), positive=True)
    values = cash["value"]
    amounts = tuple(_number(values.get(key)) for key in ("available", "committed", "reserve"))
    capital_costs = row.get("capital_costs")
    if not isinstance(capital_costs, Mapping):
        return None
    investment = _number(capital_costs.get("total_investment"), positive=True)
    after = _number(row.get("cash_after_purchase"))
    required = _number(row.get("cash_required_reserve"))
    oldest = _number(row.get("observed_at_oldest"), positive=True)
    oldest_proof = min(proof["observed_at"] for proof in provenance.values())
    if (stamp is None or not 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS
            or oldest is None or not 0 <= now - oldest <= DEFAULT_MAX_AGE_SECONDS
            or abs(oldest - oldest_proof) > 0.001
            or any(amount is None for amount in amounts)
            or investment is None or after is None or required is None):
        return None
    available, committed, reserve = amounts
    if (abs(after - (available - committed - investment)) > 0.011
            or abs(required - reserve) > 0.011):
        return None
    return available, committed, reserve


def _a4_risk_index(row: Mapping[str, Any], profit: float) -> float | None:
    """Downside protection from A3's explicit stress scenarios, not a game risk quote."""
    stress = row.get("sensitivity")
    if not isinstance(stress, Mapping):
        return None
    downside = []
    for name in ("fuel_price", "co2_price", "occupancy", "demand"):
        scenario = stress.get(name)
        if not isinstance(scenario, Mapping):
            return None
        value = scenario.get("daily_net_profit_estimate")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            value = float(value)
        except (OverflowError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        downside.append(value)
    return min(1.0, max(0.0, min(downside) / profit))


def compare_audited_portfolio(
    evaluations: Sequence[Mapping[str, Any]], *, profile_id: str, snapshot_id: str,
    controls: Mapping[str, Any] | None = None,
    hub_capacity: Mapping[str, Any] | None = None,
    diversification_evidence: Mapping[str, Any] | None = None,
    confidence_evidence: Mapping[str, Any] | None = None,
    fleet_coverage_verified: bool = False,
    research_coverage_verified: bool = False,
    commitments_verified: bool = False,
    max_single_investment: object = None,
    min_daily_profit: object = 0,
    max_payback_days: object = None,
    profit_weight: float = DEFAULT_PROFIT_WEIGHT,
    efficiency_weight: float = DEFAULT_EFFICIENCY_WEIGHT,
    return_weight: float = 0.0,
    risk_weight: float = DEFAULT_RISK_WEIGHT,
    confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
    diversification_weight: float = DEFAULT_DIVERSIFICATION_WEIGHT,
    policy_valid: bool = True,
    now: float | None = None,
) -> dict[str, Any]:
    """Rank audited A3 economics across hubs without authorizing purchases.

    ``controls`` contains independent verified, snapshot-bound envelopes for
    the names in ``_A4_CONTROL_SOURCES``. Pending orders and future commitments
    are *additional amounts not yet included* in A3 ``cash.committed``. They
    must be reconciled by the ledger before setting ``commitments_verified``.
    ``hub_capacity`` contains one ``game_hub_select`` envelope per hub with
    available hangar slots. Unknown controls or slots exclude a purchase.

    Risk, when weighted, uses the worst evidenced A3 stress scenario relative
    to the base profit. Optional confidence and diversification require their
    own normalized [0, 1] verified observations keyed by ``economics_id``.
    No unstated numerical proxy is constructed from hub size or model name.
    """
    now = time.time() if now is None else now
    blockers: list[str] = []
    excluded: Counter[str] = Counter()
    if _number(now, positive=True) is None or not profile_id or not snapshot_id:
        blockers.append("identidade_ou_relogio_invalido")
        now = 0
    if policy_valid is not True:
        blockers.append("politica_invalida")
    for verified, reason in (
        (fleet_coverage_verified, "cobertura_frota_a_confirmar"),
        (research_coverage_verified, "cobertura_pesquisa_a_confirmar"),
        (commitments_verified, "compromissos_a_conciliar"),
    ):
        if verified is not True:
            blockers.append(reason)

    weights = {
        "profit": _number(profit_weight),
        "capital_efficiency": _number(efficiency_weight),
        "return": _number(return_weight),
        "risk": _number(risk_weight),
        "confidence": _number(confidence_weight),
        "diversification": _number(diversification_weight),
    }
    total_weight = (math.fsum(weights.values())
                    if all(value is not None for value in weights.values()) else None)
    minimum_profit = _number(min_daily_profit)
    maximum_payback = (_number(max_payback_days, positive=True)
                       if max_payback_days is not None else None)
    single_limit = _number(max_single_investment, positive=True)
    if (total_weight is None or not math.isfinite(total_weight) or total_weight <= 0
            or minimum_profit is None or single_limit is None
            or (max_payback_days is not None and maximum_payback is None)):
        blockers.append("criterios_planejamento_invalidos")

    controls = controls if isinstance(controls, Mapping) else {}
    observed = {
        name: _audited_value(controls.get(name), source=source, profile_id=profile_id,
                             snapshot_id=snapshot_id, now=now)
        for name, source in _A4_CONTROL_SOURCES.items()
    }
    for name, value in observed.items():
        if value is None:
            blockers.append(f"evidencia_{name}_a_confirmar")
    for name in ("unrouted_aircraft_count",):
        if observed[name] is not None and not observed[name].is_integer():
            blockers.append(f"evidencia_{name}_invalida")
    if observed["unrouted_aircraft_count"] is not None and observed["unrouted_aircraft_count"] > 0:
        blockers.append("aeronaves_sem_rota_a_resolver")

    valid_evaluations = (isinstance(evaluations, Sequence)
                         and not isinstance(evaluations, (str, bytes)))
    if not valid_evaluations:
        blockers.append("formato_avaliacoes_a3_invalido")
    raw_rows = list(evaluations) if valid_evaluations else []
    # A3's ranking expects capital_costs to be a mapping. Reject malformed
    # payloads before handing them to that validator, including truthy scalars.
    safe_rows = [row for row in raw_rows if not isinstance(row, Mapping)
                 or isinstance(row.get("capital_costs"), Mapping)]
    excluded_a3 = len(raw_rows) - len(safe_rows)
    validated = rank_expansion_economics(safe_rows)
    excluded_a3 += validated["excluded_count"]
    if excluded_a3:
        blockers.append("avaliacoes_a3_invalidas_ou_conflitantes")
        excluded["avaliacao_a3_invalida_ou_conflitante"] += excluded_a3

    prepared = []
    cash_baselines = set()
    for row in validated["alternatives"]:
        if (type(row.get("schema_version")) is not int or row["schema_version"] != 1
                or row.get("profile_id") != profile_id
                or row.get("snapshot_id") != snapshot_id or row.get("excluded_costs") != []
                or not isinstance(row.get("plan_id"), str) or not row["plan_id"]
                or not isinstance(row.get("economics_id"), str) or not row["economics_id"]
                or row["identity"]["hub_id"] != row["identity"]["origin_id"]):
            excluded["identidade_snapshot_ou_custos_a_confirmar"] += 1
            blockers.append("avaliacoes_a3_incompativeis")
            continue
        cash = _audited_a3_cash(row, profile_id=profile_id, snapshot_id=snapshot_id, now=now)
        if cash is None:
            excluded["saldo_a3_sem_prova_atual"] += 1
            blockers.append("saldo_a3_a_confirmar")
            continue
        cash_baselines.add(cash)
        prepared.append(row)
    if len(cash_baselines) > 1:
        blockers.append("saldos_a3_contraditorios")
    baseline = next(iter(cash_baselines)) if len(cash_baselines) == 1 else None
    budget = None
    if baseline is not None and all(value is not None for value in observed.values()):
        available, committed, reserve = baseline
        remaining_cash = (available - committed - observed["pending_orders_incremental"]
                          - observed["future_commitments_incremental"]
                          - max(reserve, observed["operational_reserve"]))
        budget = max(0.0, min(remaining_cash,
                              observed["cycle_limit"] - observed["cycle_spent"],
                              observed["period_limit"] - observed["period_spent"]))
        if remaining_cash <= 0:
            blockers.append("saldo_apos_compromissos_insuficiente")
        if observed["cycle_spent"] >= observed["cycle_limit"]:
            blockers.append("limite_ciclo_esgotado")
        if observed["period_spent"] >= observed["period_limit"]:
            blockers.append("limite_periodo_esgotado")

    hub_capacity = hub_capacity if isinstance(hub_capacity, Mapping) else {}
    confidence_evidence = confidence_evidence if isinstance(confidence_evidence, Mapping) else {}
    diversification_evidence = (diversification_evidence
                                if isinstance(diversification_evidence, Mapping) else {})
    candidates = []
    for row in prepared:
        identity = row["identity"]
        hub_id = identity["hub_id"]
        economics_id = row["economics_id"]
        components = row["components"]
        investment = _number(row["capital_costs"]["total_investment"], positive=True)
        profit = _number(components["daily_net_profit_estimate"], positive=True)
        payback = _number(components["payback_days"], positive=True)
        roi = _number(components.get("roi_365d_percent"), positive=True)
        if any(value is None for value in (investment, profit, payback, roi)):
            excluded["economia_a3_invalida"] += 1
            blockers.append("economia_a3_a_confirmar")
            continue
        if abs(roi - profit * 36500 / investment) > 0.011:
            excluded["roi_a3_contraditorio"] += 1
            blockers.append("roi_a3_a_confirmar")
            continue
        if minimum_profit is None or profit < minimum_profit:
            excluded["lucro_abaixo_do_minimo"] += 1
            continue
        if maximum_payback is not None and payback > maximum_payback:
            excluded["retorno_acima_do_limite"] += 1
            continue
        if single_limit is None or investment > single_limit:
            excluded["limite_por_aquisicao"] += 1
            continue
        if budget is None or investment > budget:
            excluded["orcamento_global_insuficiente_ou_desconhecido"] += 1
            continue
        slots = _audited_value(hub_capacity.get(hub_id), source="game_hub_select",
                               profile_id=profile_id, snapshot_id=snapshot_id, now=now,
                               hub_id=hub_id)
        if slots is None or not slots.is_integer():
            blockers.append("vagas_hangar_a_confirmar")
            excluded["vagas_hangar_a_confirmar"] += 1
            continue
        if slots < 1:
            excluded["hangar_sem_vaga"] += 1
            continue

        indexes = {}
        if weights["risk"] is not None and weights["risk"] > 0:
            indexes["risk"] = _a4_risk_index(row, profit)
        for dimension, source, evidence in (
            ("confidence", "game_research", confidence_evidence),
            ("diversification", "game_fleet_scan", diversification_evidence),
        ):
            if weights[dimension] is not None and weights[dimension] > 0:
                value = _audited_value(evidence.get(economics_id), source=source,
                                       profile_id=profile_id, snapshot_id=snapshot_id,
                                       now=now, hub_id=hub_id, economics_id=economics_id)
                indexes[dimension] = value if value is not None and value <= 1 else None
        if any(index is None for index in indexes.values()):
            for name, index in indexes.items():
                if index is None:
                    blockers.append(f"evidencia_{name}_a_confirmar")
            excluded["evidencia_ranking_incompleta"] += 1
            continue
        candidates.append({
            "economics_id": economics_id,
            "plan_id": row["plan_id"],
            "profile_id": profile_id,
            "snapshot_id": snapshot_id,
            "identity": dict(identity),
            "configuration_yjf": dict(row["configuration_yjf"]),
            "hub_id": hub_id,
            "investment": investment,
            "profit_per_day": profit,
            "payback_days": payback,
            "roi_365d_percent": roi,
            "capital_efficiency_per_day": profit / investment,
            **{f"{key}_index": value for key, value in indexes.items()},
        })

    if candidates and "criterios_planejamento_invalidos" not in blockers:
        maxima = {
            "profit": max(item["profit_per_day"] for item in candidates),
            "capital_efficiency": max(item["capital_efficiency_per_day"] for item in candidates),
            "return": max(item["roi_365d_percent"] for item in candidates),
        }
        for item in candidates:
            indexes = {
                "profit": item["profit_per_day"] / maxima["profit"],
                "capital_efficiency": item["capital_efficiency_per_day"] / maxima["capital_efficiency"],
                "return": item["roi_365d_percent"] / maxima["return"],
                **{key: item[f"{key}_index"] for key in
                   ("risk", "confidence", "diversification") if f"{key}_index" in item},
            }
            components = {name: round(value * weights[name] / total_weight, 8)
                          for name, value in indexes.items() if weights[name] > 0}
            item["score_components"] = components
            item["score"] = round(math.fsum(components.values()), 8)
        candidates.sort(key=lambda item: (
            -item["score"], -item["profit_per_day"], item["payback_days"],
            item["investment"],
            tuple(item["identity"][key] for key in
                  ("hub_id", "origin_id", "destination_id", "model_id", "engine_id")),
            tuple(item["configuration_yjf"][key] for key in ("y", "j", "f")),
            item["economics_id"],
        ))
    else:
        candidates = []

    by_hub: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        by_hub.setdefault(item["hub_id"], []).append(item)
    best_by_hub = [
        {"hub_id": hub, "best": items[0], "alternatives": items}
        for hub, items in by_hub.items()
    ]
    runner = candidates[1] if len(candidates) > 1 else None
    explanation = None
    if candidates:
        winner = candidates[0]
        explanation = {
            "winner_economics_id": winner["economics_id"],
            "runner_up_economics_id": runner["economics_id"] if runner else None,
            "score_difference": round(winner["score"] - runner["score"], 8) if runner else None,
            "profit_difference_per_day": (round(winner["profit_per_day"] - runner["profit_per_day"], 2)
                                          if runner else None),
            "investment_difference": (round(winner["investment"] - runner["investment"], 2)
                                      if runner else None),
            "ordering": "weighted_normalized_profit_efficiency_return_and_evidenced_risk",
            "tie_break": "profit_desc_payback_asc_investment_asc_identity",
        }
    blockers = list(dict.fromkeys(blockers))
    return {
        "status": "inconclusivo" if blockers else "comparacao_concluida",
        "decision": "nao_comprar" if blockers or not candidates else "sugestao_para_analise",
        "blocking_reasons": blockers,
        "best": candidates[0] if candidates else None,
        "best_by_hub": best_by_hub,
        "alternatives": candidates,
        "evaluated_count": len(raw_rows),
        "eligible_count": len(candidates),
        "excluded": dict(sorted(excluded.items())),
        "budget_after_reservations_and_limits": budget,
        "criteria": {
            "max_single_investment": single_limit,
            "minimum_daily_profit": minimum_profit,
            "maximum_payback_days": maximum_payback,
            **{f"{name}_weight": value for name, value in weights.items()},
        },
        "why_best": explanation,
        "read_only": True,
        "execution_available": False,
    }
