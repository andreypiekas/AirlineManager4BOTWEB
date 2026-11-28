"""Conservative, read-only observations from the authenticated game DOM."""
from __future__ import annotations

import logging
import math
import re
import threading
import time

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from hub_expansion import MAX_AGE_SECONDS as HUB_RESEARCH_MAX_AGE_SECONDS, HubExpansionRegistry
from hub_registry import HubRegistry
from opportunity_models import DEFAULT_MAX_AGE_SECONDS
from route_stopover import ROUTE_EVENT_WARNING_JS
from engine_catalog import EngineCatalogRegistry, MODEL_ROSTER_JS
from engine_detail import (
    MODEL_DETAIL_IDENTITY_JS, parse_displayed_metrics, parse_operational_requirements, parse_seat_observation,
)
from engine_selection import (
    EngineSelectionError, _ENGINE_OPTIONS_JS, _SET_ENGINE_JS, parse_engine_catalog,
)

log = logging.getLogger("am4bot.observations")

_ROUTE_SEARCH_SAMPLE_LIMIT = 50  # Observed in authenticated owned and custom departures.
_COUNTRY_SEARCH_MIN_CEILING_KM = 500  # The native form normalizes smaller ceilings.
_COUNTRY_DIRECT_AUDIT_LIMIT = 24
_COUNTRY_DIRECT_AUDIT_SECONDS = 20
_COUNTRY_DIRECT_AIRPORT_SECONDS = 8
_ROUTE_DESTINATION_BATCH_SIZE = 8
_ROUTE_DESTINATION_BUDGET_SECONDS = 180

# The engine groups and model identity must come from the same synchronous DOM
# snapshot. Separate stable reads can straddle an AJAX panel replacement and
# mistakenly assign one model's engines to another model. Keep the existing
# engine parser shared with the purchase flow.
_ENGINE_DETAIL_SNAPSHOT_JS = r"""
const panel = document.querySelector('#acModel');
if (!panel || document.querySelectorAll('#acModel').length !== 1 ||
    (window.jQuery && window.jQuery.active > 0) ||
    panel.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const identity = """ + MODEL_DETAIL_IDENTITY_JS + r"""(panel);
if (!identity) return null;
const groups = (() => {
""" + _ENGINE_OPTIONS_JS + r"""
})();
const metricLabels = new Set(['cruise speed', 'velocidade de cruzeiro', 'capacity', 'capacidade',
  'runway required', 'pista necessaria', 'range', 'alcance', 'consumption', 'consumo',
  'co2 emission', 'co₂ emission', 'emissao de co2', 'emissao de co₂',
  'a-check', 'maint check', 'verificacao de manutencao',
  'pilots', 'pilotos', 'crew', 'tripulacao', 'engineers', 'engenheiros', 'tech', 'tecnicos',
  'delivery time', 'tempo de entrega']);
const normalized = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
const rows = Array.from(panel.querySelectorAll('tr, .row'))
  .filter(row => row.children.length === 2)
  .map(row => Array.from(row.children, cell => String(cell.textContent || '').trim()))
  .filter(row => metricLabels.has(normalized(row[0])));
const costs = Array.from(panel.querySelectorAll('#acCost'),
  el => String(el.textContent || '').trim());
const seatObservation = (() => {
  const steps = panel.querySelectorAll('#step2');
  if (steps.length !== 1) return null;
  const step = steps[0];
  const visible = el => el.getClientRects().length > 0 &&
    !['hidden', 'collapse'].includes(window.getComputedStyle(el).visibility);
  const shown = visible(step);
  const result = {source: shown ? 'visible_native_form' : 'hidden_native_template'};
  for (const [key, selector] of [['y', '#eSeats'], ['j', '#bSeats'], ['f', '#fSeats']]) {
    const matches = panel.querySelectorAll(selector);
    if (matches.length !== 1 || !step.contains(matches[0]) || visible(matches[0]) !== shown) return null;
    result[key] = String(matches[0].textContent || '').trim();
  }
  return result;
})();
return {detail: identity, groups,
        metrics: {rows, costs}, seat_observation: seatObservation};
"""

# Only the currently selected airport can have an observed price. The country
# selector contains no price evidence, and the airport details load asynchronously.
_SELECTED_HUB_PRICE_JS = r"""
const select = document.querySelector('#hubAirportSelector');
const option = select && select.selectedOptions && select.selectedOptions[0];
const details = document.querySelector('#airportInfo');
const cost = document.querySelector('#hubCostInfo');
if (!option || !details || !cost || option.disabled ||
    !/^[1-9][0-9]{0,11}$/.test(option.value)) return null;
if ([details, cost].some(el => el.querySelector &&
    (el.querySelector('img[src*="loader"]') || el.querySelector('[aria-busy="true"]')))) return null;
const id = option.value;
const label = String(option.textContent || '').trim();
const rawCode = (option.dataset.iata || option.dataset.icao ||
  (label.match(/\(([A-Z]{3,4})\)/) || [])[1] || '').trim().toUpperCase();
const code = /^[A-Z]{3,4}$/.test(rawCode) ? rawCode : '';
const detailText = String(details.textContent || '').trim();
const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const detailId = details.getAttribute('data-airport-id');
const costId = typeof cost.getAttribute === 'function' ? cost.getAttribute('data-airport-id') : null;
if ((detailId && detailId !== id) || (costId && costId !== id)) return null;
// The live airport_info.php response embeds the selected airport's arrId.
// It is stronger evidence than the text label while AJAX replaces the panel.
const scriptIds = Array.from(details.querySelectorAll ? details.querySelectorAll('script') : [])
  .flatMap(el => Array.from(String(el.textContent || '').matchAll(/\barrId\s*=\s*([1-9][0-9]{0,11})\s*;/g),
    match => match[1]));
if (scriptIds.some(value => value !== id)) return null;
const airportName = label.replace(/\s*\([A-Z]{3,4}\)\s*$/, '').trim();
const confirmed = detailId === id || scriptIds.includes(id) || (code.length >= 3 &&
  new RegExp('\\b' + code + '\\b', 'i').test(detailText)) ||
  (airportName.length >= 4 && normalize(detailText).includes(normalize(airportName)));
if (!confirmed) return null;
// The Hub cost row has a <br> between dollars and points. textContent
// joins them into e.g. "$ 11,520,00020 Points" and corrupts both figures.
const priceCell = (cost.querySelector && cost.querySelector('td:nth-child(2)')) || cost;
const fragments = Array.from(priceCell.childNodes || [])
  .map(node => String(node.textContent || '').trim()).filter(Boolean);
if (!fragments.length) fragments.push(String(priceCell.textContent || '').trim());
const priceMatch = fragments[0].match(/(?:US\s*\$|USD\s*|\$)\s*([1-9][0-9.,]*)/i);
if (!priceMatch) return null;
const amount = priceMatch[1];
if (!(/^\d+$/.test(amount) || /^[1-9]\d{0,2}(?:,\d{3})+$/.test(amount) ||
      /^[1-9]\d{0,2}(?:\.\d{3})+$/.test(amount))) return null;
const price = Number(amount.replace(/[.,]/g, ''));
if (!Number.isSafeInteger(price) || price <= 0) return null;
const costText = fragments.join(' ');
const pointsMatch = costText.match(/(?:^|\D)([0-9][0-9,]*)\s*(?:points?|pontos?)\b/i);
if (/\b(?:points?|pontos?)\b/i.test(costText) && !pointsMatch) return null;
const points = pointsMatch ? Number(pointsMatch[1].replace(/,/g, '')) : 0;
if (!Number.isSafeInteger(points) || points < 0) return null;
return {id, name: label, code, purchasable: true, hub_price: price, hub_points: points};
"""

# Log bounded, non-sensitive evidence when a hub price cannot be correlated.
# No HTML, airport labels, credentials, cookies or raw monetary text leave the DOM.
_HUB_PRICE_DIAGNOSTIC_JS = r"""
const select = document.querySelector('#hubAirportSelector');
const option = select && select.selectedOptions && select.selectedOptions[0];
const details = document.querySelector('#airportInfo');
const cost = document.querySelector('#hubCostInfo');
const label = String(option && option.textContent || '').trim();
const code = String(option && (option.dataset.iata || option.dataset.icao) ||
  (label.match(/\(([A-Z]{3,4})\)/) || [])[1] || '').trim().toUpperCase();
const name = label.replace(/\s*\([A-Z]{3,4}\)\s*$/, '').trim();
const text = String(details && details.textContent || '').trim();
const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const airportId = option && option.value;
const detailId = details && details.getAttribute('data-airport-id');
const costId = cost && cost.getAttribute('data-airport-id');
const scriptIds = Array.from(details?.querySelectorAll?.('script') || [])
  .flatMap(el => Array.from(String(el.textContent || '').matchAll(/\barrId\s*=\s*([1-9][0-9]{0,11})\s*;/g),
    match => match[1]));
const priceCell = (cost?.querySelector && cost.querySelector('td:nth-child(2)')) || cost;
const fragments = Array.from(priceCell?.childNodes || [])
  .map(node => String(node.textContent || '').trim()).filter(Boolean);
if (!fragments.length) fragments.push(String(priceCell?.textContent || '').trim());
const costText = fragments.join(' ');
const amount = (fragments[0].match(/(?:US\s*\$|USD\s*|\$)\s*([1-9][0-9.,]*)/i) || [])[1] || '';
const amountValid = /^\d+$/.test(amount) || /^[1-9]\d{0,2}(?:,\d{3})+$/.test(amount) ||
  /^[1-9]\d{0,2}(?:\.\d{3})+$/.test(amount);
const identity = !!airportId && (detailId === airportId ||
  (scriptIds.includes(airportId) && scriptIds.every(id => id === airportId)) ||
  (/^[A-Z]{3,4}$/.test(code) && new RegExp('\\b' + code + '\\b', 'i').test(text)) ||
  (name.length >= 4 && normalize(text).includes(normalize(name))));
const pointsMatch = costText.match(/(?:^|\D)([0-9][0-9,]*)\s*(?:points?|pontos?)\b/i);
return {
  selected: !!airportId && /^[1-9][0-9]{0,11}$/.test(airportId),
  detail_present: !!details,
  cost_present: !!cost,
  ajax_active: !!(window.jQuery && window.jQuery.active > 0),
  identity_matched: identity,
  id_conflict: !!((detailId && detailId !== airportId) || (costId && costId !== airportId) ||
    scriptIds.some(id => id !== airportId)),
  amount_valid: !!amountValid,
  points_valid: !/\b(?:points?|pontos?)\b/i.test(costText) || !!pointsMatch,
  details_loading: !!(details && details.querySelector &&
    (details.querySelector('img[src*="loader"]') || details.querySelector('[aria-busy="true"]'))),
};
"""

# The game's New Hub form first loads the country list, then fetches the
# airport options and finally the selected airport's price through AJAX.
# Only selection events are sent. The Purchase hub action is never invoked.
_HUB_COUNTRIES_JS = r"""
const select = document.querySelector('#hubcountrySelector');
return select ? Array.from(select.options)
  .filter(el => !el.disabled && el.value && el.value.length <= 120)
  .map(el => el.value) : [];
"""

_HUB_AIRPORT_OPTIONS_JS = r"""
const select = document.querySelector('#hubAirportSelector');
if (!select || (window.jQuery && window.jQuery.active > 0)) return null;
const country = document.querySelector('#hubcountrySelector');
const ids = Array.from(select.options).filter(el => !el.disabled &&
  /^[1-9][0-9]{0,11}$/.test(el.value)).map(el => el.value);
const pending = window.__am4HubCountrySwitch;
if (pending && country && country.value === pending.country) {
  if (JSON.stringify(ids) === JSON.stringify(pending.previous)) return null;
  delete window.__am4HubCountrySwitch;
}
return ids;
"""

_SELECT_MARKET_COUNTRY_JS = r"""
const select = document.querySelector('#hubcountrySelector');
if (!select || !Array.from(select.options).some(el =>
    el.value === arguments[0] && !el.disabled)) return false;
if (select.value !== arguments[0]) {
  const airport = document.querySelector('#hubAirportSelector');
  window.__am4HubCountrySwitch = {
    country: arguments[0],
    previous: airport ? Array.from(airport.options).filter(el => !el.disabled &&
      /^[1-9][0-9]{0,11}$/.test(el.value)).map(el => el.value) : []
  };
  select.value = arguments[0];
  select.dispatchEvent(new Event('change', {bubbles: true}));
}
return true;
"""

_SELECT_MARKET_AIRPORT_JS = r"""
const select = document.querySelector('#hubAirportSelector');
if (!select || !Array.from(select.options).some(el =>
    el.value === arguments[0] && !el.disabled)) return false;
select.value = arguments[0];
select.dispatchEvent(new Event('change', {bubbles: true}));
return true;
"""

# Inspect the DOM after the game's own search has loaded. Unlike the normal
# fleet reader, this does not turn missing/invalid demand fields into zero.
_VERIFIED_ROUTE_DEMAND_JS = r"""
const result = document.querySelector('#resResult');
if (!result || result.querySelector('img[src*="loader"]') ||
    result.querySelector('[aria-busy="true"]')) return null;
if (typeof window !== 'undefined' && window.jQuery && window.jQuery.active > 0) return null;
const rows = Array.from(result.querySelectorAll('#list .sorter'));
if (!rows.length || rows.length > 1000) return null;
return rows.map(el => {
  const arrival = el.querySelector('.col-6.m-text:first-child > span:nth-of-type(2)')?.textContent.trim();
  const comma = arrival?.indexOf(', ') ?? -1;
  return {
    dep_id: ((String(el.getAttribute('onclick') || '').match(/(?:[?&]|\b)dep=(\d+)(?!\d)/) || [])[1]) || null,
    arr_id: ((String(el.getAttribute('onclick') || '').match(/(?:[?&]|\b)arr=(\d+)(?!\d)/) || [])[1]) || null,
    distance: el.getAttribute('data-distance'),
    runway: el.getAttribute('data-rwy'),
    y: el.getAttribute('data-yclass'),
    j: el.getAttribute('data-jclass'),
    f: el.getAttribute('data-fclass'),
    event_demand_boosted: EVENT_WARNING.test(el.textContent || '') ? true : null,
    ...(comma > 0 ? {destination_country: arrival.slice(0, comma)} : {})
  };
});
""".replace("EVENT_WARNING", ROUTE_EVENT_WARNING_JS)

_OWNED_ROUTE_SEARCH_MENU_JS = r"""
const panel = document.querySelector('#routeAction');
const hub = panel?.querySelector('select#hubSelect');
const country = panel?.querySelector('select#arrSelector');
if (!hub?.getClientRects().length || !country?.getClientRects().length ||
    hub.disabled || country.disabled || country.value !== '0' || window.jQuery?.active) return null;
const values = select => Array.from(select.options)
  .filter(option => !option.disabled && option.value && option.value !== '0').map(option => option.value).sort();
const origins = values(hub);
const target = arguments[0];
if (target && hub.value !== target) {
  if (origins.includes(target)) {
    hub.value = target;
    hub.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return null;
}
return {origin: hub.value, origins, countries: values(country)};
"""

_ROUTE_MAP_AIRPORT_IDS_JS = r"""
const airports = window.airportIconData;
return Array.isArray(airports) ? airports.map(airport => String(airport.Id || '')).sort() : null;
"""

# The Research country selector calls this same read-only fragment without an
# origin parameter. Parse it without running its scripts or changing the form.
_ROUTE_DESTINATION_BATCH_JS = r"""
const [countries, requestTimeout, done] = arguments;
const menu = document.querySelector('#routeAction select#arrSelector');
if (!menu?.getClientRects().length || menu.disabled || menu.value !== '0') {
  done(null);
  return;
}
const values = new Set([...menu.options].filter(option => !option.disabled).map(option => option.value));
if (countries.some(country => country === '0' || !values.has(country))) {
  done(null);
  return;
}
(async () => {
  const results = [];
  for (const country of countries) {
    const url = new URL('research_main.php', location.href);
    url.search = new URLSearchParams({mode: 'cityList', t: 'arr', c: country});
    if (typeof fbSig !== 'undefined') url.searchParams.set('fbSig', fbSig);
    const response = await fetch(url, {
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(requestTimeout)
    });
    if (!response.ok) return null;
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    const selectors = page.querySelectorAll('select#citySelectArr');
    if (selectors.length !== 1 || selectors[0].disabled) return null;
    const [any, ...options] = selectors[0].options;
    if (!any || any.value !== '0' || any.disabled || options.length === 0 || options.some(option => option.disabled)) {
      return null;
    }
    results.push([country, options.map(option => option.value).sort()]);
  }
  return results;
})().then(done, () => done(null));
"""

_PREPARE_COUNTRY_SEARCH_JS = """
const [origin, distance, runway, country] = arguments;
const panel = document.querySelector('#routeAction');
if (!panel) return null;
const hub = panel.querySelector('select#hubSelect');
const max = panel.querySelector('input#maxDist');
const min = panel.querySelector('input#rwyLength');
const arrival = panel.querySelector('select#arrSelector');
if (!hub || !max || !min || !arrival || [hub, max, min, arrival].some(el => el.disabled)) return null;
const hubs = Array.from(hub.options).filter(opt => !opt.disabled && opt.value === origin);
const countries = Array.from(arrival.options).filter(opt =>
  !opt.disabled && opt.value && opt.value !== '0' && opt.textContent.trim() === country);
if (hubs.length !== 1 || countries.length !== 1) return null;
if (hub.value !== origin) {
  hub.value = origin;
  hub.dispatchEvent(new Event('change', {bubbles: true}));
}
max.value = String(distance);
min.value = String(runway);
if (arrival.value !== countries[0].value || panel.querySelector('select#citySelectArr')?.value !== '0') {
  arrival.value = countries[0].value;
  arrival.dispatchEvent(new Event('change', {bubbles: true}));
}
return arrival.value;
"""

_COUNTRY_SEARCH_SELECTOR_JS = r"""
const [origin, distance, runway, country, destination = '0'] = arguments;
const panel = document.querySelector('#routeAction');
if (!panel || (window.jQuery && window.jQuery.active > 0)) return null;
const airport = panel.querySelector('select#citySelectArr');
if (!airport || airport.disabled || airport.value !== destination ||
    panel.querySelector('select#hubSelect')?.value !== origin ||
    panel.querySelector('input#maxDist')?.value !== String(distance) ||
    panel.querySelector('input#rwyLength')?.value !== String(runway) ||
    panel.querySelector('select#arrSelector')?.value !== country) return null;
return Array.from(airport.options).filter(el => !el.disabled && el.value !== '0')
  .map(el => el.value).sort();
"""

_START_COUNTRY_SEARCH_JS = r"""
const [origin, distance, runway, country, destination, expectedIds] = arguments;
const readSelector = function () {
""" + _COUNTRY_SEARCH_SELECTOR_JS + r"""
};
const panel = document.querySelector('#routeAction');
const result = panel?.querySelector('#resResult');
const button = panel?.querySelector('button#resSearch');
if (!result || !button || button.disabled || button.form) return false;
const airport = panel.querySelector('select#citySelectArr');
const controls = [origin, distance, runway, country];
const airportIds = readSelector(...controls, destination ? airport?.value : '0');
if (!airportIds?.length) return false;
if (destination) {
  if (!airportIds.includes(destination) || JSON.stringify(airportIds) !== JSON.stringify(expectedIds) ||
      result.querySelector('img[src*="loader"], [aria-busy="true"]')) return false;
  if (airport.value !== destination) {
    airport.value = destination;
    airport.dispatchEvent(new Event('change', {bubbles: true}));
  }
  if (JSON.stringify(readSelector(...controls, destination)) !== JSON.stringify(expectedIds)) return false;
}
// Discard the previous result before starting the native read-only search.
result.replaceChildren();
button.click();
return {airport_ids: airportIds};
"""

_VERIFIED_COUNTRY_DEMAND_JS = r"""
let rows = (() => {
""" + _VERIFIED_ROUTE_DEMAND_JS + r"""
})();
if (!rows) {
  const result = document.querySelector('#resResult');
  const lists = result?.querySelectorAll(':scope > #list');
  const notice = lists?.[0]?.querySelector(':scope > .row > .col-12 > .alert.alert-info');
  if (arguments[4] || (window.jQuery && window.jQuery.active > 0) || lists?.length !== 1 ||
      result.querySelector('.sorter, img[src*="loader"], [aria-busy="true"]') ||
      !notice?.getClientRects().length || notice.textContent.trim() !== 'There were no results to your search') {
    return null;
  }
  rows = [];
}
const airportIds = (() => {
""" + _COUNTRY_SEARCH_SELECTOR_JS + r"""
})();
return {rows, airport_ids: airportIds};
"""

_AIRPORT_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_COUNT = re.compile(r"^[0-9]{1,9}$")
_DISTANCE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def _stable_read(bot: object, script: str, *args, with_timestamp: bool = False) -> object:
    """Return an identical DOM pair, optionally with its second-read timestamp."""
    try:
        first = bot.js(script, *args)
        if first is None or getattr(bot, "stopping", False):
            return None
        stop = getattr(bot, "_stop", None)
        interrupted = stop.wait(0.3) if stop is not None else threading.Event().wait(0.3)
        if interrupted or getattr(bot, "stopping", False):
            return None
        second = bot.js(script, *args)
        read_at = time.time() if with_timestamp else None
        if first != second:
            return None
        return (second, read_at) if with_timestamp else second
    except Exception:  # Selenium errors can expose session details in their repr.
        log.debug("A leitura da página do jogo não foi concluída.")
        return None


def _verified_demand(candidates: list, rows: object, origin: str) -> list[dict]:
    """Require every raw game row to agree with the fleet search response."""
    if not isinstance(rows, list) or not rows or len(rows) != len(candidates):
        return []
    expected = {str(item.arr_id): item for item in candidates}
    if len(expected) != len(candidates):
        return []
    samples = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict):
            return []
        destination = raw.get("arr_id")
        if (raw.get("dep_id") != origin
                or not isinstance(destination, str) or not _AIRPORT_ID.fullmatch(destination)
                or destination == origin or destination in seen or destination not in expected):
            return []
        distance_raw = raw.get("distance")
        counts_raw = [raw.get(key) for key in ("y", "j", "f")]
        if (not isinstance(distance_raw, str) or not _DISTANCE.fullmatch(distance_raw)
                or any(not isinstance(value, str) or not _COUNT.fullmatch(value)
                       for value in counts_raw)):
            return []
        distance = float(distance_raw)
        counts = [int(value) for value in counts_raw]
        candidate = expected[destination]
        if (not math.isfinite(distance) or distance <= 0
                or not math.isclose(distance, candidate.distance, rel_tol=0, abs_tol=0.001)
                or counts != [candidate.y, candidate.j, candidate.f]):
            return []
        sample = {"arr_id": destination, "distance": distance,
                  "y": counts[0], "j": counts[1], "f": counts[2]}
        country = raw.get("destination_country")
        if isinstance(country, str) and 0 < len(country) <= 100 and country == country.strip():
            sample["destination_country"] = country
        # Keep a positive warning from either correlated DOM read.
        if candidate.event_demand_boosted is True or raw.get("event_demand_boosted") is True:
            sample["event_demand_boosted"] = True
        runway = raw.get("runway")
        if (isinstance(runway, str) and _COUNT.fullmatch(runway)
                and 0 < int(runway) <= 30000 and int(runway) == candidate.runway):
            sample["destination_runway_ft"] = int(runway)
        elif runway is not None:
            # A contradictory runway must not become physical evidence.
            if isinstance(runway, str) and _COUNT.fullmatch(runway) and int(runway) > 0:
                return []
        samples.append(sample)
        seen.add(destination)
    return samples


def collect_visible_hub_price(bot: object) -> bool:
    """Persist a selected hub price only after stable, correlated game reads."""
    reading = _stable_read(bot, _SELECTED_HUB_PRICE_JS, with_timestamp=True)
    return (isinstance(reading, tuple) and len(reading) == 2
            and isinstance(reading[0], dict)
            and HubExpansionRegistry().record_catalog(
                [reading[0]], complete=False, observed_at=reading[1]))


def _wait_airport_options(bot: object) -> list[str]:
    """Wait for a stable, post-country-switch airport list from the game."""
    for _ in range(16):
        options = _stable_read(bot, _HUB_AIRPORT_OPTIONS_JS)
        if isinstance(options, list) and options:
            verified = [item for item in options if isinstance(item, str)
                        and _AIRPORT_ID.fullmatch(item)]
            if len(verified) == len(options) and len(set(verified)) == len(verified):
                return verified
        if getattr(bot, "stopping", False):
            break
        stop = getattr(bot, "_stop", None)
        if (stop.wait(0.25) if stop is not None else threading.Event().wait(0.25)):
            break
    return []


def collect_hub_market_prices(bot: object, *, per_cycle: int = 3) -> int:
    """Read rotating purchase prices across countries, resuming after restarts."""
    if getattr(bot, "stopping", False) or per_cycle < 1:
        return 0
    registry = HubExpansionRegistry()
    collected = 0
    attempts = 0
    visited = set()

    def inspect_airport(country: str, airport_id: str) -> bool:
        nonlocal attempts, collected
        attempts += 1
        visited.add((country, airport_id))
        observation = None
        observed_at = None
        if bot.js(_SELECT_MARKET_AIRPORT_JS, airport_id):
            # AJAX replaces #airportInfo after the change event. A first
            # empty read returns immediately, so poll before switching to the
            # next airport or we would keep reading the preceding airport.
            for _ in range(20):
                reading = _stable_read(bot, _SELECTED_HUB_PRICE_JS,
                                       with_timestamp=True)
                if (isinstance(reading, tuple) and len(reading) == 2
                        and isinstance(reading[0], dict)
                        and reading[0].get("id") == airport_id):
                    observation, observed_at = reading
                    break
                if getattr(bot, "stopping", False):
                    break
                stop = getattr(bot, "_stop", None)
                if (stop.wait(0.2) if stop is not None else threading.Event().wait(0.2)):
                    break
        recorded = bool(observation and registry.record_catalog(
            [observation], complete=False, observed_at=observed_at))
        registry.record_catalog_attempt(country, airport_id, success=recorded)
        if recorded:
            collected += 1
        else:
            try:
                diagnostics = bot.js(_HUB_PRICE_DIAGNOSTIC_JS)
            except Exception:
                diagnostics = None
            if isinstance(diagnostics, dict):
                blockers = [key for key, value in diagnostics.items()
                            if (value if key in ("ajax_active", "id_conflict", "details_loading") else not value)]
                log.info("Catálogo de hubs: aeroporto %s sem preço confirmado (%s).",
                         airport_id, ", ".join(blockers) or "leitura instável")
        return recorded

    bot.open_popup("hubs_new.php", "New Hub", "nav_new_hub")
    try:
        countries = bot.js(_HUB_COUNTRIES_JS) or []
        countries = list(dict.fromkeys(item for item in countries
                                       if isinstance(item, str) and 0 < len(item) <= 120))
        if not countries:
            return 0
        # Retry one previously missing price per cycle, while normal scanning
        # keeps progressing independently of a temporarily unreadable airport.
        for retry in registry.due_catalog_retries():
            country, airport_id = retry["country"], retry["airport_id"]
            if country not in countries or attempts >= per_cycle:
                continue
            if bot.js(_SELECT_MARKET_COUNTRY_JS, country):
                airports = _wait_airport_options(bot)
                if airport_id in airports:
                    inspect_airport(country, airport_id)
                else:
                    registry.record_catalog_attempt(country, airport_id, success=False)
        cursor = registry.catalog_scan_position()
        previous_country = cursor.get("country")
        if previous_country in countries:
            country_index = countries.index(previous_country)
            if cursor.get("airport_id") is None:
                country_index = (country_index + 1) % len(countries)
        else:
            country_index = countries.index("Brazil") if "Brazil" in countries else 0
        previous_airport = cursor.get("airport_id")
        checked_countries = 0
        # Bound the work in each cycle even when several countries have no airports.
        while attempts < per_cycle and checked_countries < min(len(countries), 4):
            country = countries[country_index]
            if not bot.js(_SELECT_MARKET_COUNTRY_JS, country):
                break
            airports = _wait_airport_options(bot)
            start = 0
            if previous_country == country and previous_airport in airports:
                start = airports.index(previous_airport) + 1
            if start >= len(airports):
                registry.record_catalog_scan_position(country, None)
                country_index = (country_index + 1) % len(countries)
                previous_country, previous_airport = None, None
                checked_countries += 1
                continue
            for airport_id in airports[start:]:
                if attempts >= per_cycle or getattr(bot, "stopping", False):
                    break
                if (country, airport_id) not in visited:
                    inspect_airport(country, airport_id)
                # The cursor advances after each attempted airport, including
                # missing prices; retry scheduling is tracked independently.
                registry.record_catalog_scan_position(country, airport_id)
            break
        if collected:
            log.info("Catálogo de hubs: %d/%d preços confirmados e persistidos.", collected, attempts)
        return collected
    finally:
        bot.close_popup(quiet=True)


def _collect_route_destination_catalog(bot: object, countries: list[str]) -> dict | None:
    """Reconcile one shared arrival catalog with the map before and after the scan."""
    started_at = time.time()
    deadline = time.monotonic() + _ROUTE_DESTINATION_BUDGET_SECONDS
    map_ids = _stable_read(bot, _ROUTE_MAP_AIRPORT_IDS_JS)
    if (not isinstance(map_ids, list) or not map_ids
            or any(not isinstance(airport, str) or not _AIRPORT_ID.fullmatch(airport) for airport in map_ids)
            or len(set(map_ids)) != len(map_ids)):
        return None

    airports_by_country = {}
    for offset in range(0, len(countries), _ROUTE_DESTINATION_BATCH_SIZE):
        remaining = deadline - time.monotonic()
        if bot.stopping or remaining < 1:
            return None
        batch = countries[offset:offset + _ROUTE_DESTINATION_BATCH_SIZE]
        # One request at a time. Keep each browser call short and within the cycle budget.
        timeout_ms = min(3000, int(remaining * 1000 / len(batch)))
        rows = bot.driver.execute_async_script(_ROUTE_DESTINATION_BATCH_JS, batch, timeout_ms)
        if not isinstance(rows, list) or len(rows) != len(batch):
            log.debug("Catálogo de chegadas: lote indisponível após %d países.", offset)
            return None
        for country, row in zip(batch, rows, strict=True):
            if (not isinstance(row, list) or len(row) != 2 or row[0] != country
                    or not isinstance(row[1], list) or not row[1]
                    or any(not isinstance(airport, str) or not _AIRPORT_ID.fullmatch(airport) for airport in row[1])):
                return None
            airports_by_country[country] = row[1]

    airports = [airport for ids in airports_by_country.values() for airport in ids]
    if (bot.stopping or time.monotonic() >= deadline or sorted(airports) != map_ids
            or _stable_read(bot, _ROUTE_MAP_AIRPORT_IDS_JS) != map_ids):
        return None
    return {"started_at": started_at, "observed_at": time.time(), "map_airport_ids": map_ids,
            "airport_ids_by_country": airports_by_country}


def collect_owned_route_search_universe(bot: object) -> dict | None:
    """Read native country menus and the shared arrival catalog in one observation."""
    if bot.stopping:
        return None
    started_at = time.time()
    deadline = time.monotonic() + 45

    def read(target):
        return _poll_country_audit(bot, min(deadline, time.monotonic() + 4),
                                   _stable_read, bot, _OWNED_ROUTE_SEARCH_MENU_JS, target)

    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    try:
        bot.ajax("research_main.php", "routeAction")
        first = read(None)
        if not first or not first["origins"] or first["origin"] not in first["origins"]:
            return None
        origins = first["origins"]
        countries = {first["origin"]: first["countries"]}
        for origin in origins:
            if origin in countries:
                continue
            row = read(origin)
            if not row or row["origin"] != origin or row["origins"] != origins:
                return None
            countries[origin] = row["countries"]
        if read(first["origin"]) != first:
            return None
        result = {"started_at": started_at, "observed_at": time.time(),
                  "origin_ids": origins, "country_values_by_origin": countries}
        if all(menu == first["countries"] for menu in countries.values()):
            try:
                catalog = _collect_route_destination_catalog(bot, first["countries"])
            except WebDriverException:
                log.debug("A coleta do seletor de aeroportos foi interrompida.")
            else:
                # The detached requests need no jQuery idle period, but the same
                # form and roster must still be visible after the scan.
                if catalog is not None and _poll_country_audit(
                    bot, time.monotonic() + 4, _stable_read, bot, _OWNED_ROUTE_SEARCH_MENU_JS, None,
                ) == first:
                    result["destination_catalog"] = catalog
                    result["observed_at"] = time.time()
        return result
    finally:
        bot.close_popup(quiet=True)


def collect_owned_hub_demand(bot: object, *, origin_id: str | None = None,
                             country_windows: list[dict] | None = None) -> int:
    """Search a native owned hub, optionally the origin of a parked aircraft."""
    country = None
    if country_windows is not None and origin_id is None:
        get = getattr(bot.config, "get", None)
        if callable(get):
            target = get("investment", "route_audit_origin_id")
            target_country = get("investment", "route_audit_country")
            if _AIRPORT_ID.fullmatch(target) and target_country:
                origin_id, country = target, target_country
    return _collect_hub_demand(bot, external=False, origin_id=origin_id,
                               country=country, country_windows=country_windows)


def collect_external_hub_demand(bot: object, *, observation_only: bool = False) -> int:
    """Search one fresh purchase-catalog airport outside the owned inventory."""
    if not observation_only and not bot.config.get_bool("investment", "planning_enabled"):
        return 0
    return _collect_hub_demand(bot, external=True, observation_only=observation_only)


def _read_hub_demand_window(bot: object, origin: str, distance: int,
                            runway: int, *, country: str | None = None,
                            country_windows: list[dict] | None = None) -> tuple[list[dict], float | None]:
    from fleet import read_route_candidates, search_routes

    search_distance = distance
    audit_selector = country is not None and country_windows is not None
    if country is None:
        candidates = search_routes(bot, origin, distance, runway, persist_demand=False)
    else:
        search_distance = max(distance, _COUNTRY_SEARCH_MIN_CEILING_KM)
        selected = bot.js(_PREPARE_COUNTRY_SEARCH_JS, origin, search_distance, runway, country)
        if not isinstance(selected, str) or selected in ("", "0"):
            return [], None

        controls = (origin, search_distance, runway, selected)

        def start_search(_driver):
            return bot.stopping or bot.js(_START_COUNTRY_SEARCH_JS, *controls)

        started_at = time.time()
        started = WebDriverWait(bot.driver, 8).until(start_search)
        if bot.stopping or not bot.wait_loaded("resResult", timeout=8):
            return [], None
        candidates = read_route_candidates(bot)
    if audit_selector:
        read = _poll_country_audit(bot, time.monotonic() + 4, lambda: _stable_read(
            bot, _VERIFIED_COUNTRY_DEMAND_JS, *controls, with_timestamp=True))
    else:
        read = _stable_read(bot, _VERIFIED_ROUTE_DEMAND_JS, with_timestamp=True)
    if read is None:
        return [], None
    result, read_at = read
    rows = result["rows"] if audit_selector else result
    samples = _verified_demand(candidates, rows, origin)
    native_empty = audit_selector and rows == [] and not candidates
    if (not samples and not native_empty) or (country is not None and any(
            sample.get("destination_country") != country or sample.get("destination_runway_ft", 0) < runway
            for sample in samples)):
        return [], None
    if any(sample["distance"] > search_distance + 0.001
           or sample.get("destination_runway_ft", runway) < runway for sample in samples):
        return [], None
    native_ids = [sample["arr_id"] for sample in samples] if audit_selector else None
    if search_distance > distance:
        samples = [sample for sample in samples if sample["distance"] <= distance + 0.001]
    if audit_selector:
        options = result["airport_ids"]
        selector_verified = (isinstance(started, dict) and options == started.get("airport_ids")
                             and isinstance(options, list) and bool(options)
                             and all(isinstance(value, str) and _AIRPORT_ID.fullmatch(value) for value in options)
                             and len(options) == len(set(options)))
        country_windows.append({
            "origin_id": origin, "country": country, "country_value": selected,
            "started_at": started_at, "observed_at": read_at, "min_runway_ft": runway,
            "requested_max_distance_km": distance, "native_max_distance_km": search_distance,
            "selector_airport_ids": options if selector_verified else None,
            "native_destination_ids": sorted(native_ids),
            "accepted_destination_count": len(samples),
            "native_limit_reached": len(native_ids) >= _ROUTE_SEARCH_SAMPLE_LIMIT,
        })
    return samples, read_at


def _poll_country_audit(bot, deadline, read, *args):
    stop = getattr(bot, "_stop", None) or threading.Event()
    while not bot.stopping and time.monotonic() < deadline:
        result = read(*args)
        if time.monotonic() >= deadline or bot.stopping:
            break
        if result:
            return result
        if stop.wait(max(0, min(0.25, deadline - time.monotonic()))):
            break
    return None


def _audit_omitted_country_airports(bot: object, windows: list[dict], *,
                                   limit: int = _COUNTRY_DIRECT_AUDIT_LIMIT,
                                   budget_seconds: int = _COUNTRY_DIRECT_AUDIT_SECONDS) -> list[dict]:
    """Recheck missing IDs in this selector within the current observation cycle."""
    from fleet import read_route_candidates

    if not windows:
        return []
    last = windows[-1]
    options = last["selector_airport_ids"]
    if options is None or any(window["selector_airport_ids"] != options for window in windows):
        return []
    origin = last["origin_id"]
    observed = {value for window in windows for value in window["native_destination_ids"]}
    expected = set(options) - {origin}
    missing = sorted(expected - observed, key=int)
    if observed - expected or limit <= 0 or budget_seconds <= 0:
        return []

    country, country_value = last["country"], last["country_value"]
    distance, runway = last["native_max_distance_km"], last["min_runway_ft"]

    def start_search(controls):
        started_at = time.time()
        started = bot.js(_START_COUNTRY_SEARCH_JS, *controls, options)
        return started_at if started == {"airport_ids": options} else None

    def read_result(controls):
        candidates = read_route_candidates(bot)
        read = _stable_read(bot, _VERIFIED_COUNTRY_DEMAND_JS, *controls, with_timestamp=True)
        if read is None or read[0]["airport_ids"] is None:
            return None
        result, read_at = read
        if result["airport_ids"] != options:
            return (), read_at
        samples = _verified_demand(candidates, result["rows"], origin)
        if (len(samples) == 1 and samples[0]["arr_id"] == controls[-1]
                and samples[0].get("destination_country") == country
                and "destination_runway_ft" in samples[0]):
            return samples, read_at
        return None

    readings = []
    deadline = time.monotonic() + budget_seconds
    for destination in missing[:limit]:
        airport_deadline = min(deadline, time.monotonic() + _COUNTRY_DIRECT_AIRPORT_SECONDS)
        if bot.stopping or time.monotonic() >= airport_deadline:
            break
        controls = (origin, distance, runway, country_value, destination)

        try:
            started_at = _poll_country_audit(bot, airport_deadline, start_search, controls)
            if started_at is None:
                continue
            # After the search has started, retry only the response read.
            read = _poll_country_audit(bot, airport_deadline, read_result, controls)
        except WebDriverException:
            break
        if read is None:
            continue
        samples, read_at = read
        if not samples:
            break  # A stable but different selector invalidates further queries in this partition.
        readings.append({
            "origin_id": origin, "country": country, "country_value": country_value,
            "native_max_distance_km": distance, "min_runway_ft": runway,
            "started_at": started_at, "observed_at": read_at,
            "selector_airport_ids": options, "direct_destination": samples[0],
        })
    return readings


def _collect_country_windows(bot, origin, distance, runway, country, country_windows):
    results = []
    try:
        samples, read_at = _read_hub_demand_window(
            bot, origin, distance, runway, country=country, country_windows=country_windows)
        if samples:
            results.append((samples, read_at))
        if len(samples) >= _ROUTE_SEARCH_SAMPLE_LIMIT and not bot.stopping:
            # Keep Any airport for both bulk windows. A specific airport bypasses both filters.
            cutoff = math.ceil(min(sample["distance"] for sample in samples))
            if 300 <= cutoff < distance:
                overlap, overlap_at = _read_hub_demand_window(
                    bot, origin, cutoff, runway, country=country, country_windows=country_windows)
                if overlap:
                    results.append((overlap, overlap_at))
    except WebDriverException:
        log.debug("Uma janela da pesquisa por país do hub %s foi interrompida.", origin)
    return results


def _collect_hub_demand(bot: object, *, external: bool, origin_id: str | None = None,
                        country: str | None = None, country_windows: list[dict] | None = None,
                        observation_only: bool = False) -> int:
    from fleet import _HUB_OPTIONS_JS
    from hub_registry import _hub_id

    if getattr(bot, "stopping", False):
        return 0
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    try:
        bot.ajax("research_main.php", "routeAction")
        options = (_stable_read(bot, _HUB_OPTIONS_JS) if external
                   else bot.js(_HUB_OPTIONS_JS)) or []
        if not HubRegistry().record_options(options):
            return 0
        ids = [str(option.get("id")) for option in options if isinstance(option, dict)]
        if external:
            ids = [airport_id for value in ids if (airport_id := _hub_id(value))]
        expansion = HubExpansionRegistry()
        registry = expansion.external_demand_registry() if external else expansion
        max_age = DEFAULT_MAX_AGE_SECONDS if observation_only else HUB_RESEARCH_MAX_AGE_SECONDS
        origins = expansion.external_research_origins(set(ids), max_age_seconds=max_age) if external else ids
        if origin_id is not None and origin_id not in origins:
            return 0
        origin = origin_id if origin_id is not None else registry.next_demand_origin(origins)
        if origin is None:
            return 0
        # Reserve the rotation cursor before making AJAX requests. An empty,
        # inconsistent or interrupted response must not starve the next hub.
        distance = max(300, bot.config.get_int("settings", "route_max_distance_big", 6000))
        runway = max(0, bot.config.get_int("settings", "route_min_runway", 5000))
        # The legacy distance and runway preferences are not a universal
        # opportunity envelope. Alternate the normal query with a broad one
        # during observation and investment planning, so small runways and long routes are
        # sampled without starving the normal search. Neither proves coverage.
        planning = getattr(bot.config, "get_bool", None)
        scope = None
        if (country_windows is not None or observation_only
                or (callable(planning) and planning("investment", "planning_enabled"))):
            distance, runway = min(distance, 25000), min(runway, 30000)
            scope = "configured" if country else registry.next_demand_scope(origin)
            if scope == "broad":
                distance, runway = 20000, 0
            registry.record_demand_attempt(origin, search_scope=scope,
                                           max_distance=distance, min_runway=runway)
        else:
            registry.record_demand_attempt(origin)
        first_country_window = len(country_windows) if country_windows is not None else 0
        if country:
            windows = _collect_country_windows(bot, origin, distance, runway, country, country_windows)
        else:
            samples, read_at = _read_hub_demand_window(bot, origin, distance, runway)
            windows = [(samples, read_at)] if samples else []
        if not windows and (country_windows is None or len(country_windows) == first_country_window):
            log.debug("Pesquisa de demanda do hub %s incompleta ou sem resultados confirmados.", origin)
            return 0
        first_samples = windows[0][0] if windows else []
        if (country is None and scope is not None and len(first_samples) >= _ROUTE_SEARCH_SAMPLE_LIMIT
                and not getattr(bot, "stopping", False)):
            # Country selection is verified for owned departures. Keep the
            # overlapping distance window for the broad and custom searches.
            nearest = min(first_samples, key=lambda sample: sample["distance"])
            cutoff = math.ceil(nearest["distance"])
            country = nearest.get("destination_country") if not external and scope == "configured" else None
            try:
                if country:
                    windows.extend(_collect_country_windows(bot, origin, distance, runway, country, country_windows))
                elif 300 <= cutoff < distance:
                    extra, extra_at = _read_hub_demand_window(bot, origin, cutoff, runway)
                    if extra:
                        windows.append((extra, extra_at))
            except WebDriverException:
                log.debug("Uma janela adicional de demanda do hub %s foi interrompida.", origin)
        direct_searches = []
        if country_windows is not None and len(country_windows) > first_country_window:
            limit = bot.config.get_int("investment", "route_audit_max_airports", _COUNTRY_DIRECT_AUDIT_LIMIT)
            seconds = bot.config.get_int("investment", "route_audit_max_seconds", _COUNTRY_DIRECT_AUDIT_SECONDS)
            direct_searches = _audit_omitted_country_airports(
                bot, country_windows[first_country_window:], limit=min(200, limit), budget_seconds=min(120, seconds))
            country_windows.extend(direct_searches)
        if external:
            # A changed or missing ownership selector invalidates the external
            # classification. Keep the attempt, but discard its observations.
            confirmed_options = _stable_read(bot, _HUB_OPTIONS_JS)
            if (confirmed_options != options
                    or origin not in expansion.external_research_origins(set(ids), max_age_seconds=max_age)):
                return 0
        boosted = {sample["arr_id"] for rows, _ in windows for sample in rows
                   if sample.get("event_demand_boosted")}
        # Preserve a warning from either read if the world search and a direct
        # lookup found the same destination.
        for reading in direct_searches:
            sample = reading["direct_destination"]
            if sample.get("event_demand_boosted"):
                boosted.add(sample["arr_id"])
            elif sample["arr_id"] in boosted:
                sample["event_demand_boosted"] = True
        seen = set()
        count = 0
        for index, (rows, observed_at) in enumerate(windows):
            unseen = []
            for sample in rows:
                destination = sample["arr_id"]
                if destination in seen:
                    continue
                if destination in boosted:
                    sample["event_demand_boosted"] = True
                unseen.append(sample)
                seen.add(destination)
            if unseen:
                count += registry.record_demand(origin, unseen, observed_at=observed_at,
                                                search_scope=scope if index == 0 else None)
        if external:
            log.info("Pesquisa externa de demanda: hub %s, %d destinos observados.", origin, count)
        else:
            log.info("Pesquisa de demanda: hub %s, %d destinos confirmados.", origin, count)
        return count
    finally:
        bot.close_popup(quiet=True)


def collect_owned_route_details(bot: object) -> int:
    """Rotate independent route-detail reads over fresh owned-hub samples."""
    return _collect_hub_route_details(bot, external=False)


def collect_external_route_details(bot: object, *, observation_only: bool = False) -> int:
    """Research one independent external route detail per planning cycle."""
    if not observation_only and not bot.config.get_bool("investment", "planning_enabled"):
        return 0
    return _collect_hub_route_details(bot, external=True, observation_only=observation_only)


def _collect_hub_route_details(bot: object, *, external: bool, observation_only: bool = False) -> int:
    from route_detail_evidence import collect_route_details

    if getattr(bot, "stopping", False):
        return 0
    inventory = HubRegistry().snapshot()
    if not inventory.get("hub_catalog_fresh"):
        return 0
    codes = {hub["id"]: hub.get("code") for hub in inventory["hubs"]}
    expansion = HubExpansionRegistry()
    if external:
        max_age = DEFAULT_MAX_AGE_SECONDS if observation_only else HUB_RESEARCH_MAX_AGE_SECONDS
        snapshot = expansion.external_demand_snapshot(set(codes), max_age_seconds=max_age)
        samples = snapshot["samples"]
        codes = {hub["id"]: hub.get("code") for hub in snapshot["candidate_inventory"]}
        registry = expansion.external_demand_registry()
    else:
        samples = expansion.demand_research_snapshot(set(codes))["samples"]
        registry = expansion
    if not samples:
        return 0
    count = collect_route_details(bot, registry.route_detail_registry(), samples, codes,
                                  per_cycle=1 if external else 2)
    if count:
        if external:
            log.info("Detalhes de rotas externas: %d pares de pistas observados.", count)
        else:
            log.info("Detalhes de rotas: %d pares de pistas observados.", count)
    return count


def collect_hub_stopovers(bot: object) -> int:
    """Bound research per scope; use the same correlated engine catalogue as planning."""
    from economy import load_market_evidence
    from owned_hub_research_feed import _models, engine_variants
    from stopover_research import collect_stopover, subject_for

    if getattr(bot, "stopping", False) or not bot.config.get_bool("investment", "planning_enabled"):
        return 0
    inventory = HubRegistry().snapshot()
    market = load_market_evidence()
    if not inventory.get("hub_catalog_fresh") or not market.get("fresh"):
        return 0
    owned = {hub["id"] for hub in inventory["hubs"]}
    engines = EngineCatalogRegistry().snapshot()
    now = time.time()
    options = [(model, variant) for model in _models(market.get("models"))
               for variant in engine_variants(engines, model, now)[0]
               if variant["engine_available"] and variant.get("engine_detail")
               and variant["engine_detail"]["model_identity_verified"]]
    if not options:
        return 0
    expansion = HubExpansionRegistry()
    count = 0
    for registry, snapshot in (
        (expansion, expansion.demand_research_snapshot(owned)),
        (expansion.external_demand_registry(), expansion.external_demand_snapshot(owned)),
    ):
        if getattr(bot, "stopping", False):
            break
        subjects = ((subject, sample) for sample in snapshot["samples"]
                    if sample.get("source") == "game_route_search"
                    for model, variant in options
                    if (subject := subject_for(sample, model, variant, now)) is not None)
        count += collect_stopover(bot, registry.stopover_research_registry(), subjects)
    if count:
        log.info("Pesquisa de escalas: %d combinações dimensionais observadas.", count)
    return count


def _variant_signature(catalog):
    return (catalog.selector_type, catalog.dom_id, catalog.selector_name,
            tuple((v.engine_id, v.label, v.available) for v in catalog.variants))


def _observe_variant_details(bot, snapshot, catalog, observed_at):
    """Read reversible native choices; leave checkout and account state untouched."""
    metrics = parse_displayed_metrics(snapshot.get("metrics"))
    selected = catalog.selected_engine_id
    if not selected or metrics is None:
        return {}
    def observation(read, stamp, parsed_metrics):
        entry = {"observed_at": stamp, "metrics": parsed_metrics}
        seats = parse_seat_observation(read.get("seat_observation"), parsed_metrics.get("capacity_pax"))
        if seats is not None:
            entry["seat_observation"] = seats
        requirements = parse_operational_requirements(read.get("metrics"))
        if requirements is not None:
            entry["operational_requirements"] = requirements
        return entry

    result = {selected: observation(snapshot, observed_at, metrics)}
    # Only the native selector has been observed in the authenticated game.
    if catalog.selector_type != "select" or catalog.dom_id != "engSelection":
        return result
    signature = _variant_signature(catalog)
    last_metrics = metrics
    for variant in catalog.variants[:10]:
        if getattr(bot, "stopping", False):
            break
        if not variant.available or variant.engine_id == selected:
            continue
        if not bot.js(_SET_ENGINE_JS, "select", catalog.dom_id, variant.engine_id):
            break
        # The form may load asynchronously after the native change event.
        for _ in range(5):
            read = _stable_read(bot, _ENGINE_DETAIL_SNAPSHOT_JS, with_timestamp=True)
            if isinstance(read, tuple):
                candidate, stamp = read
                if not isinstance(candidate, dict) or candidate.get("detail") != snapshot.get("detail"):
                    return result
                current = parse_engine_catalog(candidate.get("groups"))
                if (_variant_signature(current) != signature
                        or current.selected_engine_id != variant.engine_id):
                    return result
                current_metrics = parse_displayed_metrics(candidate.get("metrics"))
                # A change of selected option alone does not prove that the
                # previous engine's specification has been refreshed.
                if (current_metrics and any(
                        key in last_metrics and key in current_metrics
                        and current_metrics[key] != last_metrics[key]
                        for key in ("speed_kph", "fuel_lbs_per_km", "range_km", "co2_kg_per_pax_km",
                                    "displayed_cost_usd"))):
                    result[variant.engine_id] = observation(candidate, stamp, current_metrics)
                    last_metrics = current_metrics
                    break
            stop = getattr(bot, "_stop", None)
            if (stop.wait(0.3) if stop is not None else threading.Event().wait(0.3)):
                return result
        else:
            break
    return result


def collect_aircraft_engine_catalog(bot: object, *, per_cycle: int = 2) -> int:
    """Inspect a bounded number of model detail screens without placing orders.

    The model list and each combined detail snapshot are stable double reads.
    The AJAX target is cleared by bot.ajax(), so an old model's form cannot
    pass as a new one while its engine options and identity stay correlated.
    Model ID correspondence comes from the detail response itself. Final engine
    prices still require verification from the actual order form before any
    investment is authorized.
    """
    from fleet import _MODELS_JS

    if getattr(bot, "stopping", False) or type(per_cycle) is not int or per_cycle < 1:
        return 0
    registry = EngineCatalogRegistry()
    collected = 0
    registry.revoke_roster()
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    try:
        bot.ajax("ac_orders.php?first=true", "routeAction")
        read = _stable_read(bot, MODEL_ROSTER_JS, with_timestamp=True)
        models = registry.record_roster(read[0], observed_at=read[1]) if isinstance(read, tuple) else None
        if models is None:
            # An unfamiliar list layout must not erase individual detail research.
            # The legacy visible slice can schedule reads without certifying coverage.
            visible = _stable_read(bot, _MODELS_JS)
            if not isinstance(visible, list):
                return 0
            models = visible
        for model in registry.next_models(models, per_cycle=per_cycle):
            if getattr(bot, "stopping", False):
                break
            model_id, name = model["id"], model["name"]
            registry.record_attempt(model_id, name)
            try:
                bot.ajax(f"ac_orders.php?mode=detail&id={model_id}&charter=0", "acModel")
                read = _stable_read(bot, _ENGINE_DETAIL_SNAPSHOT_JS, with_timestamp=True)
                if not isinstance(read, tuple):
                    continue
                snapshot, observed_at = read
                if not isinstance(snapshot, dict):
                    continue
                detail = snapshot.get("detail")
                catalog = parse_engine_catalog(snapshot.get("groups"))
            except EngineSelectionError as exc:
                log.info("Motor de %s (%s): pesquisa inconclusiva (%s).", name, model_id, exc)
                continue
            except Exception:
                log.warning("Motor de %s (%s): formulário indisponível no jogo.", name, model_id)
                continue
            if (not isinstance(detail, dict)
                    or type(detail.get("attribute_present")) is not bool):
                log.info("Motor de %s (%s): identidade do detalhe instável.", name, model_id)
                continue
            explicit = detail["attribute_present"]
            observed_id = detail.get("model_id")
            script_id = detail.get("script_model_id")
            if ((explicit and observed_id != model_id)
                    or (not explicit and observed_id is not None)
                    or (script_id is not None and script_id != model_id)):
                log.warning("Motor de %s (%s): ID de modelo divergente no detalhe.", name, model_id)
                continue
            try:
                variant_details = _observe_variant_details(bot, snapshot, catalog, observed_at)
            except Exception:
                log.debug("A pesquisa de detalhes por variante não foi concluída.")
                variant_details = {}
            if registry.record(model_id, name, catalog,
                               observed_model_id=observed_id if explicit else script_id,
                               observed_at=observed_at, variant_details=variant_details):
                collected += 1
            else:
                log.info("Motor de %s (%s): dados do formulário inconsistentes.", name, model_id)
        if collected:
            log.info("Pesquisa de motores: %d modelos atualizados no catálogo local.", collected)
        return collected
    finally:
        bot.close_popup(quiet=True)
