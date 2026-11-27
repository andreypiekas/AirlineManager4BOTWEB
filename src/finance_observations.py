"""Read the native finance summary and transaction history without altering the account."""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

from selenium.common.exceptions import WebDriverException

import paths
from fleet_commitment_observations import MAX_WINDOW, _fleet_list
from helpers import game_whole_number

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

TRANSACTIONS_JS = r"""
const roots = document.querySelectorAll('#financeAction #transactionContainer');
if (roots.length !== 1 || !window.jQuery || window.jQuery.active !== 0) return null;
const root = roots[0];
const tables = root.querySelectorAll('table');
if (!root.getClientRects().length || tables.length !== 1 ||
    root.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const rows = [...tables[0].rows];
if (!rows.length || rows.length > 100) return null;
const transactions = [];
for (const row of rows) {
    const debit = row.classList.contains('trans-expense');
    if (debit === row.classList.contains('trans-income') || row.cells.length !== 3) return null;
    transactions.push({debit, label: row.cells[1].textContent.trim(), amount: row.cells[2].textContent.trim()});
}
return transactions;
"""

_REGISTRATION = re.compile(r"[A-Z0-9][A-Z0-9-]{0,15}")
_MAINTENANCE_DEBIT = re.compile(r"([A-Z0-9][A-Z0-9-]{0,15}) (Repair|A-Check)", re.IGNORECASE | re.ASCII)


def _history_debits(rows):
    if not isinstance(rows, list) or not 0 < len(rows) <= 100:
        return None
    debits = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("debit")) is not bool
                or not isinstance(row.get("label"), str) or not 0 < len(row["label"]) <= 160
                or not isinstance(row.get("amount"), str) or len(row["amount"]) > 24):
            return None
        raw = row["amount"]
        if row["debit"] != raw.startswith("-"):
            return None
        amount = game_whole_number(raw.removeprefix("-"), currency=True)
        if amount is None or amount > 2**53 - 1 or (row["debit"] and amount == 0):
            return None
        if row["debit"]:
            debits.append((row["label"], amount))
    return debits


def read_aircraft_cash_observation(bot, pending: dict | None, checkout_amount: int) -> dict:
    """Read recent debits and pending aircraft for the authenticated preview, without asserting settlement."""
    from game_observations import _stable_read

    profile_id = paths.current().label
    company_id = bot._observation_company_id
    started = time.time()
    if (pending is not None and (pending["company_id"] != company_id or pending["profile_id"] != profile_id
            or not 0 <= started - pending["observed_until"] <= MAX_WINDOW)):
        pending = None

    history = summary = None
    try:
        if not bot.stopping:
            try:
                bot.open_popup("finances.php", "Finances", "nav_finances")
                history = _stable_read(bot, TRANSACTIONS_JS)
                if not bot.stopping:
                    bot.ajax("transactions.php?mode=summary", "transactionSummaryContainer")
                    summary = validate_summary(_stable_read(bot, SUMMARY_JS))
            finally:
                bot.close_popup(quiet=True)
    except (RuntimeError, WebDriverException):
        pass

    finished = time.time()
    if (bot.stopping or bot._observation_company_id != company_id or paths.current().label != profile_id
            or not 0 <= finished - started <= MAX_WINDOW):
        pending = history = summary = None
    if pending is not None and not 0 <= finished - pending["observed_at"] <= MAX_WINDOW:
        pending = None

    counts = _fleet_list(pending["pending"]) if pending is not None else None
    debits = _history_debits(history)
    maintenance = None
    if counts is not None:
        rows = pending["pending"]["rows"]
        registrations = Counter(row["registration"] for row in rows if isinstance(row.get("registration"), str))
        matches = {}
        for row in rows:
            registration = row.get("registration")
            if (row["status"] == "maintenance" and isinstance(registration, str)
                    and registrations[registration] == 1 and _REGISTRATION.fullmatch(registration)):
                matches[registration] = []
        for label, amount in debits or ():
            match = _MAINTENANCE_DEBIT.fullmatch(label)
            if match and match[1].upper() in matches:
                matches[match[1].upper()].append({"type": match[2].lower(), "amount_usd": amount})
        maintenance = [{"registration": registration, "recent_debits": charges if debits is not None else None}
                       for registration, charges in matches.items()]

    sources = (counts, debits, summary)
    status = "observed" if all(value is not None for value in sources) else "partial"
    if all(value is None for value in sources):
        status = "unavailable"
    return {
        "status": status, "pending_counts": counts, "pending_maintenance": maintenance,
        "recent_transaction_count": len(history) if debits is not None else None,
        "recent_debit_count": len(debits) if debits is not None else None,
        "recent_debits_equal_to_checkout": sum(amount == checkout_amount for _, amount in debits)
        if debits is not None else None,
        "aircraft_order_expenses_24h": summary["aircraft_orders"] if summary is not None else None,
        "other_expenses_24h": summary["expenses"] - sum(summary[key] for key in FIELDS[3:8])
        if summary is not None else None,
        "receipt_verified": False, "cash_commitments_verified": False,
    }


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
