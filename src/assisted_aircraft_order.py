"""Connect one explicitly approved aircraft checkout to the durable journal.

The caller must own the worker's Chrome and data locks. Readiness and receipt
readers are trusted in-process game adapters. This module is separate from the
read-only preview, the legacy buyer and the autonomous worker loop.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from contextlib import contextmanager
from uuid import uuid4

import paths
from aircraft_order_preview import AircraftPreviewRequest, _prepared_aircraft_order
from fleet_commitment_observations import read_pilot_pending
from investment_journal import InvestmentJournal, _intent_key, _validated_plan
from investment_policy import InvestmentPolicy
from investment_preflight import validate_aircraft_preflight


def aircraft_approval_key(plan: Mapping, *, profile_id: str, company_id: str,
                          delivery_hub_id: str, reserve: int) -> str:
    """Bind operator approval to the displayed choice, route and full exposure."""
    approved = [profile_id, company_id, delivery_hub_id, reserve, _validated_plan(plan)]
    return hashlib.sha256(json.dumps(approved, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class AssistedAircraftOrder:
    def __init__(self, journal: InvestmentJournal, policy: InvestmentPolicy, bot, *,
                 read_readiness, read_receipt):
        if journal.simulation:
            raise ValueError("A compra assistida exige o diário real do perfil.")
        self.journal = journal
        self.policy = policy
        self.bot = bot
        self.read_readiness = read_readiness
        self.read_receipt = read_receipt

    @contextmanager
    def _exclusive(self):
        self.journal.release_stale_executor()
        owner = uuid4().hex
        if not self.journal.acquire_executor(owner):
            yield None
            return
        try:
            self.journal.recover_submitted(owner_token=owner)
            yield owner
        finally:
            self.journal.release_executor(owner)

    def _company(self) -> str | None:
        if self.bot.stopping or paths.current().label != self.journal.profile_id:
            return None
        self.bot._require_observation_session()
        self.bot._verify_observation_company()
        return self.bot._observation_company_id

    def run(self, plan: Mapping, *, company_id: str, delivery_hub_id: str,
            approval_key: str, reserve: int) -> dict:
        policy = self.policy
        bot = self.bot
        if (not policy.enabled or not policy.valid or policy.mode != "approval"
                or policy.legacy_autobuy_aircraft or bot.dry_run or bot._observation_only or bot.stopping):
            return {"state": "BLOCKED", "reasons": ["modo_assistido_indisponivel"]}
        if not callable(self.read_readiness) or not callable(self.read_receipt):
            return {"state": "BLOCKED", "reasons": ["leitores_do_jogo_indisponiveis"]}

        profile_id = self.journal.profile_id
        if plan.get("profile_id", profile_id) != profile_id:
            return {"state": "BLOCKED", "reasons": ["perfil_divergente"]}
        exact = _validated_plan(plan)
        if (exact["kind"] != "aircraft" or "checkout_cost" not in exact
                or "configuration_yjf" not in exact):
            raise ValueError("A compra assistida exige cabine e custos discriminados.")
        if (not isinstance(company_id, str) or not company_id.isascii()
                or not company_id.isdecimal() or company_id.startswith("0") or len(company_id) > 14
                or type(reserve) is not int or reserve < 0
                or approval_key != aircraft_approval_key(
                    exact, profile_id=profile_id, company_id=company_id,
                    delivery_hub_id=delivery_hub_id, reserve=reserve)):
            return {"state": "BLOCKED", "reasons": ["aprovacao_exata_necessaria"]}
        request = AircraftPreviewRequest.from_payload({
            "model_id": exact["model_id"], "delivery_hub_id": delivery_hub_id,
            "engine_id": exact["engine_id"], "configuration_yjf": exact["configuration_yjf"],
            "expected_checkout_cost": exact["checkout_cost"],
        })
        amount = exact["estimated_cost"]
        if (amount > min(policy.max_single_investment, policy.max_cycle_spend, policy.max_daily_spend)
                or policy.max_acquisitions_per_day <= 0):
            return {"state": "BLOCKED", "reasons": ["limites_da_politica"]}

        with self._exclusive() as owner:
            if owner is None:
                return {"state": "BLOCKED", "reasons": ["executor_ocupado"]}
            key = _intent_key(profile_id, exact)
            existing = self.journal.get(key)
            if existing is not None:
                if any(existing.get(name) != value for name, value in exact.items()):
                    return {"state": "BLOCKED", "intent_key": key, "reasons": ["plano_da_intencao_divergente"]}
                if existing["state"] not in ("PROPOSED", "APPROVED", "PRECHECKED"):
                    return {"state": existing["state"], "intent_key": key, "reasons": ["intencao_existente"]}
            if any(row["intent_key"] != key for row in self.journal.unresolved()["intents"]):
                return {"state": "BLOCKED", "intent_key": key, "reasons": ["intencao_anterior_pendente"]}
            since = time.time() - 86400
            if (self.journal.budget_exposure_since(since, exclude_intent_key=key) + amount > policy.max_daily_spend
                    or self.journal.acquisition_count_since(
                        since, exclude_intent_key=key) >= policy.max_acquisitions_per_day):
                return {"state": "BLOCKED", "intent_key": key, "reasons": ["limites_de_24h"]}
            intent = {**exact, "intent_key": key, "profile_id": profile_id, "state": "PROPOSED"}
            try:
                reasons = self._prepare_and_submit(exact, existing or intent, request, company_id, reserve, owner)
            except Exception:
                if (self.journal.get(key) or {}).get("state") == "SUBMITTED":
                    return self._resolve(key, "SUBMITTED")
                reasons = ["checkout_indisponivel"]
            if reasons:
                state = (self.journal.get(key) or {}).get("state", "BLOCKED")
                return {"state": state, "intent_key": key, "reasons": reasons}
            return self._resolve(key, "SUBMITTED")

    def _prepare_and_submit(self, plan, intent, request, company_id, reserve, owner) -> list[str]:
        bot = self.bot
        key = intent["intent_key"]
        if self._company() != company_id:
            return ["companhia_divergente"]
        readiness = self.read_readiness(intent)
        if not isinstance(readiness, Mapping) or readiness.get("company_id") != company_id:
            return ["prontidao_da_companhia_indisponivel"]
        roster = read_pilot_pending(bot, baseline=True)
        if (roster is None or roster["company_id"] != company_id
                or roster["profile_id"] != self.journal.profile_id
                or sorted(row["id"] for row in roster["pending"]["rows"]) != readiness.get("pending_ids")):
            return ["frota_ou_compromissos_divergentes"]

        bot.close_popup(quiet=True)
        try:
            bot.open_popup("routes_main.php", "Routes", "nav_routes")
            bot.ajax("ac_orders.php?first=true", "routeAction")
            with _prepared_aircraft_order(
                bot, model_id=request.model_id, hub_id=request.delivery_hub_id, engine_id=request.engine_id,
                configuration_yjf=dict(zip("yjf", request.seats)),
                expected_checkout_cost=request.expected_checkout_cost,
            ) as (quote, submit):
                observation = {
                    **readiness, "source": "game_checkout_dom", "session_authenticated": True,
                    "model_id": quote["model_id"], "engine_selected_id": quote["engine_id"],
                    "hub_selection_id": quote["delivery_hub_id"], "hub_selection_confirmed": True,
                    "configuration_yjf": quote["configuration_yjf"], "price_includes_configuration": True,
                    "checkout_cost": quote["displayed_cost_usd"],
                }
                preflight = validate_aircraft_preflight({**intent, "state": "APPROVED"}, observation, reserve=reserve)
                if not preflight["ready"]:
                    return preflight["reasons"]
                if quote["order_control_available"] is not True or bot.read_money() != observation["cash"]:
                    return ["controle_de_envio_ou_saldo_divergente"]
                registered, _ = self.journal.register(plan)
                cycle_reason = self.journal.approve_in_cycle(key, owner, self.policy.max_cycle_spend)
                if cycle_reason:
                    return [cycle_reason]
                if registered["state"] != "PRECHECKED":
                    self.journal.transition(key, "APPROVED", "PRECHECKED")

                def claim():
                    if not validate_aircraft_preflight(
                        {**intent, "state": "APPROVED"}, observation, reserve=reserve,
                    )["ready"]:
                        return False
                    return self.journal.claim_submission(key, owner, baseline={
                        "company_id": company_id, "delivery_hub_id": request.delivery_hub_id,
                        "fleet_ids": roster["fleet_ids"], "observed_at": roster["observed_at"],
                        "cash": observation["cash"],
                    })

                return [] if submit(claim) else ["submissao_bloqueada"]
        finally:
            bot.close_popup(quiet=True)

    def _resolve(self, key: str, expected: str) -> dict:
        baseline = self.journal.submission_baseline(key)
        if baseline is not None:
            try:
                if self._company() == baseline["company_id"]:
                    evidence = self.read_receipt(self.journal.get(key), baseline)
                    if evidence and self._company() == baseline["company_id"] and self.journal.transition(
                        key, expected, "CONFIRMED", confirmation=evidence,
                    ):
                        return {"state": "CONFIRMED", "intent_key": key, "reasons": []}
            except Exception:
                # Browser failure, missing receipt and contradictory evidence
                # all leave the original single attempt reserved.
                pass
        if expected == "SUBMITTED":
            self.journal.transition(key, "SUBMITTED", "UNKNOWN")
        return {"state": "UNKNOWN", "intent_key": key, "reasons": ["pedido_ou_debito_sem_comprovacao"]}

    def reconcile(self, key: str) -> dict:
        """Read the recorded checkout after restart without sending another order."""
        with self._exclusive() as owner:
            if owner is None:
                return {"state": "BLOCKED", "reasons": ["executor_ocupado"]}
            intent = self.journal.get(key)
            if intent is None:
                raise KeyError("Intenção não encontrada no perfil.")
            if intent["state"] != "UNKNOWN":
                return {"state": intent["state"], "intent_key": key, "reasons": []}
            return self._resolve(key, "UNKNOWN")
