"""Read-only aircraft purchase preflight contract for future game checkout.

This module consumes separately collected, authenticated checkout observations.
It never opens the game, selects DOM controls or submits orders. Real purchase
execution remains disabled until the observations and controls are homologated.
"""
from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping

from investment_journal import canonical_configuration_yjf


MAX_CHECKOUT_AGE_SECONDS = 120
_NATIVE_ID = re.compile(r"[1-9][0-9]{0,13}")


def _timestamp_number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        timestamp = float(value)
    except OverflowError:
        return None
    return timestamp if math.isfinite(timestamp) and timestamp >= 0 else None


def _fresh_timestamp(value: object, now: float) -> bool:
    current_timestamp = _timestamp_number(now)
    observed_timestamp = _timestamp_number(value)
    return (current_timestamp is not None and observed_timestamp is not None
            and 0 <= current_timestamp - observed_timestamp <= MAX_CHECKOUT_AGE_SECONDS)


def _delivery_hub_reasons(intent: Mapping, observation: Mapping, *,
                          now: float, simulation: bool) -> list[str]:
    """Resolve airport IDs to order-option IDs using independent explicit evidence.

    The native selectors use distinct identifier namespaces. Neither equal IDs
    nor matching labels or option positions establish the association. A future
    authenticated crosswalk collector must supply explicit pairs; its existence
    is not assumed by this read-only validator.
    """
    mapping = observation.get("delivery_hub_mapping")
    source = "simulation_hub_crosswalk" if simulation else "game_owned_hub_crosswalk"
    if (not isinstance(mapping, Mapping) or mapping.get("source") != source
            or mapping.get("verified") is not True
            or not intent.get("profile_id") or mapping.get("profile_id") != intent["profile_id"]
            or not intent.get("snapshot_id") or mapping.get("snapshot_id") != intent["snapshot_id"]
            or not _fresh_timestamp(mapping.get("observed_at"), now)):
        return ["correspondencia_hub_entrega_nao_verificada"]

    pairs = mapping.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        return ["correspondencia_hub_entrega_nao_verificada"]
    airport_to_delivery: dict[str, str] = {}
    delivery_ids: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, Mapping):
            return ["correspondencia_hub_entrega_nao_verificada"]
        airport = pair.get("airport_id")
        delivery = pair.get("delivery_hub_id")
        if (not isinstance(airport, str) or not _NATIVE_ID.fullmatch(airport)
                or not isinstance(delivery, str) or not _NATIVE_ID.fullmatch(delivery)):
            return ["correspondencia_hub_entrega_nao_verificada"]
        if airport in airport_to_delivery or delivery in delivery_ids:
            return ["correspondencia_hub_entrega_ambigua"]
        airport_to_delivery[airport] = delivery
        delivery_ids.add(delivery)

    planned_airport = intent.get("hub_id")
    if not isinstance(planned_airport, str) or planned_airport not in airport_to_delivery:
        return ["correspondencia_hub_entrega_nao_verificada"]
    if observation.get("hub_selection_id") != airport_to_delivery[planned_airport]:
        return ["hub_de_entrega_divergente"]
    return []


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

    if not _fresh_timestamp(observation.get("observed_at"), now):
        reasons.append("checkout_desatualizado")

    for observed, planned, reason in (
        ("profile_id", "profile_id", "perfil_divergente"),
        ("snapshot_id", "snapshot_id", "snapshot_divergente"),
        ("origin_id", "origin_id", "origem_divergente"),
        ("destination_id", "destination_id", "destino_divergente"),
        ("model_id", "model_id", "modelo_divergente"),
        ("engine_selected_id", "engine_id", "motor_divergente"),
    ):
        if not intent.get(planned) or observation.get(observed) != intent[planned]:
            reasons.append(reason)

    reasons.extend(_delivery_hub_reasons(intent, observation, now=now, simulation=simulation))

    # Old synthetic fixtures can still be replayed. Audited plans and any game
    # checkout need both the exact layout and the price for that configuration.
    if not simulation or "configuration_yjf" in intent or "capital_costs" in intent:
        planned_cabin = canonical_configuration_yjf(intent.get("configuration_yjf"))
        checkout_cabin = canonical_configuration_yjf(observation.get("configuration_yjf"))
        if planned_cabin is None:
            reasons.append("configuracao_planejada_nao_verificada")
        elif checkout_cabin is None:
            reasons.append("configuracao_checkout_nao_verificada")
        elif checkout_cabin != planned_cabin:
            reasons.append("configuracao_checkout_divergente")
        if observation.get("price_includes_configuration") is not True:
            reasons.append("preco_configuracao_nao_confirmado")

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
    # Existing journals store checkout and full exposure as the same amount.
    # Audited A3 plans reserve future route/hangar fees separately from checkout.
    expected_checkout = intent.get("checkout_cost", expected_cost)
    checkout_cost = observation.get("checkout_cost")
    if (type(expected_cost) is not int or type(expected_checkout) is not int
            or type(checkout_cost) is not int or expected_cost <= 0
            or expected_checkout <= 0 or checkout_cost <= 0
            or expected_checkout > expected_cost or expected_checkout != checkout_cost):
        reasons.append("preco_divergente")

    cash = observation.get("cash")
    commitments = observation.get("pending_commitments")
    if (observation.get("commitments_verified") is not True
            or type(commitments) is not int or commitments < 0):
        reasons.append("compromissos_pendentes_nao_verificados")
    if (type(cash) is not int or cash < 0 or type(reserve) is not int
            or reserve < 0 or type(checkout_cost) is not int
            or checkout_cost <= 0 or type(expected_cost) is not int
            or expected_cost <= 0 or type(commitments) is not int
            or commitments < 0 or cash - reserve - commitments < expected_cost):
        reasons.append("caixa_insuficiente_ou_nao_verificado")

    return {"ready": not reasons, "reasons": reasons,
            "read_only": True, "execution_available": False}
