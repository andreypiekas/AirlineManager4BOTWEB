"""Purchase preflight needs independent, matching and recent checkout evidence."""
from __future__ import annotations

from copy import deepcopy

import pytest

from investment_journal import InvestmentJournal
from investment_preflight import validate_aircraft_preflight


NOW = 1_800_000_000


def approved_intent(tmp_path):
    ledger = InvestmentJournal(tmp_path / "intents.sqlite3", profile_id="principal")
    intent, _ = ledger.register({
        "kind": "aircraft", "plan_id": "a320-hub123", "snapshot_id": "sha256:" + "c" * 64,
        "hub_id": "123", "origin_id": "123", "destination_id": "456",
        "model_id": "A320", "engine_id": "motor-2", "estimated_cost": 10000,
    })
    assert ledger.transition(intent["intent_key"], "PROPOSED", "APPROVED")
    return ledger.get(intent["intent_key"])


def checkout(intent, **overrides):
    observation = {
        "source": "game_checkout_dom", "session_authenticated": True,
        "profile_id": intent["profile_id"], "observed_at": NOW,
        "snapshot_id": intent["snapshot_id"], "hub_selection_id": "800001",
        "delivery_hub_mapping": {
            "source": "game_owned_hub_crosswalk", "verified": True,
            "profile_id": intent["profile_id"], "snapshot_id": intent["snapshot_id"],
            "observed_at": NOW, "pairs": [
                {"airport_id": intent["hub_id"], "delivery_hub_id": "800001"},
                {"airport_id": "789", "delivery_hub_id": "800002"},
            ],
        },
        "origin_id": intent["origin_id"], "destination_id": intent["destination_id"],
        "model_id": intent["model_id"], "engine_selected_id": intent["engine_id"],
        "hub_selection_confirmed": True, "model_available": True,
        "engine_available": True, "route_available": True,
        "route_feasible": True, "demand_verified": True,
        "capacity_available": True, "price_includes_engine": True,
        "checkout_cost": intent["estimated_cost"], "cash": 25000,
        "commitments_verified": True, "pending_commitments": 2000,
    }
    observation.update(overrides)
    return observation


def test_complete_preflight_is_only_read_only_provisional_evidence(tmp_path):
    intent = approved_intent(tmp_path)
    original = deepcopy(intent)
    observation = checkout(intent)
    saved = deepcopy(observation)
    result = validate_aircraft_preflight(intent, observation, reserve=5000, now=NOW + 30)
    assert result == {"ready": True, "reasons": [], "read_only": True,
                      "execution_available": False}
    assert intent == original and observation == saved
    assert intent["state"] == "APPROVED"


@pytest.mark.parametrize(("changes", "reason"), [
    ({"source": "game_notification"}, "checkout_nao_verificado"),
    ({"session_authenticated": False}, "checkout_nao_verificado"),
    ({"observed_at": NOW - 121}, "checkout_desatualizado"),
    ({"observed_at": NOW + 10}, "checkout_desatualizado"),
    ({"profile_id": "outro"}, "perfil_divergente"),
    ({"snapshot_id": "sha256:" + "e" * 64}, "snapshot_divergente"),
    ({"hub_selection_id": "999"}, "hub_de_entrega_divergente"),
    ({"hub_selection_id": "123"}, "hub_de_entrega_divergente"),
    ({"delivery_hub_mapping": None}, "correspondencia_hub_entrega_nao_verificada"),
    ({"origin_id": "999"}, "origem_divergente"),
    ({"destination_id": "999"}, "destino_divergente"),
    ({"model_id": "B737"}, "modelo_divergente"),
    ({"engine_selected_id": "motor-3"}, "motor_divergente"),
    ({"hub_selection_confirmed": None}, "hub_nao_confirmado"),
    ({"engine_available": False}, "motor_indisponivel"),
    ({"model_available": None}, "modelo_indisponivel"),
    ({"route_available": False}, "rota_indisponivel"),
    ({"route_feasible": None}, "rota_inviavel"),
    ({"demand_verified": False}, "demanda_nao_verificada"),
    ({"capacity_available": False}, "capacidade_indisponivel"),
    ({"price_includes_engine": False}, "preco_motor_nao_confirmado"),
    ({"checkout_cost": 11000}, "preco_divergente"),
    ({"cash": 5000}, "caixa_insuficiente_ou_nao_verificado"),
    ({"cash": True}, "caixa_insuficiente_ou_nao_verificado"),
    ({"commitments_verified": False}, "compromissos_pendentes_nao_verificados"),
    ({"pending_commitments": None}, "compromissos_pendentes_nao_verificados"),
    ({"pending_commitments": 20000}, "caixa_insuficiente_ou_nao_verificado"),
])
def test_changed_unknown_or_stale_checkout_blocks_preflight(tmp_path, changes, reason):
    intent = approved_intent(tmp_path)
    result = validate_aircraft_preflight(intent, checkout(intent, **changes),
                                         reserve=5000, now=NOW)
    assert result["ready"] is False
    assert reason in result["reasons"]
    assert result["execution_available"] is False


def test_without_approved_intent_or_independent_checkout_preflight_fails(tmp_path):
    intent = approved_intent(tmp_path)
    intent["state"] = "PROPOSED"
    result = validate_aircraft_preflight(intent, checkout(intent), now=NOW)
    assert result["ready"] is False
    assert "intencao_sem_aprovacao" in result["reasons"]
    assert validate_aircraft_preflight(intent, None)["ready"] is False
    assert validate_aircraft_preflight({}, checkout(intent))["ready"] is False


@pytest.mark.parametrize(("changes", "reason"), [
    ({"source": "simulation_hub_crosswalk"}, "correspondencia_hub_entrega_nao_verificada"),
    ({"verified": False}, "correspondencia_hub_entrega_nao_verificada"),
    ({"profile_id": "outro"}, "correspondencia_hub_entrega_nao_verificada"),
    ({"snapshot_id": "outro"}, "correspondencia_hub_entrega_nao_verificada"),
    ({"observed_at": NOW - 121}, "correspondencia_hub_entrega_nao_verificada"),
    ({"observed_at": NOW + 1}, "correspondencia_hub_entrega_nao_verificada"),
    ({"pairs": [{"airport_id": "789", "delivery_hub_id": "800001"}]},
     "correspondencia_hub_entrega_nao_verificada"),
    ({"pairs": [{"airport_id": "123", "delivery_hub_id": "800001"},
                {"airport_id": "123", "delivery_hub_id": "800002"}]},
     "correspondencia_hub_entrega_ambigua"),
    ({"pairs": [{"airport_id": "123", "delivery_hub_id": "800001"},
                {"airport_id": "789", "delivery_hub_id": "800001"}]},
     "correspondencia_hub_entrega_ambigua"),
    ({"pairs": [{"airport_id": "123", "delivery_hub_id": True}]},
     "correspondencia_hub_entrega_nao_verificada"),
])
def test_crosswalk_must_be_unique_fresh_and_bound_to_intent(tmp_path, changes, reason):
    intent = approved_intent(tmp_path)
    observation = checkout(intent)
    observation["delivery_hub_mapping"].update(changes)
    result = validate_aircraft_preflight(intent, observation, now=NOW)
    assert not result["ready"]
    assert reason in result["reasons"]


def test_matching_selector_value_without_crosswalk_is_not_identity_proof(tmp_path):
    intent = approved_intent(tmp_path)
    observation = checkout(intent, hub_selection_id=intent["hub_id"])
    del observation["delivery_hub_mapping"]
    assert validate_aircraft_preflight(intent, observation, now=NOW)["reasons"] == [
        "correspondencia_hub_entrega_nao_verificada"
    ]
