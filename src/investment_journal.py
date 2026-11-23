"""Durable intent ledger for the future acquisition coordinator.

No Selenium, game requests, or purchase methods are called here. The ledger
reserves a target before submission and preserves uncertain outcomes through
process restarts. A future executor must also reconcile the live game before
creating an intent or interpreting an independent confirmation as genuine.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

import paths


_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_CHOICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_PLAN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SNAPSHOT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_INTENT_KEY = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRANSITIONS = {
    "PROPOSED": {"APPROVED", "FAILED"},
    "APPROVED": {"PRECHECKED", "FAILED"},
    "PRECHECKED": {"SUBMITTED", "FAILED"},
    "SUBMITTED": {"UNKNOWN", "CONFIRMED"},
    "UNKNOWN": {"CONFIRMED"},
    "CONFIRMED": set(),
    "FAILED": set(),
}
_RESERVED_STATES = ("APPROVED", "PRECHECKED", "SUBMITTED", "UNKNOWN")


class IntentConflict(ValueError):
    """An existing purchase target cannot be re-reserved with a new plan."""


def _game_id(value: object) -> bool:
    return isinstance(value, str) and _GAME_ID.fullmatch(value) is not None


def _choice_id(value: object) -> bool:
    return (isinstance(value, str) and _CHOICE_ID.fullmatch(value) is not None
            and value.casefold() not in ("unknown", "default", "inferred", "null"))


def _validated_plan(plan: Mapping) -> dict:
    plan_id = plan.get("plan_id")
    snapshot_id = plan.get("snapshot_id")
    kind = plan.get("kind")
    hub_id = plan.get("hub_id")
    cost = plan.get("estimated_cost")
    if (not isinstance(plan_id, str) or _PLAN_ID.fullmatch(plan_id) is None
            or not isinstance(snapshot_id, str)
            or _SNAPSHOT_ID.fullmatch(snapshot_id) is None
            or kind not in ("aircraft", "hub") or not _game_id(hub_id)
            or type(cost) is not int or not 0 < cost <= 10**15):
        raise ValueError("Plano sem identidade, snapshot ou custo verificável.")

    target = {"kind": kind, "hub_id": hub_id}
    if kind == "aircraft":
        origin_id = plan.get("origin_id")
        destination_id = plan.get("destination_id")
        model_id = plan.get("model_id")
        engine_id = plan.get("engine_id")
        if (not _game_id(origin_id) or not _game_id(destination_id)
                or origin_id == destination_id or origin_id != hub_id
                or not _choice_id(model_id) or not _choice_id(engine_id)):
            raise ValueError("Modelo, motor, hub e rota da aeronave exigem IDs reais.")
        target.update(origin_id=origin_id, destination_id=destination_id,
                      model_id=model_id, engine_id=engine_id)

    return {**target, "plan_id": plan_id, "snapshot_id": snapshot_id,
            "estimated_cost": cost}


def _intent_key(profile_id: str, plan: Mapping) -> str:
    # One acquisition slot per hub/route. Choosing another engine or aircraft
    # for the same route must not create a second purchase intention.
    target = {name: plan.get(name) for name in
              ("kind", "hub_id", "origin_id", "destination_id")}
    target["profile_id"] = profile_id
    encoded = json.dumps(target, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class InvestmentJournal:
    """Single-target, one-shot state transitions isolated by active profile."""

    def __init__(self, path: Path | None = None, *, profile_id: str | None = None):
        self.profile_id = paths.current().label if profile_id is None else profile_id
        if not isinstance(self.profile_id, str) or _PLAN_ID.fullmatch(self.profile_id) is None:
            raise ValueError("Perfil inválido para diário de investimentos.")
        self.path = Path(path) if path is not None else paths.current().data / "investment_journal.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS intents (
                    profile_id TEXT NOT NULL,
                    intent_key TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    submit_attempts INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (profile_id, intent_key)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    intent_key TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    evidence_json TEXT,
                    FOREIGN KEY (profile_id, intent_key)
                      REFERENCES intents (profile_id, intent_key)
                );
            """)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        return closing(conn)

    @staticmethod
    def _unpack(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {"profile_id": row["profile_id"], "intent_key": row["intent_key"],
                "state": row["state"], "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "submit_attempts": row["submit_attempts"], **json.loads(row["plan_json"])}

    def register(self, plan: Mapping) -> tuple[dict, bool]:
        """Reserve one purchase target. Replays return its existing state.

        A changed plan or snapshot for the same target requires reconciliation
        rather than silently allocating another purchase intention.
        """
        if not isinstance(plan, Mapping):
            raise ValueError("Plano de investimento inválido.")
        valid = _validated_plan(plan)
        key = _intent_key(self.profile_id, valid)
        encoded = json.dumps(valid, sort_keys=True, separators=(",", ":"))
        stamp = time.time()
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT * FROM intents WHERE profile_id=? AND intent_key=?",
                (self.profile_id, key),
            ).fetchone()
            if previous is not None:
                if previous["plan_json"] != encoded:
                    raise IntentConflict("Compra já registrada para este hub/rota/modelo/motor.")
                return self._unpack(previous), False
            conn.execute(
                "INSERT INTO intents (profile_id, intent_key, plan_json, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.profile_id, key, encoded, "PROPOSED", stamp, stamp),
            )
            self._event(conn, key, None, "PROPOSED", stamp)
        return self.get(key), True

    def get(self, intent_key: str) -> dict | None:
        if not isinstance(intent_key, str) or _INTENT_KEY.fullmatch(intent_key) is None:
            return None
        with self._connect() as conn:
            return self._unpack(conn.execute(
                "SELECT * FROM intents WHERE profile_id=? AND intent_key=?",
                (self.profile_id, intent_key),
            ).fetchone())

    def _event(self, conn, key, previous, current, stamp, evidence=None):
        conn.execute(
            "INSERT INTO events (profile_id, intent_key, previous_state, new_state, observed_at, evidence_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.profile_id, key, previous, current, stamp,
             json.dumps(evidence, sort_keys=True) if evidence else None),
        )

    def transition(self, intent_key: str, expected: str, next_state: str,
                   *, confirmation: Mapping | None = None) -> bool:
        """Atomic compare-and-set. Only one worker can claim SUBMITTED.

        A false result means another worker/restart advanced the intent. That
        worker must never repeat a click based on the failed transition.
        """
        if (not isinstance(intent_key, str) or _INTENT_KEY.fullmatch(intent_key) is None
                or next_state not in _TRANSITIONS.get(expected, set())):
            raise ValueError("Transição inválida.")
        stamp = time.time()
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT state, plan_json FROM intents WHERE profile_id=? AND intent_key=?",
                (self.profile_id, intent_key),
            ).fetchone()
            if row is None:
                raise KeyError("Intenção não encontrada no perfil.")
            if row["state"] != expected:
                return False
            if next_state == "CONFIRMED" and not self._confirmed(
                    confirmation, json.loads(row["plan_json"])):
                raise ValueError("Confirmação independente e vinculada ao plano obrigatória.")
            conn.execute(
                "UPDATE intents SET state=?, updated_at=?, "
                "submit_attempts=submit_attempts + ? WHERE profile_id=? AND intent_key=?",
                (next_state, stamp, int(next_state == "SUBMITTED"),
                 self.profile_id, intent_key),
            )
            # Restrict persisted evidence to audited fields (no raw session data).
            public_evidence = ({name: confirmation[name] for name in (
                "source", "profile_id", "verified", "observed_at", "purchase_id",
                "hub_id", "model_id", "engine_id", "origin_id", "destination_id",
                "before_owned", "after_owned",
            ) if name in confirmation} if next_state == "CONFIRMED" else None)
            self._event(conn, intent_key, expected, next_state, stamp, public_evidence)
        return True

    def _confirmed(self, evidence: Mapping | None, plan: Mapping) -> bool:
        if (not isinstance(evidence, Mapping)
                or evidence.get("profile_id") != self.profile_id
                or evidence.get("verified") is not True
                or type(evidence.get("observed_at")) not in (int, float)
                or not math.isfinite(evidence["observed_at"])
                or not 0 <= time.time() - evidence["observed_at"] < 900
                or evidence.get("hub_id") != plan["hub_id"]):
            return False
        if plan["kind"] == "hub":
            return (evidence.get("source") == "game_owned_hubs"
                    and evidence.get("before_owned") is False
                    and evidence.get("after_owned") is True)
        return (evidence.get("source") == "game_order_list"
                and _game_id(evidence.get("purchase_id"))
                and all(evidence.get(name) == plan[name] for name in (
                    "model_id", "engine_id", "origin_id", "destination_id")))

    def recover_submitted(self) -> int:
        """On restart, quarantine any in-flight request without retrying it."""
        stamp = time.time()
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT intent_key FROM intents WHERE profile_id=? AND state='SUBMITTED'",
                (self.profile_id,),
            ).fetchall()
            for row in rows:
                key = row["intent_key"]
                conn.execute(
                    "UPDATE intents SET state='UNKNOWN', updated_at=? "
                    "WHERE profile_id=? AND intent_key=? AND state='SUBMITTED'",
                    (stamp, self.profile_id, key),
                )
                self._event(conn, key, "SUBMITTED", "UNKNOWN", stamp)
        return len(rows)

    def unresolved(self) -> dict:
        """Return conservative committed exposure, including uncertain orders."""
        placeholders = ",".join("?" for _ in _RESERVED_STATES)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM intents WHERE profile_id=? AND state IN ({placeholders}) "
                "ORDER BY created_at, intent_key",
                (self.profile_id, *_RESERVED_STATES),
            ).fetchall()
        intents = [self._unpack(row) for row in rows]
        return {"intents": intents,
                "estimated_exposure": sum(row["estimated_cost"] for row in intents),
                "count": len(intents), "profile_id": self.profile_id}

    def history(self, intent_key: str) -> list[dict]:
        if not isinstance(intent_key, str) or _INTENT_KEY.fullmatch(intent_key) is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT previous_state, new_state, observed_at, evidence_json FROM events "
                "WHERE profile_id=? AND intent_key=? ORDER BY event_id",
                (self.profile_id, intent_key),
            ).fetchall()
        return [{"previous_state": row["previous_state"], "new_state": row["new_state"],
                 "observed_at": row["observed_at"],
                 "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else None}
                for row in rows]
