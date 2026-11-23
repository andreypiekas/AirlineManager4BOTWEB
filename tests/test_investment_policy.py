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
    assert state["execution_available"] is False
    assert "planejamento_desativado" in state["blocking_reasons"]


def test_modo_autonomo_configurado_segue_bloqueado_no_gate_g0():
    config = Config({
        ("investment", "planning_enabled"): True,
        ("investment", "mode"): "autonomous",
        ("investment", "auto_buy_aircraft"): True,
        ("investment", "auto_buy_hub"): True,
        ("investment", "max_single_investment"): "100000",
        ("investment", "max_daily_spend"): "200000",
    })
    state = InvestmentPolicy.from_config(config).report()
    assert state["auto_buy_hub"] is True
    assert state["max_daily_spend"] == 200000
    assert state["execution_available"] is False
    assert state["blocking_reasons"] == ["executor_aguarda_homologacao"]


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
