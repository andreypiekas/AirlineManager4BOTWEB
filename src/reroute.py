"""Replace an existing route through the game's Ground toggle and native route form."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import paths
from helpers import fmt, game_whole_number
from native_route_quotes import record_native_route_quote
from notify import esc
from route_registry import endpoint, endpoint_matches, same_route
from route_stopover import read_route_fares

log = logging.getLogger("am4bot.rutas")
_ID = re.compile(r"[0-9]{1,14}")

# Detached HTML keeps game scripts from running during reads. Only the explicit
# Ground request can mutate game state. Use the same signature as the game's Ajax().
_GET = r"""
const [path, read, done] = arguments;
const url = new URL(path, window.location.href);
if (typeof fbSig !== 'undefined') url.searchParams.set('fbSig', fbSig);
const controller = new AbortController();
const timer = setTimeout(() => controller.abort(), 5000);
fetch(url, {cache:'no-store', signal:controller.signal, redirect:'error'})
  .then(async response => {
    if (!response.ok) return null;
    const html = await response.text();
    if (read === 'toggle') return true;
    if (read === 'missing') return response.status === 200 && !html.trim();
    const page = new DOMParser().parseFromString(html, 'text/html');
    if (read === 'hubs') {
      const options = page.querySelectorAll('#hubSelect option');
      return Array.from(options, option => option.value).filter(id => /^[0-9]{1,12}$/.test(id));
    }
    if (read === 'base') {
      const row = page.getElementById('controls' + url.searchParams.get('aircraft'));
      return row?.closest('.maint-list-sort')?.dataset.base === '1';
    }
    const ground = page.getElementById('routeViewGround_unground');
    const restore = page.getElementById('routeViewGround_ground');
    const routeId = button => (button?.getAttribute('onclick') || '')
      .match(/fleet_ground\.php\?id=([0-9]{1,14})['"]/i)?.[1];
    const id = routeId(ground);
    if (!id || id !== routeId(restore)) return null;
    const paused = ground.classList.contains('hidden');
    if (paused === restore.classList.contains('hidden')) return null;
    const codes = Array.from(page.querySelectorAll('.col-5.bg-light span.l-text.exo'),
      e => e.textContent.trim().toUpperCase());
    const via = page.querySelector('.col-2.bg-light .glyphicons-plane + .xs-text')?.lastChild?.textContent.trim().toUpperCase();
    const timer = page.getElementById('timer');
    const label = timer?.parentElement.textContent.trim() || '';
    return {id, paused, codes, via, landed: !timer || /^(Departs in|Sale en|Parte em)\b/i.test(label)};
  }).then(done, () => done(null)).finally(() => clearTimeout(timer));
"""

_FORM = r"""
const panel = document.querySelector('#newRouteInfo #newRouteContainer');
if (!panel) return null;
const root = panel.parentElement;
const codes = Array.from(panel.querySelectorAll('.row.p-0 > .col-3.m-text > b'),
  e => e.textContent.trim().toUpperCase());
const counts = panel.querySelectorAll('.row.p-1 > .col-4.text-right.s-text');
const fees = panel.querySelectorAll('.text-danger.font-weight-bold');
const specs = panel.querySelector('.row.py-2 .xs-text')?.textContent || '';
const range = (specs.match(/([\d,]+)\s*km\//i) || [])[1];
const distance = panel.querySelector('.row.p-0 > .col-2 > span')?.textContent.trim();
const submissions = Array.from(root.querySelectorAll('script')).flatMap(s =>
  Array.from(s.textContent.matchAll(/new_route_info\.php\?mode=do&id=([0-9]+)&airportId=([0-9]+)&/g)));
return {codes, existing: counts.length === 1 ? counts[0].textContent.trim() : null,
  fee: fees.length === 1 ? fees[0].textContent.trim() : null,
  range, distance,
  bound: submissions.length > 0 && submissions.every(m => m[1] === arguments[0] && m[2] === arguments[1])};
"""

# Observe the game's own request and wait for its response. A lost response
# cannot be treated as permission to toggle the old route back on.
_SUBMIT = """
const [button, aircraft, destination, done] = arguments;
const $ = window.jQuery;
if (!$ || button.disabled || button.classList.contains('not-active')) {
    done(false);
    return;
}
const events = $(document);
const event = 'ajaxComplete.am4Reroute';
const finish = result => {
    clearTimeout(timeout);
    events.off(event, onComplete);
    done(result);
};
const onComplete = (_, response, settings) => {
    const url = new URL(settings.url, location.href);
    if (url.origin === location.origin && url.pathname.endsWith('/new_route_info.php') &&
        url.searchParams.get('mode') === 'do' && url.searchParams.get('id') === aircraft &&
        url.searchParams.get('airportId') === destination) {
        finish(response.status === 200);
    }
};
const timeout = setTimeout(() => finish(false), 18000);
events.on(event, onComplete);
button.click();
"""


@dataclass(frozen=True)
class LiveRoute:
    id: str
    paused: bool
    codes: tuple[str, str]
    landed: bool
    stopover: str = ""

    def matches(self, relation: dict) -> bool:
        return same_route(relation, {
            "origin": endpoint(code=self.codes[0]),
            "destination": endpoint(code=self.codes[1]),
        })


def _live_route(bot, aircraft_id: str) -> LiveRoute | None:
    data = bot.driver.execute_async_script(_GET, f"fleet_details.php?id={aircraft_id}", "details")
    if not data or len(data["codes"]) != 2 or not all(endpoint(code=c)["code"] for c in data["codes"]):
        return None
    return LiveRoute(data["id"], data["paused"], tuple(data["codes"]), data["landed"],
                     data.get("via") or "")


def confirm_stopover(bot, aircraft_id, origin, destination, stopover) -> bool:
    relation = {"origin": origin, "destination": destination}

    def matches(route):
        return (not route.paused and route.matches(relation)
                and endpoint_matches(stopover, endpoint(code=route.stopover)))

    live = _check_route(bot, aircraft_id, matches)
    return bool(live and matches(live))


def confirm_direct_route(bot, aircraft_id, origin, destination) -> bool:
    """Confirm the route through the aircraft's independent detail view."""
    relation = {"origin": origin, "destination": destination}

    def matches(route):
        return not route.paused and not route.stopover and route.matches(relation)

    live = _check_route(bot, aircraft_id, matches)
    return bool(live and matches(live))


def landed_departure(bot, row) -> str:
    aircraft_id = row["aircraft_id"]
    if not _ID.fullmatch(aircraft_id):
        return ""
    live = _live_route(bot, aircraft_id)
    return live.codes[0] if live and live.landed and not live.paused and live.matches(row) else ""


def aircraft_details_missing(bot, aircraft_id: str) -> bool:
    if not _ID.fullmatch(aircraft_id):
        return False
    return bot.driver.execute_async_script(_GET, f"fleet_details.php?id={aircraft_id}", "missing") is True


def _toggle(bot, route_id: str) -> bool:
    return bot.driver.execute_async_script(_GET, f"fleet_ground.php?id={route_id}", "toggle") is True


def _check_route(bot, aircraft_id, condition):
    last = None
    for delay in (0, 1, 2, 3, 4):
        time.sleep(delay)  # recovery still needs to finish if the bot is stopping
        try:
            last = _live_route(bot, aircraft_id)
        except WebDriverException:
            last = None
        if last and condition(last):
            break
    return last


def read_direct_form(bot, aircraft_id, origin, destination, *, allow_duplicates=False):
    """Validate the direct route form against the intended endpoints and aircraft."""
    form = bot.js(_FORM, aircraft_id, destination["id"])
    if not form or form.get("bound") is not True or len(form.get("codes", [])) != 2:
        return None
    if (not endpoint_matches(origin, endpoint(code=form["codes"][0]))
            or not endpoint_matches(destination, endpoint(code=form["codes"][1]))):
        return None
    occupied = game_whole_number(form.get("existing"))
    if occupied is None or (occupied and not allow_duplicates):
        return None
    distance, max_range = (game_whole_number(form.get(key)) for key in ("distance", "range"))
    if distance is None or max_range is None or distance <= 0 or distance > max_range:
        return None
    fee = game_whole_number(form.get("fee"), currency=True)
    if fee is None or fee <= 0:
        return None
    return distance, fee, occupied


def _prepare_form(bot, aircraft_id, origin, destination):
    dest_id = destination["id"]
    panel = bot.ajax(f"new_route_info.php?id={aircraft_id}&airportId={dest_id}&mode=res", "newRouteInfo")
    verified = read_direct_form(bot, aircraft_id, origin, destination)
    if verified is None:
        return None
    _, fee, _ = verified
    balance = bot.read_money()
    reserve = bot.config.get_int("settings", "cash_reserve", 0)
    if balance is None or balance - fee < reserve:
        return None
    auto = panel.find_elements(By.ID, "introAuto")
    if len(auto) != 1:
        return None
    bot.click_element(auto[0])
    # Native autoprice fills business/first prices on 200/400 ms timers.
    # Wait for the game's own validation to activate Create route.
    def ready(_driver):
        fares = read_route_fares(bot)
        buttons = panel.find_elements(By.CSS_SELECTOR, "#btnCreateNewRoute:not(.not-active):not([disabled])")
        return (buttons[0], fares) if fares is not None and len(buttons) == 1 else False

    try:
        button, fares = WebDriverWait(bot.driver, 5).until(ready)
    except TimeoutException:
        return None
    balance = bot.read_money()
    if (read_direct_form(bot, aircraft_id, origin, destination) != verified
            or read_route_fares(bot) != fares or balance is None or balance - fee < reserve):
        return None
    record_native_route_quote(bot, aircraft_id=aircraft_id, origin_id=origin.get("id"),
                              destination_id=dest_id, distance=verified[0], fee=fee,
                              occupied=verified[2], fares=fares)
    return button, fee


def _transaction_path():
    return paths.current().data / "reroute_pending.json"


def has_pending_reroute() -> bool:
    return _transaction_path().exists()


_UNCONFIRMED_REQUEST_GRACE = 120  # seconds to let a delayed game response settle


def _save_job(job, phase: str) -> None:
    job["phase"] = phase
    job["phase_at"] = time.time()
    paths.write_atomic(_transaction_path(), json.dumps(job), private=True)


def _phase_age(job: dict) -> float:
    """Older journals predate phase_at; retain them and use file mtime."""
    timestamp = job.get("phase_at")
    if not isinstance(timestamp, (int, float)):
        try:
            timestamp = _transaction_path().stat().st_mtime
        except OSError:
            timestamp = time.time()
    return max(0.0, time.time() - timestamp)


def _stable_live_route(bot, aircraft_id: str, condition) -> LiveRoute | None:
    """Require two matching game reads before clearing or compensating a journal."""
    first = _live_route(bot, aircraft_id)
    if not first or not condition(first):
        return None
    time.sleep(1)
    second = _live_route(bot, aircraft_id)
    return second if second == first and condition(second) else None


def _resolve(bot, registry, job, *, poll=False) -> str:
    """Reconcile a route transaction safely without repeating a route purchase.

    An uncertain create request may have succeeded despite a lost AJAX reply.
    Give it a grace period, then prove a stable original route before attempting
    one recovery Ground toggle. The journal survives every inconclusive read.
    """
    aircraft_id = job["aircraft_id"]
    if not _ID.fullmatch(aircraft_id) or not _ID.fullmatch(job["old_id"]):
        return "troca_requer_verificacao"
    target = {"origin": job["origin"], "destination": job["destination"]}
    phase = job["phase"]

    def confirmed_new(route):
        # Some game versions may reuse an existing route ID. The independently
        # verified, changed pair of endpoints is the authoritative evidence.
        return (phase in ("creating", "create_answered", "restoring")
                and not route.paused and route.matches(target)
                and not route.matches(job["old_route"]))

    def old_route(route):
        return route.id == job["old_id"] and route.matches(job["old_route"])

    if poll:
        live = _check_route(bot, aircraft_id, confirmed_new)
    else:
        live = _live_route(bot, aircraft_id)
    if live and confirmed_new(live):
        registry.record(aircraft_id, job["registration"], job["model"], **target,
                        source="redirecionamento", profit_per_day=job["profit"])
        _transaction_path().unlink(missing_ok=True)
        bot.spent(job["fee"], invest=True)
        bot.count("routes")
        summary = f"{job['registration']} mudou para {job['origin']['code']}–{job['destination']['code']} (taxa ${fmt(job['fee'])})."
        log.info("Duplicidade resolvida: %s", summary)
        bot.notify(f"🛫 <b>Rota alterada</b>: {esc(summary)}", category="routes")
        return "trocada"

    if live and old_route(live):
        age = _phase_age(job)
        request_uncertain = phase in ("creating", "create_answered")
        # A grounding command may have been sent but not yet applied. Never
        # release its journal immediately just because the old route is visible.
        ground_uncertain = phase == "grounding" and not live.paused
        restore_uncertain = phase == "restoring" and live.paused
        waiting = (request_uncertain or ground_uncertain or restore_uncertain) and (
            age < _UNCONFIRMED_REQUEST_GRACE
        )
        if waiting:
            log.info(
                "%s: aguardando estabilização da troca (%s, %.0fs/%ds).",
                job["registration"], phase, age, _UNCONFIRMED_REQUEST_GRACE,
            )
            return "troca_requer_verificacao"
        else:
            if (live.paused and not bot.dry_run
                    and phase in ("grounding", "ground_answered", "grounded",
                                  "creating", "create_answered", "restoring")):
                # Never toggle a route that has changed in the game. A lost
                # restoration reply gets a fresh, time-delayed retry only
                # while the SAME old route remains paused and landed.
                stable = _stable_live_route(
                    bot, aircraft_id,
                    lambda route: old_route(route) and route.paused and route.landed,
                )
                if stable:
                    _save_job(job, "restoring")
                    registry.invalidate_fleet_coverage()
                    _toggle(bot, stable.id)
                    live = _check_route(
                        bot, aircraft_id, lambda route: old_route(route) and not route.paused
                    )
            if live and old_route(live) and not live.paused:
                stable = _stable_live_route(
                    bot, aircraft_id,
                    lambda route: old_route(route) and not route.paused,
                )
                if stable:
                    _transaction_path().unlink(missing_ok=True)
                    log.info(
                        "%s: rota original confirmada e transação pendente encerrada.",
                        job["registration"],
                    )
                    return "rota_original_preservada"

    log.error("%s: troca pendente de verificação. Novas trocas aguardam a confirmação do jogo.",
              job["registration"])
    return "troca_requer_verificacao"


def recover_pending(bot, registry) -> bool:
    path = _transaction_path()
    if not path.exists():
        return True
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        return _resolve(bot, registry, job) != "troca_requer_verificacao"
    except (OSError, ValueError, KeyError, TypeError, WebDriverException):
        log.exception("Não foi possível verificar a troca de rota pendente.")
        return False


def replace_route(bot, registry, row, origin, destination, *, keeper_id, expected_id, profit) -> str:
    """Verify the landed aircraft, stage and submit one real replacement."""
    if bot.dry_run or bot.stopping or has_pending_reroute():
        return "troca_adiada"
    aircraft_id = row["aircraft_id"]
    if aircraft_id == keeper_id or not all(_ID.fullmatch(value) for value in
                                           (aircraft_id, keeper_id, expected_id, destination["id"])):
        return "troca_dados_invalidos"
    if registry.is_occupied(origin, destination, aircraft_id):
        return "destino_ocupado_no_jogo"
    first = _live_route(bot, aircraft_id)
    if not first or first.id != expected_id or not first.matches(row) or not first.landed or first.paused:
        return "troca_rota_ou_pouso_nao_confirmado"
    if first.stopover:
        return "troca_rota_com_escala"
    keeper = _live_route(bot, keeper_id)
    if not keeper or keeper.id == first.id or not keeper.matches(row):
        return "troca_duplicidade_nao_confirmada"
    if not endpoint_matches(origin, endpoint(code=first.codes[0])):
        return "troca_aeronave_fora_da_base_de_origem"
    owned_hubs = bot.driver.execute_async_script(_GET, "research_main.php", "hubs") or []
    if origin.get("id") not in owned_hubs and destination.get("id") not in owned_hubs:
        return "troca_sem_base_propria_para_manutencao"
    # The native reroute form independently verifies this physical origin.
    # Owned-hub membership does not restrict a landed aircraft's rerouting.
    form = _prepare_form(bot, aircraft_id, origin, destination)
    if not form:
        return "troca_formulario_ou_reserva_indisponivel"
    current = _live_route(bot, aircraft_id)
    if current != first or bot.stopping or bot.dry_run:
        return "troca_rota_ou_pouso_nao_confirmado"
    job = dict(aircraft_id=aircraft_id, old_id=first.id,
               old_route={"origin": row["origin"], "destination": row["destination"]},
               registration=row["registration"], model=row["model"], origin=origin, destination=destination,
               profit=profit, fee=form[1])
    _save_job(job, "grounding")
    registry.invalidate_fleet_coverage()
    try:
        if _toggle(bot, first.id):
            _save_job(job, "ground_answered")
        paused = _check_route(bot, aircraft_id, lambda route: route.id == first.id and route.paused)
        if paused and paused.id == first.id and paused.paused and paused.landed and paused.matches(row):
            _save_job(job, "grounded")
            form = _prepare_form(bot, aircraft_id, origin, destination)
            if form and not bot.stopping and not bot.dry_run:
                button, job["fee"] = form
                _save_job(job, "creating")
                answered = bot.driver.execute_async_script(_SUBMIT, button, aircraft_id, destination["id"])
                if answered:
                    _save_job(job, "create_answered")
    except WebDriverException:
        log.warning("%s: o jogo interrompeu a troca. Verificando a rota atual.", row["registration"])
    return _resolve(bot, registry, job, poll=job["phase"] in ("creating", "create_answered"))
