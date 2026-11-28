"""Read-only handoff from audited A3/A4 rankings to an A5 aircraft intent.

An eligible portfolio suggestion is still subject to approval, a fresh checkout
and exclusive, one-shot execution. This adapter never registers or buys anything.
"""
from __future__ import annotations

import math
import time
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from investment_journal import _validated_plan, canonical_configuration_yjf
from portfolio_planner import _audited_a3_cash


_COST_COMPONENTS = ("aircraft_cost", "engine_delta_cost", "hub_cost",
                    "route_fee", "hangar_cost", "other_fees")
_IDENTITY = ("hub_id", "origin_id", "destination_id", "model_id", "engine_id")


def _whole_game_money(value: object) -> int:
    """Never round fractional A3/A4 game-money amounts into an order."""
    if type(value) not in (int, float, Decimal):
        raise ValueError("Custo de investimento sem unidade inteira confirmada.")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Valor monetario invalido.") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("Custos fracionarios requerem validacao de unidade monetaria.")
    return int(amount)


def build_aircraft_intent_plan(
    portfolio: Mapping, evaluation: Mapping, *, now: float | None = None,
) -> dict:
    """Create a durable-plan payload for the portfolio winner, without approval.

    Requires the exact A3 economics record used for the global A4 winner. The
    journal reserves total capex. Checkout must quote the exact cabin and engine.
    ``hub_id`` remains the research airport ID. A5 must independently resolve
    the native delivery option at checkout.
    """
    if (not isinstance(portfolio, Mapping) or not isinstance(evaluation, Mapping)
            or portfolio.get("status") != "comparacao_concluida"
            or portfolio.get("decision") != "sugestao_para_analise"
            or portfolio.get("blocking_reasons") != []
            or portfolio.get("read_only") is not True
            or portfolio.get("execution_available") is not False
            or evaluation.get("status") != "evaluated"
            or evaluation.get("schema_version") != 1
            or evaluation.get("excluded_costs") != []
            or evaluation.get("evidence_confidence") != "provenance_complete"):
        raise ValueError("Comparacao global ou economia auditada inconclusiva.")

    winner = portfolio.get("best")
    identity = evaluation.get("identity")
    if not isinstance(winner, Mapping) or not isinstance(identity, Mapping):
        raise ValueError("Identidade da oportunidade ausente.")
    if identity.get("stopover_id") is not None:
        raise ValueError("Execucao de itinerario com escala ainda nao homologada.")
    configuration = canonical_configuration_yjf(evaluation.get("configuration_yjf"))
    if (configuration is None
            or canonical_configuration_yjf(winner.get("configuration_yjf")) != configuration):
        raise ValueError("Configuração Y/J/F ausente, inválida ou divergente da avaliação A3.")
    if (any(winner.get(field) != evaluation.get(field) for field in
            ("plan_id", "profile_id", "snapshot_id", "economics_id"))
            or winner.get("identity") != identity
            or any(not isinstance(identity.get(field), str) for field in _IDENTITY)):
        raise ValueError("Oportunidade difere da avaliacao A3 selecionada.")

    amounts = evaluation.get("capital_costs")
    if not isinstance(amounts, Mapping):
        raise ValueError("Custos discriminados ausentes.")

    observed_at = time.time() if now is None else now
    if (type(observed_at) not in (int, float)
            or not math.isfinite(observed_at)
            or _audited_a3_cash(evaluation, profile_id=winner["profile_id"],
                                snapshot_id=winner["snapshot_id"], now=observed_at) is None):
        raise ValueError("Saldo ou procedencia A3 vencidos ou contraditorios.")

    capital_costs = {field: _whole_game_money(amounts.get(field))
                     for field in (*_COST_COMPONENTS, "total_investment")}
    investment = capital_costs["total_investment"]
    if _whole_game_money(winner.get("investment")) != investment:
        raise ValueError("Investimento A4 diverge dos componentes A3.")

    plan = {
        "kind": "aircraft", "plan_id": winner["plan_id"],
        "profile_id": winner["profile_id"], "snapshot_id": winner["snapshot_id"],
        **{field: identity[field] for field in _IDENTITY},
        "configuration_yjf": configuration,
        "estimated_cost": investment,
        "checkout_cost": capital_costs["aircraft_cost"] + capital_costs["engine_delta_cost"],
        "capital_costs": capital_costs,
    }
    _validated_plan(plan)
    return plan
