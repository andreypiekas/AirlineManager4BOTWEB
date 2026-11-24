"""Motorização: nunca comprar quando a seleção não foi confirmada no jogo."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

import engine_selection
import fleet
import web


def engines(*, speed=True, fuel=True, selected="1"):
    options = [
        {"label": "Trent 970", "value": "1", "selected": selected == "1",
         "speed": 905 if speed else None, "fuel": 12.1 if fuel else None, "disabled": False},
        {"label": "GP7270", "value": "2", "selected": selected == "2",
         "speed": 921 if speed else None, "fuel": 12.4 if fuel else None, "disabled": False},
        {"label": "RR Trent 972", "value": "3", "selected": selected == "3",
         "speed": 945 if speed else None, "fuel": 12.8 if fuel else None, "disabled": False},
    ]
    return [{"type": "select", "id": "acEngine", "name": "engine", "options": options}]


def radios(*, selected="2"):
    group = engines(selected=selected)[0]
    group.update({"type": "radio", "id": "", "name": "engineChoice",
                  "selectedValue": selected if selected in ("1", "2", "3") else None})
    return [group]


@pytest.mark.parametrize("groups,kind,selector,selected", [
    (engines(), "select", "acEngine", "1"),
    (radios(), "radio", "engineChoice", "2"),
])
def test_catalogo_somente_leitura_expoe_ids_reais_e_disponibilidade(groups, kind, selector, selected):
    groups[0]["options"][2]["disabled"] = True
    scripts = []

    class Bot:
        def js(self, script, *args):
            assert not args
            scripts.append(script)
            return groups

        def pause(self, *_):
            pytest.fail("Inventário não deve alterar o formulário")

    catalog = engine_selection.read_engine_catalog(Bot())
    assert scripts == [engine_selection._ENGINE_OPTIONS_JS]
    assert catalog.selector_type == kind
    assert catalog.selector_id == selector
    assert catalog.selected_engine_id == selected
    assert [v.engine_id for v in catalog.variants] == ["1", "2", "3"]
    assert [v.available for v in catalog.variants] == [True, True, False]
    assert [v.selected for v in catalog.variants] == [selected == "1", selected == "2", False]
    assert catalog.variants[1].label == "GP7270"
    assert catalog.variants[1].speed == 921


@pytest.mark.parametrize("groups,reason", [
    (engines(selected="none"), "sem motor selecionado"),
    (radios(selected="none"), "sem motor selecionado"),
    (engines() + radios(), "único seletor"),
    ([], "bloqueada"),
])
def test_catalogo_rejeita_ausencia_ou_ambiguidade_de_grupo_e_selecao(groups, reason):
    with pytest.raises(engine_selection.EngineSelectionError, match=reason):
        engine_selection.parse_engine_catalog(groups)


def test_catalogo_aceita_um_unico_motor_sem_selecao():
    groups = engines(selected="none")
    groups[0]["options"] = groups[0]["options"][:1]
    catalog = engine_selection.parse_engine_catalog(groups)
    assert catalog.selected_engine_id is None
    assert catalog.variants[0].engine_id == "1"


@pytest.mark.parametrize("problem,reason", [
    ("duplicate_id", "IDs duplicados"),
    ("duplicate_selected", "Seleção ambígua"),
    ("disabled_selected", "indisponível"),
    ("selected_mismatch", "inconsistente"),
    ("missing_identifier", "identificador estável"),
    ("missing_option_id", "identificação"),
])
def test_catalogo_rejeita_identidade_e_estado_inconsistentes(problem, reason):
    groups = radios() if problem == "missing_identifier" else engines()
    group = groups[0]
    if problem == "duplicate_id":
        group["options"][2]["value"] = "2"
        group["options"][2]["disabled"] = True
    elif problem == "duplicate_selected":
        group["options"][1]["selected"] = True
    elif problem == "disabled_selected":
        group["options"][0]["disabled"] = True
    elif problem == "selected_mismatch":
        group["selectedValue"] = "2"
    elif problem == "missing_identifier":
        group["name"] = ""
    elif problem == "missing_option_id":
        group["options"][0]["value"] = ""
    with pytest.raises(engine_selection.EngineSelectionError, match=reason):
        engine_selection.parse_engine_catalog(groups)


@pytest.mark.parametrize("kind", ["select", "radio"])
def test_dom_reconstruido_mantem_selecao_quando_identidade_e_opcoes_coincidem(kind):
    before = engines() if kind == "select" else radios(selected="1")
    before[0]["selectedValue"] = "1"
    after = deepcopy(before)
    after[0]["options"].reverse()
    for option in after[0]["options"]:
        option["selected"] = option["value"] == "3"
    after[0]["selectedValue"] = "3"
    calls = []

    class Bot:
        dry_run = False

        def js(self, script, *args):
            calls.append(args)
            if args:
                return args == (kind, "acEngine" if kind == "select" else "engineChoice", "3")
            return deepcopy(before if len(calls) == 1 else after)

        def pause(self, *_):
            pass

    assert engine_selection.prepare_engine(Bot(), "name:Trent 972") == "RR Trent 972"
    assert len(calls) == 3


@pytest.mark.parametrize("change,reason", [
    ("group_id", "grupo de motores mudou"),
    ("group_name", "grupo de motores mudou"),
    ("label", "Nome ou disponibilidade"),
    ("availability", "Nome ou disponibilidade"),
    ("removed_variant", "Nome ou disponibilidade"),
    ("selected_value", "inconsistente"),
])
def test_revalidacao_bloqueia_formulario_alterado_apos_ajax(change, reason):
    before = engines()
    after = deepcopy(before)
    for option in after[0]["options"]:
        option["selected"] = option["value"] == "3"
    after[0]["selectedValue"] = "3"
    if change == "group_id":
        after[0]["id"] = "novoEngine"
    elif change == "group_name":
        after[0]["name"] = "outroGrupo"
    elif change == "label":
        after[0]["options"][2]["label"] = "Motor substituído"
    elif change == "availability":
        after[0]["options"][1]["disabled"] = True
    elif change == "removed_variant":
        after[0]["options"].pop(1)
    elif change == "selected_value":
        after[0]["selectedValue"] = "2"
    reads = 0

    class Bot:
        dry_run = False

        def js(self, script, *args):
            nonlocal reads
            if args:
                return True
            reads += 1
            return deepcopy(before if reads == 1 else after)

        def pause(self, *_):
            pass

    with pytest.raises(engine_selection.EngineSelectionError, match=reason):
        engine_selection.prepare_engine(Bot(), "name:Trent 972")


@pytest.mark.parametrize("metric", ["speed", "fuel"])
@pytest.mark.parametrize(
    "before_value,after_value,blocked",
    [
        (945, 946, True),
        (945, None, True),
        (945, 0, True),
        (None, 945, True),
        (None, None, False),
    ],
)
def test_revalidacao_confere_metricas_da_variante_escolhida_apos_ajax(
    metric, before_value, after_value, blocked
):
    before = engines()
    before[0]["options"][2][metric] = before_value
    after = deepcopy(before)
    after[0]["options"][2][metric] = after_value
    for option in after[0]["options"]:
        option["selected"] = option["value"] == "3"
    after[0]["selectedValue"] = "3"
    reads = 0

    class Bot:
        dry_run = False

        def js(self, script, *args):
            nonlocal reads
            if args:
                return args == ("select", "acEngine", "3")
            reads += 1
            return deepcopy(before if reads == 1 else after)

        def pause(self, *_):
            pass

    if blocked:
        with pytest.raises(engine_selection.EngineSelectionError, match="Métricas"):
            engine_selection.prepare_engine(Bot(), "name:Trent 972")
    else:
        assert engine_selection.prepare_engine(Bot(), "name:Trent 972") == "RR Trent 972"


@pytest.mark.parametrize(
    "preference,selected_id,index,metric,before_value,after_value",
    [
        ("fastest", "3", 2, "speed", 945, 946),
        ("fastest", "3", 2, "fuel", 12.8, 12.9),
        ("economical", "1", 0, "speed", 905, 906),
        ("economical", "1", 0, "fuel", 12.1, 12.2),
    ],
)
def test_revalidacao_confere_metricas_da_variante_escolhida_por_preferencia(
    preference, selected_id, index, metric, before_value, after_value
):
    before = engines()
    before[0]["options"][index][metric] = before_value
    after = deepcopy(before)
    after[0]["options"][index][metric] = after_value
    for option in after[0]["options"]:
        option["selected"] = option["value"] == selected_id
    after[0]["selectedValue"] = selected_id
    reads = 0

    class Bot:
        dry_run = False

        def js(self, script, *args):
            nonlocal reads
            if args:
                return args == ("select", "acEngine", selected_id)
            reads += 1
            return deepcopy(before if reads == 1 else after)

        def pause(self, *_):
            pass

    with pytest.raises(engine_selection.EngineSelectionError, match="Métricas"):
        engine_selection.prepare_engine(Bot(), preference)


@pytest.mark.parametrize(
    "preference,selected_id,index,metric,changed_value",
    [
        ("fastest", "3", 2, "speed", 800),
        ("economical", "1", 0, "fuel", 13.0),
    ],
)
def test_revalidacao_recalcula_preferencia_de_motor_apos_ajax(
    preference, selected_id, index, metric, changed_value
):
    before = engines()
    after = deepcopy(before)
    after[0]["options"][index][metric] = changed_value
    for option in after[0]["options"]:
        option["selected"] = option["value"] == selected_id
    after[0]["selectedValue"] = selected_id
    reads = 0

    class Bot:
        dry_run = False

        def js(self, script, *args):
            nonlocal reads
            if args:
                return args == ("select", "acEngine", selected_id)
            reads += 1
            return deepcopy(before if reads == 1 else after)

        def pause(self, *_):
            pass

    with pytest.raises(engine_selection.EngineSelectionError, match="preferência"):
        engine_selection.prepare_engine(Bot(), preference)


@pytest.mark.parametrize("pref,expected", [
    ("name:Trent 972", "RR Trent 972"),
    ("name:rr TRENT 972", "RR Trent 972"),
    ("fastest", "RR Trent 972"),
    ("economical", "Trent 970"),
])
def test_escolhe_motor_por_nome_ou_metricas_observadas(pref, expected):
    group, selected = engine_selection.choose_engine(engines(), pref)
    assert group["type"] == "select"
    assert selected.label == expected


@pytest.mark.parametrize("pref", [
    "name:", "unknown", "name:" + "x" * 76,
])
def test_preferencias_invalidas_sao_bloqueadas(pref):
    with pytest.raises(engine_selection.EngineSelectionError):
        engine_selection.validate_preference(pref)


def test_opcao_desativada_nao_pode_ser_escolhida():
    groups = engines()
    groups[0]["options"][2]["disabled"] = True
    with pytest.raises(engine_selection.EngineSelectionError):
        engine_selection.choose_engine(groups, "name:Trent 972")


def test_nome_ambiguo_impede_compra():
    with pytest.raises(engine_selection.EngineSelectionError):
        engine_selection.choose_engine(engines(), "name:Trent")


def test_velocidade_e_consumo_sem_dados_nao_sao_adivinhados():
    with pytest.raises(engine_selection.EngineSelectionError, match="velocidade"):
        engine_selection.choose_engine(engines(speed=False), "fastest")
    with pytest.raises(engine_selection.EngineSelectionError, match="consumo"):
        engine_selection.choose_engine(engines(fuel=False), "economical")


def test_nenhum_seletor_nao_faz_fallback():
    with pytest.raises(engine_selection.EngineSelectionError, match="bloqueada"):
        engine_selection.choose_engine([], "name:RR Trent 972")


def test_varios_seletores_ambiguos_bloqueiam():
    with pytest.raises(engine_selection.EngineSelectionError):
        engine_selection.choose_engine(engines() + engines(), "fastest")


def test_selecao_exata_confirmada_apos_clique():
    calls = []

    class Bot:
        dry_run = False

        def js(self, script, *args):
            calls.append(args)
            if len(args) == 3:
                return args == ("select", "acEngine", "3")
            return engines(selected="3") if len(calls) > 2 else engines()

        def pause(self, *_):
            pass

    motor = engine_selection.prepare_engine(Bot(), "name:Trent 972")
    assert motor == "RR Trent 972"
    assert calls[1] == ("select", "acEngine", "3")


@pytest.mark.parametrize("preference", ["default", "economical", "name:GP7270"])
def test_id_planejado_prevalece_sobre_preferencia_global(preference):
    calls = []

    class Bot:
        dry_run = False

        def js(self, script, *args):
            calls.append(args)
            if args:
                return args == ("select", "acEngine", "3")
            return engines(selected="3") if len(calls) > 2 else engines()

        def pause(self, *_):
            pass

    assert engine_selection.prepare_engine(Bot(), preference, expected_engine_id="3") == "RR Trent 972"
    assert calls[1] == ("select", "acEngine", "3")


@pytest.mark.parametrize("engine_id", ["missing", "3"])
def test_id_planejado_ausente_ou_indisponivel_bloqueia_sem_mutacao(engine_id):
    groups = engines()
    groups[0]["options"][2]["disabled"] = True

    class Bot:
        dry_run = False

        def js(self, script, *args):
            assert not args
            return deepcopy(groups)

    with pytest.raises(engine_selection.EngineSelectionError, match="aprovada"):
        engine_selection.prepare_engine(Bot(), "default", expected_engine_id=engine_id)


def test_ausencia_de_confirmacao_bloqueia_compra():
    class Bot:
        dry_run = False

        def js(self, script, *args):
            return True if args else engines(selected="1")

        def pause(self, *_):
            pass

    with pytest.raises(engine_selection.EngineSelectionError, match="não confirmou"):
        engine_selection.prepare_engine(Bot(), "name:Trent 972")


def test_simulacao_nunca_seleciona_nem_compra():
    calls = []

    class Bot:
        dry_run = True

        def js(self, script, *args):
            calls.append(args)
            return engines(speed=False, fuel=False)

        def pause(self, *_):
            pytest.fail("Simulação não deve aguardar após selecionar o motor")

    assert engine_selection.prepare_engine(Bot(), "name:Trent 972") == "RR Trent 972"
    assert len(calls) == 1
    assert calls[0] == ()


def test_padrao_aceita_metricas_nao_expostas_pelo_dom():
    groups = engines(selected="2")
    for option in groups[0]["options"]:
        option["speed"] = None
        option["fuel"] = None

    class Bot:
        def js(self, script, *args):
            assert script == engine_selection._ENGINE_OPTIONS_JS and not args
            return deepcopy(groups)

    assert engine_selection.prepare_engine(Bot(), "default") == "GP7270"


@pytest.mark.parametrize("groups,expected", [
    (engines(selected="2"), "GP7270"),
    (radios(selected="2"), "GP7270"),
])
def test_padrao_exige_leitura_da_variante_selecionada_sem_alterar_o_formulario(groups, expected):
    calls = []

    class Bot:
        dry_run = False

        def js(self, script, *args):
            assert not args, "Motor padrão não deve alterar o navegador"
            calls.append(script)
            return deepcopy(groups)

    assert engine_selection.prepare_engine(Bot(), "default") == expected
    assert calls == [engine_selection._ENGINE_OPTIONS_JS]


@pytest.mark.parametrize("groups", [
    [],
    engines(selected="none"),
    engines(),
])
def test_padrao_bloqueia_quando_motor_nao_pode_ser_confirmado(groups):
    if groups and groups[0]["options"][0]["selected"]:
        groups[0]["options"][0]["disabled"] = True

    class Bot:
        dry_run = False

        def js(self, script, *args):
            assert script == engine_selection._ENGINE_OPTIONS_JS and not args
            return deepcopy(groups)

    with pytest.raises(engine_selection.EngineSelectionError):
        engine_selection.prepare_engine(Bot(), "default")


@pytest.mark.parametrize("preference", ["fastest", "economical"])
def test_metricas_empatadas_nao_escolhem_uma_variante_arbitraria(preference):
    groups = engines()
    groups[0]["options"][1]["speed"] = 905
    groups[0]["options"][1]["fuel"] = 12.1
    groups[0]["options"][2]["disabled"] = True

    with pytest.raises(engine_selection.EngineSelectionError, match="ambíg"):
        engine_selection.choose_engine(groups, preference)


@pytest.mark.parametrize("preference,missing_metric", [
    ("fastest", "fuel"),
    ("economical", "speed"),
])
def test_empate_sem_dado_de_desempate_eh_ambiguo(preference, missing_metric):
    groups = engines()
    groups[0]["options"][1]["speed"] = 905
    groups[0]["options"][1]["fuel"] = 12.1
    groups[0]["options"][1][missing_metric] = None
    groups[0]["options"][2]["disabled"] = True

    with pytest.raises(engine_selection.EngineSelectionError, match="ambíg"):
        engine_selection.choose_engine(groups, preference)


@pytest.mark.parametrize("preference,expected", [
    ("fastest", "Trent 970"),
    ("economical", "GP7270"),
])
def test_empate_com_dado_de_desempate_identifica_uma_variante(preference, expected):
    groups = engines()
    groups[0]["options"][2]["disabled"] = True
    if preference == "fastest":
        groups[0]["options"][1]["speed"] = 905
    else:
        groups[0]["options"][1]["fuel"] = 12.1

    _, choice = engine_selection.choose_engine(groups, preference)
    assert choice.label == expected


def test_fluxo_de_compra_nao_aciona_confirmacao_sem_motor_verificado(monkeypatch):
    cfg = SimpleNamespace(get=lambda section, key, fallback="": (
        "name:Trent 972" if key == "engine_preference" else fallback
    ))
    called = []

    class Detail:
        def find_elements(self, *args):
            return []

    bot = SimpleNamespace(config=cfg, ajax=lambda *_args: Detail(),
                          dry_run=False, click_element=lambda *_args: called.append("click"))
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)
    monkeypatch.setattr(engine_selection, "prepare_engine",
                        lambda _bot, _pref: (_ for _ in ()).throw(
                            engine_selection.EngineSelectionError("Sem seletor válido")))
    assert fleet.order_aircraft(bot, choice) is False
    assert called == []


def test_desativar_compra_automatica_impede_clique_apos_pesquisa_do_motor(monkeypatch):
    cfg = SimpleNamespace(
        get=lambda *_args: "default",
        get_bool=lambda section, key, fallback=True: False if key == "autobuy_aircraft" else fallback,
    )
    calls = []

    class Detail:
        def find_elements(self, *_args):
            return []

    bot = SimpleNamespace(
        config=cfg, dry_run=False,
        ajax=lambda *_args: Detail(),
        js=lambda *_args: "PP-001",
        read_money=lambda: pytest.fail("Não deve consultar saldo para submeter pedido suspenso"),
        click_element=lambda *_args: calls.append("click"),
    )
    choice = fleet.AircraftModel("123", "A380-800", 15000, 940, 600, 12, 300_000_000)
    assert fleet.order_aircraft(bot, choice) is False
    assert calls == []


def test_api_nao_salva_preferencia_invalida():
    class Cfg:
        def __init__(self):
            self.values = {}
            self.saved = False

        def set(self, section, key, value):
            self.values[key] = value

        def save(self):
            self.saved = True

    dashboard = web.WebDashboard.__new__(web.WebDashboard)
    dashboard.cfg = Cfg()
    ok, message = dashboard.update_settings({"text": {"engine_preference": "name:"}})
    assert not ok
    assert "motor" in message.lower()
    assert dashboard.cfg.values == {}
    assert not dashboard.cfg.saved


def test_api_salva_preferencia_valida():
    class Cfg:
        def __init__(self):
            self.values = {}

        def set(self, section, key, value):
            self.values[key] = value

        def save(self):
            pass

    dashboard = web.WebDashboard.__new__(web.WebDashboard)
    dashboard.cfg = Cfg()
    ok, _ = dashboard.update_settings({"text": {"engine_preference": "name:Trent 972"}})
    assert ok
    assert dashboard.cfg.values["engine_preference"] == "name:Trent 972"


def test_nova_interface_exige_confirmacao():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "assets/web/index.html").read_text(encoding="utf-8")
    assert "Configuração do motor" in html
    assert "Mais rápido (dados confirmados)" in html
    assert "Menor consumo (dados confirmados)" in html
    assert "Motor específico (nome)" in html
    assert 'draftKey("text", "engine_preference")' in html
    assert "Informe o nome do motor antes de salvar." in html
