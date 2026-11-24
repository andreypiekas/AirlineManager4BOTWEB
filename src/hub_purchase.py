"""Simulated two-stage hub acquisition with durable, profile-isolated intents.

Hub ownership is reconciled through an independent fake registry before an
aircraft plan can be considered for that hub. No game or network operations
exist in this module.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from investment_executor import (
    SimulatedAircraftGateway,
    SimulatedInvestmentExecutor,
    SimulatedProcessCrash,
)
from investment_journal import InvestmentJournal
from investment_policy import InvestmentPolicy


MAX_AGE_SECONDS = 900


def _fresh(stamp: object, now: float) -> bool:
    return type(stamp) in (int, float) and 0 <= now - stamp <= MAX_AGE_SECONDS


def validate_hub_preflight(plan: Mapping, checkout: Mapping, *, reserve: int = 0,
                           now: float | None = None) -> dict:
    """Require exact, current hub, price, balance and points at fake checkout."""
    now = time.time() if now is None else now
    reasons = []
    if (checkout.get("source") != "simulation_hub_checkout"
            or checkout.get("verified") is not True
            or not _fresh(checkout.get("observed_at"), now)):
        reasons.append("checkout_sem_evidencia_atual")
    if (plan.get("kind") != "hub" or checkout.get("profile_id") != plan.get("profile_id")
            or checkout.get("snapshot_id") != plan.get("snapshot_id")
            or checkout.get("selected_hub_id") != plan.get("hub_id")):
        reasons.append("identidade_hub_ou_snapshot_divergente")
    if checkout.get("before_owned") is not False or checkout.get("can_purchase") is not True:
        reasons.append("hub_ja_adquirido_ou_indisponivel")
    price = checkout.get("final_price")
    if (type(price) is not int or price <= 0 or price != plan.get("estimated_cost")):
        reasons.append("preco_divergente")
    cash = checkout.get("available_cash")
    if (type(reserve) is not int or reserve < 0 or type(cash) is not int
            or cash < 0 or type(price) is not int or cash < price + reserve):
        reasons.append("caixa_ou_reserva_insuficiente")
    points = checkout.get("available_points")
    required = checkout.get("required_points")
    if (type(points) is not int or type(required) is not int or points < 0
            or required < 0 or points < required):
        reasons.append("pontos_insuficientes_ou_incertos")
    return {"ready": not reasons, "reasons": reasons, "simulated": True}


class SimulatedHubGateway:
    """Fake checkout and durable ownership reader, with delayed observations."""

    OUTCOMES = {"confirmed", "timeout", "refused", "crash"}

    def __init__(self, checkout: Mapping, *, outcome: str = "confirmed",
                 ownership_store: Path):
        if outcome not in self.OUTCOMES:
            raise ValueError("Resultado simulado de hub desconhecido.")
        self.checkout = dict(checkout)
        self.outcome = outcome
        self.submit_calls = 0
        self.ownership_store = Path(ownership_store)
        self.ownership_store.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.ownership_store) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS hub_outcomes (
                profile_id TEXT NOT NULL, intent_key TEXT NOT NULL,
                hub_id TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY (profile_id, intent_key))""")

    def read_checkout(self) -> dict:
        checkout = dict(self.checkout)
        profile_id = checkout.get("profile_id")
        hub_id = checkout.get("selected_hub_id")
        if isinstance(profile_id, str) and profile_id and isinstance(hub_id, str) and hub_id:
            with sqlite3.connect(self.ownership_store) as db:
                owned = db.execute(
                    "SELECT 1 FROM hub_outcomes "
                    "WHERE profile_id=? AND hub_id=? AND status='owned' LIMIT 1",
                    (profile_id, hub_id),
                ).fetchone()
            if owned is not None:
                checkout["before_owned"] = True
                checkout["can_purchase"] = False
        return checkout

    def submit_order(self, intent: Mapping) -> None:
        if intent.get("profile_id") != self.checkout.get("profile_id"):
            raise ValueError("Pedido de outro perfil.")
        if intent.get("hub_id") != self.checkout.get("selected_hub_id"):
            raise ValueError("Pedido para hub diferente do checkout.")
        status = "refused" if self.outcome == "refused" else "owned"
        with sqlite3.connect(self.ownership_store) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT 1 FROM hub_outcomes "
                    "WHERE profile_id=? AND hub_id=? AND status='owned' LIMIT 1",
                    (intent["profile_id"], intent["hub_id"]),
                ).fetchone()
                if existing is not None:
                    raise AssertionError("Tentativa de recompra do mesmo hub.")
                db.execute(
                    "INSERT INTO hub_outcomes (profile_id, intent_key, hub_id, status) "
                    "VALUES (?, ?, ?, ?)",
                    (intent["profile_id"], intent["intent_key"], intent["hub_id"], status),
                )
            except sqlite3.IntegrityError as exc:
                raise AssertionError(
                    "Tentativa de recompra do mesmo hub ou repetição da intenção."
                ) from exc
        self.submit_calls += 1
        if self.outcome == "crash":
            raise SimulatedProcessCrash("Queda simulada após envio do hub.")

    def read_order_result(self, intent: Mapping) -> dict | None:
        if self.outcome in ("timeout", "crash"):
            return None
        with sqlite3.connect(self.ownership_store) as db:
            row = db.execute(
                "SELECT hub_id, status FROM hub_outcomes WHERE profile_id=? AND intent_key=?",
                (intent["profile_id"], intent["intent_key"]),
            ).fetchone()
        if row is None or row[0] != intent["hub_id"]:
            return None
        evidence = {"profile_id": intent["profile_id"], "hub_id": row[0],
                    "observed_at": time.time(), "verified": True}
        if row[1] == "owned":
            return {**evidence, "source": "simulation_owned_hubs",
                    "before_owned": False, "after_owned": True}
        return {**evidence, "source": "simulation_order_rejection",
                "request_rejected": True, "orders_checked": True,
                "order_absent": True, "refusal_code": "SIMULATED_HUB_REJECTION"}


class SimulatedHubExecutor:
    """One-shot hub purchase simulator backed by InvestmentJournal."""

    def __init__(self, journal: InvestmentJournal, policy: InvestmentPolicy):
        if not journal.simulation:
            raise ValueError("Compra simulada exige diário de simulação.")
        self.journal = journal
        self.policy = policy

    def _policy_reasons(self, plan: Mapping, approved: bool) -> list[str]:
        reasons = []
        if not self.policy.enabled or not self.policy.valid or self.policy.mode == "analyze":
            reasons.append("politica_nao_autorizada")
        if self.policy.mode == "approval" and not approved:
            reasons.append("aprovacao_pendente")
        if self.policy.mode == "autonomous" and not self.policy.auto_buy_hub:
            reasons.append("compra_de_hub_desabilitada")
        if (type(plan.get("estimated_cost")) is not int
                or self.policy.max_single_investment <= 0
                or plan["estimated_cost"] > self.policy.max_single_investment):
            reasons.append("limite_por_compra")
        if self.policy.max_daily_spend <= 0 or self.policy.max_acquisitions_per_day <= 0:
            reasons.append("limites_diarios_ausentes")
        return reasons

    def run(self, plan: Mapping, gateway: SimulatedHubGateway, *,
            approved: bool = False, reserve: int = 0) -> dict:
        if not isinstance(plan, Mapping) or plan.get("kind") != "hub":
            raise ValueError("Plano de hub inválido.")
        if not isinstance(gateway, SimulatedHubGateway):
            raise TypeError("Exige gateway de hub simulado.")
        reasons = self._policy_reasons(plan, approved)
        if reasons:
            return {"state": "BLOCKED", "reasons": reasons, "simulated": True}
        self.journal.release_stale_executor()
        owner = uuid4().hex
        if not self.journal.acquire_executor(owner):
            return {"state": "BLOCKED", "reasons": ["executor_ocupado"], "simulated": True}
        crashed = False
        try:
            intent, _ = self.journal.register(plan)
            key = intent["intent_key"]
            if intent["state"] not in ("PROPOSED", "APPROVED", "PRECHECKED"):
                return {"state": intent["state"], "intent_key": key,
                        "reasons": ["intencao_existente"], "simulated": True}
            if any(item["state"] in ("SUBMITTED", "UNKNOWN")
                   for item in self.journal.unresolved()["intents"]):
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": ["intencao_pendente"], "simulated": True}
            if (self.journal.budget_exposure_since(time.time() - 86400,
                                                   exclude_intent_key=key)
                    + intent["estimated_cost"] > self.policy.max_daily_spend):
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": ["limite_de_24h"], "simulated": True}
            if (self.journal.acquisition_count_since(time.time() - 86400,
                                                     exclude_intent_key=key)
                    >= self.policy.max_acquisitions_per_day):
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": ["limite_de_aquisicoes"], "simulated": True}
            cycle_reason = self.journal.approve_in_cycle(key, owner, self.policy.max_cycle_spend)
            if cycle_reason:
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": [cycle_reason], "simulated": True}
            preflight = validate_hub_preflight(intent, gateway.read_checkout(),
                                               reserve=reserve)
            if not preflight["ready"]:
                return {"state": self.journal.get(key)["state"], "intent_key": key,
                        "reasons": preflight["reasons"], "simulated": True}
            if self.journal.get(key)["state"] == "APPROVED":
                self.journal.transition(key, "APPROVED", "PRECHECKED")
            if not self.journal.claim_submission(key, owner):
                return {"state": self.journal.get(key)["state"], "intent_key": key,
                        "reasons": ["submissao_bloqueada"], "simulated": True}
            try:
                gateway.submit_order(self.journal.get(key))
            except SimulatedProcessCrash:
                crashed = True
                return {"state": "SUBMITTED", "intent_key": key,
                        "stopped_owner_token": owner,
                        "reasons": ["queda_simulada"], "simulated": True}
            except Exception:
                self.journal.transition(key, "SUBMITTED", "UNKNOWN")
                return {"state": "UNKNOWN", "intent_key": key,
                        "reasons": ["envio_inconclusivo"], "simulated": True}
            return self._resolve(key, gateway, "SUBMITTED")
        finally:
            if not crashed:
                self.journal.release_executor(owner)

    def _resolve(self, key: str, gateway: SimulatedHubGateway, expected: str) -> dict:
        intent = self.journal.get(key)
        evidence = gateway.read_order_result(intent)
        if evidence is not None:
            outcome = ("FAILED" if evidence["source"] == "simulation_order_rejection"
                       else "CONFIRMED")
            try:
                if self.journal.transition(key, expected, outcome, confirmation=evidence):
                    return {"state": outcome, "intent_key": key, "reasons": [],
                            "simulated": True}
            except ValueError:
                pass
        if expected == "SUBMITTED":
            self.journal.transition(key, "SUBMITTED", "UNKNOWN")
        return {"state": self.journal.get(key)["state"], "intent_key": key,
                "reasons": ["posse_ainda_nao_confirmada"], "simulated": True}

    def reconcile(self, key: str, gateway: SimulatedHubGateway, *,
                  stopped_owner_token: str | None = None) -> dict:
        if not isinstance(gateway, SimulatedHubGateway):
            raise TypeError("Exige gateway de hub simulado.")
        if self.journal.get(key) is None:
            raise KeyError("Intenção não encontrada.")
        if stopped_owner_token is not None:
            if not self.journal.release_executor(stopped_owner_token):
                return {"state": "BLOCKED", "reasons": ["executor_anterior_incerto"],
                        "simulated": True}
        else:
            self.journal.release_stale_executor()
        owner = uuid4().hex
        if not self.journal.acquire_executor(owner):
            return {"state": "BLOCKED", "reasons": ["executor_ocupado"], "simulated": True}
        try:
            self.journal.recover_submitted(owner_token=owner)
            state = self.journal.get(key)["state"]
            if state != "UNKNOWN":
                return {"state": state, "intent_key": key, "reasons": [],
                        "simulated": True}
            return self._resolve(key, gateway, "UNKNOWN")
        finally:
            self.journal.release_executor(owner)


def validate_aircraft_after_hub(hub_intent: Mapping, aircraft_plan: Mapping,
                                ownership: Mapping, *, now: float | None = None) -> dict:
    """Check independent, newer proof of ownership before phase-two planning."""
    now = time.time() if now is None else now
    reasons = []
    if (hub_intent.get("kind") != "hub" or hub_intent.get("state") != "CONFIRMED"
            or hub_intent.get("profile_id") != aircraft_plan.get("profile_id")
            or hub_intent.get("hub_id") != aircraft_plan.get("hub_id")
            or aircraft_plan.get("kind") != "aircraft"
            or aircraft_plan.get("origin_id") != hub_intent.get("hub_id")
            or hub_intent.get("snapshot_id") == aircraft_plan.get("snapshot_id")):
        reasons.append("plano_de_aeronave_precisa_reavaliacao_apos_hub")
    if (ownership.get("source") != "simulation_owned_hubs"
            or ownership.get("verified") is not True
            or ownership.get("profile_id") != aircraft_plan.get("profile_id")
            or ownership.get("snapshot_id") != aircraft_plan.get("snapshot_id")
            or ownership.get("hub_id") != hub_intent.get("hub_id")
            or ownership.get("after_owned") is not True
            or ownership.get("coverage_complete") is not True
            or not _fresh(ownership.get("observed_at"), now)
            or type(hub_intent.get("updated_at")) not in (int, float)
            or ownership.get("observed_at", 0) < hub_intent.get("updated_at", now)):
        reasons.append("posse_atualizada_ainda_nao_comprovada")
    return {"ready": not reasons, "reasons": reasons, "simulated": True}


class SimulatedExpansionCoordinator:
    """Keep the two purchases in one profile journal across process restarts.

    Phase two must be called with a *new* observed snapshot after the first
    purchase is confirmed. Its aircraft checkout is independently revalidated
    by the existing simulator immediately before submission.
    """

    def __init__(self, journal: InvestmentJournal, policy: InvestmentPolicy):
        self.journal = journal
        self.hubs = SimulatedHubExecutor(journal, policy)
        self.aircraft = SimulatedInvestmentExecutor(journal, policy)

    def acquire_hub(self, plan: Mapping, gateway: SimulatedHubGateway, *,
                    approved: bool = False, reserve: int = 0) -> dict:
        return {**self.hubs.run(plan, gateway, approved=approved, reserve=reserve),
                "stage": "hub"}

    def acquire_aircraft(self, hub_intent_key: str, plan: Mapping,
                         ownership: Mapping, gateway: SimulatedAircraftGateway, *,
                         approved: bool = False, reserve: int = 0) -> dict:
        """Advance only after independently verified ownership and new research."""
        hub_intent = self.journal.get(hub_intent_key)
        if hub_intent is None or hub_intent.get("kind") != "hub":
            return {"state": "BLOCKED", "stage": "aircraft", "simulated": True,
                    "reasons": ["hub_sem_intencao_confirmada"]}
        if not isinstance(plan, Mapping) or not isinstance(ownership, Mapping):
            return {"state": "BLOCKED", "stage": "aircraft", "simulated": True,
                    "reasons": ["plano_ou_posse_invalidos"]}
        gate = validate_aircraft_after_hub(hub_intent, plan, ownership)
        if not gate["ready"]:
            return {"state": "BLOCKED", "stage": "aircraft", "simulated": True,
                    "reasons": gate["reasons"]}
        result = self.aircraft.run(plan, gateway, approved=approved, reserve=reserve)
        return {**result, "stage": "aircraft", "hub_intent_key": hub_intent_key}
