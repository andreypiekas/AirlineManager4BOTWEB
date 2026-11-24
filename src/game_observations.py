"""Conservative, read-only observations from the authenticated game DOM."""
from __future__ import annotations

import logging
import math
import re
import threading
import time

from hub_expansion import HubExpansionRegistry
from hub_registry import HubRegistry
from engine_catalog import EngineCatalogRegistry
from engine_detail import MODEL_DETAIL_IDENTITY_JS, parse_displayed_metrics
from engine_selection import (
    EngineSelectionError, _ENGINE_OPTIONS_JS, _SET_ENGINE_JS, parse_engine_catalog,
)

log = logging.getLogger("am4bot.observations")

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
  'a-check', 'maint check', 'verificacao de manutencao']);
const normalized = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
const rows = Array.from(panel.querySelectorAll('tr, .row'))
  .filter(row => row.children.length === 2)
  .map(row => Array.from(row.children, cell => String(cell.textContent || '').trim()))
  .filter(row => metricLabels.has(normalized(row[0])));
const costs = Array.from(panel.querySelectorAll('#acCost'),
  el => String(el.textContent || '').trim());
return {detail: identity, groups,
        metrics: {rows, costs}};
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
return rows.map(el => ({
  dep_id: ((String(el.getAttribute('onclick') || '').match(/(?:[?&]|\b)dep=(\d+)(?!\d)/) || [])[1]) || null,
  arr_id: ((String(el.getAttribute('onclick') || '').match(/(?:[?&]|\b)arr=(\d+)(?!\d)/) || [])[1]) || null,
  distance: el.getAttribute('data-distance'),
  runway: el.getAttribute('data-rwy'),
  y: el.getAttribute('data-yclass'),
  j: el.getAttribute('data-jclass'),
  f: el.getAttribute('data-fclass'),
  event_demand_boosted: /\bDemand is currently boosted due to a special event\b/i.test(el.textContent || '') ? true : null
}));
"""

_AIRPORT_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_COUNT = re.compile(r"^[0-9]{1,9}$")
_DISTANCE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def _stable_read(bot: object, script: str, *, with_timestamp: bool = False) -> object:
    """Return an identical DOM pair, optionally with its second-read timestamp."""
    try:
        first = bot.js(script)
        if first is None or getattr(bot, "stopping", False):
            return None
        stop = getattr(bot, "_stop", None)
        interrupted = stop.wait(0.3) if stop is not None else threading.Event().wait(0.3)
        if interrupted or getattr(bot, "stopping", False):
            return None
        second = bot.js(script)
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
        if raw.get("event_demand_boosted") is True:
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


def collect_owned_hub_demand(bot: object) -> int:
    """Search one purchased hub per cycle, using the game's read-only research."""
    return _collect_hub_demand(bot, external=False)


def collect_external_hub_demand(bot: object) -> int:
    """Search one fresh purchase-catalog airport outside the owned inventory."""
    if not bot.config.get_bool("investment", "planning_enabled"):
        return 0
    return _collect_hub_demand(bot, external=True)


def _collect_hub_demand(bot: object, *, external: bool) -> int:
    from fleet import _HUB_OPTIONS_JS, search_routes
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
        origins = expansion.external_research_origins(set(ids)) if external else ids
        origin = registry.next_demand_origin(origins)
        if origin is None:
            return 0
        # Reserve the rotation cursor before making AJAX requests. An empty,
        # inconsistent or interrupted response must not starve the next hub.
        distance = max(300, bot.config.get_int("settings", "route_max_distance_big", 6000))
        runway = max(0, bot.config.get_int("settings", "route_min_runway", 5000))
        # The legacy distance and runway preferences are not a universal
        # opportunity envelope. Alternate the normal query with a broad one
        # during investment planning, so small runways and long routes are
        # sampled without starving the normal search. Neither proves coverage.
        planning = getattr(bot.config, "get_bool", None)
        scope = None
        if callable(planning) and planning("investment", "planning_enabled"):
            distance, runway = min(distance, 25000), min(runway, 30000)
            scope = registry.next_demand_scope(origin)
            if scope == "broad":
                distance, runway = 20000, 0
            registry.record_demand_attempt(origin, search_scope=scope,
                                           max_distance=distance, min_runway=runway)
        else:
            registry.record_demand_attempt(origin)
        candidates = search_routes(bot, origin, distance, runway, persist_demand=False)
        read = _stable_read(bot, _VERIFIED_ROUTE_DEMAND_JS, with_timestamp=True)
        rows, read_at = read if isinstance(read, tuple) and len(read) == 2 else (None, None)
        samples = _verified_demand(candidates, rows, origin)
        if external:
            # A changed or missing ownership selector invalidates the external
            # classification. Keep the attempt, but discard its observations.
            confirmed_options = _stable_read(bot, _HUB_OPTIONS_JS)
            if (confirmed_options != options
                    or origin not in expansion.external_research_origins(set(ids))):
                return 0
        if not samples or any(sample["distance"] > distance + 0.001
                              or sample.get("destination_runway_ft", runway) < runway
                              for sample in samples):
            log.debug("Pesquisa de demanda do hub %s incompleta ou sem resultados confirmados.", origin)
            return 0
        count = registry.record_demand(origin, samples, observed_at=read_at, search_scope=scope)
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


def collect_external_route_details(bot: object) -> int:
    """Research one independent external route detail per planning cycle."""
    if not bot.config.get_bool("investment", "planning_enabled"):
        return 0
    return _collect_hub_route_details(bot, external=True)


def _collect_hub_route_details(bot: object, *, external: bool) -> int:
    from route_detail_evidence import collect_route_details

    if getattr(bot, "stopping", False):
        return 0
    inventory = HubRegistry().snapshot()
    if not inventory.get("hub_catalog_fresh"):
        return 0
    codes = {hub["id"]: hub.get("code") for hub in inventory["hubs"]}
    expansion = HubExpansionRegistry()
    if external:
        snapshot = expansion.external_demand_snapshot(set(codes))
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
    result = {selected: {"observed_at": observed_at, "metrics": metrics}}
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
                    result[variant.engine_id] = {"observed_at": stamp, "metrics": current_metrics}
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
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    try:
        bot.ajax("ac_orders.php?first=true", "routeAction")
        raw_models = _stable_read(bot, _MODELS_JS)
        if not isinstance(raw_models, list):
            return 0
        models = [{"id": row.get("id"), "name": row.get("name")}
                  for row in raw_models if isinstance(row, dict)]
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
