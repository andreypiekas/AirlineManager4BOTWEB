"""Read-only, sanitized DOM inventory for an *existing* authenticated game session.

Call ``probe_game_sources(bot)`` while the desired game popup is already open,
where ``bot`` is the application's running ``Bot`` instance. A Selenium driver
can be passed directly instead: ``probe_game_sources(bot.driver)``. The function
executes one DOM-only JavaScript snapshot through ``bot.js`` or Selenium's
``execute_script`` and returns an in-memory dictionary. It does not open popups,
navigate, send requests, persist state, or invoke game controls.

The result contains only fixed selector names, element counts, numeric game IDs,
bounded page numbers, and booleans indicating whether allowlisted DOM
attributes exist. IDs are sampled up to 40 per source, with separate total
counts and truncation flags. ID-bearing sources additionally report the number
of nodes with an explicit, parseable ID. ``pagination`` records only page
numbers supported by DOM evidence, flags conflicting observations, and reports
which known selectors and attributes supplied numeric evidence. A loading
indicator is reported without exposing its URL.
``aircraft_order_hub_selection`` checks the currently selected option against
the live ``#hubSelection`` value. This proves consistency of a visible DOM
selection only, and cannot establish a purchase or ownership of that hub.
``aircraft_checkout_diagnostics`` reports the structural location of possible
price fields and engine controls inside ``#acModel``. Candidate counts are
diagnostic only: they never verify the final price for a selected motor.
``model_hub_correlated`` requires a single, idle aircraft detail panel that
actually contains the selected hub control. It only describes one DOM snapshot.
``probe_flight_history_structure(session, aircraft_id)`` is a separate, explicit
read-only GET of one aircraft's details through the session owner. It returns
only structural counts and availability hints for A9 calibration research.
No flight IDs, dates, revenues, costs, or HTML leave the browser. The probe
cannot establish complete history, unique flights, or verified ledger costs.
The source view depends on the popup currently displayed. Missing selectors are
expected when their corresponding game pane is closed.

Example, from an already running bot process::

    import json
    from game_source_probe import probe_game_sources

    report = probe_game_sources(bot)
    print(json.dumps(report, indent=2))

No username, password, cookie, token, raw HTML, registration, or
human-readable page text is returned. The only attribute values emitted are
strictly validated numeric game IDs and bounded page numbers. The Python
boundary independently validates every field returned by JavaScript.
"""

from __future__ import annotations

import json
import re
from typing import Any


SAMPLE_LIMIT = 40
_NUMERIC_ID = re.compile(r"^[1-9][0-9]{0,13}$")
_MAX_COUNT = 10_000_000
_PAGINATION_EVIDENCE = (
    "popup_present",
    "pagination_present",
    "active_page_present",
    "current_page_attribute_numeric",
    "active_page_numeric",
    "total_pages_attribute_numeric",
    "total_pages_route_count_numeric",
    "loading_indicator_present",
)

# Structural leads for inspecting the actual aircraft checkout DOM. The game
# has not yet supplied an authenticated, verified final-price selector. These
# fixed selectors expose counts and currency-shape flags, never text or prices.
_CHECKOUT_PRICE_CANDIDATES = (
    ("data_price", "#acModel [data-price]"),
    ("data_final_price", "#acModel [data-final-price]"),
    ("data_total_price", "#acModel [data-total-price]"),
    ("id_price", "#acModel [id*='price' i]"),
    ("id_cost", "#acModel [id*='cost' i]"),
    ("class_price", "#acModel [class*='price' i]"),
    ("class_cost", "#acModel [class*='cost' i]"),
)

_CHECKOUT_CONTROL_SELECTORS = {
    "all_selects": "#acModel select",
    "all_radios": "#acModel input[type='radio']",
    "engine_named_selects": (
        "#acModel select[name*='engine' i], #acModel select[id*='engine' i], "
        "#acModel select[name*='motor' i], #acModel select[id*='motor' i]"
    ),
    "engine_named_radios": (
        "#acModel input[type='radio'][name*='engine' i], "
        "#acModel input[type='radio'][name*='motor' i]"
    ),
    "purchase_buttons": "#acModel #btnPurchaseIntro",
    "insufficient_balance_warnings": "#acModel #accountLow",
}

# Only these literal selectors and attribute *names* may appear in the result.
# Attribute values are examined exclusively to extract strictly numeric IDs.
_SOURCES = (
    {"key": "owned_hub_selector", "selector": "#hubSelect",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "owned_hub_options", "selector": "#hubSelect option",
     "attrs": ["value", "data-iata", "data-icao", "data-code", "title", "selected"],
     "id_source": "option"},
    {"key": "purchase_hub_country_selector", "selector": "#hubcountrySelector",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "purchase_hub_countries", "selector": "#hubcountrySelector option",
     "attrs": ["value", "selected", "disabled"], "id_source": "none"},
    {"key": "purchase_hub_selector", "selector": "#hubAirportSelector",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "purchase_hub_options", "selector": "#hubAirportSelector option",
     "attrs": ["value", "data-iata", "data-icao", "data-code", "selected"],
     "id_source": "option"},
    {"key": "purchase_hub_cost", "selector": "#hubCostInfo",
     "attrs": ["id"], "id_source": "none"},
    {"key": "purchase_hub_airport_info", "selector": "#airportInfo",
     "attrs": ["id"], "id_source": "none"},
    {"key": "acquired_hub_rows", "selector": "#hubList > .row[onclick]",
     "attrs": ["onclick"], "id_source": "none"},
    {"key": "aircraft_order_hub_selector", "selector": "#hubSelection",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "aircraft_order_hub_options", "selector": "#hubSelection option",
     "attrs": ["value", "selected"], "id_source": "option"},
    {"key": "aircraft_catalog", "selector": "#acListItems .acListItem",
     "attrs": ["onclick", "data-id", "data-range", "data-speed", "data-capacity",
               "data-fuel", "data-price"], "id_source": "model"},
    {"key": "aircraft_detail", "selector": "#acModel",
     "attrs": ["id", "data-model-id"], "id_source": "none"},
    {"key": "aircraft_registration", "selector": "#acReg",
     "attrs": ["id", "name", "value", "required"], "id_source": "none"},
    {"key": "fleet_popup", "selector": "#popContent",
     "attrs": ["data-current-page", "data-total-pages"], "id_source": "none"},
    {"key": "fleet_routes", "selector": "#popContent [id^='routeMainList']",
     "attrs": ["id", "data-dep", "data-arr", "data-origin-id",
               "data-destination-id", "data-home-hub-id", "data-aircraft-id"],
     "id_source": "route"},
    {"key": "fleet_parked", "selector": "#routesContainer [id^='routeMainParkedList']",
     "attrs": ["id", "data-home-hub-id", "data-aircraft-id"], "id_source": "parked"},
    {"key": "fleet_home_hub_attributes", "selector": "#popContent [data-home-hub-id]",
     "attrs": ["data-home-hub-id", "data-aircraft-id"],
     "id_source": "data", "id_attribute": "data-home-hub-id"},
    {"key": "fleet_aircraft_attributes", "selector": "#popContent [data-aircraft-id]",
     "attrs": ["data-aircraft-id", "data-home-hub-id"],
     "id_source": "data", "id_attribute": "data-aircraft-id"},
    {"key": "research_results", "selector": "#resResult #list .sorter",
     "attrs": ["onclick", "data-distance", "data-yclass", "data-jclass",
               "data-fclass", "data-large", "data-heavy", "data-rwy"],
     "id_source": "arrival"},
    {"key": "routes_pagination", "selector": "#popContent .pagination",
     "attrs": ["data-current-page", "data-total-pages"], "id_source": "none"},
    {"key": "routes_active_page",
     "selector": "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link",
     "attrs": ["aria-current", "data-page"], "id_source": "page"},
    {"key": "routes_count_label",
     "selector": "#popContent .row.font-weight-bold > .col-12.exo.text-center.p-2",
     "attrs": ["class"], "id_source": "none"},
    {"key": "route_details", "selector": "#rDetails",
     "attrs": ["id", "data-dep", "data-arr"], "id_source": "none"},
)

# This script is intentionally self-contained and uses only synchronous DOM reads.
# It never serializes source nodes, arbitrary attribute values or global objects.
PROBE_JS = ("const specs = " + json.dumps(_SOURCES) + ";\n"
            + "const checkoutPriceSpecs = " + json.dumps(_CHECKOUT_PRICE_CANDIDATES) + ";\n"
            + "const checkoutControlSpecs = " + json.dumps(_CHECKOUT_CONTROL_SELECTORS) + ";\n") + r"""
const sampleLimit = 40;
const isNumericId = value => /^[1-9][0-9]{0,13}$/.test(String(value ?? '').trim());
const pageNumber = value => {
  const text = String(value ?? '').trim();
  return /^[1-9][0-9]{0,2}$/.test(text) ? Number(text) : null;
};
const safeAttribute = (node, name) =>
  typeof node.getAttribute === 'function' ? node.getAttribute(name) : null;
const hasAttribute = (node, name) =>
  typeof node.hasAttribute === 'function' ? node.hasAttribute(name) :
  safeAttribute(node, name) !== null;

function idFromNode(node, spec) {
  const attr = name => safeAttribute(node, name) || '';
  let candidate = '';
  switch (spec.id_source) {
    case 'option':
      // The implicit option.value can equal its label, which is not an airport ID.
      candidate = attr('value');
      break;
    case 'route':
      candidate = (String(node.id || '').match(/^routeMainList([0-9]{1,14})$/) || [])[1];
      break;
    case 'parked':
      candidate = (String(node.id || '').match(/^routeMainParkedList([0-9]{1,14})$/) || [])[1];
      break;
    case 'model':
      candidate = isNumericId(attr('data-id')) ? attr('data-id') :
        (String(attr('onclick')).match(/\bid=([0-9]{1,14})(?![0-9])/) || [])[1];
      break;
    case 'arrival':
      candidate = (String(attr('onclick')).match(/\barr=([0-9]{1,14})(?![0-9])/) || [])[1];
      break;
    case 'data':
      candidate = attr(spec.id_attribute);
      break;
    case 'page':
      candidate = pageNumber(attr('data-page')) || pageNumber(node.textContent);
      break;
  }
  return isNumericId(candidate) ? String(candidate).trim() : null;
}

function addNumericId(ids, value) {
  if (isNumericId(value)) ids.add(String(value).trim());
}

function summarizeIds(ids) {
  const numericIds = Array.from(ids).slice(0, sampleLimit);
  return {numeric_id_count: ids.size, numeric_ids: numericIds,
          ids_truncated: ids.size > numericIds.length};
}

const result = {schema_version: 1, sources: {}, status_data: {}, pagination: {}};
for (const spec of specs) {
  const nodes = Array.from(document.querySelectorAll(spec.selector));
  const attributes = {};
  for (const name of spec.attrs) {
    attributes[name] = nodes.some(node => hasAttribute(node, name));
  }
  const ids = new Set();
  const linked = new Set();
  let parseableNodes = 0;
  for (const node of nodes) {
    const id = idFromNode(node, spec);
    if (id !== null) parseableNodes++;
    addNumericId(ids, id);
    if (spec.key === 'fleet_routes' && typeof node.querySelector === 'function') {
      const link = node.querySelector("a[onclick*='fleet_details.php']");
      const aircraftId = link &&
        (String(safeAttribute(link, 'onclick') || '')
          .match(/fleet_details\.php\?id=([0-9]{1,14})(?![0-9])/) || [])[1];
      addNumericId(linked, aircraftId);
    }
  }
  result.sources[spec.key] = {
    count: nodes.length, attribute_presence: attributes, ...summarizeIds(ids)
  };
  if (spec.id_source !== 'none') {
    result.sources[spec.key].id_parseable_nodes = parseableNodes;
  }
  if (spec.key === 'fleet_routes') {
    result.sources[spec.key].linked_aircraft_ids = Array.from(linked).slice(0, sampleLimit);
    result.sources[spec.key].linked_aircraft_id_count = linked.size;
    result.sources[spec.key].linked_aircraft_ids_truncated =
      linked.size > result.sources[spec.key].linked_aircraft_ids.length;
  }
}

// Read page metadata independently of route rows (the page may be loading).
// Keep conflicting evidence visible without returning any raw page text.
const pageValues = new Set();
const totalValues = new Set();
const observe = (set, value) => {
  const parsed = pageNumber(value);
  if (parsed !== null) set.add(parsed);
  return parsed !== null;
};
const popupNodes = document.querySelectorAll('#popContent');
const paginationNodes = document.querySelectorAll('#popContent .pagination');
const activeNodes = document.querySelectorAll(
  "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link");
let currentAttributeNumeric = false;
let totalAttributeNumeric = false;
let routeCountNumeric = false;
let activePageNumeric = false;
for (const node of popupNodes) {
  currentAttributeNumeric = observe(pageValues, safeAttribute(node, 'data-current-page')) ||
    currentAttributeNumeric;
  totalAttributeNumeric = observe(totalValues, safeAttribute(node, 'data-total-pages')) ||
    totalAttributeNumeric;
}
for (const node of paginationNodes) {
  currentAttributeNumeric = observe(pageValues, safeAttribute(node, 'data-current-page')) ||
    currentAttributeNumeric;
  totalAttributeNumeric = observe(totalValues, safeAttribute(node, 'data-total-pages')) ||
    totalAttributeNumeric;
}
for (const node of activeNodes) {
  activePageNumeric = observe(pageValues, safeAttribute(node, 'data-page')) ||
    activePageNumeric;
  activePageNumeric = observe(pageValues, node.textContent) || activePageNumeric;
}
// AM4 shows "205 Routes" and uses offsets 0, 20, 40 ... even when
// fewer than 20 rows are rendered because aircraft statuses change.
const routeCountNodes = document.querySelectorAll(
  '#popContent .row.font-weight-bold > .col-12.exo.text-center.p-2');
for (const node of routeCountNodes) {
  const match = String(node.textContent || '').trim().match(/^([1-9][0-9]{0,4})\s+Routes$/i);
  if (match) {
    routeCountNumeric = observe(totalValues, Math.ceil(Number(match[1]) / 20)) ||
      routeCountNumeric;
  }
}
const currentPage = pageValues.size === 1 ? Array.from(pageValues)[0] : null;
const totalPages = totalValues.size === 1 ? Array.from(totalValues)[0] : null;
result.pagination = {
  current_page: currentPage,
  total_pages: totalPages,
  evidence_conflict: pageValues.size > 1 || totalValues.size > 1 ||
    (currentPage !== null && totalPages !== null && currentPage > totalPages),
  evidence: {
    popup_present: popupNodes.length > 0,
    pagination_present: paginationNodes.length > 0,
    active_page_present: activeNodes.length > 0,
    current_page_attribute_numeric: currentAttributeNumeric,
    active_page_numeric: activePageNumeric,
    total_pages_attribute_numeric: totalAttributeNumeric,
    total_pages_route_count_numeric: routeCountNumeric,
    // Equivalent to the existing Bot.open_popup() loader check.
    loading_indicator_present:
      document.querySelectorAll("#popContent img[src*='loader']").length > 0
  }
};

// The selected property reflects the live select state; the HTML 'selected'
// attribute can remain stale after a user/script changes the current value.
const orderHubSelectors = Array.from(document.querySelectorAll('#hubSelection'));
const orderHubOptions = Array.from(document.querySelectorAll('#hubSelection option'));
const orderHubSelection = {
  selector_count: orderHubSelectors.length,
  option_count: orderHubOptions.length,
  selected_option_count: orderHubOptions.filter(option => option.selected === true).length,
  selected_hub_id: null,
  status: orderHubSelectors.length === 0 ? 'missing' :
    orderHubSelectors.length !== 1 ? 'ambiguous' : 'unverified'
};
if (orderHubSelectors.length === 1) {
  const selector = orderHubSelectors[0];
  if (selector.disabled === true) {
    orderHubSelection.status = 'disabled';
  } else {
    const chosen = String(selector.value ?? '').trim();
    const matching = orderHubOptions.filter(option =>
      String(option.value ?? '').trim() === chosen);
    const selected = orderHubOptions.filter(option => option.selected === true);
    if (isNumericId(chosen) && matching.length === 1 && selected.length === 1 &&
        selected[0] === matching[0] && matching[0].disabled === false &&
        selector.disabled === false) {
      orderHubSelection.selected_hub_id = chosen;
      orderHubSelection.status = 'dom_consistent';
    }
  }
}
result.aircraft_order_hub_selection = orderHubSelection;

// Snapshot only structural clues for the unverified final-price field.
// Never emit checkout text, attributes, registration, or potential balances.
const checkoutPanels = Array.from(document.querySelectorAll('#acModel'));
const checkoutModelId = checkoutPanels.length === 1 ?
  safeAttribute(checkoutPanels[0], 'data-model-id') : null;
const checkoutAjaxIdleConfirmed = typeof window !== 'undefined' &&
  !!window.jQuery && window.jQuery.active === 0;
const checkoutAjaxActive = typeof window !== 'undefined' &&
  !!window.jQuery && typeof window.jQuery.active === 'number' &&
  window.jQuery.active > 0;
const checkoutLoading = checkoutPanels.some(panel =>
  safeAttribute(panel, 'aria-busy') === 'true' ||
  (typeof panel.querySelector === 'function' &&
    !!panel.querySelector('img[src*="loader"], [aria-busy="true"]')));
const modelHubCorrelated = checkoutPanels.length === 1 &&
  isNumericId(checkoutModelId) && orderHubSelection.status === 'dom_consistent' &&
  orderHubSelectors.length === 1 &&
  typeof checkoutPanels[0].contains === 'function' &&
  checkoutPanels[0].contains(orderHubSelectors[0]) &&
  checkoutAjaxIdleConfirmed && !checkoutLoading;
const checkoutControls = {};
for (const [key, selector] of Object.entries(checkoutControlSpecs)) {
  checkoutControls[key] = document.querySelectorAll(selector).length;
}
const checkoutPrices = {};
for (const [key, selector] of checkoutPriceSpecs) {
  const nodes = Array.from(document.querySelectorAll(selector));
  let currencyTextNodes = 0;
  let numericPriceAttributeNodes = 0;
  for (const node of nodes) {
    const text = String(node.textContent || '').slice(0, 256);
    if (/(?:US\s*\$|USD\s*|\$)\s*[1-9][0-9,.]{0,14}/i.test(text)) {
      currencyTextNodes++;
    }
    if (['data-price', 'data-final-price', 'data-total-price'].some(name =>
      isNumericId(safeAttribute(node, name)))) {
      numericPriceAttributeNodes++;
    }
  }
  checkoutPrices[key] = {
    count: nodes.length,
    currency_text_nodes: currencyTextNodes,
    numeric_price_attribute_nodes: numericPriceAttributeNodes
  };
}
result.aircraft_checkout_diagnostics = {
  detail_panel_count: checkoutPanels.length,
  detail_model_id: isNumericId(checkoutModelId) ?
    String(checkoutModelId).trim() : null,
  ajax_active: checkoutAjaxActive,
  ajax_idle_confirmed: checkoutAjaxIdleConfirmed,
  detail_loading: checkoutLoading,
  model_hub_correlated: modelHubCorrelated,
  controls: checkoutControls,
  price_candidates: checkoutPrices
};

const hasStatus = typeof window !== 'undefined' &&
  window.statusData !== null && typeof window.statusData === 'object' &&
  !Array.isArray(window.statusData);
const keys = hasStatus ? Object.keys(window.statusData) : [];
const statusIds = new Set();
for (const key of keys) addNumericId(statusIds, key);
result.status_data = {present: hasStatus, count: keys.length, ...summarizeIds(statusIds)};
return result;
"""


# The legacy financial reader fetches the same aircraft-details fragment.
# This diagnostic keeps the response entirely inside the authenticated browser
# and returns counts of candidate evidence, never individual flight records.
FLIGHT_HISTORY_PROBE_JS = r"""
const aircraftId = String(arguments[0] ?? '');
const done = arguments[arguments.length - 1];
const numericId = value => /^[1-9][0-9]{0,13}$/.test(String(value ?? ''));
const absoluteTime = value => {
  const text = String(value ?? '').trim();
  if (/^[0-9]{10}(?:[0-9]{3})?$/.test(text)) {
    const timestamp = Number(text) * (text.length === 10 ? 1000 : 1);
    return timestamp >= 946684800000 && timestamp < 4102444800000;
  }
  return /^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$/i.test(text)
    && Number.isFinite(Date.parse(text));
};
const newReport = status => ({
  schema_version: 1, status, aircraft_id: aircraftId,
  history_present: false, row_count: 0, four_column_rows: 0,
  numeric_cost_rows: 0, currency_revenue_rows: 0,
  id_candidates: Object.fromEntries(['data_flight_id', 'data_id', 'dom_id']
    .map(key => [key, {rows: 0, distinct: 0, duplicates: 0}])),
  absolute_time_sources: {time_datetime: 0, data_completed_at: 0, data_timestamp: 0},
  pagination_controls_present: false
});
const inspect = html => {
  const report = newReport('inspected');
  const doc = new DOMParser().parseFromString(html, 'text/html');
  report.history_present = doc.querySelectorAll('#flight-history').length === 1;
  if (!report.history_present) {
    report.status = 'missing_history';
    return report;
  }
  const rows = Array.from(doc.querySelectorAll('#flight-history > .row'));
  report.row_count = rows.length;
  report.pagination_controls_present =
    doc.querySelectorAll('#flight-history .pagination, #flight-history [data-page]').length > 0;
  const ids = {data_flight_id: new Set(), data_id: new Set(), dom_id: new Set()};
  for (const row of rows) {
    const values = {
      data_flight_id: row.getAttribute('data-flight-id'),
      data_id: row.getAttribute('data-id'),
      dom_id: row.getAttribute('id')
    };
    for (const [key, value] of Object.entries(values)) {
      if (!numericId(value)) continue;
      report.id_candidates[key].rows++;
      ids[key].add(String(value));
    }
    const time = row.querySelector('time[datetime]');
    if (time && absoluteTime(time.getAttribute('datetime'))) {
      report.absolute_time_sources.time_datetime++;
    }
    if (absoluteTime(row.getAttribute('data-completed-at'))) {
      report.absolute_time_sources.data_completed_at++;
    }
    if (absoluteTime(row.getAttribute('data-timestamp'))) {
      report.absolute_time_sources.data_timestamp++;
    }
    const cells = Array.from(row.querySelectorAll(':scope > .col-3'));
    if (cells.length !== 4) continue;
    report.four_column_rows++;
    const looksNumeric = value => /[0-9]/.test(String(value || ''));
    if (looksNumeric(cells[1].textContent) && looksNumeric(cells[2].textContent)) {
      report.numeric_cost_rows++;
    }
    if (/(?:US\s*\$|USD\s*|\$)\s*[0-9]/i.test(String(cells[3].textContent || ''))) {
      report.currency_revenue_rows++;
    }
  }
  for (const [key, values] of Object.entries(ids)) {
    report.id_candidates[key].distinct = values.size;
    report.id_candidates[key].duplicates = report.id_candidates[key].rows - values.size;
  }
  return report;
};
(async () => {
  if (!numericId(aircraftId)) return newReport('invalid_id');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch('fleet_details.php?id=' + aircraftId, {
      credentials: 'same-origin', signal: controller.signal
    });
    if (!response.ok) return newReport('http_error');
    return inspect(await response.text());
  } catch (error) {
    return newReport(error && error.name === 'AbortError' ? 'timeout' : 'fetch_error');
  } finally {
    clearTimeout(timeout);
  }
})().then(done, () => done(newReport('fetch_error')));
"""


def _count(value: Any) -> int:
    return value if type(value) is int and 0 <= value <= _MAX_COUNT else 0


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for candidate in value[:SAMPLE_LIMIT * 10]:
        if (type(candidate) is str and len(candidate) <= 14
                and _NUMERIC_ID.fullmatch(candidate) and candidate not in ids):
            ids.append(candidate)
            if len(ids) == SAMPLE_LIMIT:
                break
    return ids


def _id_fields(data: dict) -> dict:
    sample = _ids(data.get("numeric_ids"))
    total = max(_count(data.get("numeric_id_count")), len(sample))
    return {"numeric_ids": sample, "numeric_id_count": total,
            "ids_truncated": total > len(sample)}


def _page(value: Any) -> int | None:
    return value if type(value) is int and 1 <= value <= 999 else None


def _sanitize(raw: Any) -> dict:
    if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
            or raw["schema_version"] != 1):
        raise ValueError("Unexpected DOM probe response")
    sources = raw.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    cleaned: dict[str, dict] = {}
    for spec in _SOURCES:
        entry = sources.get(spec["key"])
        entry = entry if isinstance(entry, dict) else {}
        attrs = entry.get("attribute_presence")
        attrs = attrs if isinstance(attrs, dict) else {}
        cleaned_entry = {
            "selector": spec["selector"],
            "count": _count(entry.get("count")),
            "attribute_presence": {name: attrs.get(name) is True for name in spec["attrs"]},
            **_id_fields(entry),
        }
        if spec["id_source"] != "none":
            matched = entry.get("id_parseable_nodes")
            cleaned_entry["id_parseable_nodes"] = (
                min(matched, cleaned_entry["count"])
                if type(matched) is int and 0 <= matched <= _MAX_COUNT else None
            )
        if spec["key"] == "fleet_routes":
            linked = _ids(entry.get("linked_aircraft_ids"))
            cleaned_entry["linked_aircraft_ids"] = linked
            cleaned_entry["linked_aircraft_id_count"] = max(
                _count(entry.get("linked_aircraft_id_count")), len(linked))
            cleaned_entry["linked_aircraft_ids_truncated"] = (
                cleaned_entry["linked_aircraft_id_count"] > len(linked))
        cleaned[spec["key"]] = cleaned_entry

    status = raw.get("status_data")
    status = status if isinstance(status, dict) else {}
    pagination = raw.get("pagination")
    pagination = pagination if isinstance(pagination, dict) else {}
    evidence = pagination.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    current_page = _page(pagination.get("current_page"))
    total_pages = _page(pagination.get("total_pages"))
    selection = raw.get("aircraft_order_hub_selection")
    selection = selection if isinstance(selection, dict) else {}
    selector_count = _count(selection.get("selector_count"))
    option_count = _count(selection.get("option_count"))
    selected_count = _count(selection.get("selected_option_count"))
    hub_id = selection.get("selected_hub_id")
    selection_status = selection.get("status")
    if selection_status not in ("missing", "ambiguous", "disabled", "unverified",
                                "dom_consistent"):
        selection_status = "unverified"
    if (selection_status != "dom_consistent" or selector_count != 1
            or selected_count != 1
            or option_count < 1 or type(hub_id) is not str
            or _NUMERIC_ID.fullmatch(hub_id) is None):
        hub_id = None
        if selection_status == "dom_consistent":
            selection_status = "unverified"
    checkout = raw.get("aircraft_checkout_diagnostics")
    checkout = checkout if isinstance(checkout, dict) else {}
    detail_panel_count = _count(checkout.get("detail_panel_count"))
    detail_model_id = checkout.get("detail_model_id")
    if (detail_panel_count != 1 or type(detail_model_id) is not str
            or _NUMERIC_ID.fullmatch(detail_model_id) is None):
        detail_model_id = None
    model_hub_correlated = (
        checkout.get("model_hub_correlated") is True
        and checkout.get("ajax_active") is False
        and checkout.get("ajax_idle_confirmed") is True
        and checkout.get("detail_loading") is False
        and detail_model_id is not None
        and hub_id is not None
        and selection_status == "dom_consistent"
    )
    checkout_controls = checkout.get("controls")
    checkout_controls = checkout_controls if isinstance(checkout_controls, dict) else {}
    checkout_prices = checkout.get("price_candidates")
    checkout_prices = checkout_prices if isinstance(checkout_prices, dict) else {}
    price_candidates = {}
    for key, selector in _CHECKOUT_PRICE_CANDIDATES:
        candidate = checkout_prices.get(key)
        candidate = candidate if isinstance(candidate, dict) else {}
        count = _count(candidate.get("count"))
        price_candidates[key] = {
            "selector": selector,
            "count": count,
            "currency_text_nodes": min(count, _count(candidate.get("currency_text_nodes"))),
            "numeric_price_attribute_nodes": min(
                count, _count(candidate.get("numeric_price_attribute_nodes"))),
        }
    return {
        "schema_version": 1,
        "sources": cleaned,
        "aircraft_order_hub_selection": {
            "selector_count": selector_count,
            "option_count": option_count,
            "selected_option_count": selected_count,
            "selected_hub_id": hub_id,
            "status": selection_status,
            "read_only": True,
        },
        "aircraft_checkout_diagnostics": {
            "detail_panel_count": detail_panel_count,
            "detail_model_id": detail_model_id,
            "ajax_active": checkout.get("ajax_active") is True,
            "ajax_idle_confirmed": checkout.get("ajax_idle_confirmed") is True,
            "detail_loading": checkout.get("detail_loading") is True,
            "model_hub_correlated": model_hub_correlated,
            "controls": {key: _count(checkout_controls.get(key))
                         for key in _CHECKOUT_CONTROL_SELECTORS},
            "price_candidates": price_candidates,
            "price_verified": False,
            "read_only": True,
        },
        "pagination": {
            "current_page": current_page,
            "total_pages": total_pages,
            "evidence_conflict": pagination.get("evidence_conflict") is True or (
                current_page is not None and total_pages is not None
                and current_page > total_pages),
            "evidence": {name: evidence.get(name) is True
                         for name in _PAGINATION_EVIDENCE},
        },
        "status_data": {"present": status.get("present") is True,
                        "count": _count(status.get("count")), **_id_fields(status)},
    }


def probe_game_sources(session: Any) -> dict:
    """Inspect one already-loaded page via ``Bot.js`` or ``driver.execute_script``.

    The caller owns the authenticated session and decides which popup is visible.
    The probe makes precisely one script call and cannot change the game state.
    It neither logs nor stores the result; the caller can serialize it as JSON.

    Raises ``TypeError`` for an unsupported session and ``ValueError`` if the
    driver returns a malformed response. Driver exceptions propagate normally.
    """
    execute = getattr(session, "js", None)
    if not callable(execute):
        driver = getattr(session, "driver", session)
        execute = getattr(driver, "execute_script", None)
    if not callable(execute):
        raise TypeError("Expected an existing Bot or Selenium WebDriver session")
    return _sanitize(execute(PROBE_JS))


_FLIGHT_ID_CANDIDATES = ("data_flight_id", "data_id", "dom_id")
_FLIGHT_TIME_SOURCES = ("time_datetime", "data_completed_at", "data_timestamp")
_FLIGHT_STATUSES = {"inspected", "missing_history", "http_error", "timeout", "fetch_error"}


def _sanitize_flight_history(raw: Any, aircraft_id: str) -> dict:
    """Keep only bounded structural signals, even if the driver is compromised."""
    if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
            or raw["schema_version"] != 1 or raw.get("aircraft_id") != aircraft_id):
        raise ValueError("Unexpected flight-history probe response")
    status = raw.get("status")
    if status not in _FLIGHT_STATUSES:
        status = "fetch_error"
    present = status == "inspected" and raw.get("history_present") is True
    if status == "inspected" and not present:
        status = "missing_history"
    count = _count(raw.get("row_count")) if present else 0
    candidates = raw.get("id_candidates")
    candidates = candidates if isinstance(candidates, dict) else {}
    ids = {}
    for key in _FLIGHT_ID_CANDIDATES:
        entry = candidates.get(key)
        entry = entry if isinstance(entry, dict) else {}
        rows = min(count, _count(entry.get("rows")))
        distinct = min(rows, _count(entry.get("distinct")))
        # Duplicate counts are derived from rows and distinct IDs, never trusted.
        ids[key] = {"rows": rows, "distinct": distinct,
                    "duplicates": rows - distinct}
    times = raw.get("absolute_time_sources")
    times = times if isinstance(times, dict) else {}
    return {
        "schema_version": 1, "aircraft_id": aircraft_id,
        "status": status, "history_present": present, "row_count": count,
        "four_column_rows": min(count, _count(raw.get("four_column_rows"))),
        "numeric_cost_rows": min(count, _count(raw.get("numeric_cost_rows"))),
        "currency_revenue_rows": min(count, _count(raw.get("currency_revenue_rows"))),
        "id_candidates": ids,
        "absolute_time_sources": {
            key: min(count, _count(times.get(key))) for key in _FLIGHT_TIME_SOURCES
        },
        "pagination_controls_present": present and raw.get("pagination_controls_present") is True,
        "possible_truncation": count >= 20,
        "flight_identity_verified": False,
        "complete_history_verified": False,
        "financial_ledger_verified": False,
        "read_only": True,
    }


def probe_flight_history_structure(session: Any, aircraft_id: str | int) -> dict:
    """Inspect one aircraft's history through the authenticated Selenium owner.

    Performs one read-only GET for ``fleet_details.php``. Results are
    diagnostics for source research only, never accounting evidence for A9.
    """
    if type(aircraft_id) not in (str, int) or not _NUMERIC_ID.fullmatch(str(aircraft_id)):
        raise ValueError("Expected a positive numeric aircraft ID")
    driver = getattr(session, "driver", session)
    execute = getattr(driver, "execute_async_script", None)
    if not callable(execute):
        raise TypeError("Expected an existing Selenium WebDriver async session")
    normalized_id = str(aircraft_id)
    return _sanitize_flight_history(
        execute(FLIGHT_HISTORY_PROBE_JS, normalized_id), normalized_id
    )
