import json
import shutil
import subprocess
from unittest.mock import Mock

import pytest

import game_observations
from hub_operations import HUB_OPERATIONS_JS, collect_hub_operations


@pytest.mark.parametrize(("failure", "enumerated"), [
    (None, True), ("wrong_panel", False), ("changed_roster", False),
])
def test_collection_requires_the_requested_panel_and_a_stable_managed_roster(monkeypatch, failure, enumerated):
    bot = Mock(stopping=False)
    panel = {"management_id": "23678242", "icao": "SBGR", "iata": "GRU", "rows": []}
    if failure == "wrong_panel":
        panel["management_id"] = "23678243"
    refreshed = ["23678243"] if failure == "changed_roster" else ["23678242"]
    reader = Mock(side_effect=[["23678242"], panel, refreshed])
    monkeypatch.setattr(game_observations, "_stable_read", reader)

    result = collect_hub_operations(bot)

    assert result["enumerated"] is enumerated
    assert result["panels"] == ([] if failure == "wrong_panel" else [panel])
    assert bot.ajax.call_args.args == ("hub_details.php?id=23678242", "hubDetail")
    assert bot.open_popup.call_count == (1 if failure == "wrong_panel" else 2)
    bot.close_popup.assert_called_once_with(quiet=True)


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
global.document = {querySelectorAll: key => key === '#hubDetail' ? [outer, detail] : []};
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
