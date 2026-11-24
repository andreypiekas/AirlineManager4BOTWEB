"""Feature gate for the planned acquisition workflow.

The legacy aircraft autobuyer is independent. Until the execution coordinator
is homologated, this module exposes configuration and read-only diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MODES = {"analyze", "approval", "autonomous"}


@dataclass(frozen=True)
class InvestmentPolicy:
    enabled: bool = False
    mode: str = "analyze"
    auto_buy_aircraft: bool = False
    auto_buy_hub: bool = False
    max_single_investment: int = 0
    max_daily_spend: int = 0
    max_cycle_spend: int = 0
    max_acquisitions_per_day: int = 0
    min_daily_profit: int = 0
    max_payback_days: int = 0
    profit_weight: int = 60
    efficiency_weight: int = 40
    risk_weight: int = 0
    confidence_weight: int = 0
    diversification_weight: int = 0
    valid: bool = True
    legacy_autobuy_aircraft: bool = False

    @classmethod
    def from_config(cls, config: Any) -> "InvestmentPolicy":
        """Read isolated defaults. Invalid limits or modes fail closed."""
        get = getattr(config, "get", None)
        get_bool = getattr(config, "get_bool", None)

        def read(key: str, fallback: str) -> str:
            return get("investment", key, fallback) if callable(get) else fallback

        def enabled(key: str, section: str = "investment") -> bool:
            return bool(get_bool(section, key, False)) if callable(get_bool) else False

        mode = read("mode", "analyze")
        valid = mode in MODES
        limits = []
        bounds = (("max_single_investment", 10**15, 0), ("max_daily_spend", 10**15, 0),
                  ("max_acquisitions_per_day", 100, 0), ("min_daily_profit", 10**15, 0),
                  ("max_payback_days", 3650, 0), ("profit_weight", 100, 60),
                  ("efficiency_weight", 100, 40), ("risk_weight", 100, 0),
                  ("confidence_weight", 100, 0), ("diversification_weight", 100, 0),
                  ("max_cycle_spend", 10**15, 0))
        for key, upper, fallback in bounds:
            raw = read(key, str(fallback)).strip()
            if not raw.isascii() or not raw.isdecimal() or len(raw) > 16 or int(raw) > upper:
                valid = False
                limits.append(0)
            else:
                limits.append(int(raw))
        if not any(limits[5:10]):
            valid = False

        return cls(
            enabled=enabled("planning_enabled"),
            mode=mode if mode in MODES else "analyze",
            auto_buy_aircraft=enabled("auto_buy_aircraft"),
            auto_buy_hub=enabled("auto_buy_hub"),
            max_single_investment=limits[0],
            max_daily_spend=limits[1],
            max_acquisitions_per_day=limits[2],
            min_daily_profit=limits[3],
            max_payback_days=limits[4],
            profit_weight=limits[5],
            efficiency_weight=limits[6],
            risk_weight=limits[7],
            confidence_weight=limits[8],
            diversification_weight=limits[9],
            max_cycle_spend=limits[10],
            valid=valid,
            legacy_autobuy_aircraft=enabled("autobuy_aircraft", "options"),
        )

    def report(self) -> dict:
        """Explain the new workflow's gate without authorizing any purchase."""
        reasons = []
        if not self.enabled:
            reasons.append("planejamento_desativado")
        if not self.valid:
            reasons.append("politica_invalida")
        if self.mode == "analyze":
            reasons.append("modo_somente_analise")
        if self.mode == "approval":
            reasons.append("aprovacao_humana_necessaria")
        if self.mode == "autonomous" and (
            not self.max_single_investment or not self.max_daily_spend
            or not self.max_acquisitions_per_day or not self.max_cycle_spend
        ):
            reasons.append("limites_de_gasto_a_configurar")
        reasons.append("executor_aguarda_homologacao")
        return {
            "planning_enabled": self.enabled,
            "mode": self.mode,
            "auto_buy_aircraft": self.auto_buy_aircraft,
            "auto_buy_hub": self.auto_buy_hub,
            "max_single_investment": self.max_single_investment,
            "max_daily_spend": self.max_daily_spend,
            "max_cycle_spend": self.max_cycle_spend,
            "max_acquisitions_per_day": self.max_acquisitions_per_day,
            "min_daily_profit": self.min_daily_profit,
            "max_payback_days": self.max_payback_days,
            "profit_weight": self.profit_weight,
            "efficiency_weight": self.efficiency_weight,
            "risk_weight": self.risk_weight,
            "confidence_weight": self.confidence_weight,
            "diversification_weight": self.diversification_weight,
            "valid": self.valid,
            "legacy_autobuy_aircraft": self.legacy_autobuy_aircraft,
            "execution_available": False,
            "release_gate": "G0",
            "blocking_reasons": reasons,
        }
