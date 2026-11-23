from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

import aircraft_order_hub
import engine_selection
import fleet
import game_source_probe


def hub_state(selected="101", options=None, *, selector_count=1, disabled=False):
    options = options or [
        {"id": "101", "disabled": False},
        {"id": "202", "disabled": False},
    ]
    return {
        "selector_count": selector_count,
        "selector_disabled": disabled if selector_count == 1 else None,
        "value": selected if selector_count == 1 else "",
        "selected_values": [selected] if selector_count == 1 else [],
        "options": deepcopy(options),
    }


class FakeBot:
    def __init__(self, state=None, *, dry_run=False, confirm_selection=True):
        self.state = deepcopy(state or hub_state())
        self.dry_run = dry_run
        self.confirm_selection = confirm_selection
        self.selection_calls = []
        self.pauses = []

    def js(self, script, *args):
        if script == aircraft_order_hub._ORDER_HUB_STATE_JS:
            return deepcopy(self.state)
        if script == aircraft_order_hub._SELECT_ORDER_HUB_JS:
            target = args[0]
            self.selection_calls.append(target)
            if self.confirm_selection:
                self.state["value"] = target
                self.state["selected_values"] = [target]
            return True
        raise AssertionError("Script JavaScript inesperado")

    def pause(self, minimum, maximum):
        self.pauses.append((minimum, maximum))


def test_base_atual_e_confirmada_sem_alterar_o_formulario():
    bot = FakeBot()

    hub_id, changed = aircraft_order_hub.prepare_order_hub(bot)

    assert hub_id == "101"
    assert changed is False
    assert bot.selection_calls == []


def test_seleciona_base_do_plano_e_confirma_estado_apos_evento_dom():
    bot = FakeBot()

    hub_id, changed = aircraft_order_hub.prepare_order_hub(bot, "202")

    assert hub_id == "202"
    assert changed is True
    assert bot.selection_calls == ["202"]
    assert bot.pauses == [(0.4, 0.8)]
    assert bot.state["value"] == "202"


def test_simulacao_valida_base_sem_modificar_o_formulario():
    bot = FakeBot(dry_run=True)

    hub_id, changed = aircraft_order_hub.prepare_order_hub(bot, "202")

    assert hub_id == "202"
    assert changed is False
    assert bot.selection_calls == []
    assert bot.state["value"] == "101"


@pytest.mark.parametrize("state", [
    hub_state(selector_count=0),
    hub_state(selector_count=2),
    hub_state(disabled=True),
    hub_state(selected=""),
    hub_state(options=[{"id": "101", "disabled": False}, {"id": "101", "disabled": False}]),
])
def test_bloqueia_seletor_ausente_ambiguo_ou_inconsistente(state):
    with pytest.raises(aircraft_order_hub.AircraftOrderHubError):
        aircraft_order_hub.prepare_order_hub(FakeBot(state))


def test_bloqueia_base_inexistente_ou_indisponivel():
    bot = FakeBot(hub_state(options=[{"id": "101", "disabled": False},
                                    {"id": "202", "disabled": True}]))

    with pytest.raises(aircraft_order_hub.AircraftOrderHubError, match="indisponível"):
        aircraft_order_hub.prepare_order_hub(bot, "202")
    with pytest.raises(aircraft_order_hub.AircraftOrderHubError, match="não aparece"):
        aircraft_order_hub.prepare_order_hub(bot, "303")


def test_bloqueia_selecao_que_nao_pode_ser_confirmada():
    bot = FakeBot(confirm_selection=False)

    with pytest.raises(aircraft_order_hub.AircraftOrderHubError, match="não foi confirmada"):
        aircraft_order_hub.prepare_order_hub(bot, "202")


def test_bloqueia_encomenda_quando_base_nao_pode_ser_comprovada(monkeypatch):
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args: "Trent 970")
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    bot = SimpleNamespace(
        config=SimpleNamespace(get=lambda *_args: "default"),
        dry_run=False,
        ajax=lambda *_args: Detail(),
        js=lambda *_args: hub_state(selector_count=0),
        click_element=lambda *_args: calls.append("click"),
        read_money=lambda: calls.append("read_money"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(bot, choice, hub_id="202") is False
    assert calls == []


def test_encomenda_seleciona_base_do_plano_antes_de_reler_o_formulario(monkeypatch):
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args: "Trent 970")
    state = hub_state()
    events = []

    class Detail:
        def find_elements(self, *_args):
            return []

    class Driver:
        def find_element(self, by, selector):
            events.append(("refresh_detail", by, selector))
            return Detail()

    def execute_js(script, *args):
        if script == aircraft_order_hub._ORDER_HUB_STATE_JS:
            return deepcopy(state)
        if script == aircraft_order_hub._SELECT_ORDER_HUB_JS:
            state["value"] = args[0]
            state["selected_values"] = [args[0]]
            events.append(("select_hub", args[0]))
            return True
        if script == "return $('#acReg').val();":
            return "PP-123"
        raise AssertionError("Script JavaScript inesperado")

    bot = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda *_args: "default",
            get_bool=lambda *_args: False,
        ),
        dry_run=False,
        ajax=lambda *_args: Detail(),
        js=execute_js,
        pause=lambda *_args: None,
        driver=Driver(),
        click_element=lambda *_args: events.append(("click",)),
        read_money=lambda: pytest.fail("A compra foi suspensa antes da leitura do saldo"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(bot, choice, hub_id="202") is False
    assert state["value"] == "202"
    assert events[0] == ("select_hub", "202")
    assert events[1][0] == "refresh_detail"
    assert not any(event[0] == "click" for event in events)


def test_plano_bloqueia_compra_quando_preco_final_nao_esta_verificado(monkeypatch):
    snapshot = object()
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args: "Trent 970")
    monkeypatch.setattr(engine_selection, "read_engine_catalog", lambda _bot: snapshot)
    monkeypatch.setattr(engine_selection, "verify_engine_selection",
                        lambda _bot, expected: "Trent 970")
    monkeypatch.setattr(aircraft_order_hub, "verify_order_hub_selection",
                        lambda _bot, expected: expected)
    monkeypatch.setattr(fleet, "prepare_order_hub", lambda *_args: ("202", False))
    monkeypatch.setattr(game_source_probe, "probe_game_sources", lambda _bot: {
        "aircraft_checkout_diagnostics": {
            "detail_model_id": "123",
            "model_hub_correlated": True,
            "ajax_idle_confirmed": True,
            "detail_loading": False,
            "price_verified": False,
        }
    })
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    class Driver:
        def find_element(self, *_args):
            return Detail()

    bot = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda *_args: "default",
            get_bool=lambda *_args: True,
        ),
        dry_run=False,
        ajax=lambda *_args: Detail(),
        driver=Driver(),
        js=lambda *_args: "PP-123",
        read_money=lambda: pytest.fail("Preço não verificado deve bloquear antes do saldo"),
        click_element=lambda *_args: calls.append("click"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(bot, choice, hub_id="202") is False
    assert calls == []


def test_fluxo_legado_nao_depende_do_novo_diagnostico_de_checkout(monkeypatch):
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args: "Trent 970")
    monkeypatch.setattr(engine_selection, "read_engine_catalog",
                        lambda _bot: pytest.fail("Fluxo legado não usa snapshot novo"))
    monkeypatch.setattr(game_source_probe, "probe_game_sources",
                        lambda _bot: pytest.fail("Fluxo legado não exige diagnóstico novo"))
    monkeypatch.setattr(fleet, "prepare_order_hub", lambda *_args: ("101", False))
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

        def find_element(self, *_args):
            return object()

    class Driver:
        def find_element(self, *_args):
            return Detail()

    bot = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda *_args: "default",
            get_bool=lambda *_args: True,
        ),
        dry_run=False,
        ajax=lambda *_args: Detail(),
        driver=Driver(),
        js=lambda *_args: "PP-123",
        read_money=lambda: 1_000_000_000,
        click_element=lambda *_args: calls.append("click"),
        wait_text=lambda *_args, **_kwargs: "Pedido recebido",
        confirm_purchase=lambda *_args: False,
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(bot, choice) is False
    assert calls == ["click"]
