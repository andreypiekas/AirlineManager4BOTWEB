from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

import aircraft_order_hub
import engine_selection
import fleet
import game_source_probe
import investment_policy


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
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args, **_kwargs: "Trent 970")
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    bot = SimpleNamespace(
        config=SimpleNamespace(get=lambda *_args: "default"),
        dry_run=True,
        ajax=lambda *_args: Detail(),
        js=lambda *_args: hub_state(selector_count=0),
        click_element=lambda *_args: calls.append("click"),
        read_money=lambda: calls.append("read_money"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(
        bot, choice, hub_id="202",
        expected_checkout_cost=300_000_000,
        expected_engine_id="trent-970",
    ) is False
    assert calls == []


def test_gate_g0_bloqueia_encomenda_planejada_antes_de_abrir_formulario():
    bot = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda _section, _key, fallback: fallback,
        ),
        dry_run=False,
        ajax=lambda *_args: pytest.fail("Gate G0 deve impedir abertura do formulário"),
        js=lambda *_args: pytest.fail("Gate G0 deve impedir alteração do formulário"),
        click_element=lambda *_args: pytest.fail("Gate G0 deve impedir clique"),
        read_money=lambda: pytest.fail("A compra foi suspensa antes da leitura do saldo"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(
        bot, choice, hub_id="202",
        expected_checkout_cost=300_000_000,
        expected_engine_id="trent-970",
    ) is False


def test_plano_bloqueia_compra_quando_preco_final_nao_esta_verificado(monkeypatch):
    snapshot = SimpleNamespace(selected_engine_id="engine-1")
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args, **_kwargs: "Trent 970")
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
            "ajax_active": False,
            "price_verified": False,
        },
        "aircraft_order_hub_selection": {
            "selected_hub_id": "202",
            "status": "dom_consistent",
        },
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
        dry_run=True,
        ajax=lambda *_args: Detail(),
        driver=Driver(),
        js=lambda *_args: "PP-123",
        read_money=lambda: pytest.fail("Preço não verificado deve bloquear antes do saldo"),
        click_element=lambda *_args: calls.append("click"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(
        bot, choice, hub_id="202",
        expected_checkout_cost=310_000_000,
        expected_engine_id="engine-1",
    ) is False
    assert calls == []


def test_fluxo_legado_nao_depende_do_novo_diagnostico_de_checkout(monkeypatch):
    monkeypatch.setattr(
        investment_policy.InvestmentPolicy,
        "from_config",
        classmethod(lambda cls, _config: pytest.fail("O fluxo legado não depende da nova política")),
    )
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args, **_kwargs: "Trent 970")
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


def test_simulacao_de_plano_bloqueia_checkout_sem_preco_verificado(monkeypatch):
    snapshot = SimpleNamespace(selected_engine_id="engine-1")
    monkeypatch.setattr(engine_selection, "prepare_engine", lambda *_args, **_kwargs: "Trent 970")
    monkeypatch.setattr(engine_selection, "read_engine_catalog", lambda _bot: snapshot)
    monkeypatch.setattr(fleet, "prepare_order_hub", lambda *_args: ("202", False))
    probes = []
    monkeypatch.setattr(game_source_probe, "probe_game_sources", lambda _bot: probes.append(True) or {
        "aircraft_checkout_diagnostics": {
            "detail_model_id": "123",
            "model_hub_correlated": True,
            "ajax_idle_confirmed": True,
            "detail_loading": False,
            "ajax_active": False,
            "price_verified": False,
        },
        "aircraft_order_hub_selection": {
            "selected_hub_id": "202",
            "status": "dom_consistent",
        },
    })
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    bot = SimpleNamespace(
        config=SimpleNamespace(get=lambda *_args: "default"),
        dry_run=True,
        ajax=lambda *_args: Detail(),
        js=lambda *_args: "PP-123",
        notify=lambda *args, **kwargs: calls.append(("notify", args, kwargs)),
        read_money=lambda: pytest.fail("A simulação não deve consultar saldo para comprar"),
        click_element=lambda *_args: calls.append(("click",)),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(
        bot, choice, hub_id="202",
        expected_checkout_cost=310_000_000,
        expected_engine_id="engine-1",
    ) is False
    assert probes == [True]
    assert calls == []


@pytest.mark.parametrize("case", [
    "valid", "price_changed", "engine_excluded", "untrusted_source", "model_changed",
    "hub_changed", "ajax_active", "second_price_changed", "engine_changed", "late_low_balance", "live_gate",
])
def test_prevoo_planejado_valida_checkout_sem_submeter_pedido(monkeypatch, case):
    snapshot = SimpleNamespace(selected_engine_id="engine-1")
    if case == "engine_changed":
        snapshot.selected_engine_id = "engine-2"
    prepared = []

    def prepare(_bot, preference, *, expected_engine_id):
        prepared.append((preference, expected_engine_id))
        return "Trent 970"

    monkeypatch.setattr(engine_selection, "prepare_engine", prepare)
    monkeypatch.setattr(engine_selection, "read_engine_catalog", lambda _bot: snapshot)
    motor_checks = []
    monkeypatch.setattr(engine_selection, "verify_engine_selection",
                        lambda _bot, expected: motor_checks.append(expected) or "Trent 970")
    checkout_price_checks = []

    def require_checkout_price(catalog, *, expected_engine_id, checkout_price):
        checkout_price_checks.append((catalog, expected_engine_id, checkout_price))
        assert checkout_price.engine_id == expected_engine_id
        return checkout_price.amount_usd

    monkeypatch.setattr(engine_selection, "require_verified_checkout_price", require_checkout_price)
    hub_checks = []
    monkeypatch.setattr(aircraft_order_hub, "verify_order_hub_selection",
                        lambda _bot, expected: hub_checks.append(expected) or expected)
    monkeypatch.setattr(fleet, "prepare_order_hub", lambda *_args: ("202", False))
    probes = []

    def verified_probe(_bot):
        probes.append(True)
        report = {
            "aircraft_checkout_diagnostics": {
                "detail_model_id": "123",
                "model_hub_correlated": True,
                "ajax_idle_confirmed": True,
                "detail_loading": False,
                "ajax_active": False,
                "price_verified": True,
                "checkout_cost": 310_000_000,
                "price_includes_engine": True,
                "price_source": "data_final_price",
            },
            "aircraft_order_hub_selection": {
                "selected_hub_id": "202",
                "status": "dom_consistent",
            },
        }
        checkout = report["aircraft_checkout_diagnostics"]
        if case == "price_changed" or (case == "second_price_changed" and len(probes) == 2):
            checkout["checkout_cost"] = 320_000_000
        elif case == "engine_excluded":
            checkout["price_includes_engine"] = False
        elif case == "untrusted_source":
            checkout["price_source"] = "data_price"
        elif case == "model_changed":
            checkout["detail_model_id"] = "456"
        elif case == "hub_changed":
            report["aircraft_order_hub_selection"]["selected_hub_id"] = "101"
        elif case == "ajax_active":
            checkout["ajax_active"] = True
        return report

    monkeypatch.setattr(game_source_probe, "probe_game_sources", verified_probe)
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    def current_detail(*_args):
        assert len(probes) == 2
        if case == "late_low_balance":
            warning = SimpleNamespace(is_displayed=lambda: True)
            return SimpleNamespace(find_elements=lambda *_args: [warning])
        return Detail()

    bot = SimpleNamespace(
        config=SimpleNamespace(get=lambda section, key, fallback: fallback),
        dry_run=case != "live_gate",
        ajax=lambda *_args: Detail(),
        driver=SimpleNamespace(find_element=current_detail),
        js=lambda *_args: "PP-123",
        notify=lambda *args, **kwargs: calls.append(("notify", args, kwargs)),
        read_money=lambda: pytest.fail("A simulação não deve consultar saldo para comprar"),
        click_element=lambda *_args: calls.append(("click",)),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    result = fleet.order_aircraft(
        bot, choice, hub_id="202",
        expected_checkout_cost=310_000_000,
        expected_engine_id="engine-1",
    )
    assert prepared == ([] if case == "live_gate" else [("default", "engine-1")])
    assert result is (case == "valid")
    if case == "late_low_balance":
        assert len(checkout_price_checks) == 1
    if case != "valid":
        assert calls == []
        return
    assert len(probes) == 2
    assert len(motor_checks) == 2
    assert hub_checks == ["202"]
    assert len(checkout_price_checks) == 1
    _, checked_engine_id, checked_price = checkout_price_checks[0]
    assert checked_engine_id == "engine-1"
    assert checked_price.amount_usd == 310_000_000
    assert checked_price.source == "data_final_price"
    assert checked_price.status == "verified"
    assert len(calls) == 1
    assert calls[0][0] == "notify"
    assert "310,000,000" in calls[0][1][0]


@pytest.mark.parametrize("hub,engine", [("101", "1"), ("202", "1"), ("101", "2")])
def test_simulacao_planejada_nao_altera_base_motor_nem_compra(hub, engine):
    state = hub_state()
    groups = [{"type": "select", "id": "acEngine", "name": "engine", "options": [
        {"label": "Trent 970", "value": "1", "selected": True,
         "speed": 905, "fuel": 12.1, "disabled": False},
        {"label": "GP7270", "value": "2", "selected": False,
         "speed": 921, "fuel": 12.4, "disabled": False},
    ]}]
    report = {
        "schema_version": 1,
        "aircraft_order_hub_selection": {
            "selector_count": 1, "option_count": 2,
            "selected_option_count": 1, "selected_hub_id": "101",
            "status": "dom_consistent",
        },
        "aircraft_checkout_diagnostics": {
            "detail_panel_count": 1, "detail_model_id": "123",
            "model_hub_correlated": True, "ajax_active": False,
            "ajax_idle_confirmed": True, "detail_loading": False,
            # Even a candidate price supplied by the page is not proof.
            "price_verified": True, "checkout_cost": 310_000_000,
            "price_includes_engine": True, "price_source": "data_final_price",
        },
    }
    calls = []

    def execute_js(script, *args):
        assert not args, "A simulação não pode selecionar uma opção no DOM"
        calls.append(script)
        if script == aircraft_order_hub._ORDER_HUB_STATE_JS:
            return deepcopy(state)
        if script == engine_selection._ENGINE_OPTIONS_JS:
            return deepcopy(groups)
        if script == game_source_probe.PROBE_JS:
            return deepcopy(report)
        if script == "return $('#acReg').val();":
            return "PP-123"
        pytest.fail("Script inesperado na simulação")

    class Detail:
        def find_elements(self, *_args):
            return []

    def open_detail(url, target):
        assert url == "ac_orders.php?mode=detail&id=123&charter=0"
        assert target == "acModel"
        return Detail()

    bot = SimpleNamespace(
        config=SimpleNamespace(get=lambda _section, _key, fallback: fallback),
        dry_run=True, ajax=open_detail, js=execute_js,
        pause=lambda *_args: pytest.fail("Simulação não deve aguardar mutações"),
        notify=lambda *_args, **_kwargs: pytest.fail("Checkout inconclusivo"),
        click_element=lambda *_args: pytest.fail("Simulação não deve clicar"),
        read_money=lambda: pytest.fail("Simulação não deve iniciar a compra"),
        confirm_purchase=lambda *_args: pytest.fail("Simulação não deve confirmar compra"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)

    assert fleet.order_aircraft(
        bot, choice, hub_id=hub, expected_engine_id=engine,
        expected_checkout_cost=310_000_000,
    ) is False
    assert aircraft_order_hub._ORDER_HUB_STATE_JS in calls
    assert engine_selection._ENGINE_OPTIONS_JS in calls
    assert (game_source_probe.PROBE_JS in calls) is (engine == "1")
    assert state["value"] == "101"
    assert groups[0]["options"][0]["selected"] is True
