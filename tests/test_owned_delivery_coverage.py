import json
import shutil
import subprocess
import time

import pytest

import game_observations
from fleet import _MODELS_JS
from hub_registry import HubRegistry
from owned_delivery_coverage import (
    MANAGED_HUB_IDS_JS, ORDER_DELIVERY_IDS_JS, SOURCE, collect_owned_delivery_coverage,
    compare_coverage, coverage_snapshot,
)


def _order(ids=("800001", "800002"), *, model="2"):
    return {"model_id": model, "state": {"selector_count": 1, "selector_disabled": False,
            "value": ids[0], "selected_values": [ids[0]],
            "options": [{"id": value, "disabled": index > 0} for index, value in enumerate(ids)]}}


def test_identical_sets_independent_of_order_and_no_ids_in_result():
    before = ["800002", "800001"]
    assert compare_coverage(before, _order(), list(reversed(before)), "2") == {
        "managed_count": 2, "delivery_count": 2, "matching_count": 2, "disabled_count": 1,
    }
    assert compare_coverage(before, _order(("800001", "800003")), before, "2")["matching_count"] == 1


@pytest.mark.parametrize("before,after,order,model", [
    ([], [], _order(), "2"),
    (["800001", "800001"], ["800001", "800001"], _order(), "2"),
    (["800001", None], ["800001", None], _order(), "2"),
    (["800001"], ["800002"], _order(), "2"),
    (["800001"], ["800001"], _order(("800001", "800001")), "2"),
    (["800001"], ["800001"], _order(), "5"),
    (["800001"], ["800001"], {"model_id": "2", "state": {"selector_count": True}}, "2"),
])
def test_incomplete_or_unstable_reads_cannot_verify_coverage(before, after, order, model):
    assert compare_coverage(before, order, after, model) is None


def test_disabled_or_ambiguous_selection_is_inconclusive():
    order = _order()
    order["state"]["selected_values"] = ["800002"]
    order["state"]["value"] = "800002"
    assert compare_coverage(["800001"], order, ["800001"], "2") is None


class _Bot:
    stopping = False

    def __init__(self):
        self.calls = []

    def open_popup(self, url, title, nav):
        self.calls.append(url)

    def close_popup(self, quiet):
        self.calls.append("close")

    def ajax(self, url, target):
        self.calls.append(url)


def test_collector_brackets_form_and_persists_only_profile_counts(tmp_path, monkeypatch):
    path = tmp_path / "owned_delivery_coverage.json"
    first = ["800001", "800002"]
    reads = iter([(MANAGED_HUB_IDS_JS, first), (_MODELS_JS, [{"id": "5"}, {"id": "2"}]),
                  (ORDER_DELIVERY_IDS_JS, _order()), (MANAGED_HUB_IDS_JS, first)])

    def read(bot, script):
        expected, result = next(reads)
        assert script == expected
        return result

    monkeypatch.setattr(game_observations, "_stable_read", read)
    bot = _Bot()
    assert collect_owned_delivery_coverage(bot, path=path)
    assert bot.calls == ["close", "hubs.php", "close", "routes_main.php", "ac_orders.php?first=true",
                         "ac_orders.php?mode=detail&id=2&charter=0", "close", "close", "hubs.php", "close"]
    assert "80000" not in path.read_text(encoding="utf-8")
    report = HubRegistry(tmp_path / "hubs.json").snapshot({"relations": []})["delivery_coverage"]
    assert report["status"] == "matched"
    assert report["airport_crosswalk_verified"] is False
    assert report["source"] == SOURCE
    assert coverage_snapshot(path, now=time.time() + 901)["status"] == "unverified"
    assert coverage_snapshot(tmp_path / "other" / path.name, now=time.time())["status"] == "unverified"
    monkeypatch.setattr(game_observations, "_stable_read", lambda *_: None)
    assert not collect_owned_delivery_coverage(bot, path=path)
    assert coverage_snapshot(path, now=time.time())["status"] == "unverified"


def test_saved_mismatch_is_visible_and_invalid_counts_cannot_certify(tmp_path):
    path = tmp_path / "owned_delivery_coverage.json"
    now = int(time.time())
    data = {"source": SOURCE, "observed_at": now, "managed_count": 2,
            "delivery_count": 3, "matching_count": 2, "disabled_count": 1}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert coverage_snapshot(path, now=now)["status"] == "different"
    data["matching_count"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    assert coverage_snapshot(path, now=now)["status"] == "unverified"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for DOM contract")
def test_native_management_and_order_dom_contract(tmp_path):
    script = tmp_path / "coverage.js"
    script.write_text("""
const assert = require('node:assert/strict');
const managed = new Function(""" + json.dumps(MANAGED_HUB_IDS_JS) + """);
const order = new Function(""" + json.dumps(ORDER_DELIVERY_IDS_JS) + """);
const makeRow = id => ({matches: selector => selector === '.row[onclick]',
  getAttribute: () => `playSound('neutral_click');Ajax('hub_details.php?id=${id}','hubDetail',this,true);`});
const list = {children: [makeRow('800001'), makeRow('800002')], querySelector: () => null};
const selector = {value:'800001', disabled:false, options:[
  {value:'800001', selected:true, matches:()=>false},
  {value:'800002', selected:false, matches:()=>true}]};
const panel = {contains: element=>element===selector, getAttribute:()=>null,
  querySelector:()=>null, querySelectorAll:()=>[{textContent:'var acId=2;'}]};
global.window = {jQuery:{active:0}};
global.document = {querySelectorAll: key=>({'#hubList':[list], '#acModel':[panel],
  '#hubSelection':[selector]})[key] || []};
assert.deepEqual(managed(), ['800001','800002']);
assert.equal(order().model_id, '2');
assert.deepEqual(order().state.options, [{id:'800001',disabled:false},{id:'800002',disabled:true}]);
list.children.push({matches:()=>false});
assert.equal(managed(), null);
window.jQuery.active = 1;
assert.equal(order(), null);
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
