"""Plan a single stop using the game's airport map and native route form."""
from __future__ import annotations

import re
from dataclasses import dataclass

from airport_catalog import game_code
from helpers import game_whole_number, to_int
from route_registry import endpoint, endpoint_matches

_ID = re.compile(r"[0-9]{1,14}")
ROUTE_EVENT_WARNING_JS = r"/\bDemand is currently boosted due to a special event\b/i"

# The fragments contain map callbacks. Parse their data in detached documents
# so research does not change the map state or run any of the returned scripts.
_READ = r"""
const [path, aircraft, done] = arguments;
const url = new URL(path, location.href);
if (typeof fbSig !== 'undefined') url.searchParams.set('fbSig', fbSig);
fetch(url, {cache:'no-store', signal:AbortSignal.timeout(5000), redirect:'error'})
  .then(async response => {
    if (!response.ok) return null;
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (aircraft) {
      const script = Array.from(page.scripts, node => node.textContent).join('\n');
      const reg = page.getElementById('ac-reg-' + aircraft);
      const specs = reg?.parentElement.querySelectorAll('.xs-text');
      const model = Array.from(specs || [], node => node.textContent)
        .map(text => text.match(/([\d,]+)\s*km\s*\/\s*[\d,.]+\s*kph\s*\/\s*([\d,]+)\s*ft/i))
        .find(Boolean);
      const lat = script.match(/\bvar startLat\s*=\s*(-?[\d.]+);/);
      const lon = script.match(/\bvar startLon\s*=\s*(-?[\d.]+);/);
      if (!model || !lat || !lon) return null;
      const airports = (window.airportIconData || []).filter(a =>
        Math.abs(Number(a.lat) - Number(lat[1])) < 0.001 &&
        Math.abs(Number(a.lon) - Number(lon[1])) < 0.001);
      return airports.length === 1 ? {id:String(airports[0].Id), range:model[1], runway:model[2]} : null;
    }
    const detail = page.getElementById('rDetails') || page.body;
    const roads = detail.querySelectorAll('.glyphicons-road');
    const countRows = Array.from(detail.querySelectorAll('table.m-text:not(.table-bordered) tr'));
    const countCell = label => {
      const rows = countRows.filter(row => row.cells.length === 2 && row.cells[0].textContent.trim() === label
        && row.cells[1].classList.contains('text-right'));
      return rows.length === 1 ? rows[0].cells[1].textContent.trim() : null;
    };
    const onRoute = countCell('A/C on route');
    const capableMenus = detail.querySelectorAll('select#capAc');
    const capableAircraft = capableMenus.length === 1
      ? Array.from(capableMenus[0].options).filter(option => !option.disabled && option.value !== '')
          .map(option => /^([1-9][0-9]{0,13});/.exec(option.value)?.[1] ?? null)
      : null;
    const rowTexts = table => Array.from(table.rows, row => Array.from(row.cells, cell => cell.textContent.trim()));
    const paxTables = Array.from(detail.querySelectorAll('table.table-bordered'), rowTexts)
      .filter(rows => rows[0]?.join('|') === '|Y class|J class|F class');
    const paxRows = [];
    if (paxTables.length === 1) {
      // Cargo shares the table and repeats the same row labels under a new header.
      for (const row of paxTables[0].slice(1)) {
        if (row[0] !== 'Daily' && row[0] !== 'Today') break;
        paxRows.push(row);
      }
    }
    const demandRow = label => {
      const rows = paxRows.filter(row => row[0] === label);
      if (rows.length !== 1 || rows[0].length !== 4) return null;
      const [, y, j, f] = rows[0];
      return {y, j, f};
    };
    const codes = Array.from(detail.querySelectorAll('.row .col-4 .xl-text'), node => node.textContent.trim());
    return {codes, runways:Array.from(roads, node => node.parentElement.textContent.trim()),
            occupied:onRoute, occupancy_label:onRoute !== null ? 'A/C on route' : null,
            observed_capable_aircraft:countCell('A/C capable'),
            capable_aircraft_ids:capableAircraft,
            observed_daily_demand:demandRow('Daily'), observed_today_demand:demandRow('Today'),
            event_demand_boosted:EVENT_WARNING.test(detail.textContent || '') ? true : null};
  }).then(done, () => done(null));
""".replace("EVENT_WARNING", ROUTE_EVENT_WARNING_JS)

_CANDIDATES = r"""
const [from, to, range, limit] = arguments;
const airports = window.airportIconData || [];
const origin = airports.find(a => String(a.Id) === from);
const destination = airports.find(a => String(a.Id) === to);
if (!origin || !destination || typeof getDistance !== 'function') return [];
const distance = (a, b) => getDistance(+a.lat, +a.lon, +b.lat, +b.lon);
if (distance(origin, destination) <= range) return [];
return airports.filter(a => /^\d+$/.test(a.Id) && a !== origin && a !== destination)
  .map(a => ({id:String(a.Id), first:distance(origin,a), second:distance(a,destination)}))
  .filter(a => a.first > 0 && a.first <= range && a.second > 0 && a.second <= range
              && a.first + a.second <= limit)
  .sort((a,b) => a.first + a.second - b.first - b.second)
  .slice(0, 8);
"""

_FORM = r"""
const [aircraft, destination, stop] = arguments;
const panel = document.querySelector('#newRouteInfo #newRouteContainer');
if (!panel) return null;
const endpoints = panel.querySelector('.row.p-0');
const codes = Array.from(endpoints?.querySelectorAll('.col-3.m-text > b') || [],
  node => node.textContent.trim().toUpperCase());
const via = panel.querySelector('.row > .col-12.text-center.s-text > b > b')?.textContent.trim().toUpperCase();
const occupied = panel.querySelectorAll('.row.p-1 > .col-4.text-right.s-text');
const fees = panel.querySelectorAll('.text-danger.font-weight-bold');
const daily = panel.querySelector('table.s-text')?.rows[2];
const button = panel.querySelector('#btnCreateNewRoute');
const prefix = 'new_route_info.php?mode=do&id=' + aircraft + '&airportId=' + destination + '&';
const script = Array.from(panel.closest('#newRouteInfo').querySelectorAll('script'), node => node.textContent).join('\n');
const submit = script.split(prefix).slice(1);
const bound = submit.length > 0 && submit.every(t => t.split("'routeNewAction'")[0].includes('&stopoverId=' + stop + '&'));
return {codes, via, bound, ready:!!button && !button.disabled && !button.classList.contains('not-active'),
        distance:endpoints?.querySelector('.col-2 > span')?.textContent.trim(),
        occupied:occupied.length === 1 ? occupied[0].textContent.trim() : null,
        fee:fees.length === 1 ? fees[0].textContent.trim() : null,
        demand:daily ? Array.from(daily.cells, cell => cell.textContent.trim()) : []};
"""


_FARES = r"""
const roots = document.querySelectorAll('#newRouteInfo');
if (roots.length !== 1) return null;
const root = roots[0];
const buttons = root.querySelectorAll('#btnCreateNewRoute');
if (buttons.length !== 1 || buttons[0].disabled || buttons[0].classList.contains('not-active')) return null;
return ['eSeat', 'bSeat', 'fSeat'].map(id => {
    const fields = root.querySelectorAll('[id="' + id + '"]');
    if (fields.length !== 1) return null;
    return {value:fields[0].value, disabled:fields[0].disabled === true};
});
"""


def read_route_fares(bot):
    """Read all three fares from the active native route form without changing it."""
    fields = bot.js(_FARES)
    if not isinstance(fields, list) or len(fields) != 3:
        return None
    fares = []
    for field in fields:
        if not isinstance(field, dict) or type(field.get("disabled")) is not bool:
            return None
        value = field.get("value")
        price = 0 if field["disabled"] and value == "" else game_whole_number(value)
        if price is None or (price == 0 and not field["disabled"]):
            return None
        fares.append(price)
    return tuple(fares) if any(fares) else None


@dataclass(frozen=True)
class Stopover:
    id: str
    first: float
    second: float

    @property
    def distance(self) -> float:
        return self.first + self.second


def parked_specs(bot, aircraft_id):
    if not _ID.fullmatch(aircraft_id):
        return None
    url = f"flight_info.php?id={aircraft_id}"
    specs = bot.driver.execute_async_script(_READ, url, aircraft_id)
    if not specs and bot.js("return Number(window.statusData?.[arguments[0]]?.routeId) === 0;", aircraft_id):
        specs = bot.driver.execute_async_script(_READ, f"{url}&mode=reroute", aircraft_id)
    return specs


def research_details(bot, origin_id, destination):
    return bot.driver.execute_async_script(
        _READ, f"route_research_route.php?dep={origin_id}&arr={destination}", "",
    )


def find_stopover(bot, origin, destination, aircraft_range, max_distance, min_runway):
    suggestions = bot.js(_CANDIDATES, origin["id"], destination, aircraft_range, max_distance) or []
    for row in suggestions:
        stop = Stopover(row["id"], row["first"], row["second"])
        if not _ID.fullmatch(stop.id):
            continue
        details = research_details(bot, origin["id"], stop.id) or {}
        runways = details.get("runways", [])
        route = details.get("codes", [])
        if (len(route) == 2 and _same_airports((origin["id"], stop.id), route)
                and len(runways) == 2 and all((to_int(runway) or 0) >= min_runway for runway in runways)):
            return stop
    return None


def _same_airports(ids, codes):
    return all(code and endpoint_matches(endpoint(id_, code=game_code(id_)), endpoint(code=code))
               for id_, code in zip(ids, codes))


def read_form(bot, aircraft_id, origin, destination, stop):
    form = bot.js(_FORM, aircraft_id, destination, stop.id)
    if not form or not form["bound"] or not form["ready"] or len(form["codes"]) != 2:
        return None
    if not _same_airports((origin, destination, stop.id), (*form["codes"], form.get("via"))):
        return None
    distance = game_whole_number(form["distance"])
    demand = [game_whole_number(value) for value in form["demand"]]
    fee = game_whole_number(form["fee"], currency=True)
    occupied = game_whole_number(form["occupied"])
    if (distance is None or abs(distance - stop.distance) > 5 or fee is None or fee < 0
            or occupied is None or len(demand) != 3 or any(value is None for value in demand)):
        return None
    return distance, demand, fee, occupied
