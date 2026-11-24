"""Independent historical company-wide cash flow from the native 24h summary."""
from __future__ import annotations

import json
import time
from pathlib import Path

import paths

SOURCE = "game_transaction_summary"
FILENAME = "finance_observations.json"
MAX_AGE = 900
FIELDS = ("expenses", "income", "result", "fuel_expenses", "quota_expenses",
          "route_fees", "aircraft_orders", "hubs", "ticket_income")

SUMMARY_JS = r"""
const roots = document.querySelectorAll('#financeAction #transactionSummaryContainer');
if (roots.length !== 1 || !window.jQuery || window.jQuery.active !== 0) return null;
const root = roots[0];
if (!root.getClientRects().length || root.children.length !== 1 ||
    root.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const row = root.firstElementChild;
if (!row.classList.contains('row') || row.children.length !== 10) return null;
const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ').trim().toLowerCase();
const title = row.children[0].lastElementChild;
if (!title || !['summary for the last 24 hours', 'resumo das ultimas 24 horas',
    'resumo para as ultimas 24 horas'].includes(norm(title.textContent))) return null;
const labels = {
    'expenses':'expenses', 'despesas':'expenses', 'income':'income', 'receitas':'income',
    'result':'result', 'resultado':'result', 'fuel expenses':'fuel_expenses',
    'despesas com combustivel':'fuel_expenses', 'quota expenses':'quota_expenses',
    'despesas com cotas':'quota_expenses', 'route fees':'route_fees', 'taxas de rota':'route_fees',
    'a/c orders':'aircraft_orders', 'encomendas de aeronaves':'aircraft_orders',
    'hubs':'hubs', 'ticket income':'ticket_income', 'receita de passagens':'ticket_income'
};
const values = {};
for (const cell of [...row.children].slice(1)) {
    const label = cell.firstElementChild;
    const value = cell.lastElementChild;
    if (!label || !value || label === value || label.tagName !== 'SPAN' ||
        !label.classList.contains('text-secondary')) return null;
    const key = labels[norm(label.textContent)];
    if (!key || Object.hasOwn(values, key)) return null;
    const raw = String(value.textContent || '').trim();
    const match = raw.match(/^(?:\$\s*(-?)\s*|(-)\s*\$\s*)(0|[1-9]\d{0,2}(?:,\d{3})*|[1-9]\d{0,2}(?:\.\d{3})*)$/);
    if (!match || (key !== 'result' && (match[1] || match[2]))) return null;
    const amount = Number(match[3].replace(/[,.]/g, '')) * (match[1] || match[2] ? -1 : 1);
    if (!Number.isSafeInteger(amount)) return null;
    values[key] = amount;
}
return {window_hours:24, ...values};
"""


def validate_summary(raw):
    if not isinstance(raw, dict) or type(raw.get("window_hours")) is not int or raw["window_hours"] != 24:
        return None
    if any(type(raw.get(key)) is not int or abs(raw[key]) > 2**53 - 1
           or (key != "result" and raw[key] < 0) for key in FIELDS):
        return None
    if (raw["income"] - raw["expenses"] != raw["result"]
            or sum(raw[key] for key in FIELDS[3:8]) > raw["expenses"]
            or raw["ticket_income"] > raw["income"]):
        return None
    return {"window_hours": 24, **{key: raw[key] for key in FIELDS}}


def finance_snapshot(path: Path | None = None, *, now: float | None = None) -> dict:
    profile = paths.current()
    path = path if path is not None else profile.data / FILENAME
    now = time.time() if now is None else now
    unknown = {"status": "unverified", "historical_only": True, "summary": None}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return unknown
    if (not isinstance(saved, dict) or saved.get("source") != SOURCE
            or saved.get("profile_id") != profile.label):
        return unknown
    stamp = saved.get("observed_at")
    if type(stamp) not in (int, float) or not 0 < stamp <= now or now - stamp > MAX_AGE:
        return unknown
    summary = validate_summary(saved.get("summary"))
    if summary is None:
        return unknown
    return {**unknown, "status": "observed", "source": SOURCE, "profile_id": profile.label,
            "observed_at": stamp, "summary": summary}


def collect_finance_observations(bot, *, path=None) -> bool:
    from game_observations import _stable_read

    if getattr(bot, "stopping", False):
        return False
    profile = paths.current()
    path = Path(path) if path is not None else profile.data / FILENAME
    paths.write_atomic(path, "{}", private=True)
    started = time.time()
    try:
        bot.open_popup("finances.php", "Finances", "nav_finances")
        bot.ajax("transactions.php?mode=summary", "transactionSummaryContainer")
        summary = validate_summary(_stable_read(bot, SUMMARY_JS))
    finally:
        bot.close_popup(quiet=True)
    if summary is None or getattr(bot, "stopping", False) or not 0 <= time.time() - started <= 120:
        return False
    paths.write_atomic(path, json.dumps({"source": SOURCE, "profile_id": profile.label,
                                        "observed_at": int(started), "summary": summary}), private=True)
    return True
