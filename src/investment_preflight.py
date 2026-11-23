"""Read-only aircraft purchase preflight contract for future game checkout.

This module consumes separately collected, authenticated checkout observations.
It never opens the game, selects DOM controls or submits orders. Real purchase
execution remains disabled until the observations and controls are homologated.
"""
from __future__ import annotations

import math
import time
from collections.abc import Mapping


MAX_CHECKOUT_AGE_SECONDS = 120


def validate_aircraft_preflight(
    intent: Mapping,
    observation: Mapping | None,
    *,
    reserve: int = 0,
    now: float | None = None,
    simulation: bool = False,
) -> dict:
    """Reject missing, stale or changed checkout evidence before any order.

    The future checkout reader must independently attest these observations;
    an untrusted caller cannot turn this pure validation into purchase approval.
    """
    now = time.time() if now is None else now
    reasons: list[str] = []
    if not isinstance(intent, Mapping) or intent.get("kind") != "aircraft":
        return {"ready": False, "reasons": ["intencao_aeronave_invalida"],
                "read_only": True, "execution_available": False}
    if intent.get("state") != "APPROVED":
        reasons.append("intencao_sem_aprovacao")
    expected_source = "simulation_checkout" if simulation else "game_checkout_dom"
    verified = (isinstance(observation, Mapping)
                and (observation.get("simulated") is True if simulation
                     else observation.get("session_authenticated") is True))
    if (not isinstance(observation, Mapping)
            or observation.get("source") != expected_source
            or not verified):
        return {"ready": False, "reasons": reasons + ["checkout_nao_verificado"],
                "read_only": True, "execution_available": False}

    timestamp = observation.get("observed_at")
    if (type(now) not in (int, float) or not math.isfinite(now)
            or type(timestamp) not in (int, float) or not math.isfinite(timestamp)
            or not 0 <= now - timestamp <= MAX_CHECKOUT_AGE_SECONDS):
        reasons.append("checkout_desatualizado")

    for observed, planned, reason in (
        ("profile_id", "profile_id", "perfil_divergente"),
        ("snapshot_id", "snapshot_id", "snapshot_divergente"),
        ("hub_selection_id", "hub_id", "hub_de_entrega_divergente"),
        ("origin_id", "origin_id", "origem_divergente"),
        ("destination_id", "destination_id", "destino_divergente"),
        ("model_id", "model_id", "modelo_divergente"),
        ("engine_selected_id", "engine_id", "motor_divergente"),
    ):
        if not intent.get(planned) or observation.get(observed) != intent[planned]:
            reasons.append(reason)

    for check, reason in (
        ("hub_selection_confirmed", "hub_nao_confirmado"),
        ("model_available", "modelo_indisponivel"),
        ("engine_available", "motor_indisponivel"),
        ("route_available", "rota_indisponivel"),
        ("route_feasible", "rota_inviavel"),
        ("demand_verified", "demanda_nao_verificada"),
        ("capacity_available", "capacidade_indisponivel"),
        ("price_includes_engine", "preco_motor_nao_confirmado"),
    ):
        if observation.get(check) is not True:
            reasons.append(reason)

    expected_cost = intent.get("estimated_cost")
    checkout_cost = observation.get("checkout_cost")
    if (type(expected_cost) is not int or type(checkout_cost) is not int
            or expected_cost <= 0 or checkout_cost <= 0
            or expected_cost != checkout_cost):
        reasons.append("preco_divergente")

    cash = observation.get("cash")
    commitments = observation.get("pending_commitments")
    if (observation.get("commitments_verified") is not True
            or type(commitments) is not int or commitments < 0):
        reasons.append("compromissos_pendentes_nao_verificados")
    if (type(cash) is not int or cash < 0 or type(reserve) is not int
            or reserve < 0 or type(checkout_cost) is not int
            or checkout_cost <= 0 or type(commitments) is not int
            or commitments < 0 or cash - reserve - commitments < checkout_cost):
        reasons.append("caixa_insuficiente_ou_nao_verificado")

    return {"ready": not reasons, "reasons": reasons,
            "read_only": True, "execution_available": False}
