import json
import shutil
import subprocess
import time

import pytest

import game_observations
from fleet_commitment_observations import (
    FILENAME, PARKED_FLEET_JS, PASSENGER_HANGAR_JS, PENDING_FLEET_JS, SOURCE,
    _fleet_list, _hangar, collect_fleet_commitment_observations, observations_snapshot,
)
from hub_registry import HubRegistry
from portfolio_planner import compare_portfolio


@pytest.mark.parametrize("sample", [None, {"capacity": 2, "occupied": 2, "free": 1},
    {"capacity": 1, "occupied": 1, "free": False}, {"capacity": 1, "occupied": -1, "free": 2}])
def test_invalid_hangar(sample):
    assert _hangar(sample) is None


def test_pending_count_is_not_an_order_count():
    raw = {"total": 2, "rows": [{"id": "101", "status": "maintenance"},
                                {"id": "102", "status": "unclassified"}]}
    assert _fleet_list(raw) == {"total": 2, "maintenance": 1, "unclassified": 1}
    raw["rows"][1]["id"] = "101"
    assert _fleet_list(raw) is None
    raw["rows"].pop()
    assert _fleet_list(raw) is None


class Bot:
    stopping = False

    def __init__(self):
        self.calls = []

    def open_popup(self, url, *_):
        self.calls.append(url)

    def ajax(self, url, *_):
        self.calls.append(url)

    def close_popup(self, quiet):
        self.calls.append("close")


def test_collector_and_profile_snapshot(tmp_path, monkeypatch):
    path = tmp_path / FILENAME
    bot = Bot()
    data = {PASSENGER_HANGAR_JS: {"capacity": 223, "occupied": 223, "free": 0,
                                "upgrade_quotes": {"1": {"cost": 190835956, "duration_seconds": 1080}}},
            PENDING_FLEET_JS: {"total": 1, "rows": [{"id": "12345678", "status": "maintenance"}]},
            PARKED_FLEET_JS: {"total": 0, "rows": []}}
    monkeypatch.setattr(game_observations, "_stable_read", lambda _, script: data[script])
    assert collect_fleet_commitment_observations(bot, path=path)
    assert bot.calls == ["maintenance_main.php", "hangars.php?type=pax", "close", "routes_main.php",
                         "fleet_pending.php", "fleet_parked.php", "close"]
    assert "12345678" not in path.read_text(encoding="utf-8")
    report = HubRegistry(tmp_path / "hubs.json").snapshot({"relations": []})["fleet_commitment_observations"]
    assert report["status"] == "observed"
    assert report["passenger_hangar"]["free"] == 0
    assert report["passenger_hangar"]["upgrade_quotes"] == {"1": {"cost": 190835956, "duration_seconds": 1080}}
    assert report["pending_fleet"] == {"total": 1, "maintenance": 1, "unclassified": 0}
    assert report["parked_count"] == 0
    assert report["pending_orders_verified"] is False
    assert report["commitments_verified"] is False
    assert observations_snapshot(path, now=time.time() + 901)["status"] == "unverified"
    assert observations_snapshot(path, now=time.time() + 901)["passenger_hangar"] is None
    assert observations_snapshot(tmp_path / "other" / FILENAME)["status"] == "unverified"
    data[PENDING_FLEET_JS] = None
    assert not collect_fleet_commitment_observations(bot, path=path)
    assert observations_snapshot(path)["status"] == "partial"
    assert observations_snapshot(path)["pending_fleet"] is None
    data[PASSENGER_HANGAR_JS] = None
    data[PARKED_FLEET_JS] = None
    assert not collect_fleet_commitment_observations(bot, path=path)
    assert observations_snapshot(path)["status"] == "unverified"


def test_malformed_cached_counts_do_not_certify_or_leak_extra_fields(tmp_path):
    path = tmp_path / FILENAME
    data = {"source": SOURCE, "observed_at": time.time(), "passenger_hangar": {"capacity": 10, "occupied": 3, "free": 3},
            "pending_fleet": {"total": 1, "maintenance": 1, "unclassified": 0, "ids": ["100001"]}, "parked_count": False,
            "commitments_verified": True, "pending_orders_verified": True}
    path.write_text(json.dumps(data), encoding="utf-8")
    report = observations_snapshot(path)
    assert report["status"] == "partial"
    assert report["passenger_hangar"] is None and report["parked_count"] is None
    assert "ids" not in report["pending_fleet"]
    assert report["commitments_verified"] is False and report["pending_orders_verified"] is False


def test_portfolio_exposes_missing_or_full_hangar_without_certifying_orders():
    report = {"partial_fleet": False, "available_cash": 100, "fleet_commitment_observations": {
        "status": "observed", "passenger_hangar": {"capacity": 1, "occupied": 1, "free": 0}}}
    result = compare_portfolio(report, research_coverage_verified=True)
    assert result["status"] == "inconclusivo"
    assert "hangar_sem_vaga" in result["blocking_reasons"]
    assert "pedidos_pendentes_a_conciliar" in result["blocking_reasons"]
    report["fleet_commitment_observations"] = {"status": "unverified"}
    assert "vagas_hangar_a_confirmar" in compare_portfolio(report)["blocking_reasons"]


def test_expansion_quote_does_not_certify_capacity_or_final_cost():
    hangar = {"capacity": 1, "occupied": 1, "free": 0, "upgrade_quotes": {
        "1": {"cost": 50, "duration_seconds": 1080},
        "10": {"cost": 500, "duration_seconds": 10740}}}
    report = {"partial_fleet": False, "available_cash": 100, "fleet_commitment_observations": {
        "status": "observed", "passenger_hangar": hangar}}
    result = compare_portfolio(report, known_local_commitments=25)
    assert result["hangar_expansion"] == {"required": True, "final_cost_verified": False, "displayed_quotes": [
        {"additional_slots": 1, "cost": 50, "duration_seconds": 1080,
         "fits_reconciled_budget": None, "fits_budget_upper_bound": True},
        {"additional_slots": 10, "cost": 500, "duration_seconds": 10740,
         "fits_reconciled_budget": None, "fits_budget_upper_bound": False}]}
    assert "hangar_sem_vaga" in result["blocking_reasons"]
    assert not result["execution_available"]
    reconciled = compare_portfolio(report, commitments_verified=True, committed_cash=75)
    assert reconciled["hangar_expansion"]["displayed_quotes"][0]["fits_reconciled_budget"] is False
    hangar.update(occupied=0, free=1)
    assert compare_portfolio(report)["hangar_expansion"] is None


def test_invalid_quotes_preserve_verified_counts():
    hangar = {"capacity": 1, "occupied": 1, "free": 0}
    assert _hangar({**hangar, "upgrade_quotes": {"1": {"cost": True},
        "10": {"cost": 100, "duration_seconds": -1}}}) == hangar
    assert _hangar({**hangar, "upgrade_quotes": {"1": {"cost": 5, "private": "ignore"},
        "5": {"cost": 20}}}) == {**hangar, "upgrade_quotes": {"1": {"cost": 5, "duration_seconds": None}}}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for DOM contract")
def test_native_dom_contract(tmp_path):
    script = tmp_path / "fleet_commitments.js"
    script.write_text("""
const assert = require('node:assert/strict');
const hangar = new Function(""" + json.dumps(PASSENGER_HANGAR_JS) + """);
const pending = new Function(""" + json.dumps(PENDING_FLEET_JS) + """);
const parked = new Function(""" + json.dumps(PARKED_FLEET_JS) + """);
const cell = textContent => ({textContent});
const row = (...texts) => ({cells:texts.map(cell)});
const pax = {getAttribute:()=>"playSound('neutral_click'); Ajax('hangars.php?type=pax','maintAction',this);"};
const rows = [row('', 'PAX A/C', '223'), row('', 'Available hangar slots', '0')];
let upgrades = [];
const upgrade = (amount, price, duration) => ({textContent:price, disabled:false,
  getClientRects:()=>[{}],
  getAttribute:key=>key==='onclick'?`Ajax('hangars.php?mode=upgrade&amount=${amount}&type=','runme');`:null,
  classList:{contains:key=>key==='btn-success'},
  parentElement:{innerText:`INCREASE CAPACITY BY +${amount} A/C\\n${duration}\\n${price}`}});
const hg = {querySelector:()=>null, querySelectorAll:key=>({
  'button.active':[pax], 'button[onclick]':upgrades, '.xl-text span':[cell('223')], table:[{rows}]}[key]||[])};
let kind = 'pending', total = 2;
const button = {get textContent(){return `${kind} (${total})`},
  getAttribute:()=>`Ajax('fleet_${kind}.php','routesContainer',this);`};
const panel = {querySelector:()=>null, children:[cell('2 AIRCRAFT'),
  {id:'routeMainPendingList101',innerText:'Synthetic\\nPending maintenance: 12:00:00'},
  {id:'routeMainPendingList102',innerText:'Synthetic\\nOther status'}, {tagName:'SCRIPT'}]};
global.window = {jQuery:{active:0}};
global.document = {querySelectorAll:key=>({'#maintAction':[hg], '#routesContainer':[panel],
  '#routeAction .listBtns':[button]}[key]||[])};
assert.deepEqual(hangar(), {capacity:223,occupied:223,free:0});
const one = upgrade(1,'$190,835,956','00:18:00');
const ten = upgrade(10,'$1,908,359,562','02:59:00');
upgrades = [one,ten];
assert.deepEqual(hangar().upgrade_quotes, {'1':{cost:190835956,duration_seconds:1080},'10':{cost:1908359562,duration_seconds:10740}});
one.disabled=true; assert.deepEqual(hangar().upgrade_quotes, {'10':{cost:1908359562,duration_seconds:10740}});
one.disabled=false; one.getClientRects=()=>[]; assert.deepEqual(Object.keys(hangar().upgrade_quotes),['10']);
one.getClientRects=()=>[{}];
one.disabled=false; upgrades=[one,one,ten]; assert.deepEqual(Object.keys(hangar().upgrade_quotes),['10']);
upgrades=[one,ten]; ten.parentElement.innerText='INCREASE CAPACITY BY +1 A/C\\n02:59:00\\n$1,908,359,562';
assert.deepEqual(Object.keys(hangar().upgrade_quotes),['1']);
one.textContent='$190,835,956 00:18:00'; assert.equal(hangar().upgrade_quotes,undefined);
rows[1].cells[1].textContent = 'Other slots'; assert.equal(hangar(),null);
assert.deepEqual(pending(), {total:2,rows:[{id:'101',status:'maintenance'},{id:'102',status:'unclassified'}]});
total=3; assert.equal(pending(),null);
kind='parked'; total=0; panel.children=[cell('0 AIRCRAFT'),cell('THERE ARE NO PARKED AIRCRAFT'),{tagName:'SCRIPT'}];
assert.deepEqual(parked(), {total:0,rows:[]});
panel.children=[cell('0 AIRCRAFT')]; assert.equal(parked(),null);
window.jQuery.active=1; assert.equal(hangar(),null); assert.equal(parked(),null);
""", encoding="utf-8")
    subprocess.run(["node", str(script)], check=True)
