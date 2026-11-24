"""Durable intent for the creation of a parked aircraft's route."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import uuid

from selenium.common.exceptions import WebDriverException

import paths
from helpers import fmt
from notify import esc
from reroute import confirm_direct_route, confirm_stopover
from route_registry import route_key

log = logging.getLogger("am4bot.rutas")


def pending_path():
    return paths.current().data / "route_creation_pending.json"


def has_pending_creation() -> bool:
    return pending_path().exists()


def _valid(job) -> bool:
    if not isinstance(job, dict):
        return False
    if (job.get("phase") not in ("submitted", "confirmed")
            or not re.fullmatch(r"[0-9a-f]{32}", str(job.get("intent_id", "")))
            or not re.fullmatch(r"[0-9]{1,14}", str(job.get("aircraft_id", "")))
            or type(job.get("fee")) is not int or job["fee"] <= 0
            or not all(isinstance(job.get(k), str) for k in ("registration", "model"))
            or job.get("source") not in ("criacao_confirmada", "redirecionamento")):
        return False
    origin, destination, stop = (job.get(k) for k in ("origin", "destination", "stopover"))
    if not all(isinstance(e, dict) and e.get("id") and e.get("code") for e in (origin, destination)):
        return False
    if not route_key(origin, destination) or (stop is not None and (
            not isinstance(stop, dict) or not stop.get("id") or not stop.get("code"))):
        return False
    profit = job.get("profit")
    return profit is None or (type(profit) in (int, float) and math.isfinite(profit))


def stage_creation(aircraft, origin, destination, stopover, fee, profit, *, reroute=False):
    """Reserve the intent before the click; a partial file also blocks retries."""
    job = dict(intent_id=uuid.uuid4().hex, phase="submitted", submitted_at=time.time(),
               aircraft_id=aircraft.id, registration=aircraft.reg, model=aircraft.model,
               origin=origin, destination=destination, stopover=stopover, fee=fee,
               profit=profit, source="redirecionamento" if reroute else "criacao_confirmada")
    if not _valid(job):
        return None
    payload = json.dumps(job, allow_nan=False)
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return job


def finish_creation(bot, registry, job, *, at_base=None) -> bool:
    """Called only after a matching independent game read or persisted confirmation."""
    if job["phase"] == "submitted":
        if not registry.record(job["aircraft_id"], job["registration"], job["model"],
                               job["origin"], job["destination"], source=job["source"],
                               profit_per_day=job["profit"], at_base=at_base, stopover=job["stopover"]):
            return False
        job = {**job, "phase": "confirmed"}
        paths.write_atomic(pending_path(), json.dumps(job, allow_nan=False), private=True)
    bot.record_route_expense(job["intent_id"], job["fee"])
    pending_path().unlink()
    return True


def recover_pending_creation(bot, registry) -> bool:
    """Never resend the purchase: missing or contradictory reads retain the journal."""
    path = pending_path()
    if not path.exists():
        return True
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        if not _valid(job):
            raise ValueError("invalid route creation journal")
        if job["phase"] == "submitted":
            args = (bot, job["aircraft_id"], job["origin"], job["destination"])
            confirmed = (confirm_stopover(*args, job["stopover"]) if job["stopover"]
                         else confirm_direct_route(*args))
            if not confirmed:
                log.warning("Criação de rota pendente de conciliação; nenhuma nova aquisição ou criação será enviada.")
                return False
        if not finish_creation(bot, registry, job):
            return False
    except (OSError, ValueError, KeyError, TypeError, WebDriverException):
        log.warning("Não foi possível conciliar a criação de rota pendente; transação preservada.")
        return False
    summary = f"{job['origin']['code']}–{job['destination']['code']} (taxa cotada ${fmt(job['fee'])})"
    log.info("Criação de rota conciliada: %s.", summary)
    bot.notify(f"🛫 <b>Rota conciliada</b>: {esc(summary)}.", category="routes")
    return True
