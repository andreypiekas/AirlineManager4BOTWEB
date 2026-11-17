"""Disparo individual pelo controle nativo do detalhe da aeronave (Fleet).

Nenhuma URL de voo é inventada. Uma aeronave pronta e aprovada pela política
pode decolar SOMENTE se seu próprio painel expuser um botão único de despacho.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

log = logging.getLogger("am4bot.vuelos")
_ID = re.compile(r"^\d{1,14}$")
_DEPART = re.compile(r"\b(?:depart|dispatch|decolar|despegar|take[\s-]*off)\b", re.I)
_BULK = re.compile(r"\b(?:all|todos?|todas?|every)\b", re.I)
_ENDPOINT = re.compile(r"route_depart\.php\?([^'\"<>\s();]{1,220})", re.I)
_SELECTOR = 'button,a,[role="button"],input[type="button"],input[type="submit"]'

_FLEET_CONTROLS_JS = """
const root = document.getElementById("detailsAction");
if (!root) return [];
return Array.from(root.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'))
.map((e, index) => ({
  index, label: (e.textContent || e.value || e.getAttribute("aria-label") ||
    e.getAttribute("title") || "").trim().slice(0,120),
  action: (e.getAttribute("onclick") || e.getAttribute("href") || "").trim().slice(0,360),
  visible: !!e.getClientRects().length,
  disabled: !!e.disabled || e.classList.contains("not-active") ||
    e.getAttribute("aria-disabled") === "true"
}));
"""

_MARK_FLEET_JS = """
const [id, index, label, action] = arguments;
if (!/^\\d{1,14}$/.test(String(id))) return false;
const root = document.getElementById("detailsAction");
if (!root) return false;
const elements = Array.from(root.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'));
const e = elements[index];
if (!e || !e.getClientRects().length || e.disabled ||
    e.classList.contains("not-active") || e.getAttribute("aria-disabled") === "true") return false;
const nowLabel = (e.textContent || e.value || e.getAttribute("aria-label") ||
    e.getAttribute("title") || "").trim().slice(0,120);
const nowAction = (e.getAttribute("onclick") || e.getAttribute("href") || "").trim().slice(0,360);
if (nowLabel !== label || nowAction !== action) return false;
root.querySelectorAll("[data-am4-fleet-depart]").forEach(n => n.removeAttribute("data-am4-fleet-depart"));
e.setAttribute("data-am4-fleet-depart", String(id));
return true;
"""

_INFLIGHT_JS = """
const id = String(arguments[0]), list = document.getElementById("inflightList");
const row = document.getElementById("flightStatus" + id);
return !!list && !!row && list.contains(row);
"""


def choose_depart_control(aircraft_id: str, controls: list[dict]) -> dict | None:
    """Aceita só um controle de decolagem não global na janela individual."""
    if not _ID.fullmatch(str(aircraft_id)):
        return None
    matches = []
    for item in controls or []:
        if not isinstance(item, dict) or item.get("disabled") or not item.get("visible"):
            continue
        label, action = str(item.get("label") or ""), str(item.get("action") or "")
        if _BULK.search(label) or "fleet_ground.php" in action.lower():
            continue
        req = _ENDPOINT.search(action)
        if req:
            params = parse_qs(req.group(1), keep_blank_values=True)
            ids = params.get("id", []) + params.get("ids", [])
            if (len(ids) != 1 or ids[0] != str(aircraft_id)
                    or params.get("mode", [""])[0].lower() in ("", "all")):
                continue
        elif "route_depart.php" in action.lower() or "fleet_details.php" in action.lower():
            continue
        elif not _DEPART.search(label):
            continue
        if not isinstance(item.get("index"), int) or item["index"] < 0:
            continue
        matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _confirm_inflight(bot, aircraft_id: str) -> bool:
    try:
        WebDriverWait(bot.driver, 6).until(
            lambda driver: bool(driver.execute_script(_INFLIGHT_JS, aircraft_id))
        )
        return True
    except TimeoutException:
        try:
            bot.open_popup("routes_main.php", "Routes", "nav_routes")
            return bool(bot.js(_INFLIGHT_JS, aircraft_id))
        except (TimeoutException, WebDriverException):
            return False


def fleet_dispatch(bot, registry, eligible: list, *, limit: int = 20) -> dict:
    """Executa uma tentativa por aeronave, confirma antes de ir para a próxima."""
    from selective_depart import collect_dispatch_rows, plan_dispatch

    result = {"status": "controle_individual_nao_disponivel", "departed": 0,
              "native_individual": 0, "not_supported": 0}
    if not callable(getattr(bot, "ajax", None)):
        result["not_supported"] = len(eligible)
        return result

    for decision in eligible[:max(0, int(limit))]:
        if bot.stopping or bot.dry_run:
            break
        aircraft_id = str(decision.aircraft_id)
        if not _ID.fullmatch(aircraft_id):
            result["not_supported"] += 1
            continue
        ready = {str(row.get("id")) for row in collect_dispatch_rows(bot)}
        fresh = plan_dispatch([aircraft_id], registry.snapshot(allow_duplicates=False))
        if aircraft_id not in ready or len(fresh) != 1 or not fresh[0].approved:
            continue
        try:
            bot.ajax(f"fleet_details.php?id={aircraft_id}", "detailsAction", timeout=12)
            controls = bot.js(_FLEET_CONTROLS_JS) or []
        except (WebDriverException, TimeoutException) as exc:
            log.warning("Fleet: detalhes de %s indisponíveis (%s).",
                        decision.registration, type(exc).__name__)
            result["not_supported"] += 1
            continue
        action = choose_depart_control(aircraft_id, controls)
        if not action:
            result["not_supported"] += 1
            labels = [str(c.get("label", ""))[:40] for c in controls[:8] if c.get("visible")]
            log.info("Fleet: %s sem botão individual verificável (%d controles; visíveis: %s).",
                     decision.registration, len(controls), labels)
            continue
        result["native_individual"] += 1
        if not bot.js(_MARK_FLEET_JS, aircraft_id, action["index"],
                      action.get("label", ""), action.get("action", "")):
            log.warning("Fleet: botão de %s mudou antes do despacho.", decision.registration)
            continue
        ready = {str(row.get("id")) for row in collect_dispatch_rows(bot)}
        fresh = plan_dispatch([aircraft_id], registry.snapshot(allow_duplicates=False))
        if aircraft_id not in ready or len(fresh) != 1 or not fresh[0].approved:
            continue
        try:
            control = bot.driver.find_element(
                By.CSS_SELECTOR, f'#detailsAction [data-am4-fleet-depart="{aircraft_id}"]'
            )
            if bot.stopping or bot.dry_run:
                break
            control.click()  # Clique nativo, nunca executa URL construída.
        except WebDriverException as exc:
            result["status"] = "clique_individual_resultado_incerto"
            log.warning("Fleet: clique de %s incerto (%s); parando.",
                        decision.registration, type(exc).__name__)
            break
        if not _confirm_inflight(bot, aircraft_id):
            result["status"] = "decolagem_sem_confirmacao"
            log.warning("Fleet: %s não apareceu em voo; interrompendo despachos.",
                        decision.registration)
            break
        bot.count("departures")
        result["departed"] += 1
        result["status"] = "decolagens_confirmadas"
        log.info("Fleet: decolagem individual CONFIRMADA de %s (ID %s).",
                 decision.registration, aircraft_id)
    return result
