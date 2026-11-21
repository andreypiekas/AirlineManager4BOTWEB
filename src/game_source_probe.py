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
    "loading_indicator_present",
)

# Only these literal selectors and attribute *names* may appear in the result.
# Attribute values are examined exclusively to extract strictly numeric IDs.
_SOURCES = (
    {"key": "owned_hub_selector", "selector": "#hubSelect",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "owned_hub_options", "selector": "#hubSelect option",
     "attrs": ["value", "data-iata", "data-icao", "data-code", "title", "selected"],
     "id_source": "option"},
    {"key": "purchase_hub_selector", "selector": "#hubSelection",
     "attrs": ["id", "name", "disabled"], "id_source": "none"},
    {"key": "purchase_hub_options", "selector": "#hubSelection option",
     "attrs": ["value", "data-iata", "data-icao", "data-code", "selected"],
     "id_source": "option"},
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
               "data-fclass", "data-rwy"], "id_source": "arrival"},
    {"key": "routes_pagination", "selector": "#popContent .pagination",
     "attrs": ["data-current-page", "data-total-pages"], "id_source": "none"},
    {"key": "routes_active_page",
     "selector": "#popContent .pagination .active, #popContent .pagination [aria-current='page']",
     "attrs": ["aria-current", "data-page"], "id_source": "page"},
    {"key": "route_details", "selector": "#rDetails",
     "attrs": ["id", "data-dep", "data-arr"], "id_source": "none"},
)

# This script is intentionally self-contained and uses only synchronous DOM reads.
# It never serializes source nodes, arbitrary attribute values or global objects.
PROBE_JS = "const specs = " + json.dumps(_SOURCES) + ";\n" + r"""
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
  "#popContent .pagination .active, #popContent .pagination [aria-current='page']");
let currentAttributeNumeric = false;
let totalAttributeNumeric = false;
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
    // Equivalent to the existing Bot.open_popup() loader check.
    loading_indicator_present:
      document.querySelectorAll("#popContent img[src*='loader']").length > 0
  }
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
    return {
        "schema_version": 1,
        "sources": cleaned,
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
