"""HTTP contract for the native demand dashboard."""

from __future__ import annotations

import http.client
import json
import shutil
import sqlite3
import subprocess
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, call

import pytest

from config import AppConfig
from conftest import ROOT
from web import WebDashboard


STATUS_PATH = "/api/research/demand"
REQUEST_PATH = "/api/research/demand/request"
TOKEN = "test-native-demand-token"
TOKEN_HEADER = {"X-Token": TOKEN}
TOKEN_COOKIE = {"Cookie": f"am4token={TOKEN}"}
ACTION_HEADER = {"X-AM4": "1"}
ACTION_AUTH = {**TOKEN_HEADER, **ACTION_HEADER}
CONFIRMED = {"confirm": True}
PENDING = {
    "state": "pending", "processed_partitions": 0, "total_partitions": 0,
    "observed_pairs": 0, "searched_pairs": 0, "expected_pairs": 0, "updated_at": None, "error": None,
}


@pytest.fixture
def store_factory(monkeypatch):
    factory = Mock(return_value=Mock(spec_set=["status", "request", "lookup"]))
    monkeypatch.setattr("web.DemandStore", factory)
    return factory


@contextmanager
def served(tmp_path, token=TOKEN):
    secrets = tmp_path / "secrets.ini"
    secrets.write_text(f"[web]\ntoken={token}\n", encoding="utf-8")
    config = AppConfig(
        settings_file=tmp_path / "settings.ini",
        secrets_file=secrets,
        defaults_file=ROOT / "config/defaults.ini",
    )
    worker = Mock()
    dashboard = WebDashboard(worker, config, object(), start_bot=worker.start)
    with ThreadingHTTPServer(("127.0.0.1", 0), dashboard._handler()) as server:
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True,
        )
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=3)
    assert worker.mock_calls == []


def request(port, method, path, *, payload=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(
            method, path,
            body=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body.startswith("{") else body
    finally:
        connection.close()


def test_demand_status_returns_raw_store_data_without_queuing(tmp_path, store_factory):
    store = store_factory.return_value
    report = {
        "state": "partial", "processed_partitions": 3, "total_partitions": 10,
        "observed_pairs": 60, "searched_pairs": 75, "expected_pairs": 200, "updated_at": 1795709093.0,
        "error": "Partição indisponível.",
    }
    store.status.return_value = report

    with served(tmp_path) as port:
        assert request(port, "GET", STATUS_PATH)[0] == 403
        store_factory.assert_not_called()

        assert request(port, "GET", STATUS_PATH, headers=TOKEN_HEADER) == (200, report)
        assert request(port, "GET", STATUS_PATH, headers=TOKEN_COOKIE) == (200, report)
        assert request(port, "GET", f"{STATUS_PATH}?token={TOKEN}") == (200, report)

    assert store.mock_calls == [call.status()] * 3


def test_demand_lookup_is_authenticated_read_only_and_directional(tmp_path, store_factory):
    store = store_factory.return_value
    observation = {"origin_id": "1440", "destination_id": "432", "y": 1341, "source": "game_route_search"}
    store.lookup.side_effect = [observation, None]
    query = f"{STATUS_PATH}?origin_id=1440&destination_id=432"

    with served(tmp_path) as port:
        assert request(port, "GET", query)[0] == 403
        store_factory.assert_not_called()
        assert request(port, "GET", query, headers=TOKEN_HEADER) == (200, {"observation": observation})
        assert request(port, "GET", f"{STATUS_PATH}?destination_id=1440&origin_id=432", headers=TOKEN_HEADER) == (
            200, {"observation": None},
        )

    assert store.mock_calls == [call.lookup("1440", "432"), call.lookup("432", "1440")]


@pytest.mark.parametrize("query", [
    "origin_id=1440", "destination_id=432", "origin_id=&destination_id=432", "origin_id=GRU&destination_id=432",
    "origin_id=0&destination_id=432", "origin_id=1440&origin_id=1441&destination_id=432",
    "origin_id=1440&destination_id=1440", "origin_id=1440&destination_id=1234567890123",
])
def test_demand_lookup_requires_two_distinct_valid_native_ids(tmp_path, store_factory, query):
    with served(tmp_path) as port:
        assert request(port, "GET", f"{STATUS_PATH}?{query}", headers=TOKEN_HEADER)[0] == 400
    store_factory.assert_not_called()


def test_demand_request_returns_queued_and_already_queued_results(tmp_path, store_factory):
    store = store_factory.return_value
    store.request.side_effect = [True, False]

    with served(tmp_path) as port:
        status, result = request(
            port, "POST", REQUEST_PATH, payload=CONFIRMED, headers=ACTION_AUTH,
        )
        assert (status, result) == (200, {"queued": True})
        assert result["queued"] is True

        status, result = request(
            port, "POST", f"{REQUEST_PATH}?token=wrong", payload=CONFIRMED,
            headers={**TOKEN_COOKIE, **ACTION_HEADER},
        )
        assert (status, result) == (200, {"queued": False})
        assert result["queued"] is False

    assert store.mock_calls == [call.request(), call.request()]


@pytest.mark.parametrize("payload", [
    None, {}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1},
    {"confirm": [True]}, {"confirm": {"value": True}}, {"confirm": True, "extra": 1},
])
def test_demand_request_rejects_invalid_confirmation(tmp_path, store_factory, payload):
    with served(tmp_path) as port:
        status, _ = request(port, "POST", REQUEST_PATH, payload=payload, headers=ACTION_AUTH)

    assert status == 400
    store_factory.assert_not_called()


@pytest.mark.parametrize("headers,path", [
    (ACTION_HEADER, REQUEST_PATH),
    ({**ACTION_HEADER, "X-Token": "wrong"}, REQUEST_PATH),
    (TOKEN_HEADER, REQUEST_PATH),
    ({**TOKEN_COOKIE, "X-AM4": "true"}, REQUEST_PATH),
    (ACTION_HEADER, f"{REQUEST_PATH}?token={TOKEN}"),
])
def test_demand_request_requires_action_header_and_header_or_cookie_token(
    tmp_path, store_factory, headers, path,
):
    with served(tmp_path) as port:
        status, _ = request(port, "POST", path, payload=CONFIRMED, headers=headers)

    assert status == 403
    store_factory.assert_not_called()


def test_demand_endpoints_without_token_require_loopback_host(tmp_path, store_factory):
    store = store_factory.return_value
    store.status.return_value = PENDING
    store.request.return_value = True
    remote_host = {"Host": "dashboard.example"}

    with served(tmp_path, token="") as port:
        assert request(port, "GET", STATUS_PATH, headers=remote_host)[0] == 403
        assert request(
            port, "POST", REQUEST_PATH, payload=CONFIRMED, headers={**remote_host, **ACTION_HEADER},
        )[0] == 403
        assert request(port, "POST", REQUEST_PATH, payload=CONFIRMED)[0] == 403
        store_factory.assert_not_called()

        assert request(port, "GET", STATUS_PATH) == (200, PENDING)
        assert request(port, "POST", REQUEST_PATH, payload=CONFIRMED, headers=ACTION_HEADER) == (
            200, {"queued": True},
        )

    assert store.mock_calls == [call.status(), call.request()]


def test_demand_endpoints_return_unavailable_when_store_is_busy(tmp_path, store_factory):
    store = store_factory.return_value
    store.status.side_effect = sqlite3.OperationalError("database is locked")
    store.request.side_effect = sqlite3.OperationalError("database is locked")

    with served(tmp_path) as port:
        assert request(port, "GET", STATUS_PATH, headers=TOKEN_HEADER)[0] == 503
        assert request(
            port, "POST", REQUEST_PATH, payload=CONFIRMED, headers=ACTION_AUTH,
        )[0] == 503


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_demand_dashboard_consent_and_status_without_browser(tmp_path):
    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    api = page[page.index("async function api("):page.index("// ------------------------------------------------------------------ status tiles")]
    state = page[page.index("const nativeDemandPath ="):page.index('window.addEventListener("hashchange"')]
    ui = page[page.index("function renderNativeDemand("):page.index("async function loadInvestmentPolicy(")]
    harness = r"""
const assert = require("node:assert/strict");
const elements = new Map();
const $ = id => {
  if (!elements.has(id)) {
    elements.set(id, {
      addEventListener(name, listener) { this[name] = listener; },
      removeAttribute(name) { delete this[name]; },
    });
  }
  return elements.get(id);
};
const tr = (text, value) => value === undefined ? text : text.replace("{x}", value);
const nf = new Intl.NumberFormat("pt-BR");
const hubDate = () => "data da coleta";
let confirmed = false;
const window = {confirm: () => confirmed};
const requests = [];
let report = {state: "pending", processed_partitions: 0, total_partitions: 10,
                observed_pairs: 0, searched_pairs: 0, expected_pairs: 100, updated_at: null, error: null};
async function fetch(path, options) {
  requests.push([path, options]);
  if (options.method === "POST") {
    if (report.state === "pending") { report = {...report, state: "queued"}; }
    return {ok: true, json: async () => ({queued: report.state === "queued"})};
  }
  return {ok: true, json: async () => report};
}
"""
    checks = r"""
(async () => {
  const button = $("nativeDemandRequest");
  const warning = $("nativeDemandWarning");
  const progress = $("nativeDemandProgress");
  const status = $("nativeDemandStatus");
  await loadNativeDemand();
  assert.equal(warning.hidden, false);
  assert.equal(button.disabled, false);
  await button.click();
  assert.deepEqual(requests, [["/api/research/demand", {}]]);

  confirmed = true;
  await button.click();
  assert.deepEqual(requests.slice(1).map(([path]) => path),
    ["/api/research/demand/request", "/api/research/demand"]);
  assert.equal(requests[1][1].method, "POST");
  assert.equal(requests[1][1].headers["X-AM4"], "1");
  assert.deepEqual(JSON.parse(requests[1][1].body), {confirm: true});
  assert.match(status.textContent, /Na fila/);
  assert.equal(button.hidden, true);

  report = {...report, state: "running", processed_partitions: 3, searched_pairs: 30, observed_pairs: 25, updated_at: 42};
  await loadNativeDemand();
  assert.equal(progress.hidden, false);
  assert.equal($("nativeDemandBar").value, 3);
  assert.equal($("nativeDemandBar").max, 10);
  assert.match(status.textContent, /30 \/ 100 pares pesquisados/);
  assert.match(status.textContent, /25 com demanda observada/);
  assert.match(status.textContent, /data da coleta/);

  report = {...report, state: "partial", error: "Partição indisponível."};
  await loadNativeDemand();
  assert.equal(progress.hidden, true);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, "Retomar varredura");
  assert.match(status.textContent, /Partição indisponível/);

  report = {...report, state: "completed", error: null};
  await loadNativeDemand();
  assert.equal(warning.hidden, true);
  assert.equal(button.textContent, "Solicitar nova varredura");
  await button.click();  // false from the store still triggers a fresh GET
  assert.deepEqual(requests.slice(-2).map(([path]) => path),
    ["/api/research/demand/request", "/api/research/demand"]);
  assert.match(status.textContent, /Varredura concluída/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    script = tmp_path / "native-demand.cjs"
    script.write_text("\n".join((harness, api, state, ui, checks)), encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, encoding="utf-8", check=False, timeout=10)
    assert result.returncode == 0, result.stderr
