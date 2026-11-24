"""Native staffing and daily salary references, independent of acquisition costs."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import paths
from engine_detail import _normalize, validate_operational_requirements

SOURCE = "game_staff_salary"
FILENAME = "staff_observations.json"
MAX_AGE = 900
ROLES = {"pilots": ("pilot_main", "pilots", "pilotos"),
         "cabin_crew": ("crew_main", "crew", "tripulacao"),
         "engineers": ("engineer_main", "engineers", "engenheiros"),
         "technicians": ("tech_main", "technicians", "tecnicos")}
MAX_VALUE = 2**53 - 1

STAFF_JS = r"""
const roots = document.querySelectorAll('#popup');
if (roots.length !== 1 || !window.jQuery || window.jQuery.active !== 0) return null;
const root = roots[0];
if (!root.getClientRects().length || root.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ').trim().toLowerCase();
if (!/\b(daily salary|salario diario)\b/.test(norm(root.innerText))) return null;
const result = {};
for (const id of ['pilot_main', 'crew_main', 'engineer_main', 'tech_main']) {
    const matches = root.querySelectorAll('#' + id);
    if (matches.length !== 1) return null;
    const card = matches[0];
    const header = card.previousElementSibling;
    if (!card.getClientRects().length || !header || !header.getClientRects().length ||
        !header.classList.contains('font-weight-bold')) return null;
    const rows = [...card.querySelectorAll('table tr')].filter(row => row.getClientRects().length &&
        ['salary', 'salario'].includes(norm(row.children[0]?.innerText)));
    if (rows.length !== 1 || rows[0].children.length !== 2) return null;
    result[id] = {header: header.innerText.trim(), salary: rows[0].children[1].innerText.trim()};
}
return result;
"""


def _amount(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]{0,2}(?:\.[0-9]{3})+)", raw):
        return None
    digits = raw.replace(",", "").replace(".", "")
    return int(digits) if len(digits) <= 16 and int(digits) <= MAX_VALUE else None


def validate_staff(raw):
    if not isinstance(raw, dict) or raw.keys() != ROLES.keys():
        return None
    result = {}
    for role, entry in raw.items():
        if not isinstance(entry, dict) or entry.keys() != {"count", "daily_rate", "daily_total"}:
            return None
        if any(type(value) is not int or not 0 <= value <= MAX_VALUE for value in entry.values()):
            return None
        if entry["count"] * entry["daily_rate"] != entry["daily_total"]:
            return None
        result[role] = dict(entry)
    return result if sum(row["daily_total"] for row in result.values()) <= MAX_VALUE else None


def parse_staff(raw):
    if not isinstance(raw, dict) or raw.keys() != {labels[0] for labels in ROLES.values()}:
        return None
    result = {}
    for role, (key, *labels) in ROLES.items():
        entry = raw[key]
        if not isinstance(entry, dict) or not isinstance(entry.get("header"), str):
            return None
        header = _normalize(entry["header"]).split(maxsplit=1)
        if len(header) != 2 or header[1] not in labels:
            return None
        salary = entry.get("salary")
        match = re.fullmatch(r"\$\s*([0-9,.]+)\s*/\s*\$\s*([0-9,.]+)", salary) if isinstance(salary, str) else None
        if match is None:
            return None
        result[role] = {"count": _amount(header[0]), "daily_rate": _amount(match[1]),
                        "daily_total": _amount(match[2])}
    return validate_staff(result)


def staff_snapshot(path: Path | None = None, *, now=None):
    path = path if path is not None else paths.current().data / FILENAME
    now = time.time() if now is None else now
    unknown = {"status": "unverified", "staff": None}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return unknown
    if not isinstance(saved, dict) or saved.get("source") != SOURCE:
        return unknown
    stamp = saved.get("observed_at")
    staff = validate_staff(saved.get("staff"))
    if staff is None or type(stamp) not in (int, float) or not 0 < stamp <= now or now - stamp > MAX_AGE:
        return unknown
    return {"status": "observed", "source": SOURCE, "observed_at": stamp, "staff": staff}


def collect_staff_observations(bot, *, path=None):
    from game_observations import _stable_read

    if getattr(bot, "stopping", False):
        return False
    path = Path(path) if path is not None else paths.current().data / FILENAME
    paths.write_atomic(path, "{}", private=True)
    started = time.time()
    try:
        bot.open_popup("staff.php?nav=1", "Staff", "nav_staff")
        staff = parse_staff(_stable_read(bot, STAFF_JS))
    finally:
        bot.close_popup(quiet=True)
    if staff is None or getattr(bot, "stopping", False) or not 0 <= time.time() - started <= 120:
        return False
    paths.write_atomic(path, json.dumps({"source": SOURCE, "observed_at": int(started), "staff": staff}), private=True)
    return True


def salary_reference(observation, detail, *, now):
    """Hypothetical daily payroll if every displayed requirement is additional."""
    from engine_catalog import MAX_AGE_SECONDS

    if not isinstance(observation, dict) or observation.get("source") != SOURCE or observation.get("status") != "observed":
        return None
    if not isinstance(detail, dict) or detail.get("model_identity_verified") is not True:
        return None
    stamp, detail_stamp = observation.get("observed_at"), detail.get("observed_at")
    if any(type(value) not in (int, float) or not 0 < value <= now or now - value > age
           for value, age in ((stamp, MAX_AGE), (detail_stamp, MAX_AGE_SECONDS))):
        return None
    staff = validate_staff(observation.get("staff"))
    requirements = validate_operational_requirements(detail.get("operational_requirements"))
    if staff is None or requirements is None:
        return None
    amount = sum(requirements[role] * staff[role]["daily_rate"] for role in ROLES)
    if amount > MAX_VALUE:
        return None
    return {"source": SOURCE, "observed_at": stamp,
            "expires_at": min(stamp + MAX_AGE, detail_stamp + MAX_AGE_SECONDS),
            "daily_salary_if_all_additional": amount, "incremental_cost_verified": False}
