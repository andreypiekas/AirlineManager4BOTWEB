"""Read-only passenger hangar and native fleet status observations for A4."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import paths

SOURCE = "game_hangar_and_fleet_status"
MAX_AGE = 900
MAX_WINDOW = 120
FILENAME = "fleet_commitment_observations.json"
_ROW_ID = re.compile(r"[1-9][0-9]{0,13}")
_OBSERVATION_ID = re.compile(r"[0-9a-f]{32}")

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
const quotes = {};
for (const amount of [1, 10]) {
    const controls = [...root.querySelectorAll('button[onclick]')].filter(button =>
        (button.getAttribute('onclick') || '').includes(`Ajax('hangars.php?mode=upgrade&amount=${amount}&type=','runme')`));
    if (controls.length !== 1) continue;
    const button = controls[0];
    if (!button.getClientRects().length || button.disabled || button.classList.contains('not-active') || button.classList.contains('disabled') ||
        button.getAttribute('aria-disabled') === 'true' || !button.classList.contains('btn-success')) continue;
    const price = String(button.textContent || '').trim();
    if (!/^\$[1-9]\d{0,2}(?:,\d{3})+$|^\$[1-9]\d{0,2}$/.test(price)) continue;
    const cost = Number(price.slice(1).replace(/,/g, ''));
    if (!Number.isSafeInteger(cost)) continue;
    const lines = String(button.parentElement?.innerText || '').trim().split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const labels = [`increase capacity by +${amount} a/c`, `aumentar capacidade em +${amount} aeronaves`,
        `aumentar a capacidade em +${amount} aeronaves`];
    if (![2, 3].includes(lines.length) || !labels.includes(norm(lines[0])) || lines.at(-1) !== price) continue;
    const duration = lines.length === 3 ? lines[1].match(/^(\d{2,5}):([0-5]\d):([0-5]\d)$/) : null;
    if (lines.length === 3 && !duration) continue;
    quotes[String(amount)] = {cost, duration_seconds: duration ?
        Number(duration[1]) * 3600 + Number(duration[2]) * 60 + Number(duration[3]) : null};
}
const result = {capacity: count(capacity[0].textContent), occupied: count(occupied.cells[2].textContent),
                free: count(available.cells[2].textContent)};
if (Object.keys(quotes).length) result.upgrade_quotes = quotes;
return result;
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
const classify = row => {
    if (kind !== 'pending') return 'unclassified';
    const states = [];
    for (const cell of row.querySelectorAll('.row.p-2 > .col-6')) {
        if (cell.querySelectorAll('span.hasCountdown').length !== 1) continue;
        for (const node of cell.childNodes) {
            if (node.nodeType !== 3) continue;
            const label = norm(node.textContent);
            if (['pending maintenance:', 'manutencao pendente:'].includes(label)) states.push('maintenance');
            if (['pending delivery:', 'entrega pendente:'].includes(label)) states.push('delivery');
        }
    }
    return states.length === 1 ? states[0] : 'unclassified';
};
return {total, rows: children.map(row => ({id: row.id.slice(prefix.length), status: classify(row)}))};
"""


PENDING_FLEET_JS = _fleet_list_js("pending")
PARKED_FLEET_JS = _fleet_list_js("parked")


def _count(value):
    return type(value) is int and 0 <= value <= 1000000


def _hangar(value):
    if (not isinstance(value, dict) or any(not _count(value.get(key)) for key in ("capacity", "occupied", "free"))
            or value["occupied"] + value["free"] != value["capacity"]):
        return None
    result = {key: value[key] for key in ("capacity", "occupied", "free")}
    raw_quotes = value.get("upgrade_quotes")
    quotes = {}
    if isinstance(raw_quotes, dict):
        for amount in ("1", "10"):
            quote = raw_quotes.get(amount)
            if not isinstance(quote, dict):
                continue
            cost = quote.get("cost")
            duration = quote.get("duration_seconds")
            if (type(cost) is not int or not 0 < cost <= 2**53 - 1
                    or (duration is not None and (type(duration) is not int or not 0 <= duration <= 359999999))):
                continue
            quotes[amount] = {"cost": cost, "duration_seconds": duration}
    if quotes:
        result["upgrade_quotes"] = quotes
    return result


def _fleet_list(value):
    if not isinstance(value, dict) or not _count(value.get("total")) or not isinstance(value.get("rows"), list):
        return None
    rows = value["rows"]
    if len(rows) != value["total"] or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) or not _ROW_ID.fullmatch(row["id"])
        or row.get("status") not in ("maintenance", "delivery", "unclassified") for row in rows
    ) or len({row["id"] for row in rows}) != len(rows):
        return None
    maintenance = sum(row["status"] == "maintenance" for row in rows)
    delivery = sum(row["status"] == "delivery" for row in rows)
    return {"total": len(rows), "maintenance": maintenance, "delivery": delivery,
            "unclassified": len(rows) - maintenance - delivery}


def _pending_counts(value):
    if not isinstance(value, dict):
        return None
    keys = ("total", "maintenance", "unclassified")
    # Older caches did not distinguish deliveries. Keep their counts usable
    # without reporting an observed zero for a classification not collected.
    if "delivery" in value:
        keys += ("delivery",)
    if any(not _count(value.get(key)) for key in keys):
        return None
    if value["total"] != sum(value[key] for key in keys[1:]):
        return None
    return {key: value[key] for key in keys}


def native_identity_proof(evidence, aircraft, counts, *, started_at, now):
    """Compare ephemeral native row identities with the certified roster partition."""
    if not isinstance(evidence, dict):
        return {}
    observation_id = evidence.get("observation_id")
    start, end = evidence.get("observed_at"), evidence.get("observed_until")
    if (not isinstance(observation_id, str) or not _OBSERVATION_ID.fullmatch(observation_id)
            or type(start) is not int or type(end) is not int
            or not started_at <= start <= end <= now or now - start > MAX_WINDOW):
        return {}
    pending, parked = evidence.get("pending_ids"), evidence.get("parked_ids")
    if not all(isinstance(ids, frozenset) and all(isinstance(identity, str) and _ROW_ID.fullmatch(identity)
               for identity in ids) for ids in (pending, parked)):
        return {}
    unrouted = {identity for identity, row in aircraft.items() if row["route_id"] == 0}
    matched = (len(pending) == counts["pending"] and len(parked) == counts["parked"]
               and not pending & parked and pending | parked == unrouted)
    return {"native_observation_id": observation_id,
            "native_identity_status": "matched" if matched else "different"}


def invalidate_observations(path: Path | None = None) -> None:
    """Withdraw native fleet and hangar evidence before a refresh or mutation."""
    path = Path(path) if path is not None else paths.current().data / FILENAME
    if path.exists():
        paths.write_atomic(path, "{}")


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
    end = saved.get("observed_until")
    if "observed_until" in saved and (type(end) not in (int, float) or not stamp <= end <= now
                                     or end - stamp > MAX_WINDOW):
        return result
    hangar = _hangar(saved.get("passenger_hangar"))
    pending = _pending_counts(saved.get("pending_fleet"))
    parked = saved.get("parked_count")
    parked = parked if _count(parked) else None
    if hangar is None and pending is None and parked is None:
        return result
    return {**result, "status": "observed" if all(value is not None for value in (hangar, pending, parked)) else "partial",
            "source": SOURCE, "observed_at": stamp, "passenger_hangar": hangar,
            **({"observed_until": end} if end is not None else {}),
            **({"observation_id": saved["observation_id"]} if isinstance(saved.get("observation_id"), str)
               and _OBSERVATION_ID.fullmatch(saved["observation_id"]) else {}),
            "pending_fleet": pending,
            "parked_count": parked}


def reconcile_route_coverage(observations: dict, coverage: dict | None, *, now: float) -> dict:
    """Compare current native lists with the independently audited roster counts."""
    result = {"status": "unverified", "identity_status": "unverified", "native_parked_count": None, "native_pending_count": None,
              "audited_parked_count": None, "audited_pending_count": None,
              "unrouted_or_pending_count": None}

    def current(stamp):
        return type(stamp) in (int, float) and 0 < stamp <= now and now - stamp <= MAX_AGE

    stamp = observations.get("observed_at")
    end = observations.get("observed_until")
    native_current = (observations.get("source") == SOURCE and observations.get("status") in ("observed", "partial")
                      and current(stamp) and ("observed_until" not in observations or
                          (current(end) and stamp <= end and end - stamp <= MAX_WINDOW)))
    parked = observations.get("parked_count")
    pending = _pending_counts(observations.get("pending_fleet"))
    if native_current and _count(parked):
        result["native_parked_count"] = parked
        result["status"] = "native_only"
    if native_current and pending is not None:
        result["native_pending_count"] = pending["total"]
        result["status"] = "native_only"
    if not isinstance(coverage, dict) or coverage.get("source") != "game_roster_and_route_audit":
        return result
    keys = ("total", "routes", "parked", "pending")
    audited_at = coverage.get("observed_at")
    roster_at = coverage.get("roster_observed_at")
    if (not all(_count(coverage.get(key)) for key in keys)
            or coverage["total"] != sum(coverage[key] for key in keys[1:])
            or not current(audited_at) or not current(roster_at) or roster_at > audited_at):
        return result
    result.update(audited_parked_count=coverage["parked"], audited_pending_count=coverage["pending"],
                  unrouted_or_pending_count=coverage["total"] - coverage["routes"])
    if result["native_parked_count"] is not None and result["native_pending_count"] is not None:
        # The audit confirms the same roster and counts at both boundaries.
        # A bounded native read inside that interval can be compared to its
        # final boundary even when a complete paginated audit takes longer.
        bracketed = (end is not None and roster_at <= stamp <= end <= audited_at
                     and audited_at - stamp <= MAX_WINDOW)
        close = max(end if end is not None else stamp, audited_at) - min(stamp, roster_at) <= MAX_WINDOW
        if not (bracketed or close):
            result["status"] = "not_contemporaneous"
        else:
            result["status"] = ("matched" if parked == coverage["parked"] and pending["total"] == coverage["pending"]
                                else "different")
            observation_id = observations.get("observation_id")
            identity_status = coverage.get("native_identity_status")
            if (bracketed and isinstance(observation_id, str) and _OBSERVATION_ID.fullmatch(observation_id)
                    and observation_id == coverage.get("native_observation_id")
                    and identity_status in ("matched", "different")):
                result["identity_status"] = ("different" if result["status"] == "different" else identity_status)
    elif result["status"] == "unverified":
        result["status"] = "audit_only"
    else:
        result["status"] = "partial"
    return result


def collect_fleet_commitment_observations(bot, *, path=None, identity_evidence=None):
    """Refresh native fragments without maintenance, route, or purchase mutations."""
    from game_observations import _stable_read

    if identity_evidence is not None:
        identity_evidence.clear()
    if getattr(bot, "stopping", False):
        return False
    path = Path(path) if path is not None else paths.current().data / FILENAME
    invalidate_observations(path)
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
        pending_rows = _stable_read(bot, PENDING_FLEET_JS)
        pending = _fleet_list(pending_rows)
        if getattr(bot, "stopping", False):
            return False
        bot.ajax("fleet_parked.php", "routesContainer")
        parked_rows = _stable_read(bot, PARKED_FLEET_JS)
        parked = _fleet_list(parked_rows)
    finally:
        bot.close_popup(quiet=True)
    finished = time.time()
    if getattr(bot, "stopping", False) or not 0 <= finished - started <= MAX_WINDOW:
        return False
    observation = {"observation_id": uuid.uuid4().hex, "observed_at": int(started), "observed_until": int(finished)}
    paths.write_atomic(path, json.dumps({"source": SOURCE, **observation,
                                        "passenger_hangar": hangar,
                                        "pending_fleet": pending, "parked_count": parked["total"] if parked else None}))
    if identity_evidence is not None and pending is not None and parked is not None:
        identity_evidence.update(observation, pending_ids=frozenset(row["id"] for row in pending_rows["rows"]),
                                 parked_ids=frozenset(row["id"] for row in parked_rows["rows"]))
    return all(value is not None for value in (hangar, pending, parked))
