"""A9 daily Telegram reporting uses local evidence and durable delivery claims."""
from __future__ import annotations

import logging
import sqlite3
import time
from types import SimpleNamespace

import investment_daily
import pytest
from investment_journal import InvestmentJournal


def _timestamp(day=23, hour=12):
    return time.mktime((2026, 11, day, hour, 0, 0, 0, 0, -1))


class Config:
    def __init__(self, path, *, profile="principal", enabled=True, planning=False,
                 summary_hour=9, settings=None, legacy_autobuy=True):
        self.profile = SimpleNamespace(label=profile, is_main=profile == "principal", data=path)
        self.flags = {("options", "telegram_investment_daily"): enabled,
                      ("options", "telegram"): True,
                      ("investment", "planning_enabled"): planning,
                      ("options", "autobuy_aircraft"): legacy_autobuy}
        self.summary_hour = summary_hour
        self.settings = settings or {}

    def get_bool(self, section, key, default=False):
        return self.flags.get((section, key), default)

    def get_int(self, section, key, default=0):
        return self.summary_hour if key == "summary_hour" else default

    def get(self, section, key, default=""):
        return self.settings.get((section, key), default)


class Client:
    enabled = True

    def __init__(self, *results):
        self.calls = []
        self.results = list(results)

    def send_now(self, message):
        self.calls.append(message)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result, "mock"


class Dashboard:
    def __init__(self, bot, cfg, buffer):
        assert buffer is None

    def hub_recommendations(self):
        return {"research_queue": {
            "coverage": "partial", "has_more": True,
            "hub_coverage": [{"status": "pesquisa_iniciada", "coverage": "partial"}],
            "items": [{}],
        }, "portfolio": {"evaluated_count": 2, "eligible_count": 0,
                         "status": "inconclusivo"}}

    def audited_expansion(self):
        return None


def prepare(monkeypatch, path, *, profile="principal", enabled=True, results=(True,),
            planning=False, dry_run=False, summary_hour=9, settings=None,
            legacy_autobuy=True):
    monkeypatch.setattr(investment_daily, "WebDashboard", Dashboard)
    cfg = Config(path, profile=profile, enabled=enabled, planning=planning,
                 summary_hour=summary_hour, settings=settings,
                 legacy_autobuy=legacy_autobuy)
    return SimpleNamespace(config=cfg, telegram=Client(*results), dry_run=dry_run)


def test_disabled_and_before_hour_do_not_write_or_send(monkeypatch, tmp_path):
    bot = prepare(monkeypatch, tmp_path, enabled=False)
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "disabled"
    bot.config.flags[("options", "telegram_investment_daily")] = True
    bot.config.summary_hour = 17
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "before_hour"
    assert bot.telegram.calls == []
    assert not list(tmp_path.glob("*.sqlite3"))


def test_once_per_day_survives_restart_and_reports_unknowns(monkeypatch, tmp_path):
    day = _timestamp()
    bot = prepare(monkeypatch, tmp_path, profile="filial", results=(True,))
    assert investment_daily.publish_investment_daily(bot, now=day) == "delivered"
    message = bot.telegram.calls[0]
    assert message.startswith("[filial] ")
    assert "Planejado" in message
    assert "Confirmado no diário" in message
    assert "sem comprovação independente" in message
    assert "pesquisa dos hubs sem cobertura comprovada" in message
    assert "planejamento de investimentos desligado" in message
    assert "executor de compras aguarda homologação G0" in message
    assert "diário da nova política de investimento" in message
    assert "Compra automática legada de aeronaves: ATIVA" in message
    assert "2 avaliadas, 0 elegíveis" in message

    restarted = prepare(monkeypatch, tmp_path, profile="filial", results=(True,))
    assert investment_daily.publish_investment_daily(restarted, now=day + 3600) == "suppressed"
    assert restarted.telegram.calls == []
    assert investment_daily.publish_investment_daily(restarted, now=_timestamp(24)) == "delivered"
    assert len(restarted.telegram.calls) == 1


@pytest.mark.parametrize("age,dry_run,visible", [(0, False, True), (901, False, False), (0, True, False)])
def test_daily_financial_history_and_portfolio_blockers(monkeypatch, tmp_path, age, dry_run, visible):
    from finance_observations import SOURCE

    now = _timestamp()
    bot = prepare(monkeypatch, tmp_path, planning=True, dry_run=dry_run)

    class ObservedDashboard(Dashboard):
        def hub_recommendations(self):
            report = super().hub_recommendations()
            report["portfolio"]["blocking_reasons"] = [
                "hangar_sem_vaga", "pedidos_pendentes_a_conciliar", "hangar_sem_vaga",
                "future_unknown_code",
            ]
            report["finance_observations"] = {
                "status": "observed", "source": SOURCE, "observed_at": now - age,
                "summary": {"window_hours": 24, "income": 1000, "expenses": 1500,
                            "result": -500, "fuel_expenses": 100, "quota_expenses": 50,
                            "route_fees": 200, "aircraft_orders": 900, "hubs": 0,
                            "ticket_income": 1000},
            }
            return report

    monkeypatch.setattr(investment_daily, "WebDashboard", ObservedDashboard)
    assert investment_daily.publish_investment_daily(bot, now=now) == "delivered"
    message = bot.telegram.calls[0]
    assert ("Histórico financeiro da companhia" in message) is visible
    assert ("resultado $-500" in message) is visible
    assert ("encomendas $900" in message) is visible
    assert ("sem conciliação dos pedidos ou compromissos futuros" in message) is visible
    assert "sem comprovação independente" in message
    assert message.count("hangar sem vaga") == 1
    assert "pedidos e compromissos a conciliar" in message
    assert "1 outro impedimento no planejador" in message
    assert "future_unknown_code" not in message


@pytest.mark.parametrize("age,dry_run,visible", [(10, False, True), (901, False, False), (10, True, False)])
def test_daily_audited_decision_is_current_and_separate(monkeypatch, tmp_path, age, dry_run, visible):
    now = _timestamp()
    bot = prepare(monkeypatch, tmp_path, dry_run=dry_run)
    snapshot = "sha256:" + "a" * 64
    calls = []

    class AuditedDashboard(Dashboard):
        def audited_expansion(self):
            calls.append(True)
            return {"profile_id": "principal", "read_only": True, "status": "registrado",
                    "snapshot_id": snapshot, "evaluation_count": 3,
                    "game_observation_snapshot": {"status": "parcial", "snapshot_id": snapshot,
                                                  "captured_at": now - age,
                                                  "scopes": {"hubs": True, "fleet": True, "routes": False,
                                                             "models": False, "engines": False, "prices": False}},
                    "portfolio": {"evaluated_count": 3, "eligible_count": 1,
                                  "decision": "sugestao_para_analise"},
                    "purchase_plan_blockers": ["private_unknown_code"]}

    monkeypatch.setattr(investment_daily, "WebDashboard", AuditedDashboard)
    assert investment_daily.publish_investment_daily(bot, now=now) == "delivered"
    message = bot.telegram.calls[0]
    assert ("3 cenários registrados, 1 candidatos A4; compra bloqueada" in message) is visible
    assert ("hubs, frota." in message) is visible
    assert "2 avaliadas, 0 elegíveis" in message
    assert "private_unknown_code" not in message
    assert len(calls) == (0 if dry_run else 1)


def test_send_failed_or_exception_can_retry_without_secret_in_log(monkeypatch, tmp_path, caplog):
    secret = "bot123456:private-telegram-token"
    bot = prepare(monkeypatch, tmp_path, results=(False, RuntimeError(secret), True))
    day = _timestamp()
    assert investment_daily.publish_investment_daily(bot, now=day) == "failed"
    with caplog.at_level(logging.WARNING, logger="am4bot.telegram"):
        assert investment_daily.publish_investment_daily(bot, now=day + 1) == "failed"
    assert secret not in caplog.text
    assert investment_daily.publish_investment_daily(bot, now=day + 2) == "delivered"
    assert investment_daily.publish_investment_daily(bot, now=day + 3) == "suppressed"
    assert len(bot.telegram.calls) == 3


def test_claims_are_isolated_by_profile_and_recover_after_stale_lease(tmp_path):
    db = investment_daily.DailyInvestmentDelivery(tmp_path / "delivery.sqlite3")
    token = db.claim("principal", "2026-11-23", now=1000)
    assert token is not None
    assert db.claim("principal", "2026-11-23", now=1001) is None
    other = db.claim("filial", "2026-11-23", now=1001)
    assert other is not None
    new_token = investment_daily.DailyInvestmentDelivery(db.path).claim(
        "principal", "2026-11-23", now=1301,
    )
    assert new_token and new_token != token
    # An expired worker cannot acknowledge someone else's claim.
    db.acknowledge("principal", "2026-11-23", token, delivered=True, now=1302)
    assert db.claim("principal", "2026-11-23", now=1303) is None
    db.acknowledge("principal", "2026-11-23", new_token, delivered=True, now=1304)
    assert db.claim("principal", "2026-11-23", now=9999) is None
    db.acknowledge("filial", "2026-11-23", other, delivered=False, now=1304)
    assert db.claim("filial", "2026-11-23", now=1305)


def test_simulation_is_labeled_and_does_not_use_game_journal(monkeypatch, tmp_path):
    bot = prepare(monkeypatch, tmp_path, dry_run=True, results=(True,))
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "delivered"
    assert "Ambiente: simulação" in bot.telegram.calls[0]
    assert "simulação ativa" in bot.telegram.calls[0]
    assert (tmp_path / "investment_simulation.sqlite3").exists()
    assert not (tmp_path / "investment_journal.sqlite3").exists()


def test_planned_commitment_from_game_journal_is_never_reported_as_actual_spend(
        monkeypatch, tmp_path):
    journal = InvestmentJournal(tmp_path / "investment_journal.sqlite3", profile_id="principal")
    intent, _ = journal.register({
        "plan_id": "plan-456", "snapshot_id": "sha256:" + "a" * 64,
        "kind": "aircraft", "hub_id": "123", "estimated_cost": 20000,
        "origin_id": "123", "destination_id": "456", "model_id": "A320", "engine_id": "motor-1",
    })
    assert journal.transition(intent["intent_key"], "PROPOSED", "APPROVED")
    bot = prepare(monkeypatch, tmp_path, results=(True,), summary_hour=0, planning=True)
    assert investment_daily.publish_investment_daily(bot, now=time.time() + 60) == "delivered"
    message = bot.telegram.calls[0]
    assert "1 novas intenções" in message
    assert "Compromissos previstos em aberto: $20,000" in message
    assert "Custo previsto desses pedidos: $0" in message
    assert "gasto efetivo, entregas e lucro real ainda sem comprovação" in message
    assert "modo de investimentos somente análise" in message
    assert "Compra automática legada de aeronaves: ATIVA" in message


def test_approval_mode_and_disabled_legacy_autobuyer_are_reported(monkeypatch, tmp_path):
    bot = prepare(
        monkeypatch, tmp_path, planning=True,
        settings={("investment", "mode"): "approval"}, legacy_autobuy=False,
    )
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "delivered"
    message = bot.telegram.calls[0]
    assert "aquisições dependem de aprovação" in message
    assert "executor de compras aguarda homologação G0" in message
    assert "Compra automática legada de aeronaves: desativada" in message


def test_autonomous_mode_reports_missing_spend_limits_and_unavailable_executor(
        monkeypatch, tmp_path):
    bot = prepare(
        monkeypatch, tmp_path, planning=True,
        settings={("investment", "mode"): "autonomous"},
    )
    bot.config.flags[("investment", "auto_buy_aircraft")] = True
    bot.config.flags[("investment", "auto_buy_hub")] = True
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "delivered"
    message = bot.telegram.calls[0]
    assert "limites de gasto da política autônoma não configurados" in message
    assert "executor de compras aguarda homologação G0" in message


def test_invalid_investment_policy_is_explicitly_reported(monkeypatch, tmp_path):
    bot = prepare(
        monkeypatch, tmp_path, planning=True,
        settings={("investment", "mode"): "unknown-mode"},
    )
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "delivered"
    assert "configuração da política de investimentos inválida" in bot.telegram.calls[0]


def test_unknown_source_is_reported_without_zero_coverage(monkeypatch, tmp_path):
    bot = prepare(monkeypatch, tmp_path, results=(True,))

    class UnavailableDashboard(Dashboard):
        def hub_recommendations(self):
            raise sqlite3.Error("banco indisponível")

    monkeypatch.setattr(investment_daily, "WebDashboard", UnavailableDashboard)
    assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "delivered"
    assert "hubs sem medição" in bot.telegram.calls[0]
    assert "Oportunidades: não comprovadas" in bot.telegram.calls[0]


def test_report_failure_releases_claim(monkeypatch, tmp_path, caplog):
    bot = prepare(monkeypatch, tmp_path, results=(True,))

    class BrokenDashboard(Dashboard):
        def hub_recommendations(self):
            raise RuntimeError("token-privado")

    monkeypatch.setattr(investment_daily, "WebDashboard", BrokenDashboard)
    with caplog.at_level(logging.WARNING, logger="am4bot.telegram"):
        assert investment_daily.publish_investment_daily(bot, now=_timestamp()) == "failed"
    assert "token-privado" not in caplog.text
    monkeypatch.setattr(investment_daily, "WebDashboard", Dashboard)
    assert investment_daily.publish_investment_daily(bot, now=_timestamp() + 1) == "delivered"
