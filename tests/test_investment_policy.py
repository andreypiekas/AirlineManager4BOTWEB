"""The new investment workflow remains opt-in and read-only at G0."""
from __future__ import annotations

from investment_policy import InvestmentPolicy


class Config:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, section, key, fallback=""):
        return self.values.get((section, key), fallback)

    def get_bool(self, section, key, fallback=False):
        return self.values.get((section, key), fallback)


def test_ausencia_de_configuracao_preserva_legado_sem_habilitar_novo_fluxo():
    policy = InvestmentPolicy.from_config(Config({("options", "autobuy_aircraft"): True}))
    state = policy.report()
    assert state["legacy_autobuy_aircraft"] is True
    assert state["planning_enabled"] is False
    assert state["valid"] is True
    assert state["execution_available"] is False
    assert "planejamento_desativado" in state["blocking_reasons"]


def test_modo_autonomo_configurado_segue_bloqueado_no_gate_g0():
    config = Config({
        ("investment", "planning_enabled"): True,
        ("investment", "mode"): "autonomous",
        ("investment", "auto_buy_aircraft"): True,
        ("investment", "auto_buy_hub"): True,
        ("investment", "max_single_investment"): "100000",
        ("investment", "max_hub_investment"): "120000",
        ("investment", "max_hub_points"): "200",
        ("investment", "max_daily_spend"): "200000",
        ("investment", "max_cycle_spend"): "150000",
        ("investment", "max_acquisitions_per_day"): "5",
    })
    state = InvestmentPolicy.from_config(config).report()
    assert state["auto_buy_hub"] is True
    assert state["max_hub_investment"] == 120000
    assert state["max_hub_points"] == 200
    assert state["max_daily_spend"] == 200000
    assert state["max_cycle_spend"] == 150000
    assert state["valid"] is True
    assert state["execution_available"] is False
    assert state["blocking_reasons"] == ["executor_aguarda_homologacao"]


def test_limites_de_hub_nao_herdam_limite_de_aeronave():
    state = InvestmentPolicy.from_config(Config({
        ("investment", "auto_buy_hub"): True,
        ("investment", "max_single_investment"): "100000",
    })).report()
    assert state["max_hub_investment"] == 0
    assert state["max_hub_points"] == 0
    assert "limite_de_hub_a_configurar" in state["blocking_reasons"]
    assert not InvestmentPolicy.from_config(Config({
        ("investment", "max_hub_points"): "1000000001",
    })).valid


def test_configuracao_invalida_bloqueia_fluxo():
    config = Config({
        ("investment", "planning_enabled"): True,
        ("investment", "mode"): "qualquer",
        ("investment", "max_single_investment"): "-1",
    })
    state = InvestmentPolicy.from_config(config).report()
    assert state["mode"] == "analyze"
    assert state["max_single_investment"] == 0
    assert "politica_invalida" in state["blocking_reasons"]


def test_limite_de_aquisicoes_e_criterios_invalidos_falham_fechados():
    config = Config({
        ("investment", "planning_enabled"): True,
        ("investment", "max_acquisitions_per_day"): "101",
        ("investment", "max_payback_days"): "infinito",
    })
    state = InvestmentPolicy.from_config(config).report()
    assert state["max_acquisitions_per_day"] == 0
    assert state["max_payback_days"] == 0
    assert "politica_invalida" in state["blocking_reasons"]


def test_pesos_legados_e_configuracao_do_ranking_por_perfil():
    defaults = InvestmentPolicy.from_config(Config()).report()
    assert (defaults["profit_weight"], defaults["efficiency_weight"]) == (60, 40)
    assert defaults["return_weight"] == 0
    assert (defaults["risk_weight"], defaults["confidence_weight"],
            defaults["diversification_weight"]) == (0, 0, 0)

    custom = Config({
        ("investment", "profit_weight"): "0",
        ("investment", "efficiency_weight"): "0",
        ("investment", "risk_weight"): "100",
    })
    report = InvestmentPolicy.from_config(custom).report()
    assert report["risk_weight"] == 100
    assert "politica_invalida" not in report["blocking_reasons"]

    roi_only = Config({("investment", "profit_weight"): "0",
                       ("investment", "efficiency_weight"): "0",
                       ("investment", "return_weight"): "100"})
    assert InvestmentPolicy.from_config(roi_only).valid
    assert InvestmentPolicy.from_config(roi_only).return_weight == 100


def test_pesos_incorretos_bloqueiam_politica():
    invalid = Config({
        ("investment", "profit_weight"): "0",
        ("investment", "efficiency_weight"): "0",
        ("investment", "risk_weight"): "0",
        ("investment", "max_cycle_spend"): "100000",
    })
    assert "politica_invalida" in InvestmentPolicy.from_config(invalid).report()["blocking_reasons"]

    non_ascii = Config({("investment", "profit_weight"): "９０"})
    assert "politica_invalida" in InvestmentPolicy.from_config(non_ascii).report()["blocking_reasons"]
