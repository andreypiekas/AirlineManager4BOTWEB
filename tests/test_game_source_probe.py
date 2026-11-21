"""Sanitized game-source probe, including real JavaScript execution with a fake DOM."""

import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from game_source_probe import PROBE_JS, SAMPLE_LIMIT, probe_game_sources


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
    assert secret not in json.dumps(report)


def test_embedded_dom_probe_returns_only_allowlisted_metadata(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to run the embedded DOM probe")

    mock = r"""
function node(attrs = {}, options = {}) {
  const entry = {
    id: attrs.id || '',
    value: attrs.value || '',
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
  '#hubSelection option': [node({value: '456', selected: 'selected'})],
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
  "#popContent .pagination .active, #popContent .pagination [aria-current='page']": [
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
  "#popContent .pagination .active, #popContent .pagination [aria-current='page']": [
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
        "#popContent .pagination .active, #popContent .pagination [aria-current='page']": [
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
    assert all(report["pagination"]["evidence"].values())
