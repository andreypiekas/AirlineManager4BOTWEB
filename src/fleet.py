"""Fleet automation: routes for parked aircraft and buying the best-value aircraft.

Screen facts (verified 2026-09-30):
* Routes popup (`routes_main.php`): `#hParked` / `#hPending` counters;
  `fleet_parked.php` -> #routesContainer lists `#routeMainParkedList<id>` blocks.
* Research tab (`research_main.php` -> #routeAction): `#hubSelect` holds the hub id;
  `research_main.php?mode=search&rwy=..&dist=..&depId=..&arr=0&arrId=0&charter=0`
  -> #resResult with `.sorter` rows (data-distance / data-yclass / data-jclass /
  data-fclass / data-rwy, onclick contains `arr=<airportId>`).
* `route_research_route.php?dep=..&arr=..` -> #rDetails with `#capAc` (capable
  aircraft, option value "id;lat;lon;speed;range;arr") and "A/C on route".
* `new_route_info.php?id=<ac>&airportId=<arr>&mode=res` -> #newRouteInfo panel:
  `#introAuto` (autoprice), `#routeReg`, `#btnCreateNewRoute`, "Route fee".
* Order tab (`ac_orders.php?first=true` -> #routeAction): `#acListItems .acListItem`
  rows with data-range / data-speed / data-capacity / data-fuel / data-price and
  the model id in the onclick; `ac_orders.php?mode=detail&id=..&charter=0` ->
  #acModel with `#acReg`, `#hubSelection`, `#btnPurchaseIntro`, `#accountLow`.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import TYPE_CHECKING, Callable, Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from economy import (find_model, fmt_days, fmt_money, goal_progress, is_auto_goal, load_market, pick_ladder,
                     save_market)
from aircraft_order_hub import AircraftOrderHubError, prepare_order_hub
from gamemode import EASY, GameMode
from helpers import clean_response, fmt, game_whole_number, to_int
from notify import esc
from native_route_quotes import record_native_route_quote
from route_optimizer import estimate_route, operating_prices_valid, rank_candidates
from route_strategy import best_reroute, profitable_candidates
from route_airports import HubMatch, match_hub_options, code_from_candidate, explain_hub_options
from airport_catalog import by_code, game_code
from hub_registry import HubRegistry
from hub_expansion import HubExpansionRegistry
from route_registry import HOME_HUB_EVIDENCE, RouteRegistry, reroute_block_reason, endpoint, route_key
from reroute import (aircraft_details_missing, confirm_direct_route, confirm_stopover, has_pending_reroute,
                     landed_departure, read_direct_form, recover_pending, replace_route)
from reroute_preflight import check_existing_route
from route_creation import has_pending_creation, stage_creation, finish_creation, recover_pending_creation
from route_stopover import (ROUTE_EVENT_WARNING_JS, Stopover, find_stopover, parked_specs, read_form,
                            read_route_fares, research_details)

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.rutas")
log_fleet = logging.getLogger("am4bot.flota")
log_market = logging.getLogger("am4bot.aviones")

MAX_ROUTE_TRIES = 16  # compare more profit-ranked destinations, including occupied-route fallbacks
BIG_SEATS = 150      # from this capacity an aircraft is "big": long routes, goal candidate
GOAL_SAFETY = 2      # a small aircraft must pay back in less than half the time left to the goal

_LANDED_DUPLICATES_JS = """
const now = Date.now() / 1000;
return arguments[0].filter(id => {
    const entry = window.statusData?.[id];
    // The game sets arrived=0 once the aircraft is landed.
    return entry?.routeId > 0 && entry.arrived !== null && entry.arrived !== undefined &&
        Number.isFinite(Number(entry.arrived)) && Number(entry.arrived) <= now &&
        Number(entry.grounded) === 0;
});
"""

_STATUS_AIRCRAFT_JS = """
return Object.entries(window.statusData || {})
  .filter(([id, row]) => /^[0-9]{1,14}$/.test(id) && typeof row?.reg === "string")
  .map(([id]) => id);
"""

_GAME_ROSTER_JS = """
const status = window.statusData;
if (!status || typeof status !== 'object' || Array.isArray(status)) return null;
return Object.entries(status).map(([id, row]) => ({
  aircraft_id: id,
  registration: typeof row?.reg === 'string' ? row.reg : '',
  route_id: row?.routeId !== null && row?.routeId !== undefined &&
    /^[0-9]{1,14}$/.test(String(row.routeId)) &&
    Number.isSafeInteger(Number(row.routeId)) && Number(row.routeId) >= 0
    ? Number(row.routeId) : null
}));
"""

_FLIGHT_HISTORY_JS = """
const ids = arguments[0];
const done = arguments[arguments.length - 1];
const numeric = text => {
  const match = String(text || '').match(/[0-9][0-9,]*/);
  return match ? Number(match[0].replaceAll(',', '')) : null;
};
const recentHours = text => {
  const match = String(text || '').trim().match(/^(\\d+)\\s*(min(?:ute|uto)?s?|h(?:our|ora)?s?|d(?:ay|ia)?s?)/i);
  if (!match) return null;
  const unit = match[2].toLowerCase();
  if (unit.startsWith('min')) return Number(match[1]) / 60;
  if (unit.startsWith('h')) return Number(match[1]);
  return Number(match[1]) * 24;
};
Promise.all(ids.map(async aircraft_id => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch('fleet_details.php?id=' + encodeURIComponent(aircraft_id), {
      credentials: 'same-origin', signal: controller.signal
    });
    if (!response.ok) return {aircraft_id};
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const flights = [...doc.querySelectorAll('#flight-history > .row')].slice(0, 20)
      .map(flight => {
        const cells = [...flight.querySelectorAll(':scope > .col-3')];
        if (cells.length !== 4) return null;
        return {
          flight_route: cells[0].querySelector('.s-text')?.textContent?.trim() || '',
          co2_quotas: numeric(cells[1].querySelector('.s-text')?.textContent),
          fuel_lbs: numeric(cells[2].querySelector('.s-text')?.textContent),
          flight_value: numeric(cells[3].textContent),
          age_hours: recentHours(cells[0].childNodes[0]?.textContent)
        };
      }).filter(Boolean);
    if (!flights.length) return {aircraft_id};
    return {aircraft_id, ...flights[0],
      recent_flights: flights.filter(f => f.age_hours !== null && f.age_hours < 24)};
  } catch (_) {
    return {aircraft_id};
  } finally {
    clearTimeout(timeout);
  }
})).then(done, () => done([]));
"""

# Read game identities and numeric values from IDs, classes, data attributes and handlers.

# "A/C on route": first row of the small table under the demand table in the route details.
_ON_ROUTE_JS = """
const cell = document.querySelector("#rDetails table.m-text:not(.table-bordered) tr td.text-right");
return cell ? cell.textContent : null;
"""

_PARKED_JS = """
return Array.from(document.querySelectorAll("#routesContainer [id^='routeMainParkedList']")).map(el => {
  const bolds = Array.from(el.querySelectorAll("b")).map(b => b.textContent.trim());
  const header = el.querySelector(".col-6.text-right");                 // "90 Seats" / "90 Asientos"
  const seats = ((header ? header.textContent : "").match(/[\\d,]+/) || [])[0];
  return {id: el.id.replace("routeMainParkedList", ""), model: bolds[0] || "?", reg: bolds[1] || "", seats: seats || ""};
});
"""


_CANDIDATES_JS = r"""
return Array.from(document.querySelectorAll("#resResult #list .sorter")).map(el => {
  const arr = ((el.getAttribute("onclick") || "").match(/arr=(\d+)/) || [])[1];
  const title = el.querySelector(".exo");
  return {arr: arr || null, name: title ? title.textContent.trim() : "?",
          code: el.dataset.iata || el.dataset.icao || el.dataset.code || (title ? title.getAttribute("data-code") || title.title || "" : ""),
          distance: el.dataset.distance || "0",
          y: el.dataset.yclass || "0", j: el.dataset.jclass || "0", f: el.dataset.fclass || "0", rwy: el.dataset.rwy || "0",
          event_demand_boosted: EVENT_WARNING.test(el.textContent || "")};
});
""".replace("EVENT_WARNING", ROUTE_EVENT_WARNING_JS)

_HUB_OPTIONS_JS = """
const select = document.getElementById("hubSelect");
return select ? Array.from(select.options).map(opt => ({
  id: opt.value, text: opt.textContent.trim(),
  code: opt.dataset.iata || opt.dataset.icao || opt.dataset.code || "",
  title: opt.title || ""
})) : [];
"""

_MODELS_JS = """
return Array.from(document.querySelectorAll("#acListItems .acListItem"))
  .filter(el => el.offsetParent !== null)
  .map(el => {
    const id = ((el.getAttribute("onclick") || "").match(/id=(\\d+)/) || [])[1];
    const name = el.querySelector("b");
    return {id: id || null, name: name ? name.textContent.trim() : "?", range: el.dataset.range || "0",
            speed: el.dataset.speed || "0", capacity: el.dataset.capacity || "0", fuel: el.dataset.fuel || "0",
            price: el.dataset.price || "0"};
  });
"""


@dataclass
class ParkedAircraft:
    id: str
    model: str
    reg: str
    seats: int


@dataclass
class RouteCandidate:
    arr_id: str
    name: str
    distance: float
    y: int
    j: int
    f: int
    runway: int
    code: str = ""  # game-confirmed IATA/ICAO when available
    event_demand_boosted: bool = False


@dataclass
class AircraftModel:
    id: str
    name: str
    range_km: int
    speed: int
    capacity: int
    fuel: int
    price: int
    score: float = field(default=0.0)    # estimated net profit per day / price
    profit: float = field(default=0.0)   # estimated net profit per day ($)


# Economics calibrated on the airline's own flight history (01/10/2026, easy mode): the economy autoprice
# is 0.4 $/km + 170 and a leg takes distance / (1.5 x cruise speed) - both depend on the game mode, see
# gamemode.py -, the engine burns ~94 % of the listed fuel, CO2 is ~0.18 kg per passenger-km, and the bot
# leaves an aircraft ~6 minutes on the ground.
# The load factor is measured by the bot every cycle (it follows the airline reputation).
LOAD_DEFAULT = 0.55
TURNAROUND_H = 0.1
ENGINE_FUEL = 0.94
CO2_PER_PAX_KM = 0.18
ROUTE_DEMAND_Y = 1200   # economy passengers per day on a busy route: caps what one aircraft can sell


def daily_profit(model: AircraftModel, distance: int, load: float, fuel_price: float, co2_price: float,
                 mode: GameMode = EASY) -> float:
    """Estimated net profit per day of one aircraft flying *distance* km legs back to back
    (flight speed and economy autoprice of the game mode)."""
    if distance < 300 or model.price <= 0 or model.speed <= 0:
        return 0.0
    legs = 24 / (distance / (model.speed * mode.speed) + TURNAROUND_H)
    passengers = min(model.capacity * load * legs, ROUTE_DEMAND_Y)
    income = passengers * mode.fare(0, distance)
    fuel = legs * model.fuel * ENGINE_FUEL * distance * fuel_price / 1000
    co2 = passengers * CO2_PER_PAX_KM * distance * co2_price / 1000
    return income - fuel - co2


# ---------------------------------------------------------------------- entry point
# Only explicit DOM attributes or a dedicated route label count as game route
# evidence; never infer airports from general row text or the aircraft's model.
_ROUTE_AUDIT_JS = """
// Capture pagination from the same DOM snapshot as the route rows. A numeric
// active page is evidence of a page index; absence means page unknown.
const popup = typeof document.querySelector === "function" ? document.querySelector("#popContent") : null;
const pagination = popup && popup.querySelector ?
  popup.querySelector('#routeAction #routesContainer .pagination') || popup.querySelector('.pagination') : null;
const active = pagination && pagination.querySelector ?
  pagination.querySelector(".page-item.not-active > .page-link, .page-item.active > .page-link, .page-link[aria-current='page']") : null;
const pageNumber = value => /^[1-9][0-9]{0,2}$/.test(String(value || "").trim()) ?
  Number(String(value).trim()) : null;
const scanPage = pageNumber(active && active.textContent) ||
  pageNumber(popup && popup.getAttribute && popup.getAttribute("data-current-page"));
// The native pager may expose only Previous, the current number, and Next.
const pagerLabels = active && pagination.querySelectorAll ?
  Array.from(pagination.querySelectorAll('a.page-link'), link => link.textContent.trim()) : [];
const nativeLabels = [String(scanPage), ...(scanPage > 1 ? ['Previous'] : [])];
const hasNativeNext = pagerLabels.includes('Next');
if (hasNativeNext) nativeLabels.push('Next');
const scanHasNext = scanPage && pagerLabels.length === nativeLabels.length &&
  nativeLabels.every(label => pagerLabels.includes(label)) ? hasNativeNext : null;
const routeCount = Array.from(document.querySelectorAll(
  '#popContent .row.font-weight-bold > .col-12.exo.text-center.p-2'))
  .map(node => String(node.textContent || '').trim())
  .map(label => label.match(/^([1-9][0-9]{0,4})\\s+Routes$/i))
  .find(match => match !== null);
const totalFromRouteCount = routeCount ? Math.ceil(Number(routeCount[1]) / 20) : null;
const scanTotalPages = pageNumber(pagination && pagination.getAttribute &&
  pagination.getAttribute("data-total-pages")) ||
  pageNumber(popup && popup.getAttribute && popup.getAttribute("data-total-pages")) ||
  (scanHasNext === null ? pageNumber(totalFromRouteCount) : null);
return Array.from(document.querySelectorAll("#popContent #routeAction #routesContainer [id^='routeMainList']")).map(row => {
  // The existing seats module identifies routes by this real game link.
  const detailLink = row.querySelector("a[onclick*='fleet_details.php']");
  const link = detailLink || row.querySelector("a");
  const idFromLink = ((detailLink ? detailLink.getAttribute("onclick") : "") || "")
    .match(/fleet_details\\.php\\?id=(\\d+)/);
  const aircraftId = (idFromLink && idFromLink[1]) || "";
  // Route card IDs are route IDs, distinct from the aircraft IDs in detail links.
  const routeIdMatch = String(row.id || "").match(/^routeMainList([0-9]{1,14})$/);
  const label = link ? link.textContent.trim() : "";
  const tableData = Array.from(row.querySelectorAll("[data-dep], [data-arr], [data-origin], [data-destination], [data-route]"));
  const attrs = [row, ...tableData];
  const getAttr = (...names) => {
    for (const el of attrs) for (const name of names) {
      const value = el.getAttribute(name);
      if (value) return value.trim();
    }
    return "";
  };
  // Game-confirmed route label: .col-10 .s-text = "LEMD - EPRZ".
  // This selector already powers src/seats.py and works even without data-* attributes.
  const routeEl = row.querySelector(".col-10 .s-text") ||
    row.querySelector("[data-route], .route-name, .route-code, .routeName");
  const routeText = routeEl ? (routeEl.getAttribute("data-route") || routeEl.textContent || "").trim() : "";
  const codes = routeText.match(/\\b([A-Za-z]{3,4})\\s*(?:→|↔|–|—|-|\\/|to)\\s*([A-Za-z]{3,4})\\b/i);
  // An explicit hook containing BOTH dep and arr IDs is safe route evidence.
  const endpointHook = Array.from(row.querySelectorAll("[onclick], [href]"))
    .map(e => e.getAttribute("onclick") || e.getAttribute("href") || "")
    .find(v => /(?:[?&]|\\b)dep=\\d+/.test(v) && /(?:[?&]|\\b)arr=\\d+/.test(v)) || "";
  const depFromHook = (endpointHook.match(/(?:[?&]|\\b)dep=(\\d+)/) || [])[1] || "";
  const arrFromHook = (endpointHook.match(/(?:[?&]|\\b)arr=(\\d+)/) || [])[1] || "";
  const status = row.querySelector("[data-at-base], [data-at-hub], [data-grounded]");
  const atBaseRaw = status ? (status.getAttribute("data-at-base") ||
    status.getAttribute("data-at-hub") || status.getAttribute("data-grounded")) : "";
  return {
    aircraft_id: aircraftId,
    route_id: routeIdMatch ? Number(routeIdMatch[1]) : null,
    scan_page: scanPage,
    scan_total_pages: scanTotalPages,
    scan_has_next: scanHasNext,
    scan_route_count: routeCount ? Number(routeCount[1]) : null,
    registration: label.split(" - ")[0] || aircraftId,
    model: label.includes(" - ") ? label.split(" - ").slice(1).join(" - ") : "",
    origin_id: getAttr("data-dep", "data-origin-id") || depFromHook,
    destination_id: getAttr("data-arr", "data-destination-id") || arrFromHook,
    origin_code: getAttr("data-origin-code", "data-dep-code") || (codes ? codes[1] : ""),
    destination_code: getAttr("data-destination-code", "data-arr-code") || (codes ? codes[2] : ""),
    route_label: routeText.slice(0, 80),
    // The only home-hub evidence is an explicit per-aircraft field.
    home_hub_id: (row.getAttribute("data-home-hub-id") ||
      (detailLink && detailLink.getAttribute("data-home-hub-id")) || "").trim(),
    at_base: atBaseRaw === "1" || atBaseRaw === "true" ? true :
      atBaseRaw === "0" || atBaseRaw === "false" ? false : null,
    in_flight: !!row.querySelector("[id^='routesTimer']")
  };
});
"""


def audit_routes(bot: "Bot", registry: RouteRegistry, *,
                 page: Optional[int] = None, total_pages: Optional[int] = None,
                 _rows: Optional[list[dict]] = None,
                 _audit_run_id: Optional[str] = None) -> bool:
    """Accumulate one visible page, keeping route assignments from other pages."""
    rows = (bot.js(_ROUTE_AUDIT_JS) or []) if _rows is None else _rows
    if not isinstance(rows, list):
        rows = []
    if page is not None and not rows:
        log.warning("Controle de rotas: página %s sem linhas carregadas; cobertura não registrada.", page)
        return False
    metadata = rows[0] if rows and isinstance(rows[0], dict) else {}
    actual_page = RouteRegistry._valid_page(metadata.get("scan_page"))
    actual_total = RouteRegistry._valid_page(metadata.get("scan_total_pages"))
    expected_routes = metadata.get("scan_route_count")
    if any(isinstance(row, dict) and (
            RouteRegistry._valid_page(row.get("scan_page")) != actual_page or
            RouteRegistry._valid_page(row.get("scan_total_pages")) != actual_total or
            row.get("scan_route_count") != expected_routes)
           for row in rows):
        log.warning("Controle de rotas: paginação inconsistente entre linhas; leitura ignorada.")
        return False
    if page is not None and page != actual_page:
        log.warning("Controle de rotas: página solicitada %s, página exibida %s; leitura ignorada.",
                    page, actual_page)
        return False
    if total_pages is not None and total_pages != actual_total:
        log.warning("Controle de rotas: paginação mudou de %s para %s; leitura ignorada.",
                    total_pages, actual_total)
        return False
    if actual_page is not None and actual_total is not None and actual_page > actual_total:
        log.warning("Controle de rotas: página %s excede total %s; leitura ignorada.",
                    actual_page, actual_total)
        return False
    page = actual_page if actual_page is not None else page
    total_pages = actual_total if actual_total is not None else total_pages
    # Maintenance was read earlier in this cycle. Unlike the routes list,
    # it exposes an explicit, per-aircraft at-base flag. Reuse it as read-only
    # ground evidence without revisiting paginated aircraft lists.
    recent = getattr(bot, "recent_fleet", None)
    fleet = recent(180) if callable(recent) else None
    grounded = {str(ac.id): ac.at_base for ac in fleet or []
                if getattr(ac, "id", None) is not None}
    maintenance_seen = 0
    maintenance_at_base = 0
    maintenance_away = 0
    observations = []
    seen_aircraft: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = str(row.get("aircraft_id") or "")
        if not identity or identity in seen_aircraft:
            continue
        seen_aircraft.add(identity)
        registration = row.get("registration")
        model = row.get("model") or ""
        base = row.get("at_base")
        if identity in grounded:
            maintenance_seen += 1
            if grounded[identity] and not row.get("in_flight"):
                maintenance_at_base += 1
            else:
                maintenance_away += 1
        if row.get("in_flight"):
            base = False
        elif base is None and identity in grounded:
            base = grounded[identity]
        origin = endpoint(row.get("origin_id"), row.get("origin_code"))
        destination = endpoint(row.get("destination_id"), row.get("destination_code"))
        home_hub_id = row.get("home_hub_id")
        home_hub_evidence = ({"home_hub_evidence": HOME_HUB_EVIDENCE,
                              "home_hub_evidence_aircraft_id": identity}
                             if isinstance(home_hub_id, str)
                             and re.fullmatch(r"[1-9][0-9]{0,11}", home_hub_id) else {})
        observations.append({
            "aircraft_id": identity, "registration": registration, "model": model,
            "origin": origin, "destination": destination, "at_base": base,
            "observed_route_id": row.get("route_id"),
            "home_hub_id": home_hub_id,
            "scan_has_next": row.get("scan_has_next"),
            **home_hub_evidence,
        })
    missing = sum(1 for row in rows
                  if isinstance(row, dict) and not ((row.get("origin_id") or row.get("origin_code"))
                          and (row.get("destination_id") or row.get("destination_code"))))
    detected = registry.record_scan(len(rows), 0, missing,
                                    aircraft_ids=list(seen_aircraft), page=page,
                                    total_pages=total_pages, expected_routes=expected_routes,
                                    audit_run_id=_audit_run_id,
                                    route_observations=observations)
    if rows:
        log.info(
            "Controle de rotas: %d aeronaves visíveis, %d rotas identificadas, "
            "%d sem os dois aeroportos no HTML da página. "
            "Modo simulação não impede a leitura.",
            len(rows), detected, missing,
        )
        if fleet is not None:
            log.info(
                "Controle de rotas: manutenção forneceu estado de %d aeronaves da página atual: "
                "%d na base, %d fora da base/em voo; demais sem comprovação.",
                maintenance_seen, maintenance_at_base, maintenance_away,
            )
    else:
        log.warning(
            "Controle de rotas: nenhuma aeronave reconhecida na página atual. "
            "Confirme que o jogo carregou a lista de rotas; não é necessário "
            "desativar o modo simulação para auditar."
        )
    return True


def audit_routes_rolling(bot: "Bot", registry: RouteRegistry, *, total_pages: int,
                         load_page: Callable[[int], bool], pages_per_cycle: int = 2) -> list[int]:
    """Bounded opt-in scan using a caller-provided, game-verified page loader.

    load_page(page_number) must return True only after the native game finished
    displaying that exact page. It owns navigation and restoring the prior page.
    Unknown or moving pagination cannot be certified as a complete fleet scan.
    """
    visited = []
    for page in registry.next_scan_pages(total_pages, limit=pages_per_cycle):
        if not load_page(page):
            break
        if not audit_routes(bot, registry, page=page, total_pages=total_pages):
            break
        visited.append(page)
    return visited


_ROUTES_PAGER_LINKS_JS = r"""
return Array.from(document.querySelectorAll('#popContent .pagination [onclick]'))
  .map(node => String(node.getAttribute('onclick') || ''))
  .map(action => action.match(/^\s*Ajax\s*\(\s*(['"])(routes\.php\?start=(\d+)&sort=(?:[\w-]|%[0-9a-f]{2})*)\1\s*,\s*(['"])(routeAction)\4\s*,\s*this\s*\)\s*;?\s*$/i))
  .filter(Boolean)
  .map(match => ({offset: Number(match[3]), target: match[5], url: match[2]}));
"""


def _native_route_bindings(pages: list[tuple[int, list[dict]]], expected_routes: Optional[int]
                           ) -> Optional[dict[str, tuple]]:
    """Fingerprint complete native route assignments independently of pagination and direction."""
    bindings = {}
    route_ids = set()
    for _, rows in pages:
        for row in rows:
            aircraft_id = row["aircraft_id"]
            route_id = row.get("route_id")
            origin = endpoint(row.get("origin_id"), row.get("origin_code"))
            destination = endpoint(row.get("destination_id"), row.get("destination_code"))
            if (type(route_id) is not int or route_id <= 0 or route_id in route_ids
                    or aircraft_id in bindings or not row.get("registration") or not row.get("model")
                    or not route_key(origin, destination)):
                return None
            route_ids.add(route_id)
            airports = tuple(sorted((airport["id"], airport["code"])
                                    for airport in (origin, destination)))
            bindings[aircraft_id] = (route_id, row["registration"], row["model"],
                                     row.get("home_hub_id"), airports)
    return bindings if len(bindings) == expected_routes else None


def audit_routes_live_pages(bot: "Bot", registry: RouteRegistry, *, pages_per_cycle: int = 3,
                            attempt_full: bool = False) -> list[int]:
    """Audit verified AJAX pages across bounded cycles, restoring the initial view."""

    if pages_per_cycle <= 0 or getattr(bot, "stopping", False):
        return []

    page_limit = 25
    deadline = time.monotonic() + 120 if attempt_full else None
    declared_total: Optional[int] = None

    def expired() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def snapshot(expected_total: Optional[int] = None,
                 expected_count: Optional[int] = None
                 ) -> Optional[tuple[int, Optional[int], list[dict]]]:
        """Accept only two identical, internally consistent page reads."""
        rows = bot.js(_ROUTE_AUDIT_JS) or []
        if not isinstance(rows, list) or not 0 < len(rows) <= 20:
            return None
        if any(not isinstance(row, dict) for row in rows):
            return None
        identities = [str(row.get("aircraft_id") or "") for row in rows]
        if (any(not re.fullmatch(r"[0-9]{1,14}", identity) for identity in identities)
                or len(identities) != len(set(identities))):
            return None
        page = RouteRegistry._valid_page(rows[0].get("scan_page"))
        total = RouteRegistry._valid_page(rows[0].get("scan_total_pages"))
        has_next = rows[0].get("scan_has_next")
        if (page is None or (total is None and type(has_next) is not bool) or
                (expected_total is not None and declared_total is not None and total != declared_total) or
                (total is not None and (page > total or expected_total not in (None, total))) or
                (expected_total is not None and page > expected_total) or
                (expected_count is not None and rows[0].get("scan_route_count") != expected_count)):
            return None
        end = total if total is not None else expected_total
        if end is not None and type(has_next) is bool and has_next != (page < end):
            return None
        if any(RouteRegistry._valid_page(row.get("scan_page")) != page or
               RouteRegistry._valid_page(row.get("scan_total_pages")) != total or
               row.get("scan_has_next") != has_next or
               row.get("scan_route_count") != rows[0].get("scan_route_count")
               for row in rows):
            return None
        if bot.js(_ROUTE_AUDIT_JS) != rows:
            return None
        return page, total, rows

    try:
        initial = snapshot()
        if initial is None or expired() or getattr(bot, "stopping", False):
            return []
        start, declared_total, initial_rows = initial
        total = declared_total
        route_count = initial_rows[0].get("scan_route_count")
        if type(route_count) is not int or not 0 < route_count <= 50000:
            route_count = None
        audit_run_id = uuid.uuid4().hex
        if total == 1 or (total is None and start == 1 and
                          initial_rows[0]["scan_has_next"] is False and route_count == len(initial_rows)):
            if total is None:
                total = 1
                initial_rows = [dict(row, scan_total_pages=1) for row in initial_rows]
            return [start] if audit_routes(bot, registry, page=start, total_pages=total,
                                           _rows=initial_rows,
                                           _audit_run_id=audit_run_id) else []
        links = bot.js(_ROUTES_PAGER_LINKS_JS) or []
    except Exception as exc:  # noqa: BLE001 - the popup can disappear mid-read
        log.warning("Auditoria paginada: leitura inicial interrompida (%s).", type(exc).__name__)
        return []

    if not isinstance(links, list):
        return []
    adjacent = {20 * (page - 1) for page in (start - 1, start + 1)
                if page >= 1 and (total is None or page <= total)}

    def valid_link(link: object, offset: int) -> bool:
        if not isinstance(link, dict) or type(link.get("offset")) is not int:
            return False
        if link["offset"] != offset:
            return False
        url = link.get("url")
        return link.get("target") == "routeAction" and isinstance(url, str) and bool(
            re.fullmatch(rf"routes\.php\?start={offset}&sort=(?:[\w-]|%[0-9a-fA-F]{{2}})*", url))

    first_links = [link for link in links
                   if isinstance(link, dict) and link.get("offset") in adjacent
                   and valid_link(link, link["offset"])]
    # Page numbers and prev/next buttons can expose the same AJAX link twice.
    # A different URL for the same offset is ambiguous and must stop the audit.
    if (not first_links or any(
            len({link["url"] for link in first_links if link["offset"] == offset}) > 1
            for offset in adjacent)):
        log.warning("Auditoria paginada: links AJAX da página %d não confirmados.", start)
        return []
    target = "routeAction"
    initial_url = first_links[0].get("url")
    restore_url = (re.sub(r"start=\d+", f"start={(start - 1) * 20}", initial_url, count=1)
                   if initial_url else f"routes.php?start={(start - 1) * 20}")
    unverified_navigation = False
    verified_rows = initial_rows

    def after_ajax(next_page: int, previous_rows: list[dict], *,
                   restore: bool) -> Optional[list[dict]]:
        previous_ids = {row["aircraft_id"] for row in previous_rows}
        for attempt in range(4):
            try:
                captured = snapshot(None if restore else total,
                                    None if restore else route_count)
            except Exception:  # noqa: BLE001 - AJAX may replace the DOM mid-read
                captured = None
            if captured is not None and captured[0] == next_page:
                loaded_rows = captured[2]
                if {row["aircraft_id"] for row in loaded_rows} != previous_ids:
                    return loaded_rows
            # AJAX may return while the previous route list is still visible.
            if attempt < 3:
                time.sleep(0.1)
        return None

    def load(page: int, *, restore: bool = False) -> bool:
        nonlocal unverified_navigation, verified_rows
        if not restore and (getattr(bot, "stopping", False) or expired()):
            return False
        try:
            captured = snapshot(None if restore else total,
                                None if restore else route_count)
            if captured is None:
                return False
            current, _, current_rows = captured
            if current == page:
                verified_rows = current_rows
                return True

            for _ in range(max(total or page_limit, current)):
                if not restore and (getattr(bot, "stopping", False) or expired()):
                    return False
                if current == page:
                    verified_rows = current_rows
                    return True
                next_page = current + (1 if page > current else -1)
                page_links = bot.js(_ROUTES_PAGER_LINKS_JS) or []
                matches = [link for link in page_links
                           if valid_link(link, (next_page - 1) * 20)] if isinstance(page_links, list) else []
                urls = {link["url"] for link in matches}
                if len(urls) != 1:
                    log.warning("Auditoria paginada: falta link válido da página %d para %d.",
                                current, next_page)
                    return False
                unverified_navigation = True
                bot.ajax(urls.pop(), target)
                confirmed = after_ajax(next_page, current_rows, restore=restore)
                if confirmed is None:
                    log.warning("Auditoria paginada: página %d sem confirmação do jogo.", next_page)
                    return False
                unverified_navigation = False
                current = next_page
                current_rows = confirmed
            return False
        except Exception as exc:  # noqa: BLE001 - Ajax may already have updated the DOM
            log.warning("Auditoria paginada: falha ao carregar página %d (%s).",
                        page, type(exc).__name__)
            return False

    staged: list[tuple[int, list[dict]]] = []
    staged_ids: set[str] = set()
    restored: Optional[tuple[int, Optional[int], list[dict]]] = None

    def stage(page: int) -> bool:
        if not load(page):
            return False
        page_ids = {row["aircraft_id"] for row in verified_rows}
        if staged_ids.intersection(page_ids):
            log.warning("Auditoria paginada: aeronaves repetidas entre páginas do ciclo; "
                        "amostragem descartada por possível deslocamento da frota.")
            staged.clear()
            return False
        staged_ids.update(page_ids)
        staged.append((page, verified_rows))
        return True

    # This estimate schedules partial reads only. A full native audit must
    # reach the last page using actual Next links, within the cycle bounds.
    first_page_shortfall = 20 - len(initial_rows) if start == 1 else 0
    partial_total = max(start + int(initial_rows[0].get("scan_has_next") is True),
                        ((route_count or 0) + first_page_shortfall + 19) // 20)
    discover = total is None and attempt_full and partial_total <= page_limit
    try:
        full_attempt = attempt_full and (discover or (total is not None and total <= page_limit))
        if discover:
            selected_pages = range(1, page_limit + 1)
        elif full_attempt:
            # Travel to one end first, then sweep the remaining pages in order.
            if start <= (total + 1) / 2:
                selected_pages = list(range(start, 0, -1)) + list(range(start + 1, total + 1))
            else:
                selected_pages = list(range(start, total + 1)) + list(range(start - 1, 0, -1))
        else:
            selected_pages = registry.next_scan_pages(total or partial_total, limit=pages_per_cycle,
                                                       max_pages=page_limit)
            if attempt_full:
                log.info("Auditoria integral adiada: %d páginas excedem o limite de 25; "
                         "mantendo cobertura parcial.", total or partial_total)
        for page in selected_pages:
            if total is not None and page > total:
                continue
            if not stage(page):
                break
            if total is None and verified_rows[0].get("scan_has_next") is False:
                total = page
                if discover:
                    break
        if (total is not None and len(staged) == total and
                {page for page, _ in staged} == set(range(1, total + 1))):
            # Reread every page before publishing a full-cycle audit.
            recheck = reversed(staged) if full_attempt else staged
            recaptured = {}
            for page, original_rows in recheck:
                if not load(page) or (not full_attempt and verified_rows != original_rows):
                    log.warning("Auditoria paginada: conteúdo da página %d mudou na "
                                "releitura integral; lote descartado.", page)
                    staged.clear()
                    break
                recaptured[page] = verified_rows
            if full_attempt and staged:
                latest = [(page, recaptured[page]) for page, _ in staged]
                if latest != staged:
                    # Rows can move between pages or display the return direction.
                    # Both passes must independently reconcile every native binding.
                    bindings = _native_route_bindings(staged, route_count)
                    if bindings is None or bindings != _native_route_bindings(latest, route_count):
                        log.warning("Auditoria paginada: vínculos divergentes entre as varreduras; "
                                    "lote descartado.")
                        staged.clear()
                    else:
                        staged = latest
    finally:
        try:
            current = snapshot()
            if current is None or current[0] != start or unverified_navigation:
                if current is not None and not unverified_navigation:
                    load(start, restore=True)
                current = snapshot()
                if current is None or current[0] != start or unverified_navigation:
                    # Recover a changed-but-unconfirmed AJAX view with a
                    # same-target URL derived from a verified native pager link.
                    bot.ajax(restore_url, target)
                for attempt in range(4):
                    restored = snapshot()
                    if restored is not None and restored[0] == start:
                        break
                    if attempt < 3:
                        time.sleep(0.1)
            else:
                restored = current
        except Exception as exc:  # noqa: BLE001 - best-effort UI restoration
            log.warning("Auditoria paginada: falha ao restaurar página %d (%s).",
                        start, type(exc).__name__)

    if restored is None or restored[0] != start:
        log.warning("Auditoria paginada: página inicial %d não confirmada; cobertura descartada.", start)
        return []
    if (restored[1] != declared_total or
            (route_count is not None and restored[2][0].get("scan_route_count") != route_count)):
        # The fleet size or pagination changed while browsing. Invalidate
        # prior coverage using the verified current page before continuing.
        audit_routes(bot, registry, page=start, total_pages=restored[1], _rows=restored[2])
        log.warning("Auditoria paginada: contagem alterada durante leitura; cobertura reiniciada.")
        return []
    if unverified_navigation:
        log.warning("Auditoria paginada: navegação AJAX não confirmada; lote descartado.")
        return []
    if expired() or getattr(bot, "stopping", False):
        log.info("Auditoria paginada interrompida por prazo ou cancelamento; lote descartado.")
        return []
    if (total is not None and len(staged) == total and
            {page for page, _ in staged} == set(range(1, total + 1))):
        original_start_rows = next(rows for page, rows in staged if page == start)
        if restored[2] != original_start_rows:
            log.warning("Auditoria paginada: página inicial mudou durante a "
                        "restauração; lote integral descartado.")
            return []

    if total is None:
        staged = staged[:pages_per_cycle]
    recorded_total = total or max(partial_total, max((page for page, _ in staged), default=start))
    visited = []
    for page, rows in staged:
        if declared_total is None:
            rows = [dict(row, scan_total_pages=recorded_total) for row in rows]
        if not audit_routes(bot, registry, page=page, total_pages=recorded_total, _rows=rows,
                            _audit_run_id=audit_run_id if total is not None else None):
            break
        visited.append(page)
    coverage = registry.snapshot().get("scan_coverage") or {}
    log.info("Auditoria paginada: %d páginas confirmadas neste ciclo; cobertura %s/%s, "
             "IDs repetidos=%s, total conferido=%s.",
             len(visited), coverage.get("observed_pages", 0), recorded_total,
             coverage.get("repeated_aircraft_across_pages", 0),
             bool(coverage.get("full_page_coverage_verified")))
    if coverage.get("full_page_coverage_verified"):
        proof = registry.snapshot().get("last_verified_full_audit") or {}
        log.info("Auditoria integral comprovada no ciclo %s: %s aeronaves únicas "
                 "em %s páginas, de %s rotas anunciadas pelo jogo.",
                 proof.get("audit_run_id"), proof.get("unique_aircraft"),
                 proof.get("total_pages"), proof.get("expected_routes"))
    return visited


_ONBOARD_JS = """
return Array.from(document.querySelectorAll("#popContent [id^='routeMainList']"))
  .filter(row => row.querySelector("[id^='routesTimer']"))          // in flight: the row shows who is on board
  .map(row => {
    const link = row.querySelector("a");                              // "EC-003-2 - DC-9-10"
    const info = link ? link.parentElement.querySelector(".s-text") : null;   // "Onboard: 49 / 0 / 0" (Y / J / F)
    const nums = (((info || {}).textContent || "").match(/\\d+/g) || []).map(Number);
    // in economy slots: a business passenger takes 2, a first-class passenger 3
    return {name: link ? link.textContent.trim() : "", onboard: (nums[0] || 0) + 2 * (nums[1] || 0) + 3 * (nums[2] || 0)};
  });
"""


def measure_load(bot: "Bot") -> None:
    """Median load factor of the aircraft in flight (occupied economy slots / slots), smoothed over cycles."""
    market = load_market()
    loads = []
    for row in bot.js(_ONBOARD_JS) or []:
        model_name = row["name"].split(" - ", 1)[-1].strip()
        model = find_model(market, model_name)
        if model and model.get("capacity") and row["onboard"]:
            loads.append(min(1.0, row["onboard"] / model["capacity"]))
    if len(loads) >= 3:
        loads.sort()
        bot.record_load(loads[len(loads) // 2])


_GAME_FLEET_COUNTS_JS = """
// One consistent snapshot of the counters shown by the game's Routes popup.
const root = document.querySelector('#popContent');
if (!root) return null;
const labels = Array.from(root.querySelectorAll('.row.font-weight-bold > .col-12.exo.text-center.p-2'));
const routeLabel = labels.map(el => String(el.textContent || '').trim())
  .map(value => value.match(/^([0-9]{1,5})\\s+(?:Routes?|Rotas?)$/i))
  .find(match => match !== null);
const numeric = selector => {
  const el = root.querySelector(selector);
  const match = el && String(el.textContent || '').trim().match(/^([0-9]{1,5})$/);
  return match ? Number(match[1]) : null;
};
const parked = numeric('#hParked');
const pending = numeric('#hPending');
if (!routeLabel || parked === null || pending === null) return null;
return {routes: Number(routeLabel[1]), parked, pending};
"""


def manage_fleet(bot: "Bot", *, observation_only: bool = False) -> dict | None:
    cfg = bot.config
    registry = RouteRegistry()
    planning_enabled = observation_only or cfg.get_bool("investment", "planning_enabled", False)
    if planning_enabled:
        registry.invalidate_fleet_coverage()
    if observation_only:
        creation_ready = not has_pending_creation()
        reroute_ready = not has_pending_reroute() and creation_ready
    else:
        creation_ready = recover_pending_creation(bot, registry)
        reroute_ready = recover_pending(bot, registry) and creation_ready
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    measure_load(bot)
    counters = bot.js(_GAME_FLEET_COUNTS_JS)
    roster_verified = False
    if (isinstance(counters, dict) and all(
            type(counters.get(key)) is int and 0 <= counters[key] <= 50000
            for key in ("routes", "parked", "pending"))):
        parked, pending = counters["parked"], counters["pending"]
        bot.update_stats(route_count=counters["routes"], parked=parked, pending=pending,
                         fleet_count_read_at=time.time())
        log_fleet.info("Contagem do jogo: %d com rota + %d estacionadas + %d pendentes = %d aeronaves.",
                       counters["routes"], parked, pending, counters["routes"] + parked + pending)
        roster = bot.js(_GAME_ROSTER_JS)
        roster_verified = registry.record_game_roster(roster, counters["routes"] + parked + pending)
        if not roster_verified:
            log_fleet.warning("Lista completa de IDs do jogo não comprovada; mantendo última coleta válida.")
    else:
        parked = to_int(bot.js("return $('#hParked').text();")) or 0
        pending = to_int(bot.js("return $('#hPending').text();")) or 0
        # update_stats deliberately ignores None. Invalidate the previous
        # complete read so new partial counters cannot look verified.
        bot.update_stats(parked=parked, pending=pending, fleet_count_read_at=0)
        log_fleet.warning("Contagem total da frota não confirmada no cabeçalho de rotas do jogo.")
    log_fleet.info("%d aeronaves estacionadas sem rota, %d pendências na frota.", parked, pending)

    audit_routes(bot, registry)
    native_identity_evidence = {}
    if planning_enabled or cfg.get_bool("options", "audit_route_pages", False):
        visited = audit_routes_live_pages(
            bot, registry, pages_per_cycle=cfg.get_int("settings", "fleet_audit_pages_per_cycle", 3),
            attempt_full=planning_enabled)
        if planning_enabled and not getattr(bot, "stopping", False):
            from fleet_commitment_observations import collect_fleet_commitment_observations

            # Read the independent lists immediately before the final roster
            # check, before any route repairs or aircraft purchases in this step.
            bot._guard(lambda: collect_fleet_commitment_observations(bot, identity_evidence=native_identity_evidence),
                       "conferir hangar e pendências da frota")
            if getattr(bot, "stopping", False):
                return
            bot.open_popup("routes_main.php", "Routes", "nav_routes")
        if (planning_enabled and roster_verified and reroute_ready
                and not getattr(bot, "stopping", False)):
            after_counts = bot.js(_GAME_FLEET_COUNTS_JS)
            after_roster = bot.js(_GAME_ROSTER_JS)
            confirmed = registry.confirm_fleet_coverage(
                after_roster, before_counts=counters, after_counts=after_counts, audited_pages=visited,
                native_identity_evidence=native_identity_evidence)
            log_fleet.info("Inventário e auditoria de rotas: cobertura %s.",
                           "integral correlacionada" if confirmed else "parcial")
    parked_ids = native_identity_evidence.get("parked_ids")
    if (reroute_ready and parked_ids and not bot.stopping
            and (observation_only or cfg.get_bool("options", "collect_market_observations"))):
        from parked_route_quote import collect_parked_route_quote

        bot._guard(lambda: collect_parked_route_quote(bot, parked_ids, refresh_demand=observation_only),
                   "consultar a prévia de rota de uma aeronave estacionada")
    if not observation_only:
        _manage_fleet_actions(bot, registry, parked, creation_ready=creation_ready, reroute_ready=reroute_ready)
    flight_reader = getattr(registry, "next_flight_read_ids", None)
    read_ids = flight_reader(limit=8) if callable(flight_reader) else []
    if read_ids and not bot.stopping:
        try:
            financial = bot.driver.execute_async_script(_FLIGHT_HISTORY_JS, read_ids)
            found = registry.record_flight_readings(
                financial, fuel_price=bot.stock_price("fuel"),
                co2_price=bot.stock_price("co2"))
            log_fleet.info("Histórico financeiro: %d/%d aeronaves com leitura válida.", found, len(read_ids))
        except Exception as exc:  # noqa: BLE001 - read-only financial enrichment must not halt operations
            log_fleet.warning("Histórico financeiro indisponível neste ciclo (%s).", type(exc).__name__)
    bot.close_popup()
    return native_identity_evidence if observation_only else None


def _manage_fleet_actions(bot: "Bot", registry: RouteRegistry, parked: int, *,
                          creation_ready: bool, reroute_ready: bool) -> None:
    cfg = bot.config
    budget = max(1, cfg.get_int("settings", "fleet_actions_per_cycle", 2))
    if not cfg.get_bool("options", "allow_duplicate_routes", True):
        if reroute_ready:
            reconcile_missing_duplicate_aircraft(bot, registry)
        repaired = resolve_duplicate_routes(bot, registry, budget, reroute_ready=reroute_ready)
        budget -= repaired
    if creation_ready and not has_pending_reroute() and cfg.get_bool("options", "auto_route") and parked > 0 and budget > 0:
        # Duplicate-route research and preflight navigate away from the routes
        # list. Restore it before read_parked needs its routesContainer element.
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        created = create_routes(bot, budget)
        budget -= created
        parked -= created
    if reroute_ready and not has_pending_creation() and not has_pending_reroute() and cfg.get_bool("options", "autobuy_aircraft") and budget > 0:
        pending_duplicates = (not cfg.get_bool("options", "allow_duplicate_routes", False)
                              and registry.snapshot(allow_duplicates=False)["duplicate_routes"] > 0)
        if pending_duplicates:
            log_market.info("Compra de aeronave adiada: existem rotas duplicadas aguardando correção.")
        elif parked > 0:
            log_market.info("Não comprarei aeronaves enquanto houver %d estacionadas sem rota.", parked)
        else:
            buy_aircraft(bot)


# ---------------------------------------------------------------------- duplicate-route correction
def reconcile_missing_duplicate_aircraft(bot: "Bot", registry: RouteRegistry) -> None:
    """Retire historical duplicate entries after corroborating an empty detail response."""
    recent = getattr(bot, "recent_fleet", None)
    fleet = recent(180) if callable(recent) else None
    maintenance_ids = {str(ac.id) for ac in fleet or []}
    if not maintenance_ids:
        return
    report = registry.snapshot(allow_duplicates=False)
    stale = [
        row for row in report["relations"]
        if row["duplicate"] and row["aircraft_id"] not in maintenance_ids
        and row.get("source") in ("game", "redirecionamento")
        and time.time() - (row.get("last_seen") or 0) >= 180
    ]
    if not stale:
        return
    status_ids = set(bot.js(_STATUS_AIRCRAFT_JS) or [])
    if not maintenance_ids.issubset(status_ids):
        return
    for row in stale:
        aircraft_id = row["aircraft_id"]
        if bot.stopping:
            break
        if aircraft_id in status_ids or not aircraft_details_missing(bot, aircraft_id):
            continue
        if registry.retire_missing_assignment(aircraft_id, expected_route=row["route_key"]):
            log.info(
                "Controle de rotas: %s (ID %s) ausente do status e da manutenção, "
                "com detalhes vazios no jogo. Registro histórico de rota arquivado.",
                row["registration"], aircraft_id,
            )


def resolve_duplicate_routes(bot: "Bot", registry: RouteRegistry, budget: int,
                             *, reroute_ready: bool = True) -> int:
    """Plan alternatives independently and apply at most one verified change."""
    report = registry.snapshot(allow_duplicates=False)
    if not report["duplicate_routes"]:
        return 0
    log.warning(
        "Controle de rotas: %d rotas duplicadas, %d aeronaves envolvidas.",
        report["duplicate_routes"], report["affected_aircraft"],
    )
    records = {row["aircraft_id"]: row for row in report["relations"]}
    for conflict in report["duplicates"]:
        names = ", ".join(
            f"{aircraft.get('registration') or aircraft.get('id')} (ID {aircraft.get('id')})"
            for aircraft in conflict["aircraft"]
        )
        log.warning(
            "Controle de rotas: duplicidade na rota %s | aeronaves: %s.",
            conflict.get("route") or "não identificada", names,
        )

    def pending(aircraft_id: str, reason: str, *, proposal: Optional[dict] = None) -> None:
        """Expose the precise blocker without altering the verified assignment."""
        item = records.get(str(aircraft_id), {})
        # When the analysis is paused or limited, retain the last profitable
        # proposal instead of erasing useful comparisons from the dashboard.
        if proposal is None and reason in (
            "pendente_limite_ciclo", "aguardando_ativacao_de_analise"
        ):
            proposal = item.get("proposal")
        registry.note(aircraft_id, reason, proposal=proposal)
        origin = item.get("origin") or {}
        destination = item.get("destination") or {}
        details = ""
        if reason == "aguardando_identificacao_da_rota":
            details = (
                f" (IDs dos aeroportos ausentes; códigos disponíveis: "
                f"{origin.get('code') or '?'} ↔ {destination.get('code') or '?'})"
            )
        elif reason == "aguardando_identificacao_da_base":
            details = " (o seletor de bases do jogo não confirmou um ID da rota)"
        elif reason == "rota_fora_das_bases":
            details = " (nenhuma ponta da rota é uma base selecionável; é necessário identificar a localização atual do avião e o controle de troca de rota)"

        elif reason == "sem_destino_com_codigo_validado":
            details = " (pesquisa não exibiu um código IATA/ICAO verificável para a alternativa)"
        elif reason == "aeronave_fora_da_base":
            details = " (o jogo indica que esta aeronave NÃO está numa base; a proposta permanece salva)"
        elif reason == "localizacao_nao_confirmada":
            details = " (o jogo não disponibilizou posição de base desta aeronave)"
        elif reason == "rota_nao_confirmada_no_jogo":
            details = " (rota registrada manualmente ou sem nova leitura do jogo)"
        elif reason == "aeroportos_nao_confirmados":
            details = " (IDs ou códigos de aeroportos insuficientes)"
        elif reason == "comprovacao_desatualizada":
            details = " (evidência da rota ou localização expirou; necessária nova leitura)"
        elif reason == "aguardando_confirmacao_no_jogo":
            details = " (necessário comprovar localização na base e rota atual)"
        elif reason == "troca_automatica_desativada":
            details = " (ative Substituir rotas repetidas automaticamente na aba Frota)"
        elif reason == "sem_alternativa_melhor_que_atual":
            details = " (nenhuma alternativa lucrativa supera a estimativa da rota atual com a margem mínima)"
        elif reason == "aguardando_ativacao_de_analise":
            details = " (análise de rotas repetidas desligada; nenhuma pesquisa enviada ao jogo)"
        if proposal:
            details += (
                f" | alternativa: {proposal.get('destination') or proposal.get('destination_id')}"
                f", lucro estimado USD {fmt(proposal.get('profit_per_day', 0))}/dia"
            )
        log.info(
            "Controle de rotas: %s (ID %s), rota %s: %s%s. "
            "Nenhuma alteração enviada ao jogo.",
            item.get("registration") or aircraft_id, aircraft_id,
            item.get("route_key") or "?",
            reason.replace("_", " "), details,
        )

    # The planner does not change live routes; its own per-cycle budget must
    # be separate from the budget for creating/ordering aircraft.
    cfg = bot.config
    market = load_market()
    targets = []
    keepers = {}
    for duplicate in report["duplicates"]:
        members = [records[a["id"]] for a in duplicate["aircraft"] if a["id"] in records]
        if len(members) < 2:
            continue
        members.sort(key=lambda row: (
            -(row["profit_per_day"] if isinstance(row.get("profit_per_day"), (int, float)) else -1),
            row.get("assigned_at", 0), row["aircraft_id"],
        ))
        for row in members[1:]:
            targets.append(row)
            keepers[row["aircraft_id"]] = members[0]["aircraft_id"]
    # Fairness: unattempted targets first, then oldest last attempt.
    # Without this, the first N repeated routes were researched forever.
    targets.sort(key=lambda row: (
        row.get("last_planned_at") or 0,
        row["aircraft_id"],
    ))
    processed = 0
    if not cfg.get_bool("options", "analyze_duplicate_routes"):
        for row in targets:
            pending(row["aircraft_id"], "aguardando_ativacao_de_analise")
        return 0
    execute = reroute_ready and cfg.get_bool("options", "reroute_duplicates") and not bot.dry_run
    changed = 0
    if execute:
        # This game snapshot is a scheduling hint. The executor proves the
        # exact route and location again independently before any action.
        landed = set(bot.js(_LANDED_DUPLICATES_JS, [row["aircraft_id"] for row in targets]) or [])
        targets.sort(key=lambda row: (row["aircraft_id"] not in landed,
                                     reroute_block_reason(row, verified_hub=True) is not None))
    for row in targets:
        aircraft_id = row["aircraft_id"]
        if processed >= budget or bot.stopping:
            pending(aircraft_id, "pendente_limite_ciclo")
            continue
        processed += 1
        registry.mark_plan_attempt(aircraft_id)
        origin = row.get("origin", {})
        destination = row.get("destination", {})
        hub_id = str(origin.get("id") or "")
        hub_code = origin.get("code") or ""
        current_dest_code = destination.get("code") or ""
        # The route list often exposes only IATA/ICAO codes, not numeric
        # airport IDs. Those codes are sufficient for a read-only lookup
        # against the game's real hub selection, not for guessing an ID.
        if not (hub_id and destination.get("id")) and not (hub_code and current_dest_code):
            pending(aircraft_id, "aguardando_identificacao_da_rota")
            continue
        model = find_model(market, row.get("model") or "")
        if not model or not model.get("speed") or not model.get("fuel"):
            pending(aircraft_id, "aguardando_dados_do_modelo")
            continue
        seats = int(model.get("capacity") or 0)
        if seats <= 0:
            pending(aircraft_id, "aguardando_dados_do_modelo")
            continue
        fuel_price, co2_price = bot.fuel_cost_basis(), bot.co2_cost_basis()
        if not operating_prices_valid(fuel_price, co2_price):
            pending(aircraft_id, "aguardando_custos_operacionais_validos")
            continue
        limit = cfg.get_int("settings", "route_max_distance_big" if seats >= BIG_SEATS else "route_max_distance", 6000)
        if model.get("range"):
            limit = min(limit, int(model["range"]))
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("research_main.php", "routeAction")
        # Route labels are not direction-of-flight proof: for OSL↔DAC
        # either airport may be the actual hub. The unique match in the
        # authenticated game selector decides the planning origin.
        hub_options = bot.js(_HUB_OPTIONS_JS) or []
        HubRegistry().record_options(hub_options)
        owned_hub_ids = {str(option.get("id")) for option in hub_options}
        hub_match = match_hub_options(
            hub_code, current_dest_code, hub_options
        ) if hub_code and current_dest_code else None
        current_origin = None
        if execute:
            departure = landed_departure(bot, row)
            current_origin = by_code(departure) if departure else None
            if current_origin:
                # Native Reroute starts at the aircraft's current airport,
                # including airports outside the company's owned hubs.
                opposite = current_dest_code if departure == hub_code else hub_code
                hub_match = HubMatch(current_origin.game_id, departure, opposite)
        if execute and not hub_match and hub_code and current_dest_code:
            diag = explain_hub_options(hub_code, current_dest_code, hub_options)
            if diag["reason"] == "bases_ambiguas":
                departure = landed_departure(bot, row)
                if departure:
                    hub_match = match_hub_options(hub_code, current_dest_code, hub_options, departure=departure)
        if hub_match:
            hub_id = hub_match.airport_id
            hub_code = hub_match.code
            current_dest_code = hub_match.opposite_code
            if current_origin:
                log.info(
                    "Controle de rotas: %s pousada em %s (ID do jogo %s); "
                    "a alternativa manterá acesso a uma base adquirida.",
                    row["registration"], hub_code, hub_id,
                )
            else:
                log.info(
                "Controle de rotas: %s — aeroporto %s (ID do jogo %s) consta das bases da "
                "companhia; destino atual %s. Isso NÃO confirma a base desta aeronave.",
                row["registration"], hub_code, hub_id, current_dest_code,
                )
        elif not (hub_id and destination.get("id")):
            diag = explain_hub_options(hub_code, current_dest_code, hub_options)
            log.warning(
                "Controle de rotas: %s — seletor de bases: %s | opções %d "
                "(IDs válidos %d, rótulos com possíveis códigos %d), "
                "correspondências %s | exemplos: %s. "
                "A rota pode estar entre aeroportos que não são bases próprias; "
                "nenhuma base será presumida.",
                row["registration"], diag["reason"], diag["total_options"],
                diag["valid_ids"], diag["labels_with_possible_codes"],
                diag["matched"], " / ".join(diag["samples"]) or "(nenhum)",
            )
            pending(
                aircraft_id,
                {"nenhuma_ponta_da_rota_nas_bases": "rota_fora_das_bases",
                 "bases_ambiguas": "aguardando_pouso_para_confirmar_base"}.get(
                    diag["reason"], "aguardando_identificacao_da_base"
                ),
            )
            continue
        # The game's hub picker must prove we are searching the same origin
        # as the existing assignment. Never optimize from an unrelated hub.
        selected = current_origin is not None or bot.js(
            "var e=document.getElementById('hubSelect');"
            "if(!e || !Array.from(e.options).some(x=>x.value===arguments[0]))return false;"
            "e.value=arguments[0];e.dispatchEvent(new Event('change',{bubbles:true}));"
            "return e.value===arguments[0];", hub_id,
        )
        if not selected:
            pending(aircraft_id, "aguardando_confirmacao_da_base")
            continue
        destination_options = []
        for distance in (limit, limit // 2, limit // 4):
            if distance < 500 or bot.stopping:
                break
            options = []
            for candidate in search_routes(
                bot, hub_id, distance, cfg.get_int("settings", "route_min_runway", 5000)
            ):
                # Only a game-verifiable airport code allows comparison with
                # the historical code-only records, in both directions.
                if not candidate.code:
                    continue
                # Each round trip must include an owned base so maintenance
                # and A-checks remain reachable on the assigned route.
                if hub_id not in owned_hub_ids and candidate.arr_id not in owned_hub_ids:
                    continue
                if current_dest_code and candidate.code == current_dest_code:
                    continue
                if destination.get("id") and destination["id"] == candidate.arr_id:
                    continue
                if registry.is_occupied(
                    endpoint(code=hub_code), endpoint(code=candidate.code), aircraft_id
                ):
                    continue
                options.append(candidate)
            destination_options.extend(options)
            if options:
                break
        if not destination_options:
            pending(aircraft_id, "sem_destino_com_codigo_validado")
            continue
        ranked = rank_candidates(
            destination_options, seats=seats, model=model, mode=bot.mode,
            load_factor=bot.load_factor(), fuel_price=fuel_price,
            co2_price=co2_price, premium=cfg.get_bool("options", "auto_seats"),
        )
        alternative, required_profit = best_reroute(
            ranked, current_profit=row.get("profit_per_day"),
            minimum_gain_percent=cfg.get_int("settings", "route_min_profit_gain_pct", 5),
        )
        if alternative is None:
            pending(
                aircraft_id,
                "sem_alternativa_melhor_que_atual" if required_profit is not None
                else "sem_alternativa_lucrativa",
            )
            continue
        candidate, economics = alternative
        proposal = {
            "calculated_at": int(time.time()),
            "baseline_profit_per_day": (
                round(float(row["profit_per_day"]))
                if required_profit is not None else None
            ),
            "minimum_acceptable_profit_per_day": (
                round(required_profit) if required_profit is not None else None
            ),
            "estimated_gain_per_day": (
                round(economics.profit_per_day - float(row["profit_per_day"]))
                if required_profit is not None else None
            ),
            "origin_id": hub_id, "origin_code": hub_code,
            "destination_id": candidate.arr_id, "destination_code": candidate.code,
            "destination": candidate.name, "distance_km": round(candidate.distance),
            "profit_per_day": round(economics.profit_per_day),
            "current_route": row.get("route_key", ""),
        }
        # Confirm the existing route's own live ID and endpoints from the
        # aircraft details before considering grounding/replacing it.
        # This is a read-only probe and never submits fleet_ground.php.
        preflight = check_existing_route(bot, aircraft_id, row)
        proposal["preflight"] = {
            "status": preflight.reason,
            "route_id": preflight.route_id,
            "endpoints": list(preflight.game_endpoints),
        }
        if preflight.route_confirmed:
            log.info(
                "Controle de rotas: pré-validação de %s confirmou "
                "rota interna ID %s e aeroportos %s.",
                row["registration"], preflight.route_id,
                " ↔ ".join(preflight.game_endpoints),
            )
        else:
            log.warning(
                "Controle de rotas: pré-validação de %s pendente: %s. "
                "Nenhuma rota será alterada.",
                row["registration"], preflight.reason,
            )
        # The stored report identifies a collision, but a *fresh*, explicit
        # game reading must confirm the aircraft at base before changing it.
        reason = reroute_block_reason(row, verified_hub=hub_match is not None)
        # In live mode, preflight plus replace_route use fresh game reads.
        # The historical registry often lacks a recent observation for
        # aircraft outside the first page.
        live_candidate = execute and hub_match and preflight.route_confirmed
        if reason and not live_candidate:
            pending(aircraft_id, reason, proposal=proposal)
            continue
        if not preflight.route_confirmed:
            pending(aircraft_id, "prevalidacao_de_rota_pendente", proposal=proposal)
            continue
        if bot.dry_run:
            pending(aircraft_id, "simulacao_redirecionamento", proposal=proposal)
            log.info("[SIMULAÇÃO] Redirecionaria %s para %s (lucro estimado ~ $%s/dia).",
                     row["registration"], candidate.name, fmt(proposal["profit_per_day"]))
            continue
        if live_candidate:
            execute = False
            result = replace_route(
                bot, registry, row, endpoint(hub_id, code=hub_code),
                endpoint(candidate.arr_id, code=candidate.code, name=candidate.name),
                keeper_id=keepers[aircraft_id], expected_id=preflight.route_id,
                profit=economics.profit_per_day,
            )
            if result == "trocada":
                changed += 1
            else:
                registry.note(aircraft_id, result, proposal=proposal)
                log.warning("Controle de rotas: %s • %s.", row["registration"], result.replace("_", " "))
        else:
            pending(aircraft_id, "aguardando_troca_automatica" if cfg.get_bool("options", "reroute_duplicates")
                    else "troca_automatica_desativada", proposal=proposal)

    log.info(
        "Controle de rotas: análise de %d/%d aeronaves com duplicidade neste ciclo; "
        "próximas serão priorizadas por proposta mais antiga.",
        processed, len(targets),
    )
    return changed  # Only confirmed writes consume the live action budget.


# ---------------------------------------------------------------------- routes
def read_parked(bot: "Bot") -> list[ParkedAircraft]:
    bot.ajax("fleet_parked.php", "routesContainer")
    parked = []
    registry = RouteRegistry()
    for row in bot.js(_PARKED_JS) or []:
        if row.get("id"):
            parked.append(ParkedAircraft(row["id"], row["model"], row["reg"] or row["id"], to_int(row["seats"]) or 0))
            registry.unassign(row["id"], row["reg"] or row["id"], row["model"])
    return parked


def search_routes(bot: "Bot", hub_id: str, max_distance: int, min_runway: int, *,
                  persist_demand: bool = False) -> list[RouteCandidate]:
    bot.ajax(
        f"research_main.php?mode=search&rwy={min_runway}&dist={max_distance}&depId={hub_id}&arr=0&arrId=0&charter=0",
        "resResult",
    )
    candidates = read_route_candidates(bot)
    if persist_demand and candidates:
        samples = [{"arr_id": item.arr_id, "distance": item.distance,
                    "y": item.y, "j": item.j, "f": item.f,
                    "event_demand_boosted": item.event_demand_boosted} for item in candidates]
        count = HubExpansionRegistry().record_demand(hub_id, samples)
        log.info("Pesquisa de rotas: %d amostras de demanda persistidas para hub %s.", count, hub_id)
    return candidates


def read_route_candidates(bot: "Bot") -> list[RouteCandidate]:
    """Parse the native result list after a search has loaded."""
    candidates = []
    for row in bot.js(_CANDIDATES_JS) or []:
        if not row.get("arr"):
            continue
        try:
            distance = float(row["distance"])
        except ValueError:
            distance = 0.0
        candidates.append(RouteCandidate(
            row["arr"], row["name"], distance,
            to_int(row["y"]) or 0, to_int(row["j"]) or 0, to_int(row["f"]) or 0, to_int(row["rwy"]) or 0,
            code_from_candidate(row), event_demand_boosted=row.get("event_demand_boosted") is True,
        ))
    return candidates


def _daily_seats_sold(aircraft: ParkedAircraft, model: Optional[dict], distance: float, load: float,
                      mode: GameMode = EASY) -> float:
    """Economy passengers per day one aircraft would carry on a route of *distance* km (80 % of it, as margin)."""
    speed = (model or {}).get("speed") or 700
    legs = 24 / (max(distance, 300) / (speed * mode.speed) + TURNAROUND_H)
    return aircraft.seats * load * legs * 0.8


def _route_demand(candidate: RouteCandidate, premium: bool) -> int:
    """Daily demand in economy slots. With the seat layout by demand, business and first count too (2 and 3 slots)."""
    return candidate.y + 2 * candidate.j + 3 * candidate.f if premium else candidate.y


def _valid_route_profit(value: object) -> bool:
    try:
        return type(value) in (int, float) and isfinite(value) and value > 0
    except OverflowError:
        return False


def _try_stopover(bot, aircraft, origin, reach, limit, runway, economics, available, allow_duplicates):
    if not operating_prices_valid(economics.get("fuel_price"), economics.get("co2_price")):
        return "none", None
    hub_id = origin["id"]
    candidates = [
        candidate for candidate in search_routes(bot, hub_id, limit, runway)
        if candidate.runway >= runway and reach < candidate.distance <= limit and available(candidate)
    ]
    log.info("%s: buscando rota com escala a partir de %s.", aircraft.reg, game_code(hub_id) or hub_id)
    for candidate, _ in rank_candidates(candidates, **economics)[:4]:
        if bot.stopping:
            break
        if not allow_duplicates:
            details = research_details(bot, hub_id, candidate.arr_id) or {}
            if to_int(details.get("occupied")) != 0:
                continue
        stopover = find_stopover(bot, origin, candidate.arr_id, reach, limit, runway)
        if not stopover:
            continue
        outcome = create_route(bot, aircraft, candidate, origin_id=hub_id, stopover=stopover,
                               stopover_economics=economics, allow_duplicates=allow_duplicates)
        if outcome != "none":
            return outcome, candidate
    return "none", None


def create_routes(bot: "Bot", max_routes: int) -> int:
    cfg = bot.config
    parked = read_parked(bot)
    if not parked:
        log.info("Não há aeronaves estacionadas na lista da frota.")
        return 0
    fuel_price, co2_price = bot.fuel_cost_basis(), bot.co2_cost_basis()
    if not operating_prices_valid(fuel_price, co2_price):
        log.warning("Criação de rotas adiada: custos operacionais de combustível ou CO₂ inválidos.")
        return 0
    max_distance = cfg.get_int("settings", "route_max_distance", 2000)
    max_distance_big = cfg.get_int("settings", "route_max_distance_big", 6000)
    min_runway = cfg.get_int("settings", "route_min_runway", 5000)
    market = load_market()
    premium = cfg.get_bool("options", "auto_seats")
    created = 0
    used_pairs: set[str] = set()
    registry = RouteRegistry()
    allow_duplicates = cfg.get_bool("options", "allow_duplicate_routes", True)
    allow_stopover = cfg.get_bool("options", "route_stopover")

    for aircraft in parked:
        if created >= max_routes or bot.stopping:
            break
        # Big aircraft (150+ seats) earn most on long routes; never search beyond what the model can fly.
        configured_limit = max_distance_big if aircraft.seats >= BIG_SEATS else max_distance
        limit = configured_limit
        known = find_model(market, aircraft.model)
        if known and known.get("range"):
            limit = min(limit, int(known["range"]))
        # Creating a route closes the popup, so start from a fresh Routes > Research screen every time.
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("research_main.php", "routeAction")
        HubRegistry().record_options(bot.js(_HUB_OPTIONS_JS) or [])
        hub_id = bot.js("return $('#hubSelect').val() || (typeof depId !== 'undefined' ? String(depId) : null);")
        origin = parked_specs(bot, aircraft.id) if allow_stopover else None
        if origin:
            owned_hubs = {hub["id"] for hub in (bot.js(_HUB_OPTIONS_JS) or [])}
            if origin["id"] not in owned_hubs:
                log.warning("%s: o aeroporto atual não aparece entre as bases próprias.", aircraft.reg)
                continue
            hub_id = origin["id"]
            bot.js("$('#hubSelect').val(arguments[0]);", hub_id)
            limit = min(limit, to_int(origin["range"]) or limit)
        if not hub_id:
            log.warning("Não encontrei a base de origem na busca de rotas.")
            break
        def available(candidate: RouteCandidate, origin_id=hub_id, aircraft_id=aircraft.id) -> bool:
            return candidate.arr_id != str(origin_id) and (allow_duplicates or (
                route_key(endpoint(origin_id), endpoint(candidate.arr_id)) not in used_pairs
                and not registry.is_occupied(endpoint(origin_id), endpoint(candidate.arr_id), aircraft_id)
            ))

        economics = dict(
            seats=aircraft.seats, model=known, mode=bot.mode, load_factor=bot.load_factor(),
            fuel_price=fuel_price, co2_price=co2_price, premium=premium,
        )
        outcome = "none"
        if origin and known and limit < configured_limit and not bot.stopping:
            runway = max(min_runway, to_int(origin["runway"]) or 0) if bot.mode.key == "realism" else min_runway
            outcome, candidate = _try_stopover(
                bot, aircraft, origin, limit, configured_limit, runway, economics, available, allow_duplicates,
            )
        elif allow_stopover and not origin:
            log.info("%s: o jogo não confirmou o aeroporto atual e o alcance para planejar uma escala.", aircraft.reg)
        # Try direct routes when no suitable stopover was found.
        for distance in (limit, limit // 2, limit // 4):
            if outcome != "none" or distance < 500 or bot.stopping:
                break
            candidates = [
                c for c in search_routes(bot, hub_id, distance, min_runway)
                if available(c)
            ]
            # Use the game's known demand and the latest cached aircraft model to
            # estimate daily revenue minus fuel/CO2; missing model data keeps the
            # original demand-based ordering (no fabricated fuel/speed values).
            ranked = rank_candidates(candidates, **economics)
            estimates = {c.arr_id: estimate for c, estimate in ranked}
            profitable = profitable_candidates(ranked)
            has_estimates = any(estimate is not None for _, estimate in ranked)
            if has_estimates:
                tries = [candidate for candidate, _ in profitable[:MAX_ROUTE_TRIES]]
                if not tries:
                    log.warning(
                        "%s: rotas disponíveis até %d km apresentam lucro líquido "
                        "estimado não positivo; nenhuma taxa será paga por essas rotas.",
                        aircraft.reg, distance,
                    )
                    continue
                best = ranked[0][1]
                if best is not None:
                    log.info(
                        "%s: previsão de melhor rota: lucro ~ $%s/dia, receita ~ $%s/dia, "
                        "combustível ~ $%s/dia, CO₂ ~ $%s/dia (estimativas, não valores garantidos).",
                        aircraft.reg, fmt(int(best.profit_per_day)), fmt(int(best.revenue_per_day)),
                        fmt(int(best.fuel_cost_per_day)), fmt(int(best.co2_cost_per_day)),
                    )
            else:
                # No cached model yet: retain the known working demand heuristic.
                sorted_candidates = [candidate for candidate, _ in ranked]
                enough = [
                    c for c in sorted_candidates
                    if _route_demand(c, premium) >= _daily_seats_sold(
                        aircraft, known, c.distance, bot.load_factor(), bot.mode
                    )
                ]
                tries = (enough or sorted_candidates)[:MAX_ROUTE_TRIES]
            if not tries:
                log.info("Nenhuma rota candidata a até %d km (pista >= %d pés).", distance, min_runway)
                continue
            log.info("%s (%s, %d assentos): analisando as %d rotas com maior demanda até %d km ...",
                     aircraft.reg, aircraft.model, aircraft.seats, len(tries), distance)
            for candidate in tries:
                if bot.stopping:
                    break
                details = bot.ajax(f"route_research_route.php?dep={hub_id}&arr={candidate.arr_id}", "rDetails")
                capable = details.find_elements(By.XPATH, f".//*[@id='capAc']/option[starts-with(@value, '{aircraft.id};')]")
                if not capable:
                    log.debug("%s não pode voar para %s (alcance ou pista).", aircraft.reg, candidate.name)
                    continue
                on_route = game_whole_number(bot.js(_ON_ROUTE_JS))
                if not allow_duplicates and on_route != 0:
                    log.debug("%s: ocupação diferente de zero ou desconhecida.", candidate.name)
                    continue
                estimated = estimates.get(candidate.arr_id)
                outcome = create_route(
                    bot, aircraft, candidate, origin_id=hub_id,
                    profit_per_day=estimated.profit_per_day if estimated is not None else None,
                    allow_duplicates=allow_duplicates,
                    route_economics=economics,
                )
                if outcome != "none":
                    break
        if outcome in ("created", "dry"):
            created += 1
            if not allow_duplicates:
                used_pairs.add(route_key(endpoint(hub_id), endpoint(candidate.arr_id)))
        elif outcome == "stop":
            break
        else:
            log.info("%s: nenhuma rota válida (alcance, pista ou rota já utilizada).", aircraft.reg)
    return created


def create_route(bot: "Bot", aircraft: ParkedAircraft, candidate: RouteCandidate,
                 *, origin_id: str = "", reroute: bool = False,
                 profit_per_day: Optional[float] = None, stopover: Optional[Stopover] = None,
                 stopover_economics: Optional[dict] = None, allow_duplicates: bool = True,
                 route_economics: Optional[dict] = None) -> str:
    """Return the outcome, including 'none' when a stopover candidate is rejected before submission."""
    if has_pending_creation():
        return "stop"
    bot.js("if (typeof hideFlightInfo === 'function') { hideFlightInfo(); } arrId = arguments[0];", int(candidate.arr_id))
    url = f"new_route_info.php?id={aircraft.id}&airportId={candidate.arr_id}"
    if stopover:
        try:
            panel = bot.ajax(f"{url}&stopoverId={stopover.id}&ferry=0", "newRouteInfo", timeout=8)
        except TimeoutException:
            log.warning("%s: o jogo não abriu o formulário de rota com escala.", aircraft.reg)
            return "none"
    else:
        panel = bot.ajax(f"{url}&mode=res", "newRouteInfo")
    stop = endpoint(stopover.id, code=game_code(stopover.id)) if stopover else None
    origin = endpoint(origin_id, code=game_code(origin_id))
    destination_code = game_code(candidate.arr_id, "" if stop else candidate.code)
    destination = endpoint(candidate.arr_id, code=destination_code, name=candidate.name)
    name = f"{candidate.name} via {stop['code'] or stop['id']}" if stop else candidate.name
    if stopover:
        verified = read_form(bot, aircraft.id, origin_id, candidate.arr_id, stopover)
        if not verified or not stopover_economics or (not allow_duplicates and verified[3]):
            log.info("%s: formulário da rota com escala não confirmou %s como disponível.", aircraft.reg, name)
            bot.js("$('#newRouteInfo').hide();")
            return "none"
        distance, (y, j, f), fee, _ = verified
        candidate = replace(candidate, distance=distance, y=y, j=j, f=f)
    else:
        direct = read_direct_form(bot, aircraft.id, origin, destination, allow_duplicates=allow_duplicates)
        if direct is None:
            log.info("%s: formulário da rota direta não confirmou %s.", aircraft.reg, name)
            bot.js("$('#newRouteInfo').hide();")
            return "none"
        native_distance, fee, _ = direct
        if abs(native_distance - candidate.distance) > 5:
            bot.js("$('#newRouteInfo').hide();")
            return "none"
        candidate = replace(candidate, distance=native_distance)
    if not bot.can_spend(fee, f"a rota {candidate.name}", essential=not reroute):  # reroutes must preserve cash reserve
        bot.js("$('#newRouteInfo').hide();")
        return "none" if stop else "stop"

    autoprice = panel.find_elements(By.XPATH, ".//*[@id='introAuto']")
    if len(autoprice) != 1:
        bot.js("$('#newRouteInfo').hide();")
        return "none" if stop else "stop"
    bot.click_element(autoprice[0])
    bot.pause(0.8, 1.2)
    prices = read_route_fares(bot)
    if prices is None:
        log.warning("O preço automático não preencheu as passagens de %s; a rota não será criada.", candidate.name)
        bot.js("$('#newRouteInfo').hide();")
        return "none" if stop else "stop"
    economics = stopover_economics if stop else route_economics
    if stop or economics:
        if not stop:
            # The market-price estimate is only a ranking hint. The live form
            # fares must determine the profit stored with a direct route.
            profit_per_day = None
        estimate = estimate_route(
            candidate, **economics, prices=prices, extra_stops=1 if stop else 0,
        )
        if estimate is None:
            if stop or not bot.dry_run:
                log.info("%s: lucro da rota %s não pôde ser confirmado com as tarifas do jogo.",
                         aircraft.reg, name)
                bot.js("$('#newRouteInfo').hide();")
                return "none"
        elif not _valid_route_profit(estimate.profit_per_day):
            log.info("%s: rota %s sem lucro estimado positivo com os preços do jogo.", aircraft.reg, name)
            bot.js("$('#newRouteInfo').hide();")
            return "none"
        else:
            profit_per_day = estimate.profit_per_day
    if ((profit_per_day is None and not bot.dry_run)
            or (profit_per_day is not None and not _valid_route_profit(profit_per_day))):
        log.warning("%s: lucro diário da rota %s desconhecido ou não positivo. A taxa não será paga.",
                    aircraft.reg, name)
        bot.js("$('#newRouteInfo').hide();")
        return "none"
    reg = bot.js("return $('#routeReg').val();") or ""
    summary = (
        f"{name} ({candidate.distance:,.0f} km, demanda Y {candidate.y} / J {candidate.j} / F {candidate.f}) "
        f"para {aircraft.reg} ({aircraft.model}), passagens ${prices[0]} / ${prices[1]} / ${prices[2]}, "
        f"matrícula {reg}, taxa da rota ${fmt(fee)}"
    )
    if bot.stopping:
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    before = bot.read_money() if not bot.dry_run else None
    if stopover:
        current = read_form(bot, aircraft.id, origin_id, candidate.arr_id, stopover)
        unchanged = current == verified
    else:
        current = read_direct_form(bot, aircraft.id, origin, destination, allow_duplicates=allow_duplicates)
        unchanged = current == direct
    reserve = bot.config.get_int("settings", "cash_reserve", 0) if reroute else 0
    if not unchanged or read_route_fares(bot) != prices:
        log.warning("%s: formulário ou tarifas da rota mudaram antes da criação.", aircraft.reg)
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    record_native_route_quote(
        bot, aircraft_id=aircraft.id, origin_id=origin_id, destination_id=candidate.arr_id,
        stopover_id=stopover.id if stopover else None, distance=current[0], fee=fee,
        occupied=current[3] if stopover else current[2], fares=prices,
        total_demand=current[1] if stopover else None,
    )
    if bot.dry_run:
        log.info("[SIMULAÇÃO] Criaria a rota %s.", summary)
        bot.notify(f"🧪 SIMULAÇÃO: criaria a rota {esc(summary)}.", silent=True, category="simulation")
        bot.js("$('#newRouteInfo').hide();")
        return "dry"
    if before is None or before - fee < reserve:
        log.warning("%s: saldo da rota mudou antes da criação.", aircraft.reg)
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    button = panel.find_element(By.XPATH, ".//*[@id='btnCreateNewRoute']")
    origin["name"] = bot.js(
        "var e=document.getElementById('hubSelect');"
        "return e && e.selectedIndex>=0 ? e.options[e.selectedIndex].text : '';"
    ) or ""
    registry = RouteRegistry()
    registry.invalidate_fleet_coverage()
    job = stage_creation(aircraft, origin, destination, stop, fee, profit_per_day, reroute=reroute)
    if job is None:
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    bot.click_element(button)
    response = bot.wait_text("//*[@id='routeNewAction']", timeout=15)
    if stop:
        confirmed = confirm_stopover(bot, aircraft.id, origin, destination, stop)
    else:
        confirmed = confirm_direct_route(bot, aircraft.id, origin, destination)
    if not confirmed:
        log.warning("%s: o jogo ainda não confirmou a rota %s. Será conferida na próxima leitura da frota.",
                    aircraft.reg, name)
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    if not finish_creation(bot, registry, job, at_base=True):
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    log.info("%s: %s. %s", "Rota alterada" if reroute else "Rota criada", summary, clean_response(response))
    bot.notify(f"🛫 <b>Rota criada</b>: {esc(summary)}.\n{esc(clean_response(response, 200))}".rstrip(), category="routes")
    bot.js("$('#newRouteInfo').hide();")
    return "created"


# ---------------------------------------------------------------------- aircraft market
def read_models(bot: "Bot") -> list[AircraftModel]:
    models = []
    for row in bot.js(_MODELS_JS) or []:
        if not row.get("id"):
            continue
        models.append(AircraftModel(
            row["id"], row["name"], to_int(row["range"]) or 0, to_int(row["speed"]) or 0,
            to_int(row["capacity"]) or 0, to_int(row["fuel"]) or 0, to_int(row["price"]) or 0,
        ))
    return models


def score_models(bot: "Bot", models: list[AircraftModel]) -> None:
    """Estimate daily profit and return for every model, on the routes it will actually fly."""
    cfg = bot.config
    fuel_price = bot.fuel_cost_basis()
    co2_price = bot.co2_cost_basis()
    load = bot.load_factor()
    short = cfg.get_int("settings", "route_max_distance", 2000)
    long = cfg.get_int("settings", "route_max_distance_big", 6000)
    for model in models:
        distance = min(model.range_km, long if model.capacity >= BIG_SEATS else short)
        model.profit = daily_profit(model, distance, load, fuel_price, co2_price, bot.mode)
        model.score = model.profit / model.price if model.price > 0 else 0.0


def payback_days(model: AircraftModel) -> float:
    return 1 / model.score if model.score > 0 else float("inf")


def buy_aircraft(bot: "Bot") -> None:
    if has_pending_creation():
        log_market.warning("Compra adiada: criação de rota pendente de conciliação.")
        return
    cfg = bot.config
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    bot.ajax("ac_orders.php?first=true", "routeAction")
    models = read_models(bot)
    if not models:  # the list sometimes renders a moment after the Ajax call returns
        bot.pause(1.5, 2.0)
        models = read_models(bot)
    if not models:
        log_market.warning("A lista do mercado de aeronaves está vazia.")
        return
    score_models(bot, models)
    save_market([{"id": m.id, "name": m.name, "price": m.price, "capacity": m.capacity, "range": m.range_km,
                  "speed": m.speed, "fuel": m.fuel, "score": round(m.score, 4), "profit": int(m.profit)}
                 for m in models])

    stats = bot.stats()
    if stats.money is None:
        log_market.warning("Saldo desconhecido; nenhuma aeronave será comprada.")
        return
    reserve = cfg.get_int("settings", "cash_reserve", 0)
    budget = stats.money - reserve
    max_price = cfg.get_int("settings", "aircraft_max_price", 0)
    hangar_free = stats.hangar_free

    goal_name = cfg.get("settings", "goal_model") if cfg.get_bool("options", "save_for_goal") else ""
    if goal_name:
        save_for_goal(bot, models, goal_name, budget, reserve, max_price, hangar_free)
        return

    if hangar_free is not None and hangar_free < 1:
        log_market.info("Hangar cheio: não há vaga para outra aeronave.")
        return
    preferred = cfg.get("settings", "aircraft_model")
    if preferred:
        wanted = [m for m in models if m.name.lower() == preferred.lower()] or \
                 [m for m in models if preferred.lower() in m.name.lower()]
        if not wanted:
            log_market.warning("Não encontrei o modelo '%s' no mercado.", preferred)
            return
        choice = wanted[0]
        if choice.price > budget:
            log_market.info("%s custa $%s, acima dos $%s disponíveis após a reserva de caixa.", choice.name, fmt(choice.price), fmt(budget))
            return
    else:
        affordable = [m for m in models if 0 < m.price <= budget and (max_price == 0 or m.price <= max_price) and m.score > 0]
        if not affordable:
            log_market.info("Nenhuma aeronave dentro dos $%s disponíveis após a reserva de caixa.", fmt(budget))
            return
        affordable.sort(key=lambda m: m.score, reverse=True)
        choice = affordable[0]
        log_market.info("Aeronaves mais rentáveis: %s", ", ".join(f"{m.name} ({m.score * 100:.0f}%/dia, ${fmt(m.price)})" for m in affordable[:3]))
    order_aircraft(bot, choice)


def save_for_goal(bot: "Bot", models: list[AircraftModel], goal_name: str, budget: int, reserve: int,
                  max_price: int, hangar_free: Optional[int]) -> None:
    """Savings mode: buy the goal aircraft as soon as it fits, and meanwhile only aircraft that
    pay for themselves well before the goal would be reached (they make the goal come sooner).
    With the automatic goal the target is the next step of the growth ladder."""
    stats = bot.stats()
    if is_auto_goal(goal_name):
        cfg = bot.config
        pick = pick_ladder([{"name": m.name, "price": m.price, "profit": m.profit} for m in models
                            if max_price == 0 or m.price <= max_price],
                           stats.income_day, cfg.get_int("settings", "ladder_budget_days", 1),
                           cfg.get_int("settings", "ladder_max_payback", 5), fallback_budget=max(budget, 0))
        goal = next((m for m in models if pick and m.name == pick["name"]), None)
        if goal is None:
            log_market.info("Progressão: nenhuma aeronave atende ao orçamento e ao prazo de retorno.")
            return
        log_market.info("Progressão: próxima aeronave %s (%s, %d assentos, rende ~%s/dia e se paga em ~%.1f dias).",
                        goal.name, fmt_money(goal.price), goal.capacity, fmt_money(int(goal.profit)), payback_days(goal))
    else:
        goal = next((m for m in models if m.name.lower() == goal_name.lower()), None) or \
            next((m for m in models if goal_name.lower() in m.name.lower()), None)
    if goal is None:
        log_market.warning("Não encontrei a aeronave desejada '%s' no mercado; nenhuma compra até corrigir a meta.", goal_name)
        return
    bot.update_stats(goal_price=goal.price)
    progress = goal_progress(goal.price, stats.money, reserve, stats.income_day)
    if progress is None:  # no price for the goal in the market list, or the balance is unknown
        log_market.info("Meta %s: sem preço ou saldo disponível; nenhuma compra neste ciclo.", goal.name)
        return
    status = (f"Objetivo {goal.name}: {fmt_money(progress['have'])} de {fmt_money(goal.price)} ({progress['pct']:.0f}%), "
              f"faltam {fmt_money(progress['missing'])}, previsão {fmt_days(progress['eta_days'])}")

    if progress["reached"]:
        if hangar_free is not None and hangar_free < 1:
            log_market.info("%s. Há saldo, mas não há vaga no hangar; será ampliado no próximo ciclo.", status)
            return
        log_market.info("🎯 Meta alcançada! %s", status)
        order_aircraft(bot, goal, goal=True)
        return

    if not bot.config.get_bool("options", "goal_invest"):
        log_market.info("%s. Apenas economizando.", status)
        return
    eta = progress["eta_days"]
    if eta is None:
        log_market.info("%s. Ainda não conheço o ritmo da receita; apenas economizando.", status)
        return
    if hangar_free is not None and hangar_free < 2:
        log_market.info("%s. Reservando a última vaga do hangar para a meta.", status)
        return
    candidates = [m for m in models
                  if m.name != goal.name and 0 < m.price <= budget and (max_price == 0 or m.price <= max_price)
                  and payback_days(m) * GOAL_SAFETY < eta]
    if not candidates:
        log_market.info("%s. Nenhuma outra aeronave acessível oferece retorno antes da meta; economizando.", status)
        return
    candidates.sort(key=lambda m: m.score, reverse=True)
    choice = candidates[0]
    log_market.info("%s. Comprando um %s porque se paga em ~%.1f dias e antecipa a meta.",
                    status, choice.name, payback_days(choice))
    order_aircraft(bot, choice)


def order_aircraft(
    bot: "Bot", choice: AircraftModel, goal: bool = False,
    hub_id: str | int | None = None,
    *, expected_checkout_cost: int | None = None,
    expected_engine_id: str | None = None,
) -> bool:
    """Order using the native #hubSelection value when a delivery ID is supplied.

    For a planned purchase, the caller must resolve the plan's airport ID via
    verified delivery-hub mapping before passing it as ``hub_id``. The two
    native selectors use distinct identifier namespaces.
    """
    plan_requested = any(value is not None for value in (
        hub_id, expected_checkout_cost, expected_engine_id,
    ))
    if plan_requested:
        if type(hub_id) is int:
            normalized_hub_id = str(hub_id)
        elif type(hub_id) is str:
            normalized_hub_id = hub_id.strip()
        else:
            normalized_hub_id = ""
        if not re.fullmatch(r"[1-9][0-9]{0,13}", normalized_hub_id):
            log_market.warning(
                "Compra planejada de %s bloqueada: ID de base ausente ou inválido.",
                choice.name,
            )
            return False
        if type(expected_checkout_cost) is not int or expected_checkout_cost <= 0:
            log_market.warning(
                "Compra planejada de %s bloqueada: preço final ausente ou inválido.",
                choice.name,
            )
            return False
        if type(expected_engine_id) is not str or not expected_engine_id.strip():
            log_market.warning(
                "Compra planejada de %s bloqueada: ID da variante de motor ausente ou inválido.",
                choice.name,
            )
            return False
        hub_id = normalized_hub_id
        expected_engine_id = expected_engine_id.strip()

    if plan_requested and not bot.dry_run:
        from investment_policy import InvestmentPolicy

        policy_report = InvestmentPolicy.from_config(bot.config).report()
        if not policy_report["execution_available"]:
            log_market.warning(
                "Encomenda de %s bloqueada pelo gate %s.",
                choice.name, policy_report["release_gate"],
            )
            return False

    detail = bot.ajax(f"ac_orders.php?mode=detail&id={choice.id}&charter=0", "acModel")
    # O motor só pode ser escolhido antes de encomendar. Uma preferência
    # explícita NÃO aceita fallback silencioso para a seleção padrão do jogo.
    from engine_selection import (
        EngineSelectionError, prepare_engine, read_engine_catalog,
        require_verified_checkout_price, verify_engine_selection,
    )
    from engine_detail import FinalCheckoutPrice
    from aircraft_order_hub import verify_order_hub_selection

    try:
        selected_hub_id, hub_changed = prepare_order_hub(bot, hub_id)
        preference = bot.config.get("settings", "engine_preference", "default")
        if plan_requested:
            motor = prepare_engine(bot, preference, expected_engine_id=expected_engine_id)
            if selected_hub_id != hub_id:
                raise AircraftOrderHubError("O ID da base preparada diverge do plano aprovado.")
        else:
            motor = prepare_engine(bot, preference)
    except EngineSelectionError as exc:
        log_market.warning("Compra de %s bloqueada: %s", choice.name, exc)
        return False
    except AircraftOrderHubError as exc:
        log_market.warning("Compra de %s bloqueada: %s", choice.name, exc)
        return False

    if (motor and not bot.dry_run) or hub_changed:
        # Alterações de motor ou base podem reconstruir todo o fragmento Ajax.
        detail = bot.driver.find_element(By.ID, "acModel")
    low = detail.find_elements(By.XPATH, ".//*[@id='accountLow']")
    if low and low[0].is_displayed():
        log_market.info("O jogo informa que não há saldo suficiente para um %s.", choice.name)
        return False
    reg = bot.js("return $('#acReg').val();") or ""
    quoted_cost = expected_checkout_cost if plan_requested else choice.price
    summary = f"1 x {choice.name} por ${fmt(quoted_cost)} (matrícula {reg}, {choice.capacity} passageiros, {fmt(choice.range_km)} km de autonomia)"
    if motor:
        summary += f" | motor: {motor}"
    summary += f" | base: {selected_hub_id}"
    if bot.dry_run and not plan_requested:
        log_market.info("[SIMULAÇÃO] Encomendaria %s.", summary)
        bot.notify(f"🧪 SIMULAÇÃO: encomendaria {esc(summary)}.", silent=True, category="simulation")
        return True

    # Releia a chave imediatamente antes do pré-voo, pois o operador pode
    # suspender a compra automática durante a pesquisa do mercado.
    if not bot.dry_run and not plan_requested:
        get_bool = getattr(bot.config, "get_bool", None)
        if callable(get_bool) and not get_bool("options", "autobuy_aircraft", True):
            log_market.warning("Encomenda de %s cancelada: compra automática desativada.", choice.name)
            return False

    confirmed_cost = choice.price
    # Aquisições planejadas exigem preço integral modelo+motor, identidade
    # exata aprovada e duas leituras estáveis do checkout.
    if plan_requested:
        try:
            engine_snapshot = read_engine_catalog(bot)
            from game_source_probe import probe_game_sources

            if engine_snapshot.selected_engine_id != expected_engine_id:
                raise EngineSelectionError("O ID do motor selecionado diverge do plano aprovado.")

            def verified_checkout() -> tuple[int, str]:
                report = probe_game_sources(bot)
                checkout = report.get("aircraft_checkout_diagnostics")
                selection = report.get("aircraft_order_hub_selection")
                if not isinstance(checkout, dict) or not isinstance(selection, dict):
                    raise ValueError("O diagnóstico do formulário de encomenda está ausente.")
                if checkout.get("detail_model_id") != str(choice.id):
                    raise ValueError("O modelo aberto no formulário diverge do plano.")
                if (checkout.get("model_hub_correlated") is not True
                        or selection.get("selected_hub_id") != selected_hub_id
                        or selection.get("status") != "dom_consistent"):
                    raise ValueError("A base e o modelo não correspondem ao painel aprovado.")
                if (checkout.get("ajax_idle_confirmed") is not True
                        or checkout.get("detail_loading") is not False
                        or checkout.get("ajax_active") is not False):
                    raise ValueError("O formulário de encomenda ainda está atualizando.")
                if checkout.get("price_verified") is not True:
                    raise ValueError("O preço final ainda não possui fonte verificada.")
                cost = checkout.get("checkout_cost")
                source = checkout.get("price_source")
                if (type(cost) is not int or cost <= 0
                        or cost != expected_checkout_cost
                        or checkout.get("price_includes_engine") is not True
                        or source not in ("data_final_price", "data_total_price")):
                    raise ValueError("O custo final com motor diverge do plano ou não foi comprovado.")
                return cost, source

            first_price = verified_checkout()

            verified_motor = verify_engine_selection(bot, engine_snapshot)
            if motor and verified_motor != motor:
                raise EngineSelectionError("O motor confirmado diverge do motor preparado para o plano.")
            selected_hub_id = verify_order_hub_selection(bot, selected_hub_id)
            second_price = verified_checkout()
            if second_price != first_price:
                raise ValueError("O preço final mudou durante as verificações de motor e base.")
            verify_engine_selection(bot, engine_snapshot)
            checkout_price = FinalCheckoutPrice(
                engine_id=engine_snapshot.selected_engine_id,
                amount_usd=second_price[0],
                source=second_price[1],
                status="verified",
                reason=None,
            )
            confirmed_cost = require_verified_checkout_price(
                engine_snapshot,
                expected_engine_id=expected_engine_id,
                checkout_price=checkout_price,
            )
            # Consultar o painel atual após as leituras, pois o aviso pode
            # aparecer durante uma atualização do formulário.
            detail = bot.driver.find_element(By.ID, "acModel")
            if any(warning.is_displayed() for warning in detail.find_elements(By.XPATH, ".//*[@id='accountLow']")):
                raise ValueError("O jogo informa saldo insuficiente após a validação do checkout.")
        except Exception as exc:
            log_market.warning("Pré-voo de %s não confirmado. Encomenda bloqueada: %s", choice.name, exc)
            return False

    if bot.dry_run:
        log_market.info("[SIMULAÇÃO] Encomendaria %s.", summary)
        bot.notify(f"🧪 SIMULAÇÃO: encomendaria {esc(summary)}.", silent=True, category="simulation")
        return True

    if plan_requested and not bot.dry_run:
        from investment_policy import InvestmentPolicy

        policy_report = InvestmentPolicy.from_config(bot.config).report()
        if not policy_report["execution_available"]:
            log_market.warning(
                "Encomenda de %s cancelada pelo gate %s durante a validação.",
                choice.name, policy_report["release_gate"],
            )
            return False

    before = bot.read_money()
    RouteRegistry().invalidate_fleet_coverage()
    bot.click_element(detail.find_element(By.XPATH, ".//*[@id='btnPurchaseIntro']"))
    response = bot.wait_text("//*[@id='orderAction']", timeout=15)
    if not bot.confirm_purchase(before, confirmed_cost, f"o pedido de {choice.name}", "orderAction"):
        return False
    bot.spent(confirmed_cost, invest=True)
    bot.count("aircraft")
    free = bot.stats().hangar_free
    if free is not None:
        bot.update_stats(hangar_free=max(0, free - 1))
    log_market.info("Pedido: %s. %s", summary, clean_response(response))
    title = "🎯 <b>Meta alcançada! Aeronave encomendada</b>" if goal else "🛒 <b>Aeronave encomendada</b>"
    bot.notify(f"{title}: {esc(summary)}.\n{esc(clean_response(response, 200))}".rstrip(), category="aircraft")
    return True
