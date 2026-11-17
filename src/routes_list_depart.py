"""Safe individual departures using AM4's real Fleet route rows.

Verified against the AM4 game HTML supplied on 2026-11-17:
  #routeMainList36562620 (route ID)
    a[onclick*="fleet_details.php?id=24265127"] (aircraft ID)
    button#listDepart36562620
      Ajax('route_depart.php?id=36562620&ref=list&costIndex=200','runme',this)

IMPORTANT: route_depart.php?id is a ROUTE ID, not an aircraft ID.
Only the native button inside a route row explicitly bound to the eligible
aircraft may be clicked; never synthesize an API call or use Depart All.
"""
from __future__ import annotations

import html
import logging
import re
from urllib.parse import parse_qs

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from fleet_single_depart import _confirm_inflight

log = logging.getLogger("am4bot.vuelos")
_ID = re.compile(r"^[0-9]{1,14}$")
_ROUTE_REQUEST = re.compile(r"""route_depart\.php\?([^'"<>\s();]{1,320})""", re.I)

# Read ONLY the 20-or-fewer routes visible on the current Fleet page. The
# aircraft-to-route association is established in the same native route row.
# The link's ID is the AIRCRAFT; row/button IDs are the ROUTE.
_LIST_ROWS_JS = r"""
const root = document.querySelector("#routeAction #routesContainer");
if (!root) return [];
return Array.from(root.querySelectorAll('[id^="routeMainList"]')).map(row => {
  const routeMatch = row.id.match(/^routeMainList(\d{1,14})$/);
  const routeId = routeMatch ? routeMatch[1] : "";
  const links = Array.from(row.querySelectorAll('a[onclick*="fleet_details.php?id="]'));
  const aircraftIds = links.map(link => {
    const hit = (link.getAttribute("onclick") || "").match(/fleet_details\.php\?id=(\d{1,14})/);
    return hit ? hit[1] : "";
  }).filter(Boolean);
  const aircraftId = aircraftIds.length === 1 ? aircraftIds[0] : "";
  const button = routeId ? row.querySelector('[id="listDepart' + routeId + '"]') : null;
  return {
    row_id: row.id,
    route_id: routeId,
    aircraft_id: aircraftId,
    link_count: links.length,
    button_id: button ? button.id : "",
    action: button ? (button.getAttribute("onclick") || "") : "",
    label: button ? (button.textContent || "").trim().slice(0, 40) : "",
    visible: !!button && !!button.getClientRects().length,
    disabled: !button || !!button.disabled || button.classList.contains("not-active") ||
              button.getAttribute("aria-disabled") === "true",
  };
});
"""

# Validate the same native row AND native button immediately before Selenium
# clicks. A different aircraft/route after page mutation is never accepted.
_MARK_ROUTE_JS = r"""
const [aircraftId, routeId, expected] = Array.from(arguments, String);
if (!/^\d{1,14}$/.test(aircraftId) || !/^\d{1,14}$/.test(routeId)) return false;
const root = document.querySelector("#routeAction #routesContainer");
const row = document.getElementById("routeMainList" + routeId);
if (!root || !row || !root.contains(row)) return false;
const anchors = Array.from(row.querySelectorAll('a[onclick*="fleet_details.php?id="]'));
if (anchors.length !== 1) return false;
const hit = (anchors[0].getAttribute("onclick") || "").match(/fleet_details\.php\?id=(\d{1,14})/);
if (!hit || hit[1] !== aircraftId) return false;
const button = row.querySelector('[id="listDepart' + routeId + '"]');
if (!button || !button.getClientRects().length || button.disabled ||
    button.classList.contains("not-active") || button.getAttribute("aria-disabled") === "true")
    return false;
if ((button.getAttribute("onclick") || "") !== expected) return false;
root.querySelectorAll("[data-am4-safe-route-depart]").forEach(el =>
  el.removeAttribute("data-am4-safe-route-depart"));
button.setAttribute("data-am4-safe-route-depart", aircraftId);
return true;
"""


def native_route_button(aircraft_id: str, item: dict) -> dict | None:
    """Validate the real aircraft->route->button correspondence from one row.

    ID in the HTTP request is the ROUTE ID. We require the native game's
    ref=list contract, the unique matching row and non-bulk behavior.
    """
    aircraft_id = str(aircraft_id)
    if not _ID.fullmatch(aircraft_id) or not isinstance(item, dict):
        return None
    route_id = str(item.get("route_id") or "")
    if not _ID.fullmatch(route_id):
        return None
    if (str(item.get("aircraft_id")) != aircraft_id
            or item.get("link_count") != 1
            or item.get("row_id") != "routeMainList" + route_id
            or item.get("button_id") != "listDepart" + route_id):
        return None
    if item.get("disabled") or not item.get("visible"):
        return None
    if str(item.get("label") or "").lower() not in ("depart", "decolar", "despegar"):
        return None
    action = html.unescape(str(item.get("action") or ""))
    if action.lower().count("route_depart.php?") != 1:
        return None
    request = _ROUTE_REQUEST.search(action)
    if not request or "departAll" in action:
        return None
    query = {key.lower(): values for key, values in
             parse_qs(request.group(1), keep_blank_values=True).items()}
    # Exact live game contract. Reject unknown endpoint parameters, bulk IDs,
    # reordered/multiple targets, or a route belonging to a different row.
    if set(query) - {"id", "ref", "costindex"}:
        return None
    if query.get("id") != [route_id] or query.get("ref") != ["list"]:
        return None
    if "costindex" in query and (
        len(query["costindex"]) != 1
        or not query["costindex"][0].isdigit()
    ):
        return None
    if "Ajax(" not in action:
        return None
    return item


def collect_route_rows(bot) -> list[dict]:
    rows = bot.js(_LIST_ROWS_JS)
    return rows if isinstance(rows, list) else []


def route_list_dispatch(bot, registry, eligible: list, *, limit: int = 20) -> dict:
    """Click verified Fleet row controls; confirm each flight before the next."""
    from selective_depart import collect_dispatch_rows, plan_dispatch

    result = {"status": "controle_individual_nao_disponivel", "departed": 0,
              "native_individual": 0, "not_supported": 0}
    if not eligible:
        return result
    try:
        rows = collect_route_rows(bot)
    except WebDriverException:
        result["not_supported"] = len(eligible)
        return result
    matching_rows: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        matching_rows.setdefault(str(row.get("aircraft_id") or ""), []).append(row)
    log.info(
        "Fleet: mapeadas %d rotas da página atual com vínculo aeronave→rota→botão.",
        len(rows),
    )

    for decision in eligible[:max(0, int(limit))]:
        if bot.dry_run or bot.stopping:
            break
        aircraft_id = str(decision.aircraft_id)
        # The same aircraft appearing in more than one route row is ambiguous.
        candidates = matching_rows.get(aircraft_id, [])
        if len(candidates) != 1:
            result["not_supported"] += 1
            continue
        row = native_route_button(aircraft_id, candidates[0])
        if not row:
            result["not_supported"] += 1
            log.info(
                "Fleet: %s está na página, mas o botão de sua rota não "
                "corresponde ao contrato individual do jogo.",
                decision.registration,
            )
            continue

        # Re-read the game's live landing state and the current duplicate
        # policy before any native click. No stale or blocked route may depart.
        ready = {str(item.get("id")) for item in collect_dispatch_rows(bot)}
        fresh = plan_dispatch(
            [aircraft_id], registry.snapshot(allow_duplicates=False)
        )
        if aircraft_id not in ready or len(fresh) != 1 or not fresh[0].approved:
            log.info(
                "Fleet: %s não está mais pousada ou aprovada; sem despacho.",
                decision.registration,
            )
            continue

        # The live route row could have changed since the first read.
        latest = [
            item for item in collect_route_rows(bot)
            if str(item.get("aircraft_id") or "") == aircraft_id
        ]
        if len(latest) != 1 or not native_route_button(aircraft_id, latest[0]):
            log.warning(
                "Fleet: vínculo aeronave/rota mudou para %s; sem despacho.",
                decision.registration,
            )
            continue
        if (latest[0]["route_id"] != row["route_id"]
                or latest[0]["action"] != row["action"]):
            log.warning(
                "Fleet: rota de %s mudou desde a leitura anterior; sem despacho.",
                decision.registration,
            )
            continue
        if not bot.js(
            _MARK_ROUTE_JS, aircraft_id, row["route_id"], row["action"]
        ):
            log.warning(
                "Fleet: comando nativo da rota %s mudou; sem despacho.",
                decision.registration,
            )
            continue

        # Final authorization. The native game route button carries a ROUTE ID.
        ready = {str(item.get("id")) for item in collect_dispatch_rows(bot)}
        fresh = plan_dispatch(
            [aircraft_id], registry.snapshot(allow_duplicates=False)
        )
        if aircraft_id not in ready or len(fresh) != 1 or not fresh[0].approved:
            continue
        result["native_individual"] += 1
        try:
            control = bot.driver.find_element(
                By.CSS_SELECTOR,
                f'#routeAction #routeMainList{row["route_id"]} '
                f'[data-am4-safe-route-depart="{aircraft_id}"]',
            )
            if bot.dry_run or bot.stopping:
                break
            control.click()
        except WebDriverException as exc:
            result["status"] = "clique_individual_resultado_incerto"
            log.warning(
                "Fleet: clique de %s na rota %s incerto (%s); interrompendo.",
                decision.registration, row["route_id"], type(exc).__name__,
            )
            break
        if not _confirm_inflight(bot, aircraft_id):
            result["status"] = "decolagem_sem_confirmacao"
            log.warning(
                "Fleet: envio individual da rota %s para %s sem confirmação "
                "de voo; interrompendo outras decolagens.",
                row["route_id"], decision.registration,
            )
            break
        result["departed"] += 1
        result["status"] = "decolagens_confirmadas"
        bot.count("departures")
        log.info(
            "Fleet: decolagem individual CONFIRMADA de %s "
            "(aeronave ID %s, rota ID %s).",
            decision.registration, aircraft_id, row["route_id"],
        )
    return result
