"""Run the read-only expansion planner on the browser owner's cycle.

The last decision is bound to the capture that triggered it. A fresh capture
or a failed cycle cannot inherit an earlier purchase suggestion.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import Counter

import paths
from audited_game_snapshot import capture_game_snapshot, replay_research_page, snapshot_summary
from opportunity_models import DEFAULT_MAX_AGE_SECONDS


FILENAME = "investment_planning_cycle.json"
RESEARCH_PAGE_BUDGET = 2
_ECONOMICS_ID = re.compile(r"economics-v1-[0-9a-f]{32}")
log = logging.getLogger("am4bot.investment")


def _save(report):
    paths.write_atomic(paths.current().data / FILENAME,
                       json.dumps(report, ensure_ascii=False, allow_nan=False), private=True)


def _valid_cursor(cursor):
    return (isinstance(cursor, dict) and type(cursor.get("next_offset")) is int
            and cursor["next_offset"] > 0
            and isinstance(cursor.get("layout_fingerprint"), str)
            and re.fullmatch(r"[0-9a-f]{24}", cursor["layout_fingerprint"]) is not None)


def _load_cursor(profile):
    """Retain only scheduling state, even after a failed or expired cycle."""
    try:
        previous = json.loads((profile.data / FILENAME).read_text(encoding="utf-8"))
        cursor = previous.get("research_cursor")
        if previous.get("profile_id") == profile.label and _valid_cursor(cursor):
            return cursor
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def _research_summary(snapshot_id, cursor=None):
    """Evaluate sampled combinations within a bounded, single-snapshot sweep."""
    offset = cursor["next_offset"] if cursor else 0
    expected_layout = cursor["layout_fingerprint"] if cursor else None
    first_offset = offset
    fingerprint = None
    layout_fingerprint = None
    total = None
    combinations = layouts = pages = 0
    blockers = Counter()
    evidence_rows = []
    queue_blockers = []
    for _ in range(RESEARCH_PAGE_BUDGET):
        page = replay_research_page(offset=offset, expected_snapshot=snapshot_id,
                                    expected_fingerprint=fingerprint,
                                    expected_layout_fingerprint=expected_layout if not pages else None)
        if (page.get("status") != "parcial" or page.get("snapshot_id") != snapshot_id
                or page.get("historical_replay") is not True or page.get("read_only") is not True
                or page.get("purchase_eligible") is not False):
            raise ValueError("Replay de pesquisa divergente.")
        if not pages and cursor and page.get("cursor_reset") is True:
            offset = first_offset = 0
        elif page.get("cursor_reset") is not False:
            raise ValueError("Cursor de pesquisa divergente.")
        if page.get("offset") != offset:
            raise ValueError("Deslocamento de pesquisa divergente.")
        if total is None:
            total = page["total_candidates"]
            fingerprint = page["snapshot_fingerprint"]
            layout_fingerprint = page["layout_fingerprint"]
            queue_blockers = page["blocking_reasons"]
        elif (total != page["total_candidates"] or fingerprint != page["snapshot_fingerprint"]
              or layout_fingerprint != page["layout_fingerprint"]):
            raise ValueError("Cobertura de pesquisa alterada.")
        items = page["items"]
        if type(total) is not int or not 0 <= offset + len(items) <= total:
            raise ValueError("Contagem de pesquisa inválida.")
        for row_offset, item in enumerate(items, offset):
            gate = item["accounting_gate"]
            evaluations = []
            for evaluation in [gate, *gate["layout_evaluations"]]:
                if (evaluation["read_only"] is not True or evaluation["purchase_eligible"] is not False
                        or evaluation["status"] != "blocked"):
                    raise ValueError("Resultado de pesquisa incompatível.")
                blockers.update({reason["code"] for reason in evaluation["blocking_reasons"]})
                evaluations.append({"economics_id": evaluation["economics_id"],
                                    "blocking_reasons": evaluation["blocking_reasons"]})
            evidence_rows.append({"offset": row_offset,
                                  "evaluations": evaluations})
            layouts += len(gate["layout_evaluations"])
        combinations += len(items)
        pages += 1
        next_offset = page["next_offset"]
        end_offset = first_offset + combinations
        if end_offset == total and next_offset is None:
            break
        if not items or next_offset != end_offset or end_offset >= total:
            raise ValueError("Paginação de pesquisa inválida.")
        offset = next_offset
    summary = {"coverage": "partial", "total_sampled_combinations": total,
            "examined_combinations": combinations, "blocked_combinations": combinations,
            "hypothetical_layouts": layouts, "pages": pages,
            "first_offset": first_offset, "next_offset": next_offset,
            "sample_sweep_complete": first_offset == 0 and combinations == total and not queue_blockers,
            "queue_blocking_reasons": queue_blockers, "accounting_blocker_counts": dict(blockers)}
    # A temporary outage must not discard the scheduling position. No results
    # from previous captures are carried over to the accounting summary.
    next_cursor = (cursor if queue_blockers else None if next_offset is None else
                   {"next_offset": next_offset, "layout_fingerprint": layout_fingerprint})
    if next_cursor is not None and not _valid_cursor(next_cursor):
        raise ValueError("Cursor de pesquisa inválido.")
    audit = {"snapshot_id": snapshot_id, "snapshot_fingerprint": fingerprint,
             "layout_fingerprint": layout_fingerprint, "rows": evidence_rows}
    return summary, next_cursor, audit


def _valid_research_summary(research):
    if not isinstance(research, dict) or research.get("coverage") != "partial":
        return False
    total, examined, blocked, layouts, pages = (research.get(key) for key in (
        "total_sampled_combinations", "examined_combinations", "blocked_combinations",
        "hypothetical_layouts", "pages"))
    queue = research.get("queue_blocking_reasons")
    counts = research.get("accounting_blocker_counts")
    first = research.get("first_offset", 0)
    end = first + examined if type(first) is int and type(examined) is int else -1
    next_offset = research.get("next_offset", end if type(total) is int and end < total else None)
    return (all(type(value) is int and value >= 0 for value in (total, examined, blocked, layouts, pages))
            and type(first) is int and 0 <= first <= end <= total
            and (next_offset is None if end == total else type(next_offset) is int and next_offset == end)
            and blocked == examined and 1 <= pages <= RESEARCH_PAGE_BUDGET
            and isinstance(queue, list) and all(isinstance(code, str) and code for code in queue)
            and isinstance(counts, dict) and all(isinstance(code, str) and code
                and type(value) is int and 0 < value <= examined + layouts for code, value in counts.items())
            and research.get("sample_sweep_complete") is (first == 0 and examined == total and not queue))


def _valid_research_audit(audit, research, snapshot_id):
    """Reconcile the private scenario trace with the published aggregate."""
    if (not isinstance(audit, dict) or audit.get("snapshot_id") != snapshot_id
            or any(not isinstance(audit.get(key), str) or not re.fullmatch(r"[0-9a-f]{24}", audit[key])
                   for key in ("snapshot_fingerprint", "layout_fingerprint"))
            or not isinstance(audit.get("rows"), list)
            or len(audit["rows"]) != research["examined_combinations"]):
        return False
    counts = Counter()
    ids = set()
    layouts = 0
    for offset, row in enumerate(audit["rows"], research["first_offset"]):
        if (not isinstance(row, dict) or row.get("offset") != offset
                or not isinstance(row.get("evaluations"), list) or not row["evaluations"]):
            return False
        layouts += len(row["evaluations"]) - 1
        for entry in row["evaluations"]:
            if not isinstance(entry, dict):
                return False
            identifier, reasons = entry.get("economics_id"), entry.get("blocking_reasons")
            if (not isinstance(identifier, str) or not _ECONOMICS_ID.fullmatch(identifier)
                    or identifier in ids or not isinstance(reasons, list) or not reasons
                    or any(not isinstance(reason, dict) or set(reason) != {"code", "field"}
                           or any(not isinstance(value, str) or not value for value in reason.values())
                           for reason in reasons)):
                return False
            ids.add(identifier)
            counts.update({reason["code"] for reason in reasons})
    return layouts == research["hypothetical_layouts"] and counts == research["accounting_blocker_counts"]


def capture_and_plan(bot):
    """Recompute A4 after each productive capture, independent of web/Telegram use."""
    if bot.dry_run:
        return capture_game_snapshot(bot)
    from expansion_metrics import _audited_metrics
    from web import WebDashboard

    profile = paths.current()
    cursor = _load_cursor(profile)
    record = {"profile_id": profile.label, "status": "em_execucao", "read_only": True,
              "started_at": time.time(), "snapshot_id": None, "finished_at": None,
              "decision": None, "evaluated_count": None, "eligible_count": None,
              "blocking_reasons": [], "research_cursor": cursor}
    _save(record)
    try:
        snapshot = capture_game_snapshot(bot)
        record["snapshot_id"] = snapshot["snapshot_id"]
        research, next_cursor, audit = _research_summary(record["snapshot_id"], cursor)
        if not _valid_research_summary(research) or not _valid_research_audit(audit, research, record["snapshot_id"]):
            raise ValueError("Resumo de pesquisa inválido.")
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
                      research=research,
                      research_audit=audit,
                      research_cursor=next_cursor,
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
                      evaluated_count=None, eligible_count=None, blocking_reasons=[], research=None,
                      research_audit=None,
                      research_cursor=cursor)
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
        research = record.get("research")
        if (decision not in (None, "nao_comprar", "sugestao_para_analise")
                or (record["status"] == "concluido") != (decision is not None)
                or not (evaluated is None and eligible is None
                        or type(evaluated) is int and type(eligible) is int and 0 <= eligible <= evaluated)
                or not isinstance(blockers, list)
                or not all(isinstance(code, str) and code for code in blockers)
                or not _valid_research_summary(research)
                or not _valid_research_audit(record.get("research_audit"), research, record["snapshot_id"])):
            return {**unavailable, "status": "registro_invalido"}
        return {**unavailable, "status": record["status"], "started_at": started,
                "finished_at": finished, "snapshot_id": record["snapshot_id"],
                "decision": decision, "evaluated_count": evaluated,
                "eligible_count": eligible, "blocking_reasons": blockers, "research": research}
    except FileNotFoundError:
        return unavailable
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return {**unavailable, "status": "registro_invalido"}
