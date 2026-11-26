import json
import shutil
import subprocess
from unittest.mock import Mock, call

import pytest

import game_observations
import hub_operations
from hub_operations import HUB_OPERATIONS_JS, collect_hub_operations
from owned_delivery_coverage import SOURCE as DELIVERY_SOURCE


@pytest.mark.parametrize(("failure", "enumerated"), [
    (None, True), ("unstable_panel", True), ("wrong_panel", False), ("changed_roster", False),
])
def test_collection_requires_the_requested_panel_and_a_stable_managed_roster(monkeypatch, failure, enumerated):
    bot = Mock(stopping=False)
    panel = {"management_id": "23678242", "icao": "SBGR", "iata": "GRU", "rows": []}
    if failure == "wrong_panel":
        panel["management_id"] = "23678243"
    refreshed = ["23678243"] if failure == "changed_roster" else ["23678242"]
    first_read = [None] if failure == "unstable_panel" else [panel] if failure == "wrong_panel" else []
    reader = Mock(side_effect=[["23678242"], *first_read, panel, refreshed])
    bot._stop.wait.return_value = False
    monkeypatch.setattr(game_observations, "_stable_read", reader)
    monkeypatch.setattr(hub_operations, "open_managed_hubs", lambda bot: bot.open_native_hubs())

    result = collect_hub_operations(bot)

    assert result["enumerated"] is enumerated
    assert result["panels"] == ([] if failure == "wrong_panel" else [panel])
    open_hubs = [call.open_native_hubs()]
    read_panel = [call.ajax("hub_details.php?id=23678242", "hubDetail", timeout=10)]
    assert bot.mock_calls == [*open_hubs, *read_panel, *([call._stop.wait(0.4)] if first_read else []),
                              *(open_hubs if failure != "wrong_panel" else []), call.close_popup(quiet=True)]


@pytest.mark.parametrize("failure", [None, "stale_selector", "mixed_cycle", "changed_order_ids", "duplicate_codes"])
def test_delivery_crosswalk_joins_three_native_surfaces_in_one_cycle(failure):
    panels = [
        {"management_id": "24323457", "iata": "LAX", "icao": "KLAX", "rows": []},
        {"management_id": "23678242", "iata": "GRU", "icao": "SBGR", "rows": []},
    ]
    hubs = [{"id": "1440", "code": "LAX"}, {"id": "591", "code": "SBGR"}]
    options = [{"id": "23678242", "disabled": True}, {"id": "24323457", "disabled": False}]
    evidence = {
        "hubs": {"enumerated": True, "source": "game_hub_operations", "managed_count": 2,
                 "panels": panels, "started_at": 102.5, "observed_at": 105},
        "delivery_hubs": {"source": DELIVERY_SOURCE, "model_id": "2", "options": options,
                          "started_at": 110, "observed_at": 112.3},
    }
    if failure == "mixed_cycle":
        evidence["delivery_hubs"]["observed_at"] = 115
    elif failure == "changed_order_ids":
        options[0]["id"] = "23678243"
    elif failure == "duplicate_codes":
        panels[1]["iata"] = "LAX"
    result = hub_operations.reconcile_delivery_hubs(
        evidence, owned_hubs=hubs, hub_at=99 if failure == "stale_selector" else 100, window=(100.2, 114),
    )

    if failure:
        assert result == {"status": "incomplete", "pairs": []}
    else:
        assert result == {
            "status": "matched", "source": "game_owned_hub_crosswalk", "model_id": "2", "observed_at": 112.3,
            "disabled_count": 1, "pairs": [{"airport_id": "1440", "delivery_hub_id": "24323457",
                                           "iata": "LAX", "icao": "KLAX"}],
        }


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for DOM contract")
def test_managed_hub_detail_reads_native_operation_aircraft_link(tmp_path):
    script = tmp_path / "hub_operations.js"
    script.write_text("""
const assert = require('node:assert/strict');
const collect = new Function(""" + json.dumps(HUB_OPERATIONS_JS) + r""");
const attr = value => ({getAttribute: key => key === 'onclick' ? value : null});
const text = textContent => ({nodeType: 3, textContent});
const row = {cells: [{}, {childNodes: [{tagName: 'B'}, {tagName: 'BR'}, text('STG-PRY')]}, {
  querySelectorAll: key => key === 'a[onclick]' ? [
    attr("playSound('neutral_click');Ajax('fleet_details.php?id=25233466&ret=hub','fleetHubDetailsAction');")
  ] : []
}]};
const table = {matches: key => key === 'table.table', tBodies: [{rows: [row]}]};
const outer = {};
const detail = {parentElement: outer, querySelector: () => null, querySelectorAll: key => ({
  ':scope > .row:first-child > div': [text('St George, AK'), text('PAPB/STG')],
  '[onclick]': [attr("Ajax('hubs_lounge.php?id=23678242','hubDetail',this);")],
  'div.text-center.font-weight-bold': [{textContent: 'Operations to/from hub', nextElementSibling: table}],
})[key] || []};
global.document = {querySelectorAll: key => key === '#popup #popContent #hubDetail' ? [outer, detail] : []};
global.window = {jQuery: {active: 0}};
assert.deepEqual(collect(), {management_id: '23678242', icao: 'PAPB', iata: 'STG',
  rows: [{aircraft_id: '25233466', airports: ['STG', 'PRY']}]});
row.cells[2].querySelectorAll = () => [attr("Ajax('fleet_details.php?id=25233466','elsewhere');")];
assert.equal(collect(), null);
table.tBodies[0].rows = [];
assert.deepEqual(collect().rows, []);
window.jQuery.active = 1;
assert.equal(collect(), null);
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
