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
