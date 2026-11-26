"""Stage a planned passenger cabin in the native AM4 order preview."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from aircraft_order_hub import prepare_order_hub
from engine_detail import MODEL_DETAIL_IDENTITY_JS, parse_displayed_metrics
from engine_selection import prepare_engine
from investment_journal import canonical_configuration_yjf
from seats import SLOTS


@dataclass(frozen=True)
class AircraftPreviewRequest:
    model_id: str
    delivery_hub_id: str
    engine_id: str
    seats: tuple[int, int, int]
    expected_checkout_cost: int

    @classmethod
    def from_payload(cls, payload: dict) -> AircraftPreviewRequest:
        if set(payload) != {"model_id", "delivery_hub_id", "engine_id", "configuration_yjf",
                            "expected_checkout_cost"}:
            raise ValueError("Informe modelo, hub nativo de entrega, motor, cabine Y/J/F e preço esperado.")
        model_id, hub_id, engine_id = (payload[key] for key in ("model_id", "delivery_hub_id", "engine_id"))
        configuration = canonical_configuration_yjf(payload["configuration_yjf"])
        cost = payload["expected_checkout_cost"]
        if (type(model_id) is not str or not re.fullmatch(r"[1-9][0-9]{0,11}", model_id)
                or type(hub_id) is not str or not re.fullmatch(r"[1-9][0-9]{0,13}", hub_id)
                or type(engine_id) is not str or not re.fullmatch(r"[0-9]{1,14}", engine_id)
                or configuration is None or sum(configuration.values()) > 10000
                or type(cost) is not int or not 0 < cost <= 2**53 - 1):
            raise ValueError("Use IDs nativos numéricos, uma cabine válida e o preço inteiro esperado.")
        return cls(model_id, hub_id, engine_id, tuple(configuration[key] for key in "yjf"), cost)


class AircraftPreviewMismatch(ValueError):
    """A controlled mismatch with a message safe to return to the operator."""

    def __init__(self, message: str, *, displayed_cost_usd: int | None = None):
        super().__init__(message)
        self.displayed_cost_usd = displayed_cost_usd


_FORM_STATE_JS = r"""
const panel = arguments[0];
const unique = (root, selector) => {
  const nodes = root.querySelectorAll(selector);
  return nodes.length === 1 ? nodes[0] : null;
};
const visible = el => !!el && el.getClientRects().length > 0 &&
  !['hidden', 'collapse'].includes(window.getComputedStyle(el).visibility);
if (unique(document, '#acModel') !== panel || !visible(panel) ||
    typeof window.jQuery !== 'function' || window.jQuery.active !== 0 ||
    panel.getAttribute('aria-busy') === 'true' ||
    Array.from(panel.querySelectorAll('img[src*="loader"], [aria-busy="true"]')).some(visible)) return null;
const identity = """ + MODEL_DETAIL_IDENTITY_JS + r"""(panel);
const step = unique(panel, '#step2');
const cost = unique(panel, '#acCost');
const selected = selector => {
  const control = unique(document, selector);
  if (!control || !panel.contains(control) || control.tagName !== 'SELECT' ||
      control.matches(':disabled') || control.selectedOptions.length !== 1) return null;
  const option = control.selectedOptions[0];
  return !option.matches(':disabled') && control.value === option.value ? option.value : null;
};
if (!identity || !step || !visible(cost)) return null;
const state = {
  model_id: identity.model_id ?? identity.script_model_id,
  hub_id: selected('#hubSelection'),
  engine_id: selected('#engSelection'),
  price: cost.textContent.trim(),
  low_balance: Array.from(panel.querySelectorAll('#accountLow')).some(visible),
};
if (!visible(step)) return state;

// The observed passenger preview has two handles and a fixed quantity of one.
const slider = unique(step, '#seatSlider');
if (!visible(slider) || Array.from(step.querySelectorAll('input, select')).some(visible)) return null;
const widget = window.jQuery(slider);
if (typeof widget.slider !== 'function' || !widget.slider('instance')) return null;
const {min, max, step: increment, range, disabled} = widget.slider('option');
const handles = Array.from(slider.querySelectorAll('.ui-slider-handle'));
if (min !== 0 || increment !== 1 || range !== true || disabled ||
    !Number.isInteger(max) || max <= 0 || max > 10000 || handles.length !== 2 ||
    !handles.every(el => visible(el) && el.tabIndex === 0)) return null;
const positions = widget.slider('values');
if (!Array.isArray(positions) || positions.length !== 2 ||
    !positions.every(n => Number.isInteger(n) && n >= 0 && n <= max) ||
    positions[0] > positions[1]) return null;
const seats = {};
for (const [key, selector] of [['y', '#eSeats'], ['j', '#bSeats'], ['f', '#fSeats']]) {
  const label = unique(step, selector);
  if (!visible(label) || !/^(0|[1-9][0-9]{0,4})$/.test(label.textContent.trim())) return null;
  seats[key] = Number(label.textContent.trim());
}
const orderControl = unique(panel, '#btnPurchaseIntroA');
const orderAvailable = visible(orderControl) && !orderControl.matches(
  ':disabled, [aria-disabled="true"], .disabled, .not-active');
return {...state, capacity: max, handles, positions, seats, order_available: orderAvailable};
"""


def _slider_positions(seats: dict[str, int], capacity: int) -> tuple[int, int]:
    left = seats["y"]
    # The widget displays whole seats. The two handles can leave unused slots
    # when converting a range of economy slots to a premium class.
    business_start = left + SLOTS[1] * seats["j"]
    first_end = capacity - SLOTS[2] * seats["f"]
    right = min(business_start + SLOTS[1] - 1, first_end)
    if right < max(business_start, first_end - SLOTS[2] + 1):
        raise AircraftPreviewMismatch("A cabine da rota não cabe no seletor nativo desta aeronave.")
    return left, right


def _move_handle(handle, current: int, target: int, capacity: int) -> None:
    delta = target - current
    if not delta:
        return
    arrow, page = (Keys.ARROW_RIGHT, Keys.PAGE_UP) if delta > 0 else (Keys.ARROW_LEFT, Keys.PAGE_DOWN)
    # jQuery UI rounds each move to the step. Page keys are exact when the
    # slider's jump (one fifth of its range) is an integer.
    pages, steps = divmod(abs(delta), capacity // 5) if capacity % 5 == 0 else (0, abs(delta))
    handle.send_keys(page * pages + arrow * steps)


def _configuration_button(panel, selector: str):
    matches = panel.find_elements(By.CSS_SELECTOR, selector)
    if len(matches) != 1 or not matches[0].is_displayed() or not matches[0].is_enabled():
        raise AircraftPreviewMismatch("O formulário de configuração da encomenda mudou.")
    return matches[0]


def preview_aircraft_order(
    bot, *, model_id: str, hub_id: str, engine_id: str,
    configuration_yjf: object, expected_checkout_cost: int,
) -> dict:
    """Return the observed single-unit quote and close the preview via Back."""
    seats = canonical_configuration_yjf(configuration_yjf)
    if (seats is None or not isinstance(model_id, str) or not re.fullmatch(r"[1-9][0-9]{0,11}", model_id)
            or not isinstance(hub_id, str) or not re.fullmatch(r"[1-9][0-9]{0,13}", hub_id)
            or not isinstance(engine_id, str) or not engine_id.strip()
            or type(expected_checkout_cost) is not int or expected_checkout_cost <= 0):
        raise ValueError("Plano sem modelo, hub de entrega, motor, cabine ou preço válido.")

    panel = bot.ajax(f"ac_orders.php?mode=detail&id={model_id}&charter=0", "acModel")
    initial = bot.js(_FORM_STATE_JS, panel)
    if not initial or initial.get("model_id") != model_id or "seats" in initial:
        raise AircraftPreviewMismatch("O detalhe nativo do modelo planejado não foi confirmado.")
    prepare_order_hub(bot, hub_id, configure_preview=True)
    motor = prepare_engine(bot, "default", expected_engine_id=engine_id, configure_preview=True)
    panel = bot.driver.find_element(By.ID, "acModel")

    def read_state(*, opened: bool, wait_for_step: bool = False) -> dict:
        def read(_):
            state = bot.js(_FORM_STATE_JS, panel)
            return state if state and ("seats" in state) == opened else None

        state = WebDriverWait(bot.driver, 5).until(read) if wait_for_step else read(bot.driver)
        if (not state or (state.get("model_id"), state.get("hub_id"), state.get("engine_id"))
                != (model_id, hub_id, engine_id)):
            raise AircraftPreviewMismatch("Modelo, motor, hub ou etapa divergente no formulário da encomenda.")
        if state.get("low_balance") is not False:
            raise AircraftPreviewMismatch("O jogo sinalizou saldo insuficiente na prévia.")
        return state

    read_state(opened=False)
    next_button = _configuration_button(panel, "button#newAcNext")
    try:
        next_button.click()
        state = read_state(opened=True, wait_for_step=True)
        targets = _slider_positions(seats, state["capacity"])
        handles, current = state["handles"], state["positions"]
        # Move the right handle first if it would otherwise cap the left.
        indices = (1, 0) if current[1] < targets[0] else (0, 1)
        for index in indices:
            _move_handle(handles[index], current[index], targets[index], state["capacity"])

        observed = read_state(opened=True)
        if observed["seats"] != seats or tuple(observed["positions"]) != targets:
            raise AircraftPreviewMismatch("O seletor nativo não confirmou a cabine exata da rota.")
        if observed != read_state(opened=True):
            raise AircraftPreviewMismatch("A cabine ou o preço mudou durante a releitura do formulário.")
        metrics = parse_displayed_metrics({"rows": [], "costs": [observed["price"]]}) or {}
        displayed_cost = metrics.get("displayed_cost_usd")
        if displayed_cost != expected_checkout_cost:
            raise AircraftPreviewMismatch(
                "O total exibido pelo jogo com a cabine da rota diverge do plano.",
                displayed_cost_usd=displayed_cost,
            )
        observed_at = time.time()
    finally:
        # Back is inside the same detail panel. If the step vanished, there is
        # no prepared form to close. A detached panel cannot be clicked here.
        try:
            matches = panel.find_elements(By.CSS_SELECTOR, "button#newAcBack")
            if len(matches) == 1 and matches[0].is_displayed():
                matches[0].click()
        except WebDriverException:
            pass

    read_state(opened=False, wait_for_step=True)
    return {
        "model_id": model_id, "engine_id": engine_id, "engine": motor, "delivery_hub_id": hub_id,
        "configuration_yjf": observed["seats"], "displayed_cost_usd": displayed_cost,
        "quantity": 1, "price_verified": False, "observed_at": observed_at,
        "order_control_available": observed.get("order_available") is True,
    }


def probe_aircraft_order(bot, request: AircraftPreviewRequest) -> dict:
    """Open a fresh native order form and return the observed quote for one unit."""
    try:
        bot.close_popup(quiet=True)
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("ac_orders.php?first=true", "routeAction")
        preview = preview_aircraft_order(
            bot, model_id=request.model_id, hub_id=request.delivery_hub_id, engine_id=request.engine_id,
            configuration_yjf=dict(zip("yjf", request.seats)),
            expected_checkout_cost=request.expected_checkout_cost,
        )
    except AircraftPreviewMismatch as exc:
        return {"status": "mismatch", "message": str(exc), "read_only": True, "execution_available": False,
                "expected_checkout_cost": request.expected_checkout_cost, "displayed_cost_usd": exc.displayed_cost_usd}
    finally:
        bot.close_popup(quiet=True)
    preview.pop("engine")  # The observed ID is enough to correlate the quote.
    return {**preview, "status": "matched", "read_only": True, "execution_available": False}
