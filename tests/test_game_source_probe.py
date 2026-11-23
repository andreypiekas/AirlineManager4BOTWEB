"""Sanitized game-source probe, including real JavaScript execution with a fake DOM."""

import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from game_source_probe import (
    FLIGHT_HISTORY_PROBE_JS,
    PROBE_JS,
    SAMPLE_LIMIT,
    probe_flight_history_structure,
    probe_game_sources,
)


def test_running_bot_is_read_once_and_untrusted_fields_are_removed():
    secret = "PASSWORD_TOKEN_PRIVATE_HTML"

    class Bot:
        def __init__(self):
            self.scripts = []

        def js(self, script):
            self.scripts.append(script)
            return {
                "schema_version": 1,
                "sources": {
                    "owned_hub_options": {
                        "count": 3,
                        "numeric_ids": ["123", "123", "456", "garbage", "9" * 40],
                        "numeric_id_count": 2,
                        "attribute_presence": {"value": True, "title": "present",
                                               "onclick": secret},
                        "raw_html": secret,
                        "selector": secret,
                    },
                    "fleet_routes": {
                        "count": 1,
                        "linked_aircraft_ids": ["24133209", secret],
                        "linked_aircraft_id_count": 1,
                    },
                    "custom_source": {"token": secret},
                },
                "status_data": {"present": True, "count": 4, "numeric_ids": ["999", secret],
                                "numeric_id_count": 1, "cookie": secret},
                "user": secret,
            }

        def open_popup(self, *_args):
            raise AssertionError("The probe must not navigate")

        def ajax(self, *_args):
            raise AssertionError("The probe must not request a game resource")

    bot = Bot()
    report = probe_game_sources(bot)

    assert bot.scripts == [PROBE_JS]
    assert report["sources"]["owned_hub_options"]["numeric_ids"] == ["123", "456"]
    assert report["sources"]["owned_hub_options"]["numeric_id_count"] == 2
    assert report["sources"]["owned_hub_options"]["attribute_presence"]["title"] is False
    assert report["sources"]["owned_hub_options"]["attribute_presence"]["value"] is True
    assert report["sources"]["fleet_routes"]["linked_aircraft_ids"] == ["24133209"]
    assert report["aircraft_order_hub_selection"]["selected_hub_id"] is None
    assert report["aircraft_order_hub_selection"]["status"] == "unverified"
    assert report["status_data"]["numeric_ids"] == ["999"]
    assert report["sources"]["owned_hub_options"]["id_parseable_nodes"] is None
    assert "custom_source" not in report["sources"]
    assert secret not in json.dumps(report)


def test_existing_selenium_driver_and_wrapped_driver_are_supported():
    class Driver:
        def __init__(self):
            self.scripts = []

        def execute_script(self, script):
            self.scripts.append(script)
            return {"schema_version": 1, "sources": {}, "status_data": {}}

    direct = Driver()
    assert probe_game_sources(direct)["schema_version"] == 1
    wrapped = type("Session", (), {"driver": Driver()})()
    assert probe_game_sources(wrapped)["sources"]["aircraft_catalog"]["count"] == 0
    assert direct.scripts == [PROBE_JS]
    assert wrapped.driver.scripts == [PROBE_JS]


def test_existing_bot_js_entrypoint_works_with_driver_without_game_login():
    from bot import Bot

    class Driver:
        def __init__(self):
            self.calls = []

        def execute_script(self, script):
            self.calls.append(script)
            return {"schema_version": 1, "sources": {}, "pagination": {
                "current_page": 2, "total_pages": 4}, "status_data": {}}

    bot = Bot.__new__(Bot)
    bot.driver = Driver()
    report = probe_game_sources(bot)
    assert report["pagination"]["current_page"] == 2
    assert report["pagination"]["total_pages"] == 4
    assert report["pagination"]["evidence_conflict"] is False
    assert not any(report["pagination"]["evidence"].values())
    assert bot.driver.calls == [PROBE_JS]


def test_bad_session_or_driver_response_fails_explicitly():
    with pytest.raises(TypeError, match="existing Bot or Selenium"):
        probe_game_sources(object())
    with pytest.raises(ValueError, match="Unexpected DOM probe"):
        probe_game_sources(type("Bot", (), {"js": lambda self, _: "raw html"})())
    with pytest.raises(ValueError, match="Unexpected DOM probe"):
        probe_game_sources(type("Bot", (), {"js": lambda self, _: {
            "schema_version": True, "sources": {}}})())


@pytest.mark.parametrize("invalid", ["0", "-1", "12?token=secret", "1" * 15, " 42", True, None])
def test_history_probe_rejects_invalid_ids_before_accessing_session(invalid):
    class Driver:
        def execute_async_script(self, *_):
            pytest.fail("Invalid IDs must never trigger an HTTP request")

    with pytest.raises(ValueError, match="numeric aircraft ID"):
        probe_flight_history_structure(Driver(), invalid)


def test_history_probe_requires_async_driver_and_uses_existing_session():
    with pytest.raises(TypeError, match="async session"):
        probe_flight_history_structure(object(), "42")

    class Driver:
        def __init__(self):
            self.calls = []

        def execute_async_script(self, script, aircraft_id):
            self.calls.append((script, aircraft_id))
            return {
                "schema_version": 1, "aircraft_id": aircraft_id,
                "status": "missing_history", "history_present": False,
                "secret": "TOKEN_SHOULD_NOT_LEAK",
            }

    driver = Driver()
    session = type("Session", (), {"driver": driver})()
    report = probe_flight_history_structure(session, 42)
    assert driver.calls == [(FLIGHT_HISTORY_PROBE_JS, "42")]
    assert report["status"] == "missing_history"
    assert report["row_count"] == 0
    assert report["flight_identity_verified"] is False
    assert report["complete_history_verified"] is False
    assert report["financial_ledger_verified"] is False
    assert "TOKEN_" not in json.dumps(report)


def test_history_probe_sanitizes_hostile_counts_and_unverified_claims():
    from game_source_probe import _sanitize_flight_history

    secret = "SECRET_TOKEN_PASSWORD"
    raw = {
        "schema_version": 1, "aircraft_id": "456", "status": "inspected",
        "history_present": True, "row_count": 3, "four_column_rows": 999,
        "numeric_cost_rows": True, "currency_revenue_rows": 4,
        "id_candidates": {
            "data_flight_id": {"rows": 3, "distinct": 2, "duplicates": 0,
                               "id_values": [secret]},
            "data_id": {"rows": 1000, "distinct": 999},
            "foreign_candidate": {"rows": 2, "secret": secret},
        },
        "absolute_time_sources": {"time_datetime": True, "data_timestamp": 100,
                                  "external": secret},
        "pagination_controls_present": True,
        "flight_identity_verified": True, "complete_history_verified": True,
        "financial_ledger_verified": True, "raw_html": secret,
    }
    cleaned = _sanitize_flight_history(raw, "456")
    assert cleaned["four_column_rows"] == 3
    assert cleaned["numeric_cost_rows"] == 0
    assert cleaned["currency_revenue_rows"] == 3
    assert cleaned["id_candidates"]["data_flight_id"] == {
        "rows": 3, "distinct": 2, "duplicates": 1,
    }
    assert cleaned["id_candidates"]["data_id"]["distinct"] == 3
    assert cleaned["absolute_time_sources"] == {
        "time_datetime": 0, "data_completed_at": 0, "data_timestamp": 3,
    }
    assert cleaned["pagination_controls_present"] is True
    assert cleaned["flight_identity_verified"] is False
    assert cleaned["complete_history_verified"] is False
    assert cleaned["financial_ledger_verified"] is False
    assert secret not in json.dumps(cleaned)
    with pytest.raises(ValueError, match="Unexpected flight-history"):
        _sanitize_flight_history({**raw, "aircraft_id": "789"}, "456")
    with pytest.raises(ValueError, match="Unexpected flight-history"):
        _sanitize_flight_history({**raw, "schema_version": True}, "456")


@pytest.mark.parametrize("scenario,expected_status", [
    ("history", "inspected"),
    ("twenty", "inspected"),
    ("missing", "missing_history"),
    ("http_error", "http_error"),
    ("fetch_error", "fetch_error"),
    ("timeout", "timeout"),
])
def test_history_probe_executes_read_only_get_and_limits_output(
        tmp_path, scenario, expected_status):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to validate the history probe")

    mock = r"""
const scenario = SCENARIO;
const secret = 'PRIVATE_PASSWORD_TOKEN_999';
const node = (attrs = {}, text = '', query = {}) => ({
  textContent: text,
  getAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
  querySelector: selector => query[selector] || null,
  querySelectorAll: selector => query[selector] || [],
});
const createRow = (number, duplicate = false) => {
  const attrs = {
    'data-flight-id': duplicate ? '1001' : String(1001 + number),
    'data-id': String(2001 + number),
    'id': String(3001 + number),
    'data-completed-at': '2026-11-22T10:00:00-03:00',
    'data-timestamp': '2026-11-22 10:00:00',
  };
  const time = node({datetime: number === 1 ? 'yesterday' : '2026-11-22T13:00:00Z'});
  const cells = [node({}, 'route ' + secret), node({}, '123 CO2'),
                 node({}, '456 fuel'), node({}, '$ 1,250 ' + secret)];
  return node(attrs, secret, {'time[datetime]': time, ':scope > .col-3': cells});
};
const rows = scenario === 'twenty' ?
  Array.from({length: 20}, (_, i) => createRow(i)) :
  [createRow(0), createRow(1, true), createRow(2)];
class DOMParser {
  parseFromString() {
    return {querySelectorAll: selector => {
      if (selector === '#flight-history') return scenario === 'missing' ? [] : [node()];
      if (selector === '#flight-history > .row') return rows;
      if (selector === '#flight-history .pagination, #flight-history [data-page]') {
        return scenario === 'twenty' ? [node()] : [];
      }
      return [];
    }};
  }
}
globalThis.DOMParser = DOMParser;
globalThis.fetch = async (url, options) => {
  if (url !== 'fleet_details.php?id=456' || options.credentials !== 'same-origin' ||
      !options.signal) throw Error('unexpected request');
  if (scenario === 'fetch_error') throw Error('network failure');
  if (scenario === 'timeout') throw {name: 'AbortError'};
  return {ok: scenario !== 'http_error', text: async () => '<html>' + secret + '</html>'};
};
const run = (script, aircraftId) => new Promise(resolve => {
  new Function(script)(aircraftId, resolve);
});
run(PROBE, '456').then(value => console.log(JSON.stringify(value)));
""".replace("SCENARIO", json.dumps(scenario)).replace(
        "PROBE", json.dumps(FLIGHT_HISTORY_PROBE_JS))
    source = tmp_path / "history_probe.js"
    source.write_text(mock, encoding="utf-8")
    output = subprocess.run(["node", str(source)], capture_output=True, text=True, timeout=15)
    assert output.returncode == 0, output.stderr
    assert "PRIVATE_" not in output.stdout
    assert "1250" not in output.stdout
    from game_source_probe import _sanitize_flight_history

    report = _sanitize_flight_history(json.loads(output.stdout), "456")
    assert report["status"] == expected_status
    if scenario in ("history", "twenty"):
        expected_count = 20 if scenario == "twenty" else 3
        assert report["row_count"] == expected_count
        assert report["four_column_rows"] == expected_count
        assert report["numeric_cost_rows"] == expected_count
        assert report["currency_revenue_rows"] == expected_count
        assert report["absolute_time_sources"]["data_completed_at"] == expected_count
        assert report["absolute_time_sources"]["data_timestamp"] == 0
        assert report["absolute_time_sources"]["time_datetime"] == expected_count - 1
        assert report["id_candidates"]["data_flight_id"]["duplicates"] == (
            1 if scenario == "history" else 0)
        assert report["possible_truncation"] is (scenario == "twenty")
        assert report["pagination_controls_present"] is (scenario == "twenty")
    else:
        assert report["row_count"] == 0
        assert not report["history_present"]
    assert report["read_only"] is True
    assert report["flight_identity_verified"] is False


def test_counts_are_bounded_and_boolean_fields_reject_strings():
    class Bot:
        def js(self, _script):
            return {"schema_version": 1, "sources": {
                "aircraft_catalog": {
                    "count": -1,
                    "numeric_id_count": True,
                    "numeric_ids": ["1", "2", "abc", "1"],
                    "attribute_presence": {"onclick": "true", "data-price": 1},
                }},
                "status_data": {"present": "true", "count": 10**20, "numeric_ids": []}}

    report = probe_game_sources(Bot())
    catalog = report["sources"]["aircraft_catalog"]
    assert catalog["count"] == 0
    assert catalog["numeric_ids"] == ["1", "2"]
    assert catalog["numeric_id_count"] == 2
    assert catalog["attribute_presence"]["onclick"] is False
    assert catalog["attribute_presence"]["data-price"] is False
    assert report["status_data"]["present"] is False
    assert report["status_data"]["count"] == 0


def test_checkout_diagnostics_reject_untrusted_values_and_never_verify_price():
    from game_source_probe import _sanitize

    secret = "SECRET_PASSWORD_COOKIE_123"
    report = _sanitize({
        "schema_version": 1,
        "aircraft_checkout_diagnostics": {
            "detail_panel_count": 2,
            "detail_model_id": "123",
            "controls": {"all_selects": True, "all_radios": 2,
                         "purchase_buttons": 10**30, "injected": secret},
            "price_candidates": {
                "data_price": {"count": 1, "currency_text_nodes": 999,
                               "numeric_price_attribute_nodes": 2,
                               "text": secret, "amount": 3000000},
                "id_price": {"count": -1, "currency_text_nodes": True},
                "unknown": {"count": 10, "value": secret},
            },
            "price_verified": True,
            "raw_html": secret,
        },
    })
    checkout = report["aircraft_checkout_diagnostics"]
    assert checkout["detail_model_id"] is None
    assert checkout["controls"]["all_selects"] == 0
    assert checkout["controls"]["all_radios"] == 2
    assert checkout["controls"]["purchase_buttons"] == 0
    assert "injected" not in checkout["controls"]
    assert checkout["price_candidates"]["data_price"]["count"] == 1
    assert checkout["price_candidates"]["data_price"]["currency_text_nodes"] == 1
    assert checkout["price_candidates"]["data_price"]["numeric_price_attribute_nodes"] == 1
    assert checkout["price_candidates"]["id_price"]["count"] == 0
    assert "unknown" not in checkout["price_candidates"]
    assert checkout["price_verified"] is False
    assert checkout["read_only"] is True
    assert secret not in json.dumps(report)


def test_checkout_diagnostics_dom_probe_identifies_price_shapes_without_values(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to validate checkout DOM diagnostics")

    mock = r"""
const secret = 'SECRET_PASSWORD_TOKEN';
const node = (attrs = {}, content = '') => ({
  textContent: content,
  getAttribute: key => Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : null,
  hasAttribute: key => Object.prototype.hasOwnProperty.call(attrs, key),
});
const priceNode = node({'data-price':'3500000'}, 'US$ 3,500,000 ' + secret);
const finalNode = node({'data-final-price':secret}, 'USD 4,000,000 ' + secret);
const identity = node({'data-model-id':'785'}, secret);
const elements = {
  '#acModel': [identity],
  '#acModel select': [node(), node()],
  "#acModel input[type='radio']": [node()],
  "#acModel select[name*='engine' i], #acModel select[id*='engine' i], #acModel select[name*='motor' i], #acModel select[id*='motor' i]": [node()],
  "#acModel input[type='radio'][name*='engine' i], #acModel input[type='radio'][name*='motor' i]": [node()],
  '#acModel #btnPurchaseIntro': [node()],
  '#acModel #accountLow': [node()],
  '#acModel [data-price]': [priceNode],
  '#acModel [data-final-price]': [finalNode],
  "#acModel [id*='price' i]": [priceNode, finalNode],
};
globalThis.document = {querySelectorAll: selector => elements[selector] || []};
globalThis.window = {statusData: null};
"""
    path = tmp_path / "checkout_probe.js"
    path.write_text(mock + "\nconsole.log(JSON.stringify((new Function(" +
                    json.dumps(PROBE_JS) + "))()));\n", encoding="utf-8")
    response = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert response.returncode == 0, response.stderr
    assert "SECRET_" not in response.stdout
    assert "3500000" not in response.stdout
    assert "4000000" not in response.stdout
    from game_source_probe import _sanitize

    checkout = _sanitize(json.loads(response.stdout))["aircraft_checkout_diagnostics"]
    assert checkout["detail_panel_count"] == 1
    assert checkout["detail_model_id"] == "785"
    assert checkout["controls"] == {
        "all_selects": 2, "all_radios": 1, "engine_named_selects": 1,
        "engine_named_radios": 1, "purchase_buttons": 1,
        "insufficient_balance_warnings": 1,
    }
    assert checkout["price_candidates"]["data_price"] == {
        "selector": "#acModel [data-price]", "count": 1,
        "currency_text_nodes": 1, "numeric_price_attribute_nodes": 1,
    }
    assert checkout["price_candidates"]["data_final_price"][
        "numeric_price_attribute_nodes"] == 0
    assert checkout["price_candidates"]["id_price"]["count"] == 2
    assert checkout["price_candidates"]["id_price"]["currency_text_nodes"] == 2
    assert checkout["price_verified"] is False


@pytest.mark.parametrize("case,correlated", [
    ("same_panel", True),
    ("hub_outside_panel", False),
    ("ajax_in_progress", False),
    ("ajax_state_unavailable", False),
    ("ajax_state_invalid", False),
    ("nested_loader", False),
    ("panel_busy", False),
    ("duplicate_model_panels", False),
    ("invalid_model_id", False),
    ("hub_option_unselected", False),
])
def test_checkout_model_hub_correlation_requires_one_idle_panel(
        tmp_path, case, correlated):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to validate live checkout correlation")

    fixture = json.dumps({"case": case})
    js = r"""
const fixture = FIXTURE;
const makeNode = (attrs = {}, state = {}) => ({
  id: attrs.id || '',
  textContent: '',
  value: state.value || '',
  selected: state.selected === true,
  disabled: false,
  getAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
  hasAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name),
});
const hub = makeNode({id: 'hubSelection'}, {value: '456'});
const option = makeNode({value: '456'}, {value: '456',
  selected: fixture.case !== 'hub_option_unselected'});
const panelAttrs = {'data-model-id': fixture.case === 'invalid_model_id' ? 'invalid' : '785'};
if (fixture.case === 'panel_busy') panelAttrs['aria-busy'] = 'true';
const panel = makeNode(panelAttrs);
panel.contains = node => fixture.case !== 'hub_outside_panel' && node === hub;
panel.querySelector = () => fixture.case === 'nested_loader' ? {} : null;
const panels = fixture.case === 'duplicate_model_panels' ? [panel, makeNode(panelAttrs)] : [panel];
const nodes = {
  '#acModel': panels,
  '#hubSelection': [hub],
  '#hubSelection option': [option],
};
globalThis.document = {querySelectorAll: selector => nodes[selector] || []};
globalThis.window = {statusData: null};
if (fixture.case !== 'ajax_state_unavailable') {
  window.jQuery = {active: fixture.case === 'ajax_in_progress' ? 1 :
    fixture.case === 'ajax_state_invalid' ? '0' : 0};
}
console.log(JSON.stringify((new Function(PROBE))()));
""".replace("FIXTURE", fixture).replace("PROBE", json.dumps(PROBE_JS))
    path = tmp_path / "checkout_context.js"
    path.write_text(js, encoding="utf-8")
    response = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert response.returncode == 0, response.stderr

    from game_source_probe import _sanitize

    report = _sanitize(json.loads(response.stdout))
    checkout = report["aircraft_checkout_diagnostics"]
    assert checkout["model_hub_correlated"] is correlated
    assert checkout["ajax_active"] is (case == "ajax_in_progress")
    assert checkout["ajax_idle_confirmed"] is (
        case not in ("ajax_in_progress", "ajax_state_unavailable", "ajax_state_invalid"))
    assert checkout["detail_loading"] is (case in ("nested_loader", "panel_busy"))
    assert checkout["price_verified"] is False
    assert checkout["read_only"] is True
    if case == "hub_outside_panel":
        # A consistent hub dropdown can still belong to an unrelated pane.
        assert report["aircraft_order_hub_selection"]["status"] == "dom_consistent"
        assert checkout["detail_model_id"] == "785"


@pytest.mark.parametrize("overrides,expected", [
    ({}, True),
    ({"detail_model_id": "not_an_id"}, False),
    ({"detail_panel_count": 2}, False),
    ({"ajax_active": True}, False),
    ({"ajax_idle_confirmed": False}, False),
    ({"ajax_idle_confirmed": "true"}, False),
    ({"detail_loading": True}, False),
    ({"ajax_active": "false"}, False),
    ({"detail_loading": "false"}, False),
    ({"model_hub_correlated": "true"}, False),
])
def test_checkout_correlation_rejects_contradictory_or_untyped_evidence(overrides, expected):
    from game_source_probe import _sanitize

    checkout = {"detail_panel_count": 1, "detail_model_id": "785",
                "model_hub_correlated": True, "ajax_active": False,
                "ajax_idle_confirmed": True,
                "detail_loading": False, **overrides}
    report = _sanitize({
        "schema_version": 1,
        "aircraft_order_hub_selection": {
            "selector_count": 1, "option_count": 1,
            "selected_option_count": 1, "selected_hub_id": "456",
            "status": "dom_consistent",
        },
        "aircraft_checkout_diagnostics": checkout,
    })
    assert report["aircraft_checkout_diagnostics"]["model_hub_correlated"] is expected
    assert report["aircraft_checkout_diagnostics"]["price_verified"] is False


def test_malicious_response_cannot_inject_page_values_or_secrets():
    secret = "PASSWORD_COOKIE_TOKEN"

    class Bot:
        def js(self, _script):
            return {"schema_version": 1,
                    "sources": {"fleet_routes": {
                        "linked_aircraft_ids": [secret] * 45 + ["42", "43"],
                        "linked_aircraft_id_count": 60,
                        "numeric_ids": [secret] * 43 + ["77", "78"],
                        "numeric_id_count": 53,
                        "id_parseable_nodes": secret,
                        "pagination": {"raw": secret}}},
                    "pagination": {"current_page": secret, "total_pages": True,
                                   "evidence_conflict": secret, "raw": secret,
                                   "evidence": {"popup_present": "true",
                                                "active_page_numeric": True,
                                                "secret": secret}},
                    "status_data": {"numeric_ids": [secret, "7"]},
                    "aircraft_order_hub_selection": {
                        "selector_count": 1, "option_count": 1,
                        "selected_option_count": 1, "selected_hub_id": secret,
                        "status": "dom_consistent", "cookie": secret},
                    "secret": secret}

    report = probe_game_sources(Bot())
    assert report["pagination"]["current_page"] is None
    assert report["pagination"]["total_pages"] is None
    assert report["pagination"]["evidence_conflict"] is False
    assert report["pagination"]["evidence"]["popup_present"] is False
    assert report["pagination"]["evidence"]["active_page_numeric"] is True
    assert "secret" not in report["pagination"]["evidence"]
    assert report["sources"]["fleet_routes"]["id_parseable_nodes"] is None
    assert report["sources"]["fleet_routes"]["linked_aircraft_ids"] == ["42", "43"]
    assert report["sources"]["fleet_routes"]["linked_aircraft_ids_truncated"] is True
    assert report["sources"]["fleet_routes"]["numeric_ids"] == ["77", "78"]
    assert report["aircraft_order_hub_selection"]["status"] == "unverified"
    assert report["aircraft_order_hub_selection"]["selected_hub_id"] is None
    assert secret not in json.dumps(report)


@pytest.mark.parametrize("source,expected", [
    ({"selector_count": 1, "option_count": 3, "selected_option_count": 1,
      "selected_hub_id": "456", "status": "dom_consistent"}, "456"),
    ({"selector_count": 2, "option_count": 3, "selected_option_count": 1,
      "selected_hub_id": "456", "status": "dom_consistent"}, None),
    ({"selector_count": 1, "option_count": 3, "selected_option_count": 2,
      "selected_hub_id": "456", "status": "dom_consistent"}, None),
    ({"selector_count": 1, "option_count": 3, "selected_option_count": 1,
      "selected_hub_id": "true", "status": "dom_consistent"}, None),
])
def test_order_hub_selection_requires_one_consistent_numeric_option(source, expected):
    from game_source_probe import _sanitize

    report = _sanitize({"schema_version": 1, "aircraft_order_hub_selection": source})
    selection = report["aircraft_order_hub_selection"]
    assert selection["selected_hub_id"] == expected
    assert selection["status"] == ("dom_consistent" if expected else "unverified")
    assert selection["read_only"] is True


@pytest.mark.parametrize("selectors,options,expected_status,expected_id", [
    ([{"value": "456"}], [{"value": "456", "selected": True}],
     "dom_consistent", "456"),
    # The selected HTML attribute can be stale; the current DOM property wins.
    ([{"value": "456"}], [
        {"value": "123", "selected": False, "attr_selected": True},
        {"value": "456", "selected": True}], "dom_consistent", "456"),
    ([{"value": "456"}], [
        {"value": "123", "selected": True, "attr_selected": True},
        {"value": "456", "selected": False}], "unverified", None),
    ([{"value": "456"}], [
        {"value": "456", "selected": True},
        {"value": "456", "selected": False}], "unverified", None),
    ([{"value": "456", "disabled": True}], [
        {"value": "456", "selected": True}], "disabled", None),
    ([{"value": "456"}], [
        {"value": "456", "selected": True, "disabled": True}], "unverified", None),
    ([{"value": "456"}, {"value": "456"}], [
        {"value": "456", "selected": True}], "ambiguous", None),
    ([{"value": "456"}], [
        {"value": "456", "selected": False}], "unverified", None),
    ([], [], "missing", None),
])
def test_order_hub_live_dom_requires_unambiguous_selection(
        tmp_path, selectors, options, expected_status, expected_id):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")

    # The mock distinguishes the live .selected property from the stale HTML
    # attribute, which cannot be trusted for the current checkout selection.
    fixture = json.dumps({"selectors": selectors, "options": options})
    js = """
const fixture = FIXTURE;
const makeNode = item => ({
  id: '',
  value: item.value,
  selected: item.selected === true,
  disabled: item.disabled === true,
  textContent: '',
  hasAttribute: name => name === 'value' ||
    (name === 'selected' && item.attr_selected === true),
  getAttribute: name => name === 'value' ? item.value : null,
});
const elements = {
  '#hubSelection': fixture.selectors.map(makeNode),
  '#hubSelection option': fixture.options.map(makeNode),
};
globalThis.document = {querySelectorAll: selector => elements[selector] || []};
globalThis.window = {statusData: null};
console.log(JSON.stringify((new Function(PROBE))()));
""".replace("FIXTURE", fixture).replace("PROBE", json.dumps(PROBE_JS))
    path = tmp_path / "hub_selection.js"
    path.write_text(js, encoding="utf-8")
    response = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert response.returncode == 0, response.stderr
    from game_source_probe import _sanitize

    selection = _sanitize(json.loads(response.stdout))["aircraft_order_hub_selection"]
    assert selection["status"] == expected_status
    assert selection["selected_hub_id"] == expected_id
    assert selection["read_only"] is True


def test_embedded_dom_probe_returns_only_allowlisted_metadata(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")

    mock = r"""
function node(attrs = {}, options = {}) {
  const entry = {
    id: attrs.id || '',
    value: attrs.value || '',
    selected: options.selected === true,
    disabled: options.disabled === true,
    textContent: options.text || '',
    getAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
    hasAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name),
    querySelector: selector => selector === "a[onclick*='fleet_details.php']" ?
      (options.link || null) : null,
  };
  return Object.freeze(entry);
}
const sourceNodes = {
  '#popContent': [node({'data-current-page': '2', 'data-total-pages': '4'})],
  '#hubSelect': [node({id: 'hubSelect'})],
  '#hubSelect option': [
    node({value: '0', title: 'SECRET_PASSWORD'}),
    node({value: '123', 'data-iata': 'XAP', title: 'SECRET_TOKEN'}),
    node({value: '456', 'data-code': 'GRU'}),
  ],
  '#hubcountrySelector': [node({id: 'hubcountrySelector'})],
  '#hubcountrySelector option': [node({value: 'BR'}), node({value: 'US'})],
  '#hubAirportSelector': [node({id: 'hubAirportSelector'})],
  '#hubAirportSelector option': [node({value: '0'}), node({value: '2941'}), node({value: '2957'})],
  '#hubCostInfo': [node({id: 'hubCostInfo'}, {text: 'SECRET_TOKEN'})],
  '#airportInfo': [node({id: 'airportInfo'}, {text: 'SECRET_PASSWORD'})],
  '#hubList > .row[onclick]': [node({onclick: 'hub_details.php?id=2941&token=SECRET_TOKEN'})],
  '#hubSelection': [node({id: 'hubSelection', value: '456'})],
  '#hubSelection option': [node({value: '456', selected: 'selected'}, {selected: true})],
  '#acListItems .acListItem': [
    node({'data-price': '1900', 'data-range': '4700',
          onclick: "Ajax('ac_orders.php?mode=detail&id=785&token=SECRET_TOKEN')"}),
    node({'data-price': 'SECRET_TOKEN', 'data-id': '0',
          onclick: "Ajax('ac_orders.php?mode=detail&id=786&token=SECRET_TOKEN')"}),
  ],
  "#popContent [id^='routeMainList']": [
    node({id: 'routeMainList36562620', 'data-dep': '123'}, {
      link: node({onclick: "Ajax('fleet_details.php?id=24133209&password=SECRET_PASSWORD')"})
    }),
  ],
  "#routesContainer [id^='routeMainParkedList']": [
    node({id: 'routeMainParkedList24133209'}),
  ],
  '#popContent [data-home-hub-id]': [node({'data-home-hub-id': '123'})],
  '#popContent [data-aircraft-id]': [node({'data-aircraft-id': '24133209'})],
  '#resResult #list .sorter': [
    node({onclick: "Ajax('research_main.php?arr=789&password=SECRET_PASSWORD')",
          'data-distance': '3000'}),
  ],
  '#popContent .pagination': [node({'data-total-pages': '4'})],
  "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link": [
    node({'aria-current': 'page'}, {text: '2'}),
  ],
};
globalThis.document = Object.freeze({
  querySelectorAll: selector => sourceNodes[selector] || [],
});
globalThis.window = Object.freeze({
  statusData: {'24133209': {secret: 'SECRET_PASSWORD'},
               '24133210': {token: 'SECRET_TOKEN'},
               'username': {data: 'SECRET_USERNAME'}, '0': {}}
});
"""
    probe_js = tmp_path / "probe.js"
    probe_js.write_text(mock + "\nconsole.log(JSON.stringify((new Function(" +
                        json.dumps(PROBE_JS) + "))()));\n", encoding="utf-8")
    result = subprocess.run(["node", str(probe_js)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    raw = json.loads(result.stdout)
    assert "SECRET_" not in result.stdout
    assert raw["sources"]["owned_hub_options"]["numeric_ids"] == ["123", "456"]
    assert raw["sources"]["owned_hub_options"]["count"] == 3
    assert raw["sources"]["owned_hub_options"]["id_parseable_nodes"] == 2
    assert raw["sources"]["owned_hub_options"]["attribute_presence"]["data-iata"] is True
    assert raw["sources"]["purchase_hub_options"]["numeric_ids"] == ["2941", "2957"]
    assert raw["sources"]["purchase_hub_countries"]["count"] == 2
    assert raw["sources"]["purchase_hub_cost"]["count"] == 1
    assert raw["sources"]["purchase_hub_airport_info"]["count"] == 1
    assert raw["sources"]["acquired_hub_rows"]["count"] == 1
    assert raw["sources"]["aircraft_order_hub_options"]["numeric_ids"] == ["456"]
    assert raw["aircraft_order_hub_selection"] == {
        "selector_count": 1, "option_count": 1, "selected_option_count": 1,
        "selected_hub_id": "456", "status": "dom_consistent",
    }
    assert raw["sources"]["aircraft_catalog"]["numeric_ids"] == ["785", "786"]
    assert raw["sources"]["fleet_routes"]["numeric_ids"] == ["36562620"]
    assert raw["sources"]["fleet_routes"]["linked_aircraft_ids"] == ["24133209"]
    assert raw["sources"]["fleet_parked"]["numeric_ids"] == ["24133209"]
    assert raw["sources"]["fleet_home_hub_attributes"]["numeric_ids"] == ["123"]
    assert raw["sources"]["research_results"]["numeric_ids"] == ["789"]
    assert raw["sources"]["routes_active_page"]["numeric_ids"] == ["2"]
    assert raw["sources"]["fleet_popup"]["count"] == 1
    assert raw["pagination"]["current_page"] == 2
    assert raw["pagination"]["total_pages"] == 4
    assert raw["pagination"]["evidence_conflict"] is False
    assert raw["pagination"]["evidence"] == {
        "popup_present": True,
        "pagination_present": True,
        "active_page_present": True,
        "current_page_attribute_numeric": True,
        "active_page_numeric": True,
        "total_pages_attribute_numeric": True,
        "total_pages_route_count_numeric": False,
        "loading_indicator_present": False,
    }
    assert raw["status_data"]["count"] == 4
    assert raw["status_data"]["numeric_ids"] == ["24133209", "24133210"]


def test_dom_probe_caps_numeric_id_samples(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")
    js = ("globalThis.document = {querySelectorAll: () => []};\n"
          "globalThis.window = {statusData: Object.fromEntries("
          "Array.from({length: 65}, (_, i) => [String(i + 1), {}]))};\n"
          "console.log(JSON.stringify((new Function(" + json.dumps(PROBE_JS) + "))()));\n")
    path = tmp_path / "many_ids.js"
    path.write_text(js, encoding="utf-8")
    response = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert response.returncode == 0, response.stderr
    status = json.loads(response.stdout)["status_data"]
    assert status["numeric_id_count"] == 65
    assert len(status["numeric_ids"]) == SAMPLE_LIMIT
    assert status["ids_truncated"] is True


def test_real_am4_pager_derives_total_from_route_count(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to validate the real AM4 pager shape")

    mock = r"""
function node(attrs = {}, text = '') {
  return {
    textContent: text,
    getAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
    hasAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name),
    querySelector: () => null,
  };
}
const elements = {
  '#popContent': [node()],
  '#popContent .pagination': [node()],
  "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link": [node({}, '2')],
  '#popContent .row.font-weight-bold > .col-12.exo.text-center.p-2': [node({}, '205 Routes')],
};
globalThis.document = {querySelectorAll: selector => elements[selector] || []};
globalThis.window = {statusData: null};
"""
    path = tmp_path / "real_pager.js"
    path.write_text(mock + "\nconsole.log(JSON.stringify((new Function(" +
                    json.dumps(PROBE_JS) + "))()));\n", encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    pagination = json.loads(result.stdout)["pagination"]
    assert pagination["current_page"] == 2
    assert pagination["total_pages"] == 11
    assert pagination["evidence_conflict"] is False
    assert pagination["evidence"]["active_page_numeric"] is True
    assert pagination["evidence"]["total_pages_route_count_numeric"] is True


def test_dom_probe_identifies_conflicting_pagination_without_leaking_text(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")

    mock = r"""
function node(attrs = {}, text = '') {
  return {
    textContent: text,
    getAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
    hasAttribute: name => Object.prototype.hasOwnProperty.call(attrs, name),
  };
}
const elements = {
  '#popContent': [node({'data-current-page': '4', 'data-total-pages': '4'})],
  '#popContent .pagination': [node({'data-total-pages': '3'})],
  "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link": [
    node({'data-page': '2'}, 'secret_password_abc'),
  ],
};
globalThis.document = {querySelectorAll: selector => elements[selector] || []};
globalThis.window = {statusData: null};
"""
    path = tmp_path / "conflicting_pages.js"
    path.write_text(mock + "\nconsole.log(JSON.stringify((new Function(" +
                    json.dumps(PROBE_JS) + "))()));\n", encoding="utf-8")
    response = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert response.returncode == 0, response.stderr
    assert "secret_password" not in response.stdout
    report = json.loads(response.stdout)
    assert report["pagination"]["current_page"] is None
    assert report["pagination"]["total_pages"] is None
    assert report["pagination"]["evidence_conflict"] is True
    assert report["pagination"]["evidence"]["active_page_numeric"] is True
    assert report["sources"]["routes_active_page"]["numeric_ids"] == ["2"]


def test_static_game_html_fixture_requires_explicit_hub_ids_and_reports_loader(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")

    # Fragment shaped like the known 2026-11-17 AM4 route-list HTML. An option
    # without value gets its text as the implicit .value in real browsers.
    html = """
    <div id="popContent" data-current-page="2" data-total-pages="4">
      <nav class="pagination" data-total-pages="4">
        <a class="active" data-page="2">2</a>
      </nav>
      <div class="row listDepartable" id="routeMainList36562620">
        <a onclick="Ajax('fleet_details.php?id=24265127','detailsAction')">PP-141-4</a>
      </div>
      <img src="/assets/loader.svg">
    </div>
    <select id="hubSelect">
      <option>789</option>
      <option value="123">XAP</option>
      <option value="123">XAP duplicate</option>
      <option value="SECRET_TOKEN">Secret label</option>
    </select>
    """

    class GameFixture(HTMLParser):
        def __init__(self):
            super().__init__()
            self.popup = {}
            self.pagination = {}
            self.active = None
            self.in_active = False
            self.row = {}
            self.link = {}
            self.options = []
            self.option = None
            self.loader = {}

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if attrs.get("id") == "popContent":
                self.popup = attrs
            elif tag == "nav" and "pagination" in attrs.get("class", "").split():
                self.pagination = attrs
            elif tag == "a" and "active" in attrs.get("class", "").split():
                self.active = {"attrs": attrs, "text": ""}
                self.in_active = True
            elif attrs.get("id", "").startswith("routeMainList"):
                self.row = attrs
            elif tag == "a" and "fleet_details.php" in attrs.get("onclick", ""):
                self.link = attrs
            elif tag == "img" and "loader" in attrs.get("src", ""):
                self.loader = attrs
            elif tag == "option":
                self.option = {"attrs": attrs, "text": ""}
                self.options.append(self.option)

        def handle_data(self, data):
            if self.option is not None:
                self.option["text"] += data
            if self.in_active:
                self.active["text"] += data

        def handle_endtag(self, tag):
            if tag == "option":
                self.option = None
            elif tag == "a":
                self.in_active = False

    fixture = GameFixture()
    fixture.feed(html)
    assert fixture.link["onclick"].startswith("Ajax('fleet_details.php?id=24265127")
    nodes = {
        "#popContent": [{"attrs": fixture.popup}],
        "#popContent .pagination": [{"attrs": fixture.pagination}],
        "#popContent .pagination .active, #popContent .pagination [aria-current='page'], #popContent .pagination .page-item.not-active > .page-link": [
            fixture.active],
        "#popContent [id^='routeMainList']": [
            {"attrs": fixture.row, "link": fixture.link}],
        "#popContent img[src*='loader']": [{"attrs": fixture.loader}],
        "#hubSelect option": fixture.options,
    }
    js = "const fixture = " + json.dumps(nodes) + ";\n" + r"""
function node(entry) {
  const attrs = entry.attrs;
  return {
    id: attrs.id || '',
    value: attrs.value || entry.text || '',
    textContent: entry.text || '',
    getAttribute: key => Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : null,
    hasAttribute: key => Object.prototype.hasOwnProperty.call(attrs, key),
    querySelector: key => key === "a[onclick*='fleet_details.php']" && entry.link ?
      node({attrs: entry.link}) : null
  };
}
globalThis.document = {querySelectorAll: selector => (fixture[selector] || []).map(node)};
globalThis.window = {statusData: null};
""" + "\nconsole.log(JSON.stringify((new Function(" + json.dumps(PROBE_JS) + "))()));\n"
    path = tmp_path / "game_fixture.js"
    path.write_text(js, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "SECRET_TOKEN" not in result.stdout
    raw = json.loads(result.stdout)
    report = probe_game_sources(type("Bot", (), {"js": lambda self, _script: raw})())
    assert report["sources"]["owned_hub_options"]["count"] == 4
    assert report["sources"]["owned_hub_options"]["numeric_ids"] == ["123"]
    assert report["sources"]["owned_hub_options"]["id_parseable_nodes"] == 2
    assert report["sources"]["fleet_routes"]["numeric_ids"] == ["36562620"]
    assert report["sources"]["fleet_routes"]["linked_aircraft_ids"] == ["24265127"]
    assert report["pagination"]["current_page"] == 2
    assert report["pagination"]["total_pages"] == 4
    assert report["pagination"]["evidence_conflict"] is False
    assert all(value for key, value in report["pagination"]["evidence"].items()
               if key != "total_pages_route_count_numeric")
    assert report["pagination"]["evidence"]["total_pages_route_count_numeric"] is False
