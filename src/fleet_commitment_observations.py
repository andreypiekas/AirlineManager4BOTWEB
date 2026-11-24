"""Read-only passenger hangar and native fleet status observations for A4."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import paths

SOURCE = "game_hangar_and_fleet_status"
MAX_AGE = 900
MAX_WINDOW = 120
FILENAME = "fleet_commitment_observations.json"
_ROW_ID = re.compile(r"[1-9][0-9]{0,13}")

_DOM_HELPERS = r"""
const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ').trim().toLowerCase();
const count = value => {
    const text = String(value || '').trim();
    if (!/^(?:0|[1-9]\d{0,5}|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{0,2}(?:\.\d{3})+)$/.test(text)) return null;
    const number = Number(text.replace(/[.,]/g, ''));
    return Number.isSafeInteger(number) && number <= 1000000 ? number : null;
};
const rootFor = selector => {
    const roots = document.querySelectorAll(selector);
    if (roots.length !== 1 || !window.jQuery || window.jQuery.active !== 0 ||
        roots[0].querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
    return roots[0];
};
"""

PASSENGER_HANGAR_JS = _DOM_HELPERS + r"""
const root = rootFor('#maintAction');
if (!root) return null;
const pax = [...root.querySelectorAll('button.active')].filter(button =>
    /Ajax\('hangars\.php\?type=pax','maintAction',this\)/.test(button.getAttribute('onclick') || ''));
const capacity = root.querySelectorAll('.xl-text span');
const tables = root.querySelectorAll('table');
if (pax.length !== 1 || capacity.length !== 1 || tables.length !== 1 || tables[0].rows.length !== 2) return null;
const [occupied, available] = tables[0].rows;
if (occupied.cells.length !== 3 || available.cells.length !== 3 ||
    !['pax a/c', 'aeronaves pax', 'aeronaves de passageiros'].includes(norm(occupied.cells[1].textContent)) ||
    !['available hangar slots', 'vagas disponiveis no hangar', 'vagas de hangar disponiveis'].includes(norm(available.cells[1].textContent))) return null;
return {capacity: count(capacity[0].textContent), occupied: count(occupied.cells[2].textContent),
        free: count(available.cells[2].textContent)};
"""


def _fleet_list_js(kind):
    return _DOM_HELPERS + "const kind = " + json.dumps(kind) + r""";
const root = rootFor('#routesContainer');
if (!root) return null;
const buttons = [...document.querySelectorAll('#routeAction .listBtns')].filter(button =>
    (button.getAttribute('onclick') || '').includes(`Ajax('fleet_${kind}.php','routesContainer',this)`));
if (buttons.length !== 1) return null;
const counter = String(buttons[0].textContent || '').match(/\(([0-9.,]+)\)\s*$/);
const children = [...root.children].filter(child => child.tagName !== 'SCRIPT');
const heading = children.shift();
const headingMatch = heading && norm(heading.textContent).match(/^([0-9.,]+) (?:aircraft|aeronaves?)$/);
if (!counter || !headingMatch) return null;
const total = count(counter[1]);
if (total === null || count(headingMatch[1]) !== total) return null;
if (total === 0) {
    const emptyLabels = kind === 'parked'
        ? ['there are no parked aircraft', 'nao ha aeronaves estacionadas']
        : ['there are no pending aircraft', 'nao ha aeronaves pendentes'];
    if (children.length !== 1 || !emptyLabels.includes(norm(children[0].textContent))) return null;
    return {total, rows: []};
}
const prefix = kind === 'parked' ? 'routeMainParkedList' : 'routeMainPendingList';
if (children.length !== total || children.some(row => !row.id.startsWith(prefix))) return null;
return {total, rows: children.map(row => ({id: row.id.slice(prefix.length),
    status: kind === 'pending' && /^(?:pending maintenance|manutencao pendente)\s*:/.test(
        norm(String(row.innerText || '').trim().split('\n').at(-1))) ? 'maintenance' : 'unclassified'}))};
"""


PENDING_FLEET_JS = _fleet_list_js("pending")
PARKED_FLEET_JS = _fleet_list_js("parked")


def _count(value):
    return type(value) is int and 0 <= value <= 1000000


def _hangar(value):
    if (not isinstance(value, dict) or any(not _count(value.get(key)) for key in ("capacity", "occupied", "free"))
            or value["occupied"] + value["free"] != value["capacity"]):
        return None
    return {key: value[key] for key in ("capacity", "occupied", "free")}


def _fleet_list(value):
    if not isinstance(value, dict) or not _count(value.get("total")) or not isinstance(value.get("rows"), list):
        return None
    rows = value["rows"]
    if len(rows) != value["total"] or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) or not _ROW_ID.fullmatch(row["id"])
        or row.get("status") not in ("maintenance", "unclassified") for row in rows
    ) or len({row["id"] for row in rows}) != len(rows):
        return None
    maintenance = sum(row["status"] == "maintenance" for row in rows)
    return {"total": len(rows), "maintenance": maintenance, "unclassified": len(rows) - maintenance}


def observations_snapshot(path: Path | None = None, *, now: float | None = None) -> dict:
    """Publish only current aggregate observations. Financial obligations remain unverified."""
    path = path if path is not None else paths.current().data / FILENAME
    now = time.time() if now is None else now
    result = {"status": "unverified", "passenger_hangar": None, "pending_fleet": None, "parked_count": None,
              "pending_orders_verified": False, "commitments_verified": False}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(saved, dict) or saved.get("source") != SOURCE:
        return result
    stamp = saved.get("observed_at")
    if type(stamp) not in (int, float) or not 0 < stamp <= now or now - stamp > MAX_AGE:
        return result
    hangar = _hangar(saved.get("passenger_hangar"))
    pending = saved.get("pending_fleet")
    if (not isinstance(pending, dict) or any(not _count(pending.get(key)) for key in ("total", "maintenance", "unclassified"))
            or pending["total"] != pending["maintenance"] + pending["unclassified"]):
        pending = None
    parked = saved.get("parked_count")
    parked = parked if _count(parked) else None
    if hangar is None and pending is None and parked is None:
        return result
    return {**result, "status": "observed" if all(value is not None for value in (hangar, pending, parked)) else "partial",
            "source": SOURCE, "observed_at": stamp, "passenger_hangar": hangar,
            "pending_fleet": ({key: pending[key] for key in ("total", "maintenance", "unclassified")} if pending else None),
            "parked_count": parked}


def collect_fleet_commitment_observations(bot, *, path=None):
    """Refresh native fragments without maintenance, route, or purchase mutations."""
    from game_observations import _stable_read

    if getattr(bot, "stopping", False):
        return False
    path = Path(path) if path is not None else paths.current().data / FILENAME
    paths.write_atomic(path, "{}")
    started = time.time()
    try:
        bot.open_popup("maintenance_main.php", "Maintenance", "nav_maintenance")
        bot.ajax("hangars.php?type=pax", "maintAction")
        hangar = _hangar(_stable_read(bot, PASSENGER_HANGAR_JS))
    finally:
        bot.close_popup(quiet=True)
    if getattr(bot, "stopping", False):
        return False
    try:
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("fleet_pending.php", "routesContainer")
        pending = _fleet_list(_stable_read(bot, PENDING_FLEET_JS))
        if getattr(bot, "stopping", False):
            return False
        bot.ajax("fleet_parked.php", "routesContainer")
        parked = _fleet_list(_stable_read(bot, PARKED_FLEET_JS))
    finally:
        bot.close_popup(quiet=True)
    finished = time.time()
    if getattr(bot, "stopping", False) or not 0 <= finished - started <= MAX_WINDOW:
        return False
    paths.write_atomic(path, json.dumps({"source": SOURCE, "observed_at": int(started), "passenger_hangar": hangar,
                                        "pending_fleet": pending, "parked_count": parked["total"] if parked else None}))
    return all(value is not None for value in (hangar, pending, parked))
