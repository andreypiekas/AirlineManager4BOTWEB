"""Run the read-only expansion planner on the browser owner's cycle.

The last decision is bound to the capture that triggered it. A fresh capture
or a failed cycle cannot inherit an earlier purchase suggestion.
"""
from __future__ import annotations

import json
import logging
import math
import time

import paths
from audited_game_snapshot import capture_game_snapshot, snapshot_summary
from opportunity_models import DEFAULT_MAX_AGE_SECONDS


FILENAME = "investment_planning_cycle.json"
log = logging.getLogger("am4bot.investment")


def _save(report):
    paths.write_atomic(paths.current().data / FILENAME,
                       json.dumps(report, ensure_ascii=False, allow_nan=False), private=True)


def capture_and_plan(bot):
    """Recompute A4 after each productive capture, independent of web/Telegram use."""
    if bot.dry_run:
        return capture_game_snapshot(bot)
    from expansion_metrics import _audited_metrics
    from web import WebDashboard

    profile = paths.current()
    record = {"profile_id": profile.label, "status": "em_execucao", "read_only": True,
              "started_at": time.time(), "snapshot_id": None, "finished_at": None,
              "decision": None, "evaluated_count": None, "eligible_count": None,
              "blocking_reasons": []}
    _save(record)
    try:
        snapshot = capture_game_snapshot(bot)
        record["snapshot_id"] = snapshot["snapshot_id"]
        dashboard = WebDashboard(bot, bot.config, buffer=None)
        report = dashboard.audited_expansion()
        current = time.time()
        capture = report.get("game_observation_snapshot") or {}
        if (report.get("profile_id") != profile.label
                or capture.get("snapshot_id") != record["snapshot_id"]
                or capture.get("status") != "parcial"):
            raise ValueError("Snapshot de planejamento divergente.")
        metrics = _audited_metrics(report, profile_id=profile.label, simulation=False, now=current)
        record.update(status="concluido", finished_at=current,
                      decision=metrics["decision"], evaluated_count=metrics["evaluated_count"],
                      eligible_count=metrics["eligible_count"],
                      blocking_reasons=metrics["blocking_reasons"])
        if metrics["decision"] is None:
            record["status"] = "inconclusivo"
        _save(record)
        log.info("Planejamento de expansão: %s (%s impedimentos auditados).",
                 record["decision"] or "inconclusivo", len(record["blocking_reasons"]))
        return snapshot
    except Exception as exc:
        # Never serialize exception text: it may contain private account data.
        record.update(status="falhou", finished_at=time.time(), decision=None,
                      evaluated_count=None, eligible_count=None, blocking_reasons=[])
        _save(record)
        log.warning("Falha no planejamento de expansão (%s).", type(exc).__name__)
        raise RuntimeError("Falha no planejamento de expansão.") from None


def planning_cycle_summary(*, now=None):
    """Expose only the current worker result, never an old actionable decision."""
    now = time.time() if now is None else now
    unavailable = {"status": "sem_execucao", "read_only": True, "historical_only": True,
                   "decision": None}
    try:
        record = json.loads((paths.current().data / FILENAME).read_text(encoding="utf-8"))
        if (record.get("profile_id") != paths.current().label or record.get("read_only") is not True
                or record.get("status") not in ("em_execucao", "concluido", "inconclusivo", "falhou")):
            return {**unavailable, "status": "registro_invalido"}
        started = record.get("started_at")
        if (type(started) not in (int, float) or not math.isfinite(started)
                or not 0 < started <= now or now - started > DEFAULT_MAX_AGE_SECONDS):
            return {**unavailable, "status": "expirado"}
        if record["status"] in ("em_execucao", "falhou"):
            return {**unavailable, "status": record["status"], "started_at": started}
        finished = record.get("finished_at")
        capture = snapshot_summary(now=now)
        if (type(finished) not in (int, float) or not math.isfinite(finished)
                or not started <= finished <= now or capture.get("status") != "parcial"
                or not record.get("snapshot_id") or capture.get("snapshot_id") != record["snapshot_id"]):
            return {**unavailable, "status": "coleta_alterada"}
        decision = record.get("decision")
        evaluated, eligible = record.get("evaluated_count"), record.get("eligible_count")
        blockers = record.get("blocking_reasons")
        if (decision not in (None, "nao_comprar", "sugestao_para_analise")
                or (record["status"] == "concluido") != (decision is not None)
                or not (evaluated is None and eligible is None
                        or type(evaluated) is int and type(eligible) is int and 0 <= eligible <= evaluated)
                or not isinstance(blockers, list)
                or not all(isinstance(code, str) and code for code in blockers)):
            return {**unavailable, "status": "registro_invalido"}
        return {**unavailable, "status": record["status"], "started_at": started,
                "finished_at": finished, "snapshot_id": record["snapshot_id"],
                "decision": decision, "evaluated_count": evaluated,
                "eligible_count": eligible, "blocking_reasons": blockers}
    except FileNotFoundError:
        return unavailable
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return {**unavailable, "status": "registro_invalido"}
