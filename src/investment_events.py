"""Opt-in Telegram notifications for durable investment journal events."""
from __future__ import annotations

import logging
import math
import secrets
import sqlite3
import time
from pathlib import Path

from investment_journal import InvestmentJournal
from notify import MAX_LENGTH, esc

log = logging.getLogger("am4bot.telegram")

_CLAIM_LEASE_SECONDS = 300
_STATE_LABELS = {
    "PROPOSED": "Proposta registrada",
    "APPROVED": "Aprovação registrada",
    "PRECHECKED": "Pré-checagem concluída",
    "SUBMITTED": "Pedido enviado ao jogo, aguardando confirmação",
    "CONFIRMED": "Confirmação independente registrada",
    "UNKNOWN": "Resultado incerto, conciliação necessária",
    "FAILED": "Intenção encerrada com falha comprovada",
}


class InvestmentEventDelivery:
    """Persist ordered event claims independently per profile and game mode."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("""CREATE TABLE IF NOT EXISTS investment_event_delivery (
                profile_id TEXT NOT NULL,
                simulation INTEGER NOT NULL CHECK (simulation IN (0, 1)),
                last_event_id INTEGER NOT NULL,
                claim_event_id INTEGER,
                claim_id TEXT,
                claimed_at REAL,
                initialized_at REAL NOT NULL,
                PRIMARY KEY (profile_id, simulation)
            )""")

    @staticmethod
    def _validate(profile_id: str, now: float) -> None:
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError("Perfil de notificação inválido.")
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError("Horário de reivindicação inválido.")

    def initialize(self, profile_id: str, latest_event_id: int, *,
                   now: float, simulation: bool = False) -> bool:
        """Start at the current journal head so enabling the flag sends no backlog."""
        self._validate(profile_id, now)
        if type(latest_event_id) is not int or latest_event_id < 0:
            raise ValueError("Cursor inicial de eventos inválido.")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = conn.execute(
                "INSERT OR IGNORE INTO investment_event_delivery "
                "(profile_id, simulation, last_event_id, initialized_at) VALUES (?, ?, ?, ?)",
                (profile_id, int(simulation), latest_event_id, now),
            )
            return result.rowcount == 1

    def last_event_id(self, profile_id: str, *, simulation: bool = False) -> int | None:
        with sqlite3.connect(self.path, timeout=10) as conn:
            row = conn.execute(
                "SELECT last_event_id FROM investment_event_delivery "
                "WHERE profile_id=? AND simulation=?",
                (profile_id, int(simulation)),
            ).fetchone()
        return int(row[0]) if row is not None else None

    def claim(self, profile_id: str, candidate_event_id: int | None,
              *, now: float, simulation: bool = False) -> tuple[int, str] | None:
        """Claim the next event or recover the same event after an expired lease."""
        self._validate(profile_id, now)
        if (candidate_event_id is not None
                and (type(candidate_event_id) is not int or candidate_event_id <= 0)):
            raise ValueError("Identificador do evento inválido.")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_event_id, claim_event_id, claimed_at "
                "FROM investment_event_delivery WHERE profile_id=? AND simulation=?",
                (profile_id, int(simulation)),
            ).fetchone()
            if row is None:
                return None

            claimed_event_id = row[1]
            if claimed_event_id is not None:
                if row[2] is not None and now - row[2] < _CLAIM_LEASE_SECONDS:
                    return None
                event_id = int(claimed_event_id)
            else:
                if candidate_event_id is None or candidate_event_id <= row[0]:
                    return None
                event_id = candidate_event_id

            token = secrets.token_hex(16)
            conn.execute(
                "UPDATE investment_event_delivery SET claim_event_id=?, claim_id=?, "
                "claimed_at=? WHERE profile_id=? AND simulation=?",
                (event_id, token, now, profile_id, int(simulation)),
            )
            return event_id, token

    def acknowledge(self, profile_id: str, event_id: int, token: str,
                    *, delivered: bool, now: float, simulation: bool = False) -> bool:
        """Advance the cursor only for the worker whose Telegram send succeeded."""
        self._validate(profile_id, now)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if delivered:
                result = conn.execute(
                    "UPDATE investment_event_delivery SET last_event_id=MAX(last_event_id, ?), "
                    "claim_event_id=NULL, claim_id=NULL, claimed_at=NULL "
                    "WHERE profile_id=? AND simulation=? AND claim_event_id=? AND claim_id=?",
                    (event_id, profile_id, int(simulation), event_id, token),
                )
            else:
                result = conn.execute(
                    "UPDATE investment_event_delivery SET "
                    "claim_event_id=NULL, claim_id=NULL, claimed_at=NULL "
                    "WHERE profile_id=? AND simulation=? AND claim_event_id=? AND claim_id=?",
                    (profile_id, int(simulation), event_id, token),
                )
            return result.rowcount == 1


def format_investment_event(event: dict, *, simulation: bool) -> str:
    """Describe one state transition without presenting planned cost as actual spend."""
    plan = event["plan"]
    state = event["new_state"]
    kind = "Aeronave" if plan["kind"] == "aircraft" else "Novo hub"
    label = _STATE_LABELS.get(state, "Estado atualizado")
    stamp = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(event["observed_at"]))
    lines = [
        f"{'🧪 Simulação — ' if simulation else ''}🧾 <b>Investimento — {esc(kind)}</b>",
        f"<b>{esc(label)}</b>",
        f"Plano: {esc(plan['plan_id'])}",
        f"Hub: {esc(plan['hub_id'])}",
    ]
    if plan["kind"] == "aircraft":
        lines.extend((
            f"Rota: {esc(plan['origin_id'])} → {esc(plan['destination_id'])}",
            f"Aeronave: {esc(plan['model_id'])} | Motor: {esc(plan['engine_id'])}",
        ))
    lines.extend((
        f"Valor previsto no plano: ${plan['estimated_cost']:,} (não representa gasto observado).",
        f"Evento #{event['event_id']} em {esc(stamp)}.",
    ))
    if state == "CONFIRMED":
        lines.append("A confirmação está vinculada à evidência independente registrada no diário.")
    elif state == "UNKNOWN":
        lines.append("Não repita a aquisição enquanto o pedido não for conciliado.")
    elif state == "SUBMITTED":
        lines.append("A submissão, isoladamente, ainda não comprova a compra.")
    return "\n".join(lines)


def publish_investment_event(bot, *, now: float | None = None) -> str:
    """Send at most one new journal event per bot cycle, in durable order."""
    cfg = bot.config
    if (not cfg.get_bool("options", "telegram_investment_events")
            or not cfg.get_bool("options", "telegram")
            or not bot.telegram.enabled):
        return "disabled"

    current = time.time() if now is None else now
    simulation = bool(getattr(bot, "dry_run", False))
    journal_name = "investment_simulation.sqlite3" if simulation else "investment_journal.sqlite3"
    journal = InvestmentJournal(cfg.profile.data / journal_name,
                                profile_id=cfg.profile.label, simulation=simulation)
    delivery = InvestmentEventDelivery(
        cfg.profile.data / "investment_event_delivery.sqlite3",
    )
    if delivery.initialize(cfg.profile.label, journal.latest_event_id(),
                           now=current, simulation=simulation):
        return "initialized"

    cursor = delivery.last_event_id(cfg.profile.label, simulation=simulation)
    if cursor is None:
        return "uninitialized"
    candidates = journal.events_after(cursor, limit=1)
    candidate_id = candidates[0]["event_id"] if candidates else None
    claim = delivery.claim(cfg.profile.label, candidate_id,
                           now=current, simulation=simulation)
    if claim is None:
        return "idle"
    event_id, token = claim
    delivered = False
    try:
        event = candidates[0] if candidates and candidates[0]["event_id"] == event_id else journal.event(event_id)
        if event is None:
            log.warning("Evento do diário de investimentos não encontrado para entrega.")
            return "missing_event"
        message = format_investment_event(event, simulation=simulation)
        if not cfg.profile.is_main:
            message = f"[{esc(cfg.profile.label)}] {message}"
        if len(message) > MAX_LENGTH:
            log.warning("Notificação de investimento excedeu o limite do Telegram.")
            return "oversized"
        delivered, _description = bot.telegram.send_now(message)
        return "delivered" if delivered else "failed"
    except Exception:
        # Transport exceptions may contain token-bearing Telegram URLs.
        log.warning("Falha ao compor ou enviar evento de investimento ao Telegram.")
        return "failed"
    finally:
        delivery.acknowledge(cfg.profile.label, event_id, token,
                             delivered=delivered, now=time.time(), simulation=simulation)
