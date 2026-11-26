import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from native_demand_transport import _READ_DEMAND_BATCH_JS, read_demand_batch


def test_batch_preserves_requests_and_limits_each_driver_call():
    jobs = [("1440", "Tunisia", str(i)) for i in range(9)]
    first = [{"destination_id": "1", "y": 0, "j": 4, "f": 0, "event_demand_boosted": None}]
    execute = Mock(side_effect=[[[], first, None, []], [None], [[]]])
    results = read_demand_batch(SimpleNamespace(driver=SimpleNamespace(execute_async_script=execute)), jobs)

    assert results == [
        {"origin_id": origin, "country": country, "destination_id": dest, "rows": rows}
        for (origin, country, dest), rows in zip(jobs, [[], first, None, [], None, None, None, None, []])
    ]
    calls = [call.args[1:] for call in execute.call_args_list]
    assert [len(requests) for requests, _ in calls] == [4, 4, 1]
    assert [tuple(job) for requests, _ in calls for job in requests] == jobs
    assert all(timeout == 4000 for _, timeout in calls)


def test_driver_timeout_preserves_previous_results_and_does_not_retry():
    jobs = [("1440", "Tunisia", "0")] * 9
    execute = Mock(side_effect=[[[], [], [], []], TimeoutException("private browser error")])
    bot = SimpleNamespace(driver=SimpleNamespace(execute_async_script=execute))

    assert [result["rows"] for result in read_demand_batch(bot, jobs)] == [[], [], [], [], None, None, None, None, None]
    assert execute.call_count == 2


def test_stopping_bot_keeps_failed_placeholders_without_using_driver():
    assert read_demand_batch(SimpleNamespace(stopping=True), [("1440", "Tunisia", "0")]) == [
        {"origin_id": "1440", "country": "Tunisia", "destination_id": "0", "rows": None}
    ]


_RUN_SCRIPT = r"""
const {script, scenario, jobs} = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const assert = require('node:assert/strict');
globalThis.location = { origin: scenario.origin || 'https://www.airlinemanager.com' };
globalThis.fbSig = 'example-native-signature';
const requests = [];
globalThis.fetch = async (path, options) => {
  const {signal, ...policy} = options;
  assert(signal instanceof AbortSignal);
  requests.push({path, policy});
  if (scenario.fail === 'network') throw new Error('network error');
  if (scenario.fail === 'timeout') {
    await new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason));
      setTimeout(resolve, 60);
    });
  }
  return {ok: scenario.fail !== 'http', text: async () => '<native fragment>'};
};

const nativeNotice = 'There were no results to your search';
const warning = 'Demand is currently boosted due to a special event';
const cards = (scenario.cards || []).map(row => {
  const attrs = {
    onclick: "Ajax('route_research_route.php?dep=1440&arr=432','rDetails');",
    'data-yclass': '1341', 'data-jclass': '514', 'data-fclass': '0',
    'data-distance': '10515.5', 'data-rwy': '10499', ...row.attrs
  };
  return {
    getAttribute: name => attrs[name] ?? null,
    textContent: row.event ? warning : '',
    outside: row.outside
  };
});
const fragment = {
  querySelectorAll: name => {
    if (name === '#list') return Array.from({length: scenario.lists ?? 1}, () => list);
    assert.equal(name, '.sorter');
    return cards;
  },
  querySelector: name => {
    assert.equal(name, 'img[src*="loader"], [aria-busy="true"]');
    return scenario.busy || null;
  }
};
const list = {
  parentNode: scenario.nested ? {} : fragment,
  textContent: scenario.extraText ?? (scenario.notice || scenario.bareText ? nativeNotice : ''),
  contains: card => !card.outside,
  querySelectorAll: name => {
    assert.equal(name, ':scope > .row > .col-12 > .alert.alert-info');
    return scenario.notice ? [{
      textContent: scenario.notice === true ? nativeNotice : scenario.notice,
      closest: () => scenario.hidden || null
    }] : [];
  }
};
globalThis.document = {
  createElement: tag => {
    assert.equal(tag, 'template');
    return {set innerHTML(value) { assert.equal(value, '<native fragment>'); }, content: fragment};
  }
};
const read = new Function(script);
(async () => {
  const rows = await new Promise(done => read(jobs, 10, done));
  process.stdout.write(JSON.stringify({rows, requests}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""

@pytest.fixture
def run_script():
    if not shutil.which("node"):
        pytest.skip("Node.js indisponível")

    def run(scenario, jobs=(("1440", "Tunisia", "0"),)):
        response = subprocess.run(
            ["node", "-e", _RUN_SCRIPT],
            input=json.dumps({"script": _READ_DEMAND_BATCH_JS, "scenario": scenario, "jobs": jobs}),
            text=True, capture_output=True, check=True, timeout=8,
        )
        return json.loads(response.stdout)

    return run


def test_detached_search_pins_native_parameters_and_keeps_short_direct_match(run_script):
    result = run_script(
        {"cards": [{"event": True, "attrs": {"data-distance": "8.25", "data-rwy": "3000"}}]},
        (("1440", "Congo (Kinshasa)", "432"),),
    )

    assert result["requests"] == [{
        "path": "/research_main.php?mode=search&rwy=1000&dist=20000&depId=1440"
                "&arr=Congo+%28Kinshasa%29&arrId=432&charter=0&fbSig=example-native-signature",
        "policy": {"method": "GET", "mode": "same-origin", "credentials": "same-origin",
                   "redirect": "error", "cache": "no-store"},
    }]
    assert result["rows"] == [[{
        "destination_id": "432", "y": 1341, "j": 514, "f": 0, "event_demand_boosted": True,
        "distance_km": 8.25, "runway_ft": 3000,
    }]]


def test_explicit_native_empty_has_no_inferred_demand(run_script):
    result = run_script({"notice": True}, (("1440", "Jamaica", "0"), ("1440", "Jamaica", "432")))
    assert result["rows"] == [[], []]


@pytest.mark.parametrize("scenario", [
    {}, {"bareText": True}, {"lists": 0, "notice": True}, {"lists": 2, "notice": True},
    {"nested": True, "notice": True}, {"hidden": True, "notice": True},
    {"notice": "Internal error"}, {"notice": True, "extraText": "Please log in"},
    {"notice": True, "busy": True}, {"notice": True, "cards": [{}]},
    {"fail": "http", "notice": True}, {"fail": "network", "notice": True}, {"fail": "timeout", "notice": True},
    {"cards": [{"outside": True}]}, {"cards": [{}, {}]},
    {"cards": [{"attrs": {"data-fclass": None}}]},
    {"cards": [{"attrs": {"onclick": "Ajax('route_research_route.php?dep=999&arr=432','rDetails');"}}]},
    {"cards": [{"attrs": {"onclick": "Ajax('route_research_route.php?dep=1440&arr=432&arr=999','rDetails');"}}]},
    {"cards": [{"attrs": {"onclick": "Ajax('//elsewhere.test/route_research_route.php?dep=1440&arr=432');"}}]},
])
def test_ambiguous_native_response_is_missing(run_script, scenario):
    assert run_script(scenario)["rows"] == [None]


def test_one_wrong_arrival_does_not_invalidate_neighboring_jobs(run_script):
    result = run_script(
        {"cards": [{"attrs": {"data-distance": "", "data-rwy": "unknown"}}]},
        (("1440", "Tunisia", "12"), ("1440", "Tunisia", "0"), ("1440", "Tunisia", "432")),
    )
    row = {"destination_id": "432", "y": 1341, "j": 514, "f": 0, "event_demand_boosted": None}
    assert result["rows"] == [None, [row], [row]]


def test_declines_other_origins_and_invalid_pairs_before_fetch(run_script):
    assert run_script({"origin": "https://other.example"}) == {"rows": [None], "requests": []}
    result = run_script({}, (("0", "Tunisia", "432"), ("1440", "Tunisia", "1440"), ("1440", "Tunisia", "12&mode=other")))
    assert result == {"rows": [None, None, None], "requests": []}
