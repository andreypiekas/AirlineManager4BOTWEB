"""Read and validate the delivery hub selected in the aircraft order form."""
from __future__ import annotations

import re
from collections.abc import Mapping


_HUB_ID = re.compile(r"^[1-9][0-9]{0,13}$")

_ORDER_HUB_STATE_JS = """
const selectors = Array.from(document.querySelectorAll('#hubSelection'));
if (selectors.length !== 1) {
  return {
    selector_count: selectors.length,
    selector_disabled: null,
    value: '',
    selected_values: [],
    options: []
  };
}
const select = selectors[0];
const options = Array.from(select.options || []);
return {
  selector_count: selectors.length,
  selector_disabled: select.disabled === true,
  value: String(select.value ?? '').trim(),
  selected_values: options
    .filter(option => option.selected === true)
    .map(option => String(option.value ?? '').trim()),
  options: options.map(option => ({
    id: String(option.value ?? '').trim(),
    disabled: option.matches(':disabled')
  }))
};
"""

_SELECT_ORDER_HUB_JS = """
const target = String(arguments[0] ?? '').trim();
const selectors = Array.from(document.querySelectorAll('#hubSelection'));
if (selectors.length !== 1 || selectors[0].disabled === true) return false;
const select = selectors[0];
const matches = Array.from(select.options || []).filter(option =>
  String(option.value ?? '').trim() === target
);
if (matches.length !== 1 || matches[0].matches(':disabled')) return false;
select.value = target;
select.dispatchEvent(new Event('input', { bubbles: true }));
select.dispatchEvent(new Event('change', { bubbles: true }));
const selected = Array.from(select.options || []).filter(option => option.selected === true);
return String(select.value ?? '').trim() === target && selected.length === 1 &&
  selected[0] === matches[0] && !matches[0].matches(':disabled');
"""


class AircraftOrderHubError(RuntimeError):
    """Raised when the aircraft order form cannot prove its delivery hub."""


def _normalize_hub_id(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    hub_id = value.strip()
    return hub_id if _HUB_ID.fullmatch(hub_id) else None


def _read_order_hub_state(bot) -> tuple[str, dict[str, bool]]:
    try:
        state = bot.js(_ORDER_HUB_STATE_JS)
    except Exception as exc:
        raise AircraftOrderHubError("Não consegui ler a base selecionada no formulário.") from exc

    if not isinstance(state, Mapping) or type(state.get("selector_count")) is not int:
        raise AircraftOrderHubError("O formulário não retornou um estado válido da base.")
    if state["selector_count"] != 1:
        raise AircraftOrderHubError("O seletor de base está ausente ou ambíguo no formulário.")
    if state.get("selector_disabled") is not False:
        raise AircraftOrderHubError("O seletor de base está desabilitado ou sem confirmação.")

    raw_options = state.get("options")
    selected_values = state.get("selected_values")
    if not isinstance(raw_options, list) or not isinstance(selected_values, list):
        raise AircraftOrderHubError("As opções de base não puderam ser verificadas.")

    options: dict[str, bool] = {}
    for option in raw_options:
        if not isinstance(option, Mapping):
            raise AircraftOrderHubError("O catálogo de bases contém uma opção inválida.")
        hub_id = _normalize_hub_id(option.get("id"))
        if hub_id is None:
            continue
        if hub_id in options:
            raise AircraftOrderHubError("O catálogo contém IDs de base duplicados.")
        if type(option.get("disabled")) is not bool:
            raise AircraftOrderHubError("A disponibilidade de uma base não foi confirmada.")
        options[hub_id] = option["disabled"]

    if len(selected_values) != 1:
        raise AircraftOrderHubError("O formulário não possui uma única base selecionada.")
    selected_id = _normalize_hub_id(selected_values[0])
    current_id = _normalize_hub_id(state.get("value"))
    if selected_id is None or current_id != selected_id or selected_id not in options:
        raise AircraftOrderHubError("A base selecionada não corresponde a uma opção válida.")
    if options[selected_id]:
        raise AircraftOrderHubError("A base selecionada está indisponível.")
    return selected_id, options


def prepare_order_hub(bot, requested_hub_id: str | int | None = None) -> tuple[str, bool]:
    """Verify the current hub or select the requested hub and confirm the DOM.

    Returns the verified/planned hub ID and whether the live form changed.
    Dry-run validates availability but never changes the form.
    """
    requested_id = None
    if requested_hub_id is not None:
        requested_id = _normalize_hub_id(requested_hub_id)
        if requested_id is None:
            raise AircraftOrderHubError("O plano contém um ID de base inválido.")

    selected_id, options = _read_order_hub_state(bot)
    target_id = requested_id or selected_id
    if target_id not in options:
        raise AircraftOrderHubError("A base definida no plano não aparece no formulário de encomenda.")
    if options[target_id]:
        raise AircraftOrderHubError("A base definida no plano está indisponível para encomenda.")
    if target_id == selected_id or getattr(bot, "dry_run", False):
        return target_id, False

    try:
        changed = bot.js(_SELECT_ORDER_HUB_JS, target_id)
        if changed is not True:
            raise AircraftOrderHubError("O jogo não aceitou a seleção da base solicitada.")
        bot.pause(0.4, 0.8)
    except AircraftOrderHubError:
        raise
    except Exception as exc:
        raise AircraftOrderHubError("Falha ao selecionar a base de entrega.") from exc

    confirmed_id, _ = _read_order_hub_state(bot)
    if confirmed_id != target_id:
        raise AircraftOrderHubError("A base de entrega mudou ou não foi confirmada após a seleção.")
    return target_id, True
