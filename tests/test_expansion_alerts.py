"""The A6 cycle uses verified reporting and acknowledges real delivery."""
from __future__ import annotations

from types import SimpleNamespace

import expansion_alerts
from notify import Telegram


class Config:
    def __init__(self, data, *, profile="principal", planning=True, expansion=True,
                 telegram=True):
        self.profile = SimpleNamespace(label=profile, is_main=profile == "principal", data=data)
        self.flags = {("investment", "planning_enabled"): planning,
                      ("options", "telegram_expansion"): expansion,
                      ("options", "telegram"): telegram}

    def get_bool(self, section, key, fallback=False):
        return self.flags.get((section, key), fallback)


class Client:
    enabled = True

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def send_now(self, text):
        self.calls.append(text)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return (result, "confirmado por mock")


def prepare_alerts(monkeypatch, tmp_path, *, config=None, results=(True,)):
    config = config or Config(tmp_path)
    bot = SimpleNamespace(config=config, telegram=Client(*results))
    evidence = {"inventory": {"partial_fleet": True, "hubs": []},
                "research": {"portfolio": {"status": "inconclusivo"}},
                "external": {"catalog_complete": False, "candidates": [],
                             "planning_snapshot_id": "sha256:" + "a" * 64}}

    class FakeDashboard:
        def __init__(self, supplied_bot, supplied_config, buffer):
            assert supplied_bot is bot and supplied_config is config and buffer is None

        def hubs(self):
            return evidence["inventory"]

        def hub_recommendations(self):
            return evidence["research"]

        def hub_expansion(self, *, owned_inventory, owned_research):
            assert owned_inventory is evidence["inventory"]
            assert owned_research is evidence["research"]
            return evidence["external"]

    monkeypatch.setattr(expansion_alerts, "WebDashboard", FakeDashboard)
    return bot, evidence


def test_default_disabled_does_not_read_or_send(monkeypatch, tmp_path):
    bot, _ = prepare_alerts(monkeypatch, tmp_path, config=Config(tmp_path, expansion=False))
    assert expansion_alerts.publish_expansion_alert(bot) == "disabled"
    assert bot.telegram.calls == []
    assert not list(tmp_path.glob("*.sqlite3"))


def test_real_incomplete_coverage_suppresses_alert(monkeypatch, tmp_path):
    bot, _ = prepare_alerts(monkeypatch, tmp_path)
    assert expansion_alerts.publish_expansion_alert(bot) == "inconclusivo"
    assert bot.telegram.calls == []
    assert not list(tmp_path.glob("*.sqlite3"))


def test_missing_productive_capture_never_sends_alert(monkeypatch, tmp_path):
    bot, evidence = prepare_alerts(monkeypatch, tmp_path)
    evidence["external"].pop("planning_snapshot_id")
    assert expansion_alerts.publish_expansion_alert(bot) == "inconclusivo"
    assert bot.telegram.calls == []
    assert not list(tmp_path.glob("*.sqlite3"))


def test_delivery_acknowledged_once_per_profile_and_material_change(monkeypatch, tmp_path):
    bot, evidence = prepare_alerts(monkeypatch, tmp_path, config=Config(tmp_path, profile="filial"),
                          results=(True, True))
    observed_ids = []

    def proven_report(*args, **kwargs):
        observed_ids.append(kwargs["snapshot_id"])
        assert kwargs["profile_id"] == "filial"
        assert kwargs["owned_inventory"] is evidence["inventory"]
        assert kwargs["require_snapshot_scope"] is True
        return {"profile_id": "filial", "snapshot_id": kwargs["snapshot_id"],
                "alertable": True, "html": "<b>Candidato testado</b>",
                "material": {"status": evidence["external"].get("status", "primeiro"),
                             "candidates": []}}

    monkeypatch.setattr(expansion_alerts, "build_expansion_report", proven_report)
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    assert expansion_alerts.publish_expansion_alert(bot) == "suppressed"
    assert bot.telegram.calls == ["[filial] <b>Candidato testado</b>"]
    evidence["external"]["status"] = "atualizado"
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    assert "Atualização relevante" in bot.telegram.calls[-1]
    assert observed_ids[0] == observed_ids[1]
    assert observed_ids[2] == observed_ids[1] == evidence["external"]["planning_snapshot_id"]
    assert all(item.startswith("sha256:") and len(item) == 71 for item in observed_ids)


def test_failure_releases_claim_for_retry(monkeypatch, tmp_path):
    bot, _ = prepare_alerts(monkeypatch, tmp_path, results=(False, True))

    def proven_report(*args, **kwargs):
        return {"profile_id": "principal", "snapshot_id": kwargs["snapshot_id"],
                "alertable": True, "html": "Expansão segura",
                "material": {"status": "ready", "candidates": []}}

    monkeypatch.setattr(expansion_alerts, "build_expansion_report", proven_report)
    assert expansion_alerts.publish_expansion_alert(bot) == "failed"
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    assert expansion_alerts.publish_expansion_alert(bot) == "suppressed"
    assert bot.telegram.calls == ["Expansão segura", "Expansão segura"]


def test_send_exception_releases_claim_for_retry_without_leaking_secrets(
        monkeypatch, tmp_path, caplog):
    secret = "bot123456:telegram-secret"
    bot, _ = prepare_alerts(
        monkeypatch, tmp_path,
        results=(RuntimeError(f"https://api.telegram.org/{secret}/sendMessage"), True),
    )

    def proven_report(*args, **kwargs):
        return {"profile_id": "principal", "snapshot_id": kwargs["snapshot_id"],
                "alertable": True, "html": "Expansão segura",
                "material": {"status": "ready", "candidates": []}}

    monkeypatch.setattr(expansion_alerts, "build_expansion_report", proven_report)
    with caplog.at_level("WARNING", logger="am4bot.telegram"):
        assert expansion_alerts.publish_expansion_alert(bot) == "failed"
    assert "Exceção no envio" in caplog.text
    assert secret not in caplog.text
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    assert expansion_alerts.publish_expansion_alert(bot) == "suppressed"
    assert bot.telegram.calls == ["Expansão segura", "Expansão segura"]


def test_material_change_send_exception_preserves_prefix_on_retry(monkeypatch, tmp_path):
    bot, evidence = prepare_alerts(
        monkeypatch, tmp_path,
        results=(True, ConnectionError("falha temporária"), True),
    )

    def proven_report(*args, **kwargs):
        return {"profile_id": "principal", "snapshot_id": kwargs["snapshot_id"],
                "alertable": True, "html": "Expansão segura",
                "material": {"status": evidence["external"].get("status", "primeiro"),
                             "candidates": []}}

    monkeypatch.setattr(expansion_alerts, "build_expansion_report", proven_report)
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    evidence["external"]["status"] = "atualizado"
    assert expansion_alerts.publish_expansion_alert(bot) == "failed"
    assert bot.telegram.calls[1].startswith("<b>Atualização relevante na expansão</b>\n")
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    assert bot.telegram.calls[2] == bot.telegram.calls[1]
    assert expansion_alerts.publish_expansion_alert(bot) == "suppressed"
    assert len(bot.telegram.calls) == 3


def test_changed_long_report_is_not_truncated_or_acknowledged(monkeypatch, tmp_path):
    bot, evidence = prepare_alerts(
        monkeypatch, tmp_path, config=Config(tmp_path, profile="f" * 80),
    )

    def proven_report(*args, **kwargs):
        return {"profile_id": kwargs["profile_id"], "snapshot_id": kwargs["snapshot_id"],
                "alertable": True, "html": "A" * 3900,
                "material": {"status": evidence["external"].get("status", "primeiro"),
                             "candidates": []}}

    monkeypatch.setattr(expansion_alerts, "build_expansion_report", proven_report)
    assert expansion_alerts.publish_expansion_alert(bot) == "delivered"
    evidence["external"]["status"] = "atualizado"
    assert expansion_alerts.publish_expansion_alert(bot) == "oversized"
    assert expansion_alerts.publish_expansion_alert(bot) == "oversized"
    assert len(bot.telegram.calls) == 1


def test_send_now_preserves_legacy_default_silent_false(monkeypatch):
    client = Telegram("fake-token", "fake-chat")
    sent = []
    monkeypatch.setattr(client, "_post", lambda message, silent: (sent.append((message, silent)) or
                                                                 (True, "enviado")))
    assert client.send_now("mensagem") == (True, "enviado")
    assert client.send_now("silenciosa", silent=True) == (True, "enviado")
    assert sent == [("mensagem", False), ("silenciosa", True)]
