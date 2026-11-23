"""Independent investment controls require authorization and preserve per-profile state."""
from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from config import AppConfig
from conftest import ROOT
from investment_policy import InvestmentPolicy
from web import WebDashboard
import web as web_module


TOKEN = "test-web-investment-token"
POLICY = {
    "planning_enabled": True,
    "mode": "autonomous",
    "auto_buy_aircraft": True,
    "auto_buy_hub": True,
    "max_single_investment": 100_000,
    "max_daily_spend": 250_000,
    "max_acquisitions_per_day": 3,
    "min_daily_profit": 1500,
    "max_payback_days": 730,
    "profit_weight": 20,
    "efficiency_weight": 40,
    "risk_weight": 20,
    "confidence_weight": 10,
    "diversification_weight": 10,
}


@contextmanager
def served(tmp_path):
    secrets = tmp_path / "secrets.ini"
    secrets.write_text(f"[web]\ntoken={TOKEN}\n", encoding="utf-8")
    config = AppConfig(
        settings_file=tmp_path / "settings.ini",
        secrets_file=secrets,
        defaults_file=ROOT / "config/defaults.ini",
    )
    dashboard = WebDashboard(object(), config, object(), start_bot=lambda: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard._handler())
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], config
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(port, method="GET", path="/api/investment/policy", payload=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(
            method, path,
            body=json.dumps(payload).encode("utf-8") if method == "POST" else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        response = connection.getresponse()
        status = response.status
        body = response.read().decode("utf-8")
        return status, json.loads(body) if body.startswith("{") else body
    finally:
        connection.close()


def auth():
    return {"X-Token": TOKEN, "X-AM4": "1"}


def test_policy_update_survives_reload_without_activating_legacy_or_execution(tmp_path):
    with served(tmp_path) as (port, config):
        status, initial = request(port, headers=auth())
        assert status == 200
        assert initial["policy"]["planning_enabled"] is False
        assert initial["policy"]["execution_available"] is False

        status, saved = request(port, "POST", payload={
            "policy": POLICY, "expected_version": initial["version"],
        }, headers=auth())
        assert status == 200 and saved["ok"] is True
        assert config.settings_file.exists()
        assert config.get_bool("options", "autobuy_aircraft") is True

        config.reload()
        status, current = request(port, headers={"Cookie": f"am4token={TOKEN}"})
        assert status == 200
        for key, value in POLICY.items():
            assert current["policy"][key] == value
        assert current["policy"]["execution_available"] is False
        assert current["policy"]["release_gate"] == "G0"
        assert InvestmentPolicy.from_config(config).auto_buy_hub is True


@pytest.mark.parametrize("invalid", [
    {"mode": []},
    {"mode": "unknown"},
    {"planning_enabled": "on"},
    {"max_single_investment": True},
    {"max_single_investment": -1},
    {"max_daily_spend": 1.5},
    {"max_daily_spend": 10**16},
    {"max_acquisitions_per_day": -1},
    {"max_acquisitions_per_day": 101},
    {"max_acquisitions_per_day": True},
    {"min_daily_profit": -100},
    {"max_payback_days": 3651},
    {"profit_weight": -1},
    {"efficiency_weight": 101},
    {"risk_weight": True},
    {"confidence_weight": 0.5},
    {"diversification_weight": 101},
    {"profit_weight": 0, "efficiency_weight": 0, "risk_weight": 0,
     "confidence_weight": 0, "diversification_weight": 0},
    {"extra": "unexpected"},
])
def test_invalid_payload_is_rejected_before_any_mutation(tmp_path, invalid):
    with served(tmp_path) as (port, config):
        version = config.version
        status, result = request(port, "POST", payload={
            "policy": {**POLICY, **invalid}, "expected_version": version,
        }, headers=auth())
        assert status == 400 and result["ok"] is False
        assert config.version == version
        assert config.get_bool("investment", "planning_enabled") is False


def test_stale_update_is_rejected_but_emergency_stop_always_succeeds(tmp_path):
    with served(tmp_path) as (port, config):
        revision = config.version
        assert request(port, "POST", payload={
            "policy": POLICY, "expected_version": revision,
        }, headers=auth())[0] == 200

        status, conflict = request(port, "POST", payload={
            "policy": {**POLICY, "auto_buy_hub": False}, "expected_version": revision,
        }, headers=auth())
        assert status == 400 and conflict["ok"] is False
        assert config.get_bool("investment", "auto_buy_hub") is True

        status, stopped = request(port, "POST", "/api/investment/stop", {}, auth())
        assert status == 200 and stopped["ok"] is True
        assert config.get_bool("investment", "planning_enabled") is False
        assert config.get_bool("investment", "auto_buy_aircraft") is False
        assert config.get_bool("investment", "auto_buy_hub") is False
        assert config.get_bool("options", "autobuy_aircraft") is False


@pytest.mark.parametrize("headers,path", [
    ({"X-AM4": "1"}, "/api/investment/policy"),
    ({"X-Token": "wrong", "X-AM4": "1"}, "/api/investment/policy"),
    ({"X-Token": TOKEN}, "/api/investment/policy"),
    ({"X-AM4": "1"}, "/api/investment/policy?token=" + TOKEN),
    ({"X-AM4": "1"}, "/api/investment/stop?token=" + TOKEN),
])
def test_policy_mutations_require_authenticated_header_without_query_token(tmp_path, headers, path):
    with served(tmp_path) as (port, config):
        status, _ = request(port, "POST", path, {"policy": POLICY}, headers)
        assert status == 403
        assert config.get_bool("investment", "planning_enabled") is False


def test_stop_does_not_accept_payload(tmp_path):
    with served(tmp_path) as (port, config):
        status, response = request(port, "POST", "/api/investment/stop", {"planning_enabled": True}, auth())
        assert status == 400 and response["ok"] is False
        assert config.get_bool("investment", "planning_enabled") is False


def test_recommendations_use_saved_weights_and_reject_unverified_dimensions(tmp_path, monkeypatch):
    with served(tmp_path) as (_, config):
        config.set("investment", "planning_enabled", "on")
        config.set("investment", "profit_weight", 0)
        config.set("investment", "efficiency_weight", 0)
        config.set("investment", "risk_weight", 100)

        class EmptySource:
            def snapshot(self, *args, **kwargs):
                return {}

        class EmptyJournal:
            def unresolved(self):
                return {"intents": [], "count": 0, "estimated_exposure": 0}

        candidate = {
            "hub_id": "123", "route_key": "ids:123|456", "model": "A320",
            "engine_id": "1", "origin": {"id": "123"}, "destination": {"id": "456"},
            "investment": 1000, "profit_per_day": 100,
            "status": "viavel", "pending": [],
        }
        monkeypatch.setattr(web_module, "HubRegistry", EmptySource)
        monkeypatch.setattr(web_module, "HubAircraftResearchRegistry", EmptySource)
        monkeypatch.setattr(web_module, "InvestmentJournal", EmptyJournal)
        monkeypatch.setattr(web_module, "recent_verified_money", lambda *args: (10000, 1800000000))
        monkeypatch.setattr(web_module, "load_state", lambda: {})
        monkeypatch.setattr(web_module, "rank_next_aircraft", lambda *args, **kwargs: {
            "candidates": [candidate], "partial_fleet": False, "available_cash": 10000,
        })
        dashboard = WebDashboard(object(), config, object(), start_bot=lambda: None)
        monkeypatch.setattr(dashboard, "routes", lambda: {})

        risk_report = dashboard.hub_recommendations()["portfolio"]
        assert risk_report["criteria"]["risk_weight"] == 100
        assert risk_report["best"] is None
        assert risk_report["missing_ranking_evidence"] == {"risk": 1}

        config.set("investment", "risk_weight", 0)
        config.set("investment", "profit_weight", 60)
        config.set("investment", "efficiency_weight", 40)
        safe_report = dashboard.hub_recommendations()["portfolio"]
        assert safe_report["criteria"]["profit_weight"] == 60
        assert safe_report["best"]["hub_id"] == "123"
        assert safe_report["execution_available"] is False

        config.set("investment", "max_acquisitions_per_day", "invalido")
        invalid_report = dashboard.hub_recommendations()["portfolio"]
        assert invalid_report["status"] == "inconclusivo"
        assert "politica_invalida" in invalid_report["blocking_reasons"]


def test_local_journal_reservations_reduce_candidate_budget(tmp_path, monkeypatch):
    with served(tmp_path) as (_, config):
        class EmptySource:
            def snapshot(self, *args, **kwargs):
                return {}

        class ReservedJournal:
            def unresolved(self):
                return {"intents": [], "count": 1, "estimated_exposure": 9000}

        monkeypatch.setattr(web_module, "HubRegistry", EmptySource)
        monkeypatch.setattr(web_module, "HubAircraftResearchRegistry", EmptySource)
        monkeypatch.setattr(web_module, "InvestmentJournal", ReservedJournal)
        monkeypatch.setattr(web_module, "recent_verified_money", lambda *args: (10000, 1800000000))
        monkeypatch.setattr(web_module, "load_state", lambda: {})
        monkeypatch.setattr(web_module, "rank_next_aircraft", lambda *args, **kwargs: {
            "partial_fleet": False, "available_cash": 10000,
            "candidates": [{"hub_id": "123", "route_key": "ids:123|456", "model": "A320",
                            "engine_id": "1", "origin": {"id": "123"},
                            "destination": {"id": "456"}, "investment": 2000,
                            "profit_per_day": 100, "status": "viavel", "pending": []}],
        })
        dashboard = WebDashboard(object(), config, object(), start_bot=lambda: None)
        monkeypatch.setattr(dashboard, "routes", lambda: {})

        result = dashboard.hub_recommendations()["portfolio"]
        assert result["known_local_commitments"] == 9000
        assert result["budget_upper_bound"] == 1000
        assert result["best"] is None
        assert result["excluded"]["caixa_apos_reservas_locais_insuficiente"] == 1
