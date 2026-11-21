"""Responsive hub dashboard controls and their client-side ordering rules."""
from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from conftest import ROOT


class HubsPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = {}
        self.options = {}
        self.label_depth = 0
        self.active_select = None
        self.script_depth = 0
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "label":
            self.label_depth += 1
        if tag in ("input", "select") and props.get("id"):
            self.controls[props["id"]] = {**props, "nested_label": self.label_depth > 0}
        if tag == "select":
            self.active_select = props.get("id")
            if self.active_select:
                self.options[self.active_select] = set()
        if tag == "option" and self.active_select is not None:
            self.options[self.active_select].add(props.get("value"))
        if tag == "script" and "src" not in props:
            self.script_depth += 1

    def handle_endtag(self, tag):
        if tag == "label":
            self.label_depth -= 1
        if tag == "select":
            self.active_select = None
        if tag == "script" and self.script_depth:
            self.script_depth -= 1

    def handle_data(self, data):
        if self.script_depth:
            self.scripts.append(data)


def _page():
    page = HubsPage()
    page.feed((ROOT / "assets/web/index.html").read_text(encoding="utf-8"))
    return page


def test_hubs_filters_and_sort_controls_are_labeled_and_target_the_grids():
    page = _page()
    controls = {
        "hubsSearch": "hubsGrid hubsUnconfirmedList",
        "hubsSort": "hubsGrid",
        "hubExpansionSearch": "hubExpansionGrid",
        "hubExpansionFilter": "hubExpansionGrid",
        "hubExpansionSort": "hubExpansionGrid",
    }
    for identifier, target in controls.items():
        assert page.controls[identifier]["nested_label"], identifier
        assert page.controls[identifier]["aria-controls"] == target

    assert {"name", "profit", "average", "aircraft"} <= page.options["hubsSort"]
    assert {"recommended", "payback", "profit", "investment", "name"} <= page.options["hubExpansionSort"]

    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    assert 'id="hubsCoverage"' in html
    assert 'id="hubExpansionCoverage"' in html
    assert 'className = "hub-progress"' in html
    assert 'progress.setAttribute("aria-label"' in html
    assert '"hubsSearch", "hubsSort"' in html
    assert '"hubExpansionSearch", "hubExpansionFilter", "hubExpansionSort"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_hub_sorting_handles_partial_profit_data_without_changing_source(tmp_path):
    script = "\n".join(_page().scripts)
    full_script = tmp_path / "dashboard.js"
    full_script.write_text(script, encoding="utf-8")
    syntax = subprocess.run(
        ["node", "--check", str(full_script)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert syntax.returncode == 0, syntax.stderr

    helpers = script[script.index("const hubDate ="):script.index("function addHubMetric(")]
    assertions = r"""
const assert = require('node:assert/strict');
const LANG = 'pt_BR';
const nf = new Intl.NumberFormat('pt-BR');
const tr = x => x;
const money = value => String(value);
""" + helpers + r"""
const owned = [
  {id:'3', code:'CCC', aircraft_count:4, estimated_routes:3, estimated_profit_per_day:300},
  {id:'2', code:'BBB', aircraft_count:1, estimated_routes:1, estimated_profit_per_day:200},
  {id:'1', code:'AAA', aircraft_count:5, estimated_routes:0, estimated_profit_per_day:null},
  {id:'4', code:'DDD', aircraft_count:1, estimated_routes:1, estimated_profit_per_day:-10}
];
const codes = rows => rows.map(row => row.code);
assert.deepEqual(codes(sortHubs(owned, 'profit')), ['CCC', 'BBB', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubs(owned, 'average')), ['BBB', 'CCC', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubs(owned, 'aircraft')), ['AAA', 'CCC', 'BBB', 'DDD']);
assert.deepEqual(codes(sortHubs(owned, 'name')), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.equal(hubMeanProfit(owned[0]), 100);
assert.equal(hubMeanProfit(owned[2]), null);
assert.deepEqual(codes(owned), ['CCC', 'BBB', 'AAA', 'DDD']);

const candidates = [
  {code:'BBB', payback_days:12, profit_per_day:300, investment:600},
  {code:'AAA', payback_days:null, profit_per_day:null, investment:null},
  {code:'CCC', payback_days:2, profit_per_day:150, investment:200},
  {code:'DDD', payback_days:0, profit_per_day:0, investment:0}
];
assert.deepEqual(codes(sortHubCandidates(candidates, 'recommended')), ['BBB', 'AAA', 'CCC', 'DDD']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'payback')), ['DDD', 'CCC', 'BBB', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'profit')), ['BBB', 'CCC', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'investment')), ['DDD', 'CCC', 'BBB', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'name')), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.deepEqual(codes(candidates), ['BBB', 'AAA', 'CCC', 'DDD']);
"""
    test_script = tmp_path / "sorting.js"
    test_script.write_text(assertions, encoding="utf-8")
    result = subprocess.run(
        ["node", str(test_script)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
