"""Independent audit of aircraft operating to or from company hubs."""
from __future__ import annotations

import re
import time
from collections import defaultdict

from selenium.common.exceptions import TimeoutException

from airport_catalog import by_code
from owned_delivery_coverage import MANAGED_HUB_IDS_JS, native_ids, open_managed_hubs

MAX_WINDOW = 120

HUB_OPERATIONS_JS = r"""
const containers = document.querySelectorAll('#popup #popContent #hubDetail');
if (containers.length !== 2 || containers[1].parentElement !== containers[0] ||
    !window.jQuery || window.jQuery.active !== 0) return null;
const detail = containers[1];
if (detail.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const code = detail.querySelectorAll(':scope > .row:first-child > div');
const airport = code.length === 2 && code[1].textContent.trim().match(/^([A-Z]{4})\/([A-Z]{3})$/);
const lounge = [...detail.querySelectorAll('[onclick]')].map(node =>
    node.getAttribute('onclick').match(/Ajax\('hubs_lounge\.php\?id=([1-9][0-9]{0,13})','hubDetail',this\)/)
).filter(Boolean);
const headings = [...detail.querySelectorAll('div.text-center.font-weight-bold')].filter(node =>
    node.textContent.trim() === 'Operations to/from hub');
const table = headings.length === 1 && headings[0].nextElementSibling;
if (!airport || lounge.length !== 1 || !table || !table.matches('table.table') ||
    table.tBodies.length !== 1) return null;
const rows = [];
for (const row of table.tBodies[0].rows) {
    if (row.cells.length !== 3) return null;
    const pair = [...row.cells[1].childNodes].filter(node => node.nodeType === 3 && node.textContent.trim());
    const airports = pair.length === 1 && pair[0].textContent.trim().match(/^([A-Z]{3,4})-([A-Z]{3,4})$/);
    const links = row.cells[2].querySelectorAll('a[onclick]');
    const aircraft = links.length === 1 && links[0].getAttribute('onclick').match(
        /Ajax\('fleet_details\.php\?id=([1-9][0-9]{0,13})&ret=hub','fleetHubDetailsAction'\)/);
    if (!airports || !aircraft) return null;
    rows.push({aircraft_id: aircraft[1], airports: airports.slice(1)});
}
return {management_id: lounge[0][1], icao: airport[1], iata: airport[2], rows};
"""


def _valid_panel(panel, management_id):
    if (not isinstance(panel, dict) or panel.get("management_id") != management_id
            or not isinstance(panel.get("icao"), str) or not re.fullmatch("[A-Z]{4}", panel["icao"])
            or not isinstance(panel.get("iata"), str) or not re.fullmatch("[A-Z]{3}", panel["iata"])
            or not isinstance(panel.get("rows"), list)):
        return False
    rows = panel["rows"]
    if not rows:
        return True
    return all(
        isinstance(row, dict) and isinstance(row.get("airports"), list) and len(row["airports"]) == 2
        and all(isinstance(code, str) and re.fullmatch("[A-Z]{3,4}", code) for code in row["airports"])
        and row["airports"][0] != row["airports"][1] for row in rows
    ) and bool(native_ids([row.get("aircraft_id") for row in rows]))


def collect_hub_operations(bot):
    """Read the native panels between two independent reads of the managed hub list."""
    from game_observations import _stable_read

    started_at = time.time()
    panels = []
    managed = refreshed = None
    try:
        open_managed_hubs(bot)
        managed = native_ids(_stable_read(bot, MANAGED_HUB_IDS_JS))
        for management_id in sorted(managed or (), key=int):
            remaining = MAX_WINDOW - (time.time() - started_at)
            if bot.stopping or remaining <= 1:
                break
            bot.ajax(f"hub_details.php?id={management_id}", "hubDetail", timeout=min(10, remaining))
            panel = _stable_read(bot, HUB_OPERATIONS_JS)
            if (not _valid_panel(panel, management_id) and time.time() - started_at < MAX_WINDOW - 1
                    and not bot._stop.wait(0.4)):
                panel = _stable_read(bot, HUB_OPERATIONS_JS)
            if _valid_panel(panel, management_id):
                panels.append(panel)
        if managed and len(panels) == len(managed) and not bot.stopping:
            open_managed_hubs(bot)
            refreshed = native_ids(_stable_read(bot, MANAGED_HUB_IDS_JS))
    except TimeoutException:
        pass
    finally:
        bot.close_popup(quiet=True)
    observed_at = time.time()
    return {"source": "game_hub_operations", "started_at": started_at, "observed_at": observed_at,
            "managed_count": len(managed) if managed else None, "panels": panels,
            "enumerated": bool(managed and managed == refreshed and 0 <= observed_at - started_at <= MAX_WINDOW)}


def _pending_status(pending, fleet, cycle_start):
    if fleet["pending"] == 0:
        return set(), set()
    if (not isinstance(pending, dict) or fleet.get("native_identity_status") != "matched"
            or not fleet.get("native_observation_id")
            or fleet["native_observation_id"] != pending.get("observation_id")
            or type(pending.get("observed_at")) is not int or type(pending.get("observed_until")) is not int
            or not cycle_start <= pending["observed_at"] <= pending["observed_until"] <= fleet["observed_at"]):
        return None, set()
    maintenance, pending_ids = pending.get("maintenance_ids"), pending.get("pending_ids")
    unknown = pending.get("unclassified_pending_ids")
    if not (all(isinstance(ids, frozenset) for ids in (maintenance, unknown, pending_ids))
            and len(pending_ids) == fleet["pending"] and (maintenance | unknown) <= pending_ids
            and not maintenance & unknown):
        return None, set()
    return maintenance, unknown


def _airport_aliases(panels, owned_hubs):
    """Connect native management panels to selector airports by unique codes."""
    aliases = {}
    seen = set()
    for panel in panels:
        codes = (panel["iata"], panel["icao"])
        matches = [hub["id"] for hub in owned_hubs if hub["code"] in codes]
        if len(matches) != 1 or matches[0] in seen or any(code in aliases for code in codes):
            return None
        seen.add(matches[0])
        aliases.update(dict.fromkeys(codes, matches[0]))
    return aliases


def reconcile_hub_operations(evidence, *, owned_hubs, hub_at, routes, fleet_verified, window):
    """Compare aircraft and undirected endpoints within the confirmed observation cycle."""
    collection = evidence.get("hubs") or {}
    report = {**collection, "source": "game_hub_operations", "status": "incomplete"}
    if not collection.get("enumerated") or not window or not owned_hubs or not fleet_verified:
        return report
    cycle_start, company_confirmed = window
    fleet = routes["fleet_coverage"]
    began, ended = collection["started_at"], collection["observed_at"]
    if not (fleet.get("roster_observation_id")
            and int(cycle_start) <= hub_at <= began
            and int(cycle_start) <= fleet["roster_observed_at"] <= fleet["observed_at"] <= began
            and cycle_start <= began <= ended <= company_confirmed):
        return report
    panels = collection["panels"]
    owned_ids = {hub["id"] for hub in owned_hubs}
    if len(panels) != len(owned_ids):
        return {**report, "status": "different", "reason": "owned_hub_count"}
    aliases = _airport_aliases(panels, owned_hubs)
    if aliases is None:
        return {**report, "reason": "airport_crosswalk"}
    maintenance, unknown = _pending_status(evidence.get("pending"), fleet, int(cycle_start))

    def airport_key(code):
        if code in aliases:
            return aliases[code]
        item = by_code(code)
        # A code outside the verified hub crosswalk cannot add another
        # identity for an owned hub via the offline catalog.
        return item.game_id if item and item.game_id not in owned_ids else f"code:{code}"

    endpoints = {}
    for row in routes["current_relations"]:
        if row.get("game_route_id") == 0:
            continue
        if not row.get("game_route_id") or row.get("route_data_stale"):
            return {**report, "reason": "missing_route_identity"}
        origin, destination = row.get("origin", {}), row.get("destination", {})
        for endpoint in (origin, destination):
            code, airport_id = endpoint.get("code"), endpoint.get("id")
            if not (code or airport_id):
                return {**report, "reason": "missing_route_airport"}
            if code and airport_id:
                # Prefer the route card's own explicit code to the reference catalog.
                if aliases.setdefault(code, airport_id) != airport_id:
                    return {**report, "reason": "airport_crosswalk"}
        endpoints[row["aircraft_id"]] = (origin, destination)
    expected = {aircraft: frozenset(endpoint.get("id") or airport_key(endpoint["code"])
                                    for endpoint in pair) for aircraft, pair in endpoints.items()}
    if len(expected) != fleet["routes"] or any(len(pair) != 2 for pair in expected.values()):
        return {**report, "reason": "route_endpoint_coverage"}

    observed_hubs = defaultdict(set)
    pending_routes = {}
    unclassified = set()
    differences = []
    for panel in panels:
        hub = aliases[panel["iata"]]
        for row in panel["rows"]:
            aircraft = row["aircraft_id"]
            pair = frozenset(airport_key(code) for code in row["airports"])
            observed_hubs[aircraft].add(hub)
            if hub not in pair or len(pair) != 2:
                differences.append({"aircraft_id": aircraft, "hub_id": hub, "kind": "unrelated_airports"})
            elif aircraft in expected:
                if pair != expected[aircraft]:
                    differences.append({"aircraft_id": aircraft, "hub_id": hub, "kind": "different_route"})
            elif maintenance is not None:
                if aircraft in unknown:
                    unclassified.add(aircraft)
                elif aircraft not in maintenance:
                    differences.append({"aircraft_id": aircraft, "hub_id": hub, "kind": "unexpected_aircraft"})
                elif pending_routes.setdefault(aircraft, pair) != pair:
                    differences.append({"aircraft_id": aircraft, "hub_id": hub, "kind": "different_pending_route"})
    for aircraft, pair in {**expected, **pending_routes}.items():
        for hub in sorted((pair & owned_ids) - observed_hubs.get(aircraft, set())):
            differences.append({"aircraft_id": aircraft, "hub_id": hub, "kind": "missing_aircraft"})

    status = "matched"
    if differences:
        status = "different"
    elif maintenance is None or unclassified:
        status = "incomplete"
    return {**report, "status": status, "differences": differences,
            "route_roster_observation_id": fleet["roster_observation_id"],
            "pending_observation_id": fleet.get("native_observation_id") if maintenance is not None else None,
            "associated_maintenance_aircraft": sorted(pending_routes),
            "maintenance_without_hub_link": sorted(maintenance - observed_hubs.keys()) if maintenance is not None else None,
            "unclassified_pending_aircraft": sorted(unclassified),
            "observed_links": sum(len(hubs) for hubs in observed_hubs.values())}
