"""Read-only A9 operating metrics with explicit evidence boundaries.

Journal events prove local intent transitions. They do not prove delivery,
actual expenditure, flight profit, or full market coverage. Those values remain
unknown until independent authenticated game observations are connected.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence

from investment_journal import InvestmentJournal
from finance_observations import MAX_AGE as FINANCE_MAX_AGE, SOURCE as FINANCE_SOURCE, validate_summary


def build_expansion_metrics(
    journal: InvestmentJournal,
    *,
    now: float | None = None,
    window_days: int = 30,
    opportunity_report: Mapping | None = None,
    calibration_reports: Sequence[Mapping] | None = None,
) -> dict:
    """Summarize investment decisions without upgrading partial data to facts.

    ``calibration_reports`` may only come from the trusted read-only
    ``compare_forecast`` pipeline after it validates game delivery, flight IDs
    and the independent full accounting ledger. The web API supplies none until
    that authenticated producer exists.
    """
    current = time.time() if now is None else now
    if (type(current) not in (int, float) or not math.isfinite(current) or current <= 0
            or type(window_days) is not int or not 1 <= window_days <= 365):
        raise ValueError("Janela de métricas inválida.")
    since = float(current - window_days * 86400)
    audit = journal.audit_metrics(max(0.0, since))

    coverage = {"status": "sem_fonte", "hubs_total": None, "hubs_pesquisados": None,
                "research_tasks_shown": None, "has_more_tasks": None}
    opportunities = {"evaluated_count": None, "eligible_count": None,
                     "source": None, "status": "sem_fonte"}
    portfolio_blockers = None
    company_finance = {"status": "unverified", "historical_only": True, "summary": None}
    if isinstance(opportunity_report, Mapping):
        finance = opportunity_report.get("finance_observations")
        if isinstance(finance, Mapping) and finance.get("source") == FINANCE_SOURCE and finance.get("status") == "observed":
            stamp = finance.get("observed_at")
            summary = validate_summary(finance.get("summary"))
            if (not journal.simulation and summary is not None and type(stamp) in (int, float)
                    and 0 < stamp <= current and current - stamp <= FINANCE_MAX_AGE):
                company_finance = {**company_finance, "status": "observed", "source": FINANCE_SOURCE,
                                   "observed_at": stamp, "summary": summary}
        queue = opportunity_report.get("research_queue")
        if isinstance(queue, Mapping):
            hub_coverage = queue.get("hub_coverage")
            items = queue.get("items")
            if isinstance(hub_coverage, list) and isinstance(items, list):
                complete = (queue.get("coverage") == "complete"
                            and queue.get("has_more") is False
                            and all(isinstance(item, Mapping)
                                    and item.get("coverage") == "complete"
                                    for item in hub_coverage))
                coverage = {
                    "status": "complete" if complete else "partial",
                    "hubs_total": len(hub_coverage),
                    "hubs_pesquisados": sum(
                        item.get("status") == "pesquisa_iniciada" for item in hub_coverage
                        if isinstance(item, Mapping)
                    ),
                    "research_tasks_shown": len(items),
                    "has_more_tasks": queue.get("has_more") is True,
                }
        portfolio = opportunity_report.get("portfolio")
        if isinstance(portfolio, Mapping):
            evaluated = portfolio.get("evaluated_count")
            eligible = portfolio.get("eligible_count")
            if (type(evaluated) is int and evaluated >= 0
                    and type(eligible) is int and 0 <= eligible <= evaluated):
                opportunities = {
                    "evaluated_count": evaluated, "eligible_count": eligible,
                    "source": "portfolio_planner", "status": portfolio.get("status"),
                }
                blockers = portfolio.get("blocking_reasons")
                if isinstance(blockers, list) and all(isinstance(reason, str) for reason in blockers):
                    portfolio_blockers = list(dict.fromkeys(blockers))

    forecast = {"status": "sem_historico_verificado", "plans": 0,
                "complete_days": None, "independent_flights": None,
                "mean_absolute_daily_error": None}
    if calibration_reports is not None:
        if not isinstance(calibration_reports, (list, tuple)):
            raise ValueError("Relatórios de calibração inválidos.")
        valid: dict[str, Mapping] = {}
        seen: set[str] = set()
        duplicates: set[str] = set()
        for report in calibration_reports:
            if not isinstance(report, Mapping) or report.get("profile_id") != journal.profile_id:
                continue
            metrics = report.get("metrics")
            if (report.get("status") != "conclusivo" or report.get("reasons") != []
                    or not isinstance(metrics, Mapping)
                    or not isinstance(report.get("plan_id"), str)):
                continue
            days = metrics.get("complete_days")
            flights = metrics.get("independent_flights")
            error = metrics.get("mean_absolute_daily_error")
            if (type(days) is not int or days <= 0 or type(flights) is not int
                    or flights <= 0 or type(error) not in (int, float)
                    or not math.isfinite(error) or error < 0):
                continue
            plan_id = report["plan_id"]
            if plan_id in seen:
                # Repeated reports for one purchase do not make independent samples.
                duplicates.add(plan_id)
                valid.pop(plan_id, None)
                continue
            seen.add(plan_id)
            valid[plan_id] = metrics
        for plan_id in duplicates:
            valid.pop(plan_id, None)
        if valid:
            days_total = sum(row["complete_days"] for row in valid.values())
            forecast = {
                "status": "calibracao_verificada", "plans": len(valid),
                "complete_days": days_total,
                "independent_flights": sum(row["independent_flights"] for row in valid.values()),
                "mean_absolute_daily_error": round(sum(
                    row["complete_days"] * row["mean_absolute_daily_error"]
                    for row in valid.values()
                ) / days_total, 2),
            }

    return {
        "profile_id": journal.profile_id,
        "environment": "simulation" if journal.simulation else "game",
        "read_only": True,
        "window_days": window_days,
        "generated_at": float(current),
        "journal": audit,
        "research_coverage": coverage,
        "opportunities": opportunities,
        "portfolio_blocking_reasons": portfolio_blockers,
        "forecast": forecast,
        "company_finance_24h": company_finance,
        "actual_spend": None,
        "verified_deliveries": None,
        "verified_spend_avoided": None,
        "time_to_detect_seconds": None,
        "blocking_reasons": (["pesquisa_incompleta"] if coverage["status"] != "complete" else [])
        + (["sem_razao_financeira_completa"] if forecast["status"] != "calibracao_verificada" else []),
    }
