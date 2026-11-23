"""Isolated acquisition simulator for proving the A5 execution protocol.

The simulator has no Selenium, HTTP, or game purchase dependencies. Its gateway
models a checkout and an independent order-list observation. Production order
submission stays unavailable until the authenticated game controls are proven.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from investment_journal import InvestmentJournal
from investment_policy import InvestmentPolicy
from investment_preflight import validate_aircraft_preflight


class SimulatedProcessCrash(RuntimeError):
    """A fake process died after its one-shot order claim."""


class SimulatedAircraftGateway:
    """A fake checkout and order reader that never contacts the game."""

    OUTCOMES = {"confirmed", "refused", "timeout", "timeout_rejected", "crash"}

    def __init__(self, checkout: Mapping, *, outcome: str = "confirmed",
                 purchase_id: str = "987654321", order_store: Path | None = None):
        if outcome not in self.OUTCOMES:
            raise ValueError("Resultado de simulação desconhecido.")
        self.checkout = dict(checkout)
        self.outcome = outcome
        self.purchase_id = purchase_id
        self.submit_calls = 0
        self._submitted: dict[str, dict] = {}
        self._rejected: dict[str, dict] = {}
        self.order_store = Path(order_store) if order_store is not None else None
        if self.order_store is not None:
            self.order_store.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.order_store) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS fake_orders (
                        profile_id TEXT NOT NULL,
                        intent_key TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        PRIMARY KEY (profile_id, intent_key)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS fake_rejections (
                        profile_id TEXT NOT NULL,
                        intent_key TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        PRIMARY KEY (profile_id, intent_key)
                    )
                """)

    def read_checkout(self) -> dict:
        return dict(self.checkout)

    def submit_order(self, intent: Mapping) -> None:
        key = intent["intent_key"]
        record = {name: intent[name] for name in (
            "profile_id", "intent_key", "hub_id", "origin_id", "destination_id",
            "model_id", "engine_id",
        )}
        record["purchase_id"] = self.purchase_id
        if key in self._submitted or key in self._rejected:
            raise AssertionError("A mesma intenção foi enviada duas vezes na simulação.")
        if self.order_store is not None:
            with sqlite3.connect(self.order_store) as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT 1 FROM fake_orders WHERE profile_id=? AND intent_key=? "
                    "UNION ALL SELECT 1 FROM fake_rejections WHERE profile_id=? AND intent_key=?",
                    (intent["profile_id"], key, intent["profile_id"], key),
                ).fetchone()
                if existing is not None:
                    raise AssertionError("A compra simulada já consta no livro de pedidos.")
                table = ("fake_rejections" if self.outcome in ("refused", "timeout_rejected")
                         else "fake_orders")
                try:
                    conn.execute(
                        f"INSERT INTO {table} (profile_id, intent_key, details_json) VALUES (?, ?, ?)",
                        (intent["profile_id"], key, json.dumps(record, sort_keys=True)),
                    )
                except sqlite3.IntegrityError as error:
                    raise AssertionError("A compra simulada já consta no livro de pedidos.") from error
        if self.outcome in ("refused", "timeout_rejected"):
            self._rejected[key] = record
        else:
            self._submitted[key] = record
        self.submit_calls += 1
        if self.outcome == "crash":
            raise SimulatedProcessCrash("Falha simulada depois do envio.")

    def read_order_result(self, intent: Mapping) -> dict | None:
        if self.outcome in ("timeout", "timeout_rejected", "crash"):
            return None
        order = self._submitted.get(intent["intent_key"])
        rejection = self._rejected.get(intent["intent_key"])
        if self.order_store is not None:
            with sqlite3.connect(self.order_store) as conn:
                row = conn.execute(
                    "SELECT details_json FROM fake_orders WHERE profile_id=? AND intent_key=?",
                    (intent["profile_id"], intent["intent_key"]),
                ).fetchone()
                rejected_row = conn.execute(
                    "SELECT details_json FROM fake_rejections WHERE profile_id=? AND intent_key=?",
                    (intent["profile_id"], intent["intent_key"]),
                ).fetchone()
            order = json.loads(row[0]) if row is not None else None
            rejection = json.loads(rejected_row[0]) if rejected_row is not None else None
        record = order or rejection
        if record is None:
            return None
        evidence = {
            "profile_id": record["profile_id"], "verified": True,
            "observed_at": time.time(), "hub_id": record["hub_id"],
            "origin_id": record["origin_id"], "destination_id": record["destination_id"],
            "model_id": record["model_id"], "engine_id": record["engine_id"],
        }
        if order is not None:
            return {**evidence, "source": "simulation_order_list",
                    "purchase_id": order["purchase_id"]}
        return {**evidence, "source": "simulation_order_rejection",
                "request_rejected": True, "orders_checked": True,
                "order_absent": True, "refusal_code": "SIMULATED_REFUSAL"}


class SimulatedInvestmentExecutor:
    """Exercise policy, profile exclusivity and reconciliation without spending."""

    def __init__(self, journal: InvestmentJournal, policy: InvestmentPolicy):
        if not journal.simulation:
            raise ValueError("O simulador exige um diário isolado de simulação.")
        self.journal = journal
        self.policy = policy

    def _policy_reasons(self, plan: Mapping, *, approved: bool) -> list[str]:
        reasons = []
        if not self.policy.valid or not self.policy.enabled:
            reasons.append("politica_desabilitada_ou_invalida")
        if self.policy.mode == "analyze":
            reasons.append("somente_analise")
        if self.policy.mode == "approval" and not approved:
            reasons.append("aprovacao_explicita_pendente")
        if self.policy.mode == "autonomous" and not self.policy.auto_buy_aircraft:
            reasons.append("compra_automatica_desabilitada")
        if self.policy.mode not in ("approval", "autonomous", "analyze"):
            reasons.append("modo_invalido")
        amount = plan.get("estimated_cost")
        if (type(amount) is not int or amount <= 0
                or self.policy.max_single_investment <= 0
                or amount > self.policy.max_single_investment):
            reasons.append("limite_por_compra")
        if self.policy.max_daily_spend <= 0:
            reasons.append("limite_de_24h_nao_configurado")
        return reasons

    def run(self, plan: Mapping, gateway: SimulatedAircraftGateway, *,
            approved: bool = False, reserve: int = 0) -> dict:
        """Run an approved fake purchase; never replay an already-submitted intent."""
        if not isinstance(plan, Mapping) or plan.get("kind") != "aircraft":
            raise ValueError("Simulador de compra exige uma proposta de aeronave.")
        if not isinstance(gateway, SimulatedAircraftGateway):
            raise TypeError("Somente o gateway de simulação é aceito.")
        reasons = self._policy_reasons(plan, approved=approved)
        if reasons:
            return {"state": "BLOCKED", "reasons": reasons, "simulated": True}

        owner = uuid4().hex
        if not self.journal.acquire_executor(owner):
            return {"state": "BLOCKED", "reasons": ["executor_ocupado"],
                    "simulated": True}
        crashed = False
        try:
            intent, _ = self.journal.register(plan)
            key = intent["intent_key"]
            if intent["state"] not in ("PROPOSED", "APPROVED", "PRECHECKED"):
                return {"state": intent["state"], "intent_key": key,
                        "reasons": ["intencao_ja_registrada"], "simulated": True}

            if any(row["state"] in ("UNKNOWN", "SUBMITTED")
                   for row in self.journal.unresolved()["intents"]):
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": ["compra_anterior_sem_conciliacao"], "simulated": True}
            occupied = self.journal.budget_exposure_since(time.time() - 86400,
                                                          exclude_intent_key=key)
            if occupied + intent["estimated_cost"] > self.policy.max_daily_spend:
                return {"state": "BLOCKED", "intent_key": key,
                        "reasons": ["limite_de_24h"], "simulated": True}

            if intent["state"] == "PROPOSED":
                self.journal.transition(key, "PROPOSED", "APPROVED")
            intent = self.journal.get(key)
            # Recheck a previously prechecked plan against a new checkout after
            # restart or retry. Its stored submission count is still zero.
            preflight_intent = {**intent, "state": "APPROVED"}
            preflight = validate_aircraft_preflight(preflight_intent, gateway.read_checkout(),
                                                   reserve=reserve, simulation=True)
            if not preflight["ready"]:
                return {"state": intent["state"], "intent_key": key,
                        "reasons": preflight["reasons"], "simulated": True}
            if intent["state"] == "APPROVED":
                self.journal.transition(key, "APPROVED", "PRECHECKED")
            if not self.journal.claim_submission(key, owner):
                return {"state": "PRECHECKED", "intent_key": key,
                        "reasons": ["submissao_bloqueada"], "simulated": True}

            try:
                gateway.submit_order(self.journal.get(key))
            except SimulatedProcessCrash:
                crashed = True
                return {"state": "SUBMITTED", "intent_key": key,
                        "reasons": ["queda_de_processo_simulada"],
                        "stopped_owner_token": owner, "simulated": True}
            except Exception:
                self.journal.transition(key, "SUBMITTED", "UNKNOWN")
                return {"state": "UNKNOWN", "intent_key": key,
                        "reasons": ["envio_sem_resultado_confiavel"], "simulated": True}
            return self._resolve(key, gateway, "SUBMITTED")
        finally:
            if not crashed:
                self.journal.release_executor(owner)

    def _resolve(self, key: str, gateway: SimulatedAircraftGateway,
                 current_state: str) -> dict:
        intent = self.journal.get(key)
        evidence = gateway.read_order_result(intent)
        if evidence is not None:
            desired = "FAILED" if evidence.get("source") == "simulation_order_rejection" else "CONFIRMED"
            try:
                if self.journal.transition(key, current_state, desired, confirmation=evidence):
                    return {"state": desired, "intent_key": key,
                            "reasons": [], "simulated": True}
            except ValueError:
                pass
        if current_state == "SUBMITTED":
            self.journal.transition(key, "SUBMITTED", "UNKNOWN")
        return {"state": "UNKNOWN", "intent_key": key,
                "reasons": ["resultado_sem_comprovacao"], "simulated": True}

    def reconcile(self, key: str, gateway: SimulatedAircraftGateway, *,
                  stopped_owner_token: str | None = None) -> dict:
        """Reconcile after restart from evidence, never submit a second order."""
        if not isinstance(gateway, SimulatedAircraftGateway):
            raise TypeError("Somente o gateway de simulação é aceito.")
        if stopped_owner_token is not None and not self.journal.release_executor(stopped_owner_token):
            return {"state": "BLOCKED", "reasons": ["executor_anterior_nao_identificado"],
                    "simulated": True}
        if self.journal.executor_busy():
            return {"state": "BLOCKED", "reasons": ["executor_ocupado"],
                    "simulated": True}
        self.journal.recover_submitted()
        owner = uuid4().hex
        if not self.journal.acquire_executor(owner):
            return {"state": "BLOCKED", "reasons": ["executor_ocupado"],
                    "simulated": True}
        try:
            intent = self.journal.get(key)
            if intent is None:
                raise KeyError("Intenção não encontrada no perfil.")
            if intent["state"] != "UNKNOWN":
                return {"state": intent["state"], "intent_key": key,
                        "reasons": [], "simulated": True}
            return self._resolve(key, gateway, "UNKNOWN")
        finally:
            self.journal.release_executor(owner)
