"""Authenticated, read-only HTTP access to the active game's DOM probe."""
from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from bot import BotState
from game_source_probe import _sanitize
from web import WebDashboard


ENDPOINT = "/api/admin/game-source-probe"
HISTORY_ENDPOINT = "/api/admin/flight-history-probe"
QUOTE_ENDPOINT = "/api/admin/aircraft-order-preview"
TOKEN = "web-admin-secret"


class FakeBot:
    def __init__(self):
        self.state = BotState.RUNNING
        self.driver = object()
        self.alive = True
        self.logged_in = True
        self.error = None
        self.probe_calls = 0
        self.history_calls = []
        self.login_checks = 0
        self.busy = False
        self.timed_out = False

    def is_alive(self):
        return self.alive

    def _is_logged_in(self, timeout):
        assert timeout == 0
        self.login_checks += 1
        return self.logged_in

    def request_game_source_probe(self):
        if self.busy or not self.alive or self.driver is None or self.state != BotState.RUNNING:
            return "busy", None
        if self.timed_out:
            return "timeout", None
        if not self._is_logged_in(timeout=0):
            return "unavailable", None
        self.probe_calls += 1
        if self.error:
            raise RuntimeError(self.error)
        raw = {
            "schema_version": 1,
            "sources": {
                "owned_hub_options": {
                    "count": 3,
                    "numeric_ids": ["123", "alice@example.com", "456"],
                    "numeric_id_count": 3,
                    "attribute_presence": {"value": True, "cookie": True},
                    "raw_html": "<html>top-secret</html>",
                },
            },
            "status_data": {"present": True, "count": 1, "cookie": "secret-session"},
            "pagination": {"current_page": 2, "total_pages": 4, "raw": "session-token"},
            "credentials": {"password": "unwanted-password"},
        }
        return "ok", _sanitize(raw)

    def request_flight_history_probe(self, aircraft_id):
        if self.busy or not self.alive or self.driver is None or self.state != BotState.RUNNING:
            return "busy", None
        if self.timed_out:
            return "timeout", None
        if not self._is_logged_in(timeout=0):
            return "unavailable", None
        self.history_calls.append(aircraft_id)
        if self.error:
            raise RuntimeError(self.error)
        return "ok", {"schema_version": 1, "aircraft_id": aircraft_id, "status": "inspected",
                      "row_count": 2, "read_only": True, "complete_history_verified": False,
                      "financial_ledger_verified": False}


@contextmanager
def served(bot, token=TOKEN):
    dashboard = WebDashboard(
        bot, SimpleNamespace(web_token=token), object(), start_bot=lambda: None
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard._handler())
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], dashboard
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(port, method="POST", path=ENDPOINT, headers=None, body=b"{}"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, body=body if method == "POST" else None,
                           headers={"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        status = response.status
        raw = response.read().decode("utf-8")
        return status, raw
    finally:
        connection.close()


def authorized(**extra):
    return {"X-Token": TOKEN, "X-AM4": "1", **extra}


def test_aircraft_order_preview_requires_header_token_and_exact_quote_payload():
    bot = FakeBot()
    calls = []

    def preview(request):
        calls.append(request)
        return "ok", {"status": "matched", "read_only": True, "execution_available": False}

    bot.request_aircraft_order_preview = preview
    quote = {"model_id": "12", "delivery_hub_id": "24323457", "engine_id": "23",
             "configuration_yjf": {"y": 3, "j": 0, "f": 0}, "expected_checkout_cost": 51000}
    body = json.dumps(quote).encode()
    with served(bot) as (port, _):
        assert request(port, path=QUOTE_ENDPOINT + "?token=" + TOKEN,
                       headers={"X-AM4": "1"}, body=body)[0] == 403
        assert request(port, path=QUOTE_ENDPOINT, headers={"X-Token": TOKEN}, body=body)[0] == 403
        for change in ({"submit": True}, {"engine_id": "23&submit=1"}, {"expected_checkout_cost": True},
                       {"configuration_yjf": {"y": 0, "j": 0, "f": 0}}):
            invalid_body = json.dumps({**quote, **change}).encode()
            assert request(port, path=QUOTE_ENDPOINT, headers=authorized(), body=invalid_body)[0] == 400
        assert not calls
        status, raw = request(port, path=QUOTE_ENDPOINT, headers=authorized(), body=body)

    assert status == 200 and json.loads(raw)["report"]["execution_available"] is False
    assert len(calls) == 1 and calls[0].seats == (3, 0, 0)


def test_admin_probe_returns_only_sanitized_data_from_existing_bot():
    bot = FakeBot()
    with served(bot) as (port, _):
        status, raw = request(port, headers=authorized())

    assert status == 200
    payload = json.loads(raw)
    assert payload["ok"] is True
    report = payload["report"]
    assert report["schema_version"] == 1
    assert report["sources"]["owned_hub_options"]["numeric_ids"] == ["123", "456"]
    assert report["pagination"]["current_page"] == 2
    assert report["pagination"]["total_pages"] == 4
    assert report["pagination"]["evidence_conflict"] is False
    for forbidden in ("raw_html", "credentials", "top-secret", "password", "session-token",
                      "alice@example.com", "secret-session"):
        assert forbidden not in raw
    assert bot.login_checks == 1
    assert bot.probe_calls == 1


@pytest.mark.parametrize("headers,path", [
    ({"X-AM4": "1"}, ENDPOINT),
    ({"X-Token": "wrong", "X-AM4": "1"}, ENDPOINT),
    ({"X-Token": TOKEN}, ENDPOINT),
    ({"X-AM4": "1"}, ENDPOINT + "?token=" + TOKEN),
])
def test_admin_probe_rejects_invalid_authorization(headers, path):
    bot = FakeBot()
    with served(bot) as (port, _):
        status, _ = request(port, path=path, headers=headers)
    assert status == 403
    assert bot.probe_calls == 0
    assert bot.login_checks == 0


def test_admin_probe_requires_configured_token_even_on_loopback():
    bot = FakeBot()
    with served(bot, token="") as (port, _):
        status, _ = request(port, headers=authorized())
    assert status == 403
    assert bot.probe_calls == 0


def test_admin_probe_allows_existing_authenticated_cookie():
    bot = FakeBot()
    with served(bot) as (port, _):
        status, raw = request(port, headers={"X-AM4": "1", "Cookie": "am4token=" + TOKEN})
    assert status == 200
    assert json.loads(raw)["ok"] is True
    assert bot.probe_calls == 1


@pytest.mark.parametrize("changes", [
    {"alive": False},
    {"driver": None},
    {"state": BotState.LOGGING_IN},
    {"logged_in": False},
])
def test_admin_probe_requires_running_authenticated_game(changes):
    bot = FakeBot()
    for attribute, value in changes.items():
        setattr(bot, attribute, value)
    with served(bot) as (port, _):
        status, raw = request(port, headers=authorized())
    assert status == (503 if changes.get("logged_in") is False else 409)
    assert json.loads(raw)["ok"] is False
    assert bot.probe_calls == 0


def test_admin_probe_exposes_no_driver_error_or_traceback(caplog):
    bot = FakeBot()
    bot.error = "session_id=secret-cookie; password=highly-secret"
    with served(bot) as (port, _):
        status, raw = request(port, headers=authorized())
    assert status == 503
    assert json.loads(raw)["ok"] is False
    assert "secret-cookie" not in raw + caplog.text
    assert "highly-secret" not in raw + caplog.text
    assert "Traceback" not in raw


def test_admin_probe_rejects_payload_and_get_without_touching_game():
    bot = FakeBot()
    with served(bot) as (port, _):
        invalid, _ = request(port, headers=authorized(), body=b'{"password":"secret"}')
        get_status, _ = request(port, method="GET", headers=authorized())
    assert invalid == 400
    assert get_status == 404
    assert bot.probe_calls == 0


def test_admin_probe_prevents_overlapping_snapshots():
    bot = FakeBot()
    bot.busy = True
    with served(bot) as (port, _):
        status, raw = request(port, headers=authorized())
    assert status == 409
    assert json.loads(raw)["ok"] is False
    assert bot.probe_calls == 0


def test_admin_probe_returns_gateway_timeout_without_session_data():
    bot = FakeBot()
    bot.timed_out = True
    with served(bot) as (port, _):
        status, raw = request(port, headers=authorized())
    assert status == 504
    assert json.loads(raw)["ok"] is False
    assert bot.probe_calls == 0


def test_history_probe_requires_token_and_valid_single_aircraft_id():
    bot = FakeBot()
    with served(bot) as (port, _):
        for headers in ({"X-AM4": "1"}, {"X-Token": TOKEN}):
            status, _ = request(port, path=HISTORY_ENDPOINT, headers=headers,
                                body=b'{"aircraft_id":"42"}')
            assert status == 403
        status, _ = request(port, path=HISTORY_ENDPOINT + "?token=" + TOKEN,
                            headers={"X-AM4": "1"}, body=b'{"aircraft_id":"42"}')
        assert status == 403
        for invalid in (b'{}', b'{"aircraft_id":42}', b'{"aircraft_id":"0"}',
                        b'{"aircraft_id":"42?token=secret"}',
                        b'{"aircraft_id":"42","session":"secret"}'):
            status, _ = request(port, path=HISTORY_ENDPOINT, headers=authorized(), body=invalid)
            assert status == 400
        status, raw = request(port, path=HISTORY_ENDPOINT, headers=authorized(),
                              body=b'{"aircraft_id":"42"}')
    assert status == 200
    assert json.loads(raw)["report"]["aircraft_id"] == "42"
    assert bot.history_calls == ["42"]
    assert bot.probe_calls == 0


@pytest.mark.parametrize("changes,expected", [
    ({"busy": True}, 409),
    ({"alive": False}, 409),
    ({"logged_in": False}, 503),
    ({"timed_out": True}, 504),
    ({"error": "session=secret-cookie"}, 503),
])
def test_history_probe_is_fail_closed_and_does_not_leak_driver_data(changes, expected, caplog):
    bot = FakeBot()
    for attribute, value in changes.items():
        setattr(bot, attribute, value)
    with served(bot) as (port, _):
        status, raw = request(port, path=HISTORY_ENDPOINT, headers=authorized(),
                              body=b'{"aircraft_id":"42"}')
    assert status == expected
    assert json.loads(raw)["ok"] is False
    assert "secret-cookie" not in raw + caplog.text
    assert not bot.history_calls or "error" in changes
