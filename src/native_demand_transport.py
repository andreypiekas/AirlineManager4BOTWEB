"""Read detached responses from the game's native passenger-demand search."""
from __future__ import annotations

from collections.abc import Sequence

from selenium.common.exceptions import WebDriverException

from route_stopover import ROUTE_EVENT_WARNING_JS

_CONCURRENCY = 4
_REQUEST_TIMEOUT_MS = 4000

_READ_DEMAND_BATCH_JS = r"""
const [jobs, timeout, done] = arguments;
const airportId = /^[1-9][0-9]{0,11}$/;
const count = /^[0-9]{1,9}$/;
const distance = /^[0-9]+(?:\.[0-9]+)?$/;
const routeURL = /(?:^|['"])(\/?route_research_route\.php\?[^'"\s<>#]+)(?=$|['"])/g;
const busy = 'img[src*="loader"], [aria-busy="true"]';
const emptyNotice = 'There were no results to your search';

function readRows(html, origin, destination) {
  // A template keeps scripts, handlers and subresources inert during parsing.
  const template = document.createElement('template');
  template.innerHTML = html;
  const fragment = template.content;
  const lists = fragment.querySelectorAll('#list');
  if (lists.length !== 1 || fragment.querySelector(busy)) return null;
  const list = lists[0];
  const cards = [...fragment.querySelectorAll('.sorter')];
  const notices = list.querySelectorAll(':scope > .row > .col-12 > .alert.alert-info');
  if (!cards.length) {
    const notice = notices[0];
    return list.parentNode === fragment && notices.length === 1 && notice.textContent.trim() === emptyNotice &&
      list.textContent.trim() === emptyNotice &&
      !notice.closest('[hidden], .d-none, [aria-hidden="true"]') ? [] : null;
  }
  if ([...notices].some(notice => notice.textContent.trim() === emptyNotice) ||
      (destination !== '0' && cards.length !== 1)) return null;

  const rows = [];
  const seen = new Set([origin]);
  for (const card of cards) {
    if (!list.contains(card)) return null;
    const links = [...(card.getAttribute('onclick') || '').trim().matchAll(routeURL)];
    if (links.length !== 1) return null;
    const link = new URL(links[0][1], location.origin);
    const departures = link.searchParams.getAll('dep');
    const arrivals = link.searchParams.getAll('arr');
    if (departures.length !== 1 || departures[0] !== origin || arrivals.length !== 1) return null;
    const [arrival] = arrivals;
    if (!airportId.test(arrival) || seen.has(arrival) ||
        (destination !== '0' && arrival !== destination)) return null;

    const fields = ['y', 'j', 'f'].map(cabin => card.getAttribute('data-' + cabin + 'class'));
    if (fields.some(value => !count.test(value))) return null;
    const [y, j, f] = fields.map(Number);
    const row = {
      destination_id: arrival, y, j, f,
      event_demand_boosted: EVENT_WARNING.test(card.textContent) ? true : null
    };
    const km = card.getAttribute('data-distance');
    const ft = card.getAttribute('data-rwy');
    if (distance.test(km) && Number.isFinite(Number(km)) && Number(km) > 0) row.distance_km = Number(km);
    if (count.test(ft) && Number(ft) > 0 && Number(ft) <= 30000) row.runway_ft = Number(ft);
    rows.push(row);
    seen.add(arrival);
  }
  return rows;
}

async function search([origin, country, destination, limitKm]) {
  if (!['https://www.airlinemanager.com', 'https://airlinemanager.com'].includes(location.origin) ||
      typeof origin !== 'string' || !airportId.test(origin) ||
      typeof destination !== 'string' || (destination !== '0' && !airportId.test(destination)) ||
      destination === origin || typeof country !== 'string' || !country ||
      country.length > 100 || country !== country.trim() || /[\x00-\x1f\x7f]/.test(country) ||
      !Number.isInteger(limitKm) || limitKm < 500 || limitKm > 20000 ||
      (destination !== '0' && limitKm !== 20000)) return null;
  try {
    const params = new URLSearchParams({
      mode: 'search', rwy: '1000', dist: String(limitKm), depId: origin, arr: country, arrId: destination, charter: '0'
    });
    if (typeof fbSig !== 'undefined') params.set('fbSig', fbSig);
    const response = await fetch('/research_main.php?' + params, {
      method: 'GET', mode: 'same-origin', credentials: 'same-origin', redirect: 'error',
      cache: 'no-store', signal: AbortSignal.timeout(timeout)
    });
    return response.ok ? readRows(await response.text(), origin, destination) : null;
  } catch {
    return null;
  }
}

Promise.all(jobs.map(search)).then(done, () => done(null));
""".replace("EVENT_WARNING", ROUTE_EVENT_WARNING_JS)


def read_demand_batch(bot: object, jobs: Sequence[tuple[str, str, str, int]]) -> list[dict]:
    """Return one result per job in input order. An empty search carries no demand values."""
    results = [
        {"origin_id": origin, "country": country, "destination_id": destination, "limit_km": limit_km, "rows": None}
        for origin, country, destination, limit_km in jobs
    ]
    for offset in range(0, len(results), _CONCURRENCY):
        if getattr(bot, "stopping", False):
            break
        group = results[offset:offset + _CONCURRENCY]
        requests = jobs[offset:offset + _CONCURRENCY]
        try:
            answer = bot.driver.execute_async_script(_READ_DEMAND_BATCH_JS, requests, _REQUEST_TIMEOUT_MS)
        except WebDriverException:
            # The in-flight script may still be running after a driver timeout.
            break
        if isinstance(answer, list) and len(answer) == len(group):
            for result, rows in zip(group, answer):
                if isinstance(rows, list):
                    result["rows"] = rows
    return results
