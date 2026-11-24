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
import os
import re
import sqlite3
import socket
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
    "PRECHECKED": {"FAILED"},
    "SUBMITTED": {"UNKNOWN", "CONFIRMED", "FAILED"},
    "UNKNOWN": {"CONFIRMED", "FAILED"},
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


def _process_is_running(pid: object) -> bool:
    """Return True unless the local OS proves that a process has exited."""
    if type(pid) is not int or pid <= 0:
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


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

    if "capital_costs" in plan or "checkout_cost" in plan:
        components = plan.get("capital_costs")
        fields = ("aircraft_cost", "engine_delta_cost", "hub_cost", "route_fee",
                  "hangar_cost", "other_fees")
        if kind != "aircraft" or not isinstance(components, Mapping):
            raise ValueError("Custos discriminados exigem proposta de aeronave.")
        if (any(type(components.get(field)) is not int or components[field] < 0
                for field in fields)
                or type(components.get("total_investment")) is not int):
            raise ValueError("Componentes do investimento exigem valores inteiros verificados.")
        checkout_cost = plan.get("checkout_cost")
        if (components["aircraft_cost"] <= 0 or components["hub_cost"] != 0
                or components["total_investment"] != cost
                or sum(components[field] for field in fields) != cost
                or type(checkout_cost) is not int
                or checkout_cost != components["aircraft_cost"] + components["engine_delta_cost"]):
            raise ValueError("Preco de checkout e investimento total contraditorios.")
        target.update(checkout_cost=checkout_cost,
                      capital_costs={field: components[field] for field in (*fields, "total_investment")})

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

    def __init__(self, path: Path | None = None, *, profile_id: str | None = None,
                 simulation: bool = False):
        self.profile_id = paths.current().label if profile_id is None else profile_id
        if not isinstance(self.profile_id, str) or _PLAN_ID.fullmatch(self.profile_id) is None:
            raise ValueError("Perfil inválido para diário de investimentos.")
        self.simulation = simulation
        filename = "investment_simulation.sqlite3" if simulation else "investment_journal.sqlite3"
        self.path = Path(path) if path is not None else paths.current().data / filename
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
                CREATE TABLE IF NOT EXISTS journal_environment (
                    environment TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS executor_guards (
                    profile_id TEXT PRIMARY KEY,
                    owner_token TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    owner_pid INTEGER,
                    owner_host TEXT
                );
            """)
            # Serialize schema migration across executors starting with the
            # same journal, including installations created before PID fields.
            conn.execute("BEGIN IMMEDIATE")
            guard_columns = {row["name"] for row in conn.execute(
                "PRAGMA table_info(executor_guards)"
            )}
            if "owner_pid" not in guard_columns:
                conn.execute("ALTER TABLE executor_guards ADD COLUMN owner_pid INTEGER")
            if "owner_host" not in guard_columns:
                conn.execute("ALTER TABLE executor_guards ADD COLUMN owner_host TEXT")
            environment = "simulation" if self.simulation else "game"
            row = conn.execute("SELECT environment FROM journal_environment").fetchone()
            if row is None:
                if self.simulation and conn.execute("SELECT 1 FROM intents LIMIT 1").fetchone():
                    raise ValueError("Um diário de compras existente não pode virar simulação.")
                conn.execute("INSERT INTO journal_environment (environment) VALUES (?)", (environment,))
            elif row["environment"] != environment:
                raise ValueError("Diário de investimentos de ambiente incompatível.")

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
        if "profile_id" in plan and plan["profile_id"] != self.profile_id:
            raise ValueError("Plano de investimento pertence a outro perfil.")
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
        """Atomic compare-and-set. Submission requires claim_submission().

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
            plan = json.loads(row["plan_json"])
            if next_state == "CONFIRMED":
                if not self._confirmed(confirmation, plan):
                    raise ValueError("Confirmação independente e vinculada ao plano obrigatória.")
                if plan["kind"] == "aircraft":
                    # BEGIN IMMEDIATE serializes confirmations. Check durable
                    # receipts so one game order cannot settle two intentions.
                    receipts = conn.execute(
                        "SELECT evidence_json FROM events WHERE profile_id=? "
                        "AND intent_key<>? AND new_state='CONFIRMED' "
                        "AND evidence_json IS NOT NULL",
                        (self.profile_id, intent_key),
                    )
                    if any(json.loads(row["evidence_json"]).get("purchase_id")
                           == confirmation["purchase_id"] for row in receipts):
                        raise ValueError("comprovante de compra já usado por outra intenção.")
            if next_state == "FAILED" and expected in ("SUBMITTED", "UNKNOWN"):
                if not self._refused(confirmation, plan):
                    raise ValueError("Recusa independente com ausência de pedido obrigatória.")
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
                "before_owned", "after_owned", "request_rejected", "orders_checked",
                "order_absent", "refusal_code",
            ) if name in confirmation} if next_state in ("CONFIRMED", "FAILED")
                and confirmation is not None else None)
            self._event(conn, intent_key, expected, next_state, stamp, public_evidence)
        return True

    def _matching_evidence(self, evidence: Mapping | None, plan: Mapping) -> bool:
        if (not isinstance(evidence, Mapping)
                or evidence.get("profile_id") != self.profile_id
                or evidence.get("verified") is not True
                or type(evidence.get("observed_at")) not in (int, float)
                or not math.isfinite(evidence["observed_at"])
                or not 0 <= time.time() - evidence["observed_at"] < 900
                or evidence.get("hub_id") != plan["hub_id"]):
            return False
        if plan["kind"] == "aircraft":
            return all(evidence.get(name) == plan[name] for name in (
                "model_id", "engine_id", "origin_id", "destination_id"))
        return True

    def _confirmed(self, evidence: Mapping | None, plan: Mapping) -> bool:
        if not self._matching_evidence(evidence, plan):
            return False
        if plan["kind"] == "hub":
            source = "simulation_owned_hubs" if self.simulation else "game_owned_hubs"
            return (evidence.get("source") == source
                    and evidence.get("before_owned") is False
                    and evidence.get("after_owned") is True)
        source = "simulation_order_list" if self.simulation else "game_order_list"
        return evidence.get("source") == source and _game_id(evidence.get("purchase_id"))

    def _refused(self, evidence: Mapping | None, plan: Mapping) -> bool:
        source = "simulation_order_rejection" if self.simulation else "game_order_rejection"
        return (self._matching_evidence(evidence, plan)
                and evidence.get("source") == source
                and evidence.get("request_rejected") is True
                and evidence.get("orders_checked") is True
                and evidence.get("order_absent") is True
                and _choice_id(evidence.get("refusal_code")))

    def acquire_executor(self, owner_token: str) -> bool:
        """Acquire the single durable mutation slot for this profile."""
        if not isinstance(owner_token, str) or _PLAN_ID.fullmatch(owner_token) is None:
            raise ValueError("Identidade do executor inválida.")
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            result = conn.execute(
                "INSERT OR IGNORE INTO executor_guards "
                "(profile_id, owner_token, acquired_at, owner_pid, owner_host) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.profile_id, owner_token, time.time(), os.getpid(), socket.gethostname()),
            )
            return result.rowcount == 1

    def release_executor(self, owner_token: str) -> bool:
        if not isinstance(owner_token, str) or _PLAN_ID.fullmatch(owner_token) is None:
            raise ValueError("Identidade do executor inválida.")
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            return conn.execute(
                "DELETE FROM executor_guards WHERE profile_id=? AND owner_token=?",
                (self.profile_id, owner_token),
            ).rowcount == 1

    def executor_busy(self) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM executor_guards WHERE profile_id=?",
                (self.profile_id,),
            ).fetchone() is not None

    def release_stale_executor(self) -> bool:
        """Release a guard only when its same-host owner process is proven gone.

        Older guards without process metadata and guards owned by another host
        remain locked for explicit recovery. An inaccessible or ambiguous PID
        is treated as alive.
        """
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            guard = conn.execute(
                "SELECT owner_token, owner_pid, owner_host FROM executor_guards "
                "WHERE profile_id=?",
                (self.profile_id,),
            ).fetchone()
            if guard is None:
                return False
            if (guard["owner_host"] != socket.gethostname()
                    or type(guard["owner_pid"]) is not int
                    or _process_is_running(guard["owner_pid"])):
                return False
            return conn.execute(
                "DELETE FROM executor_guards WHERE profile_id=? AND owner_token=? "
                "AND owner_pid=? AND owner_host=?",
                (self.profile_id, guard["owner_token"], guard["owner_pid"],
                 guard["owner_host"]),
            ).rowcount == 1

    def claim_submission(self, intent_key: str, owner_token: str) -> bool:
        """Claim one submission only under the profile lock and no unknown orders."""
        if (not isinstance(intent_key, str) or _INTENT_KEY.fullmatch(intent_key) is None
                or not isinstance(owner_token, str) or _PLAN_ID.fullmatch(owner_token) is None):
            raise ValueError("Identidade de compra ou executor inválida.")
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            guard = conn.execute(
                "SELECT owner_token FROM executor_guards WHERE profile_id=?",
                (self.profile_id,),
            ).fetchone()
            if guard is None or guard["owner_token"] != owner_token:
                raise ValueError("Executor sem exclusividade sobre o perfil.")
            row = conn.execute(
                "SELECT state FROM intents WHERE profile_id=? AND intent_key=?",
                (self.profile_id, intent_key),
            ).fetchone()
            if row is None:
                raise KeyError("Intenção não encontrada no perfil.")
            if row["state"] != "PRECHECKED":
                return False
            if conn.execute(
                "SELECT 1 FROM intents WHERE profile_id=? AND intent_key<>? "
                "AND state IN ('SUBMITTED', 'UNKNOWN') LIMIT 1",
                (self.profile_id, intent_key),
            ).fetchone():
                return False
            stamp = time.time()
            conn.execute(
                "UPDATE intents SET state='SUBMITTED', updated_at=?, "
                "submit_attempts=submit_attempts+1 WHERE profile_id=? AND intent_key=?",
                (stamp, self.profile_id, intent_key),
            )
            self._event(conn, intent_key, "PRECHECKED", "SUBMITTED", stamp)
            return True

    def budget_exposure_since(self, since: float, *, exclude_intent_key: str | None = None) -> int:
        """Conservatively count current commitments plus confirmed spend in a window."""
        if type(since) not in (int, float) or not math.isfinite(since):
            raise ValueError("Início de janela inválido.")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT intent_key, state, created_at, updated_at, plan_json FROM intents "
                "WHERE profile_id=? AND (state IN ('APPROVED','PRECHECKED','SUBMITTED','UNKNOWN') "
                "OR (state='CONFIRMED' AND updated_at>=?))",
                (self.profile_id, since),
            ).fetchall()
        return sum(json.loads(row["plan_json"])["estimated_cost"] for row in rows
                   if row["intent_key"] != exclude_intent_key)

    def acquisition_count_since(self, since: float, *, exclude_intent_key: str | None = None) -> int:
        """Count current reservations and confirmed orders within the window, per profile."""
        if type(since) not in (int, float) or not math.isfinite(since):
            raise ValueError("Início de janela inválido.")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM intents WHERE profile_id=? "
                "AND (? IS NULL OR intent_key<>?) "
                "AND (state IN ('APPROVED','PRECHECKED','SUBMITTED','UNKNOWN') "
                "OR (state='CONFIRMED' AND updated_at>=?))",
                (self.profile_id, exclude_intent_key, exclude_intent_key, since),
            ).fetchone()
        return row["total"]

    def recover_submitted(self, *, owner_token: str | None = None) -> int:
        """Quarantine in-flight requests under exclusive ownership, without replay.

        An explicit owner may recover while holding the profile guard. Calls
        without an owner preserve the original stopped-executor requirement.
        """
        if owner_token is not None and (
            not isinstance(owner_token, str) or _PLAN_ID.fullmatch(owner_token) is None
        ):
            raise ValueError("Identidade do executor inválida.")
        stamp = time.time()
        with self._connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            guard = conn.execute(
                "SELECT owner_token FROM executor_guards WHERE profile_id=?",
                (self.profile_id,),
            ).fetchone()
            if owner_token is None and guard is not None:
                raise RuntimeError("Há um executor registrado: confirme sua parada antes da conciliação.")
            if owner_token is not None and (guard is None or guard["owner_token"] != owner_token):
                raise RuntimeError("Executor sem exclusividade sobre o perfil.")
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

    def unresolved(self, *, since: float | None = None) -> dict:
        """Return reservations and optionally the local period usage in one read."""
        self._validate_since(since)
        with self._connect() as conn:
            return self._read_unresolved(conn, self.profile_id, since)

    @classmethod
    def read_existing(cls, *, since: float | None = None) -> dict:
        """Read the active game's ledger without creating or migrating it."""
        cls._validate_since(since)
        profile = paths.current()
        path = profile.data / "investment_journal.sqlite3"
        try:
            path.stat()
        except FileNotFoundError:
            # This is only the absence of local reservations, not proof of
            # the game's outstanding orders or financial commitments.
            return cls._summarize_unresolved([], profile.label, since)
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            environments = conn.execute("SELECT environment FROM journal_environment").fetchall()
            if len(environments) != 1 or environments[0]["environment"] != "game":
                raise ValueError("Diário de investimentos de ambiente incompatível.")
            return cls._read_unresolved(conn, profile.label, since)

    @classmethod
    def _read_unresolved(cls, conn, profile_id: str, since: float | None) -> dict:
        placeholders = ",".join("?" for _ in _RESERVED_STATES)
        rows = conn.execute(
            f"SELECT * FROM intents WHERE profile_id=? AND (state IN ({placeholders}) "
            "OR (state='CONFIRMED' AND updated_at>=?)) "
            "ORDER BY created_at, intent_key",
            (profile_id, *_RESERVED_STATES, since),
        ).fetchall()
        return cls._summarize_unresolved(rows, profile_id, since)

    @staticmethod
    def _validate_since(since: float | None) -> None:
        if since is not None and (type(since) not in (int, float) or not math.isfinite(since) or since < 0):
            raise ValueError("Início de janela inválido.")

    @classmethod
    def _summarize_unresolved(cls, rows, profile_id: str, since: float | None) -> dict:
        intents = [cls._unpack(row) for row in rows if row["state"] in _RESERVED_STATES]
        exposure = sum(row["estimated_cost"] for row in intents)
        result = {"intents": intents, "estimated_exposure": exposure,
                  "count": len(intents), "profile_id": profile_id}
        if since is not None:
            confirmed = [row for row in rows if row["state"] == "CONFIRMED"]
            result["period_usage"] = {
                "since": since, "source": "local_investment_journal",
                "estimated_exposure": exposure + sum(json.loads(row["plan_json"])["estimated_cost"] for row in confirmed),
                "acquisition_count": len(intents) + len(confirmed),
                "last_confirmed_at": max((row["updated_at"] for row in confirmed), default=None),
            }
        return result

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

    @staticmethod
    def _event_record(row: sqlite3.Row) -> dict:
        return {
            "event_id": row["event_id"],
            "profile_id": row["profile_id"],
            "intent_key": row["intent_key"],
            "previous_state": row["previous_state"],
            "new_state": row["new_state"],
            "observed_at": row["observed_at"],
            "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else None,
            "plan": json.loads(row["plan_json"]),
        }

    def latest_event_id(self) -> int:
        """Return the newest event ID visible to this profile."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS latest_event_id FROM events "
                "WHERE profile_id=?",
                (self.profile_id,),
            ).fetchone()
        return int(row["latest_event_id"])

    def events_after(self, event_id: int, *, limit: int = 1) -> list[dict]:
        """Read ordered state changes after a profile-scoped event cursor."""
        if type(event_id) is not int or event_id < 0:
            raise ValueError("Cursor de eventos inválido.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limite de eventos inválido.")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT e.event_id, e.profile_id, e.intent_key, e.previous_state, "
                "e.new_state, e.observed_at, e.evidence_json, i.plan_json "
                "FROM events e JOIN intents i "
                "ON i.profile_id=e.profile_id AND i.intent_key=e.intent_key "
                "WHERE e.profile_id=? AND e.event_id>? ORDER BY e.event_id LIMIT ?",
                (self.profile_id, event_id, limit),
            ).fetchall()
        return [self._event_record(row) for row in rows]

    def event(self, event_id: int) -> dict | None:
        """Read one event with its validated plan, scoped to the active profile."""
        if type(event_id) is not int or event_id <= 0:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT e.event_id, e.profile_id, e.intent_key, e.previous_state, "
                "e.new_state, e.observed_at, e.evidence_json, i.plan_json "
                "FROM events e JOIN intents i "
                "ON i.profile_id=e.profile_id AND i.intent_key=e.intent_key "
                "WHERE e.profile_id=? AND e.event_id=?",
                (self.profile_id, event_id),
            ).fetchone()
        return self._event_record(row) if row is not None else None

    def audit_metrics(self, since: float) -> dict:
        """Read an atomic, profile-scoped journal summary for A9 observability.

        Costs remain *planned* amounts, even after a game order is confirmed.
        Recovery durations come only from observed journal state transitions.
        """
        if type(since) not in (int, float) or not math.isfinite(since) or since < 0:
            raise ValueError("Início de janela inválido.")
        with self._connect() as conn:
            conn.execute("BEGIN")
            intents = conn.execute(
                "SELECT state, created_at, updated_at, submit_attempts, plan_json "
                "FROM intents WHERE profile_id=?",
                (self.profile_id,),
            ).fetchall()
            events = conn.execute(
                "SELECT intent_key, new_state, observed_at FROM events "
                "WHERE profile_id=? AND observed_at>=? ORDER BY event_id",
                (self.profile_id, since),
            ).fetchall()

        by_state = {state: 0 for state in (*_TRANSITIONS,)}
        by_kind = {"aircraft": 0, "hub": 0}
        pending_cost = 0
        confirmed_planned_cost = 0
        created_in_window = 0
        confirmed_in_window = 0
        failed_in_window = 0
        submit_attempts = 0
        for row in intents:
            plan = json.loads(row["plan_json"])
            state = row["state"]
            kind = plan["kind"]
            by_state[state] = by_state.get(state, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
            submit_attempts += row["submit_attempts"]
            if state in _RESERVED_STATES:
                pending_cost += plan["estimated_cost"]
            if row["created_at"] >= since:
                created_in_window += 1
            if row["updated_at"] >= since and state == "CONFIRMED":
                confirmed_in_window += 1
                confirmed_planned_cost += plan["estimated_cost"]
            if row["updated_at"] >= since and state == "FAILED":
                failed_in_window += 1

        unknown_at: dict[str, float] = {}
        recovery_seconds: list[float] = []
        for event in events:
            key = event["intent_key"]
            state = event["new_state"]
            if state == "UNKNOWN":
                unknown_at[key] = event["observed_at"]
            elif state in ("CONFIRMED", "FAILED") and key in unknown_at:
                recovery_seconds.append(max(0.0, event["observed_at"] - unknown_at.pop(key)))

        return {
            "profile_id": self.profile_id,
            "simulation": self.simulation,
            "source": "local_investment_journal",
            "since": float(since),
            "total_intents": len(intents),
            "created_in_window": created_in_window,
            "by_state": by_state,
            "by_kind": by_kind,
            "confirmed_in_window": confirmed_in_window,
            "failed_in_window": failed_in_window,
            "submit_attempts_total": submit_attempts,
            "pending_planned_cost": pending_cost,
            "confirmed_planned_cost_in_window": confirmed_planned_cost,
            "reconciliations_from_unknown": len(recovery_seconds),
            "mean_recovery_seconds": (
                sum(recovery_seconds) / len(recovery_seconds) if recovery_seconds else None
            ),
            "last_event_at": events[-1]["observed_at"] if events else None,
        }
