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
        for key in ("max_single_investment", "max_daily_spend"):
            raw = read(key, "0").strip()
            if not raw.isdecimal():
                valid = False
                limits.append(0)
            else:
                limits.append(int(raw))

        return cls(
            enabled=enabled("planning_enabled"),
            mode=mode if mode in MODES else "analyze",
            auto_buy_aircraft=enabled("auto_buy_aircraft"),
            auto_buy_hub=enabled("auto_buy_hub"),
            max_single_investment=limits[0],
            max_daily_spend=limits[1],
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
        if self.mode == "autonomous" and (
            not self.max_single_investment or not self.max_daily_spend
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
            "legacy_autobuy_aircraft": self.legacy_autobuy_aircraft,
            "execution_available": False,
            "release_gate": "G0",
            "blocking_reasons": reasons,
        }
