import json
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException

import fleet_commitment_observations
import game_observations
import maintenance
import route_registry
import seats
from fleet_commitment_observations import (
    FILENAME, PARKED_FLEET_JS, PASSENGER_HANGAR_JS, PENDING_FLEET_JS, SOURCE,
    _OPEN_PARKED_JS, _fleet_list, _hangar, collect_fleet_commitment_observations, observations_snapshot,
    read_pilot_pending, reconcile_route_coverage,
)
from hub_registry import HubRegistry
from portfolio_planner import compare_portfolio
from route_registry import RouteRegistry


@pytest.mark.parametrize("sample", [None, {"capacity": 2, "occupied": 2, "free": 1},
    {"capacity": 1, "occupied": 1, "free": False}, {"capacity": 1, "occupied": -1, "free": 2}])
def test_invalid_hangar(sample):
    assert _hangar(sample) is None


def test_pending_count_is_not_an_order_count():
    raw = {"total": 2, "rows": [{"id": "101", "status": "maintenance"},
                                {"id": "102", "status": "unclassified"}]}
    assert _fleet_list(raw) == {"total": 2, "maintenance": 1, "delivery": 0, "unclassified": 1}
    raw["rows"][1]["id"] = "101"
    assert _fleet_list(raw) is None
    raw["rows"].pop()
    assert _fleet_list(raw) is None


class Bot:
    stopping = False
    driver = None

    def __init__(self):
        self.calls = []

    def open_popup(self, url, *_):
        self.calls.append(url)

    def ajax(self, url, *_):
        self.calls.append(url)

    def js(self, script):
        assert script == _OPEN_PARKED_JS
        self.calls.append("Parked")
        return True

    def close_popup(self, quiet):
        self.calls.append("close")


@pytest.mark.parametrize("case", [
    "complete", "company_changed", "count_changed", "roster_missing_pending", "roster_changed", "distribution_changed",
    "routes_unreadable_after",
])
def test_pilot_read_checks_company_and_correlates_baseline_roster(monkeypatch, case):
    class PilotBot(Bot):
        def _require_observation_session(self):
            self.calls.append("session")

        def _verify_observation_company(self):
            changed = case == "company_changed" and "fleet_pending.php" in self.calls
            self._observation_company_id = "99" if changed else "98"
            self.calls.append("company")

    def stable_read(bot, script):
        if script == PENDING_FLEET_JS:
            assert bot.calls[-1] == "fleet_pending.php"
            identity = "199" if case == "roster_missing_pending" else "102"
            return {"total": 1, "rows": [{"id": identity, "status": "maintenance"}]}
        assert "window.statusData" in script and "#hPending" in script
        assert bot.calls[-1] == "routes_main.php"
        after_pending = "fleet_pending.php" in bot.calls
        bot.calls.append("roster")
        if after_pending and case == "routes_unreadable_after":
            return {"counts": None, "rows": []}
        parked = int(after_pending and case == "distribution_changed")
        aircraft_id = "103" if after_pending and case == "roster_changed" else "101"
        return {"counts": {"routes": 1 - parked, "parked": parked, "pending": 2 if case == "count_changed" else 1},
                "rows": [{"aircraft_id": aircraft_id, "route_id": 0 if parked else 9},
                         {"aircraft_id": "102", "route_id": 0}]}

    monkeypatch.setattr(game_observations, "_stable_read", stable_read)
    bot = PilotBot()
    baseline = read_pilot_pending(bot, baseline=True)
    if case == "count_changed":
        assert baseline is None
        assert bot.calls == ["session", "company", "routes_main.php", "roster", "close"]
        return
    pending_calls = ["session", "company", "routes_main.php", "roster", "fleet_pending.php",
                     "close", "routes_main.php", "roster", "close"]
    if case in {"roster_changed", "distribution_changed", "routes_unreadable_after"}:
        assert baseline is None
        assert bot.calls == pending_calls
        return
    assert bot.calls == [*pending_calls, "session", "company"]
    if case != "complete":
        assert baseline is None
        return
    assert baseline["company_id"] == "98"
    assert baseline["fleet_total"] == 2
    assert baseline["fleet_ids"] == ["101", "102"]
    assert baseline["observed_at"] <= baseline["observed_until"]
    bot.calls.clear()
    pending = read_pilot_pending(bot)
    assert pending["pending"] == baseline["pending"]
    assert "fleet_ids" not in pending
    assert bot.calls == ["session", "company", "routes_main.php", "fleet_pending.php", "close", "session", "company"]


def test_collector_and_profile_snapshot(tmp_path, monkeypatch):
    path = tmp_path / FILENAME
    bot = Bot()
    data = {PASSENGER_HANGAR_JS: {"capacity": 223, "occupied": 223, "free": 0,
                                "upgrade_quotes": {"1": {"cost": 190835956, "duration_seconds": 1080}}},
            PENDING_FLEET_JS: {"total": 2, "rows": [{"id": "12345678", "status": "maintenance"},
                                                   {"id": "23456789", "status": "delivery"}]},
            PARKED_FLEET_JS: {"total": 0, "rows": []}}
    parked_initial = iter([None])

    def read(_, script):
        return next(parked_initial, data[script]) if script == PARKED_FLEET_JS else data[script]

    monkeypatch.setattr(game_observations, "_stable_read", read)

    def poll_parked(_, condition):
        for _ in range(2):
            if panel := condition(None):
                return panel
        raise TimeoutException()

    monkeypatch.setattr(fleet_commitment_observations.WebDriverWait, "until", poll_parked)
    evidence = {}
    assert collect_fleet_commitment_observations(bot, path=path, identity_evidence=evidence)
    assert evidence["pending_ids"] == frozenset({"12345678", "23456789"})
    assert evidence["maintenance_ids"] == frozenset({"12345678"})
    assert evidence["unclassified_pending_ids"] == frozenset()
    assert evidence["parked_ids"] == frozenset()
    assert json.loads(path.read_text(encoding="utf-8"))["observation_id"] == evidence["observation_id"]
    assert bot.calls == ["maintenance_main.php", "hangars.php?type=pax", "close", "routes_main.php",
                         "fleet_pending.php", "Parked", "close"]
    assert "12345678" not in path.read_text(encoding="utf-8")
    report = HubRegistry(tmp_path / "hubs.json").snapshot({"relations": []})["fleet_commitment_observations"]
    assert report["status"] == "observed"
    assert report["observed_at"] <= report["observed_until"] <= time.time()
    assert report["passenger_hangar"]["free"] == 0
    assert report["passenger_hangar"]["upgrade_quotes"] == {"1": {"cost": 190835956, "duration_seconds": 1080}}
    assert report["pending_fleet"] == {"total": 2, "maintenance": 1, "delivery": 1, "unclassified": 0}
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


def _seed_observations(path):
    path.write_text(json.dumps({"source": SOURCE, "observed_at": time.time(),
                                "passenger_hangar": {"capacity": 3, "occupied": 2, "free": 1},
                                "pending_fleet": {"total": 0, "maintenance": 0, "delivery": 0, "unclassified": 0},
                                "parked_count": 0}), encoding="utf-8")


def test_coverage_revocation_withdraws_native_cache_only_in_affected_profile(tmp_path):
    first = tmp_path / FILENAME
    other = tmp_path / "other" / FILENAME
    other.parent.mkdir()
    _seed_observations(first)
    _seed_observations(other)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert observations_snapshot(first)["status"] == "observed"
    registry.invalidate_fleet_coverage()
    registry.invalidate_fleet_coverage()
    assert observations_snapshot(first)["status"] == "unverified"
    assert observations_snapshot(other)["status"] == "observed"


@pytest.mark.parametrize("action", ["hangar", "repair", "check"])
@pytest.mark.parametrize("dry_run", [True, False])
def test_maintenance_revokes_before_uncertain_submission(tmp_path, monkeypatch, action, dry_run):
    path = tmp_path / FILENAME
    _seed_observations(path)
    monkeypatch.setattr(route_registry, "registry_file", lambda: tmp_path / "routes.json")
    button = SimpleNamespace(text="$100", get_attribute=lambda _: "btn-success")
    section = SimpleNamespace(find_elements=lambda *_: [button])
    panel = SimpleNamespace(find_elements=lambda *_: [button if action == "hangar" else section])
    monkeypatch.setattr(maintenance, "section_cost", lambda _: 100)
    calls = []

    def click(_):
        assert observations_snapshot(path)["status"] == "unverified"
        calls.append(True)
        raise TimeoutError("uncertain submission")

    bot = SimpleNamespace(
        dry_run=dry_run, ajax=lambda *_: panel, js=lambda *_: {"capacity": "3", "free": "1"},
        config=SimpleNamespace(get_int=lambda *args: 2, get_bool=lambda *args: True),
        update_stats=lambda **_: None, can_spend=lambda *args, **kwargs: True,
        read_money=lambda: 1000, click_element=click, notify=lambda *args, **kwargs: None,
    )
    aircraft = maintenance.Aircraft("101", "PP-101", "A320", 50, 1, True)

    def run():
        if action == "hangar":
            maintenance.check_hangar(bot)
        else:
            maintenance.plan(bot, aircraft, action)

    if dry_run:
        run()
        assert not calls
        assert observations_snapshot(path)["status"] == "observed"
    else:
        with pytest.raises(TimeoutError, match="uncertain submission"):
            run()
        assert calls == [True]
        assert observations_snapshot(path)["status"] == "unverified"


@pytest.mark.parametrize("dry_run", [True, False])
def test_workshop_revokes_before_uncertain_submission(tmp_path, monkeypatch, dry_run):
    path = tmp_path / FILENAME
    _seed_observations(path)
    monkeypatch.setattr(route_registry, "registry_file", lambda: tmp_path / "routes.json")
    panel = SimpleNamespace(find_elements=lambda *_: [object()])

    def click(_):
        assert observations_snapshot(path)["status"] == "unverified"
        raise TimeoutError("uncertain submission")

    bot = SimpleNamespace(dry_run=dry_run, ajax=lambda *_: panel, js=lambda *args: 100,
                          can_spend=lambda *args, **kwargs: True, read_money=lambda: 1000,
                          click_element=click, notify=lambda *args, **kwargs: None)
    plan = seats.SeatPlan("101", "PP-101", "A320", "XAP-GRU", seats.Layout(100, 0, 0),
                          seats.Layout(80, 10, 0), (300, 50, 0), (100, 300, 0), 2,
                          1000, 2000, 100, 1)
    if dry_run:
        assert seats.apply_plan(bot, plan, 30) == 1
        assert observations_snapshot(path)["status"] == "observed"
    else:
        with pytest.raises(TimeoutError, match="uncertain submission"):
            seats.apply_plan(bot, plan, 30)
        assert observations_snapshot(path)["status"] == "unverified"


def test_portfolio_exposes_missing_or_full_hangar_without_certifying_orders():
    report = {"partial_fleet": False, "available_cash": 100, "fleet_commitment_observations": {
        "status": "observed", "passenger_hangar": {"capacity": 1, "occupied": 1, "free": 0}}}
    result = compare_portfolio(report, research_coverage_verified=True)
    assert result["status"] == "inconclusivo"
    assert "hangar_sem_vaga" in result["blocking_reasons"]
    assert "pedidos_pendentes_a_conciliar" in result["blocking_reasons"]
    report["fleet_commitment_observations"] = {"status": "unverified"}
    assert "vagas_hangar_a_confirmar" in compare_portfolio(report)["blocking_reasons"]


@pytest.mark.parametrize("parked,pending,audited_parked,audited_pending,status", [
    (0, 0, 0, 0, "matched"), (0, 2, 0, 2, "matched"),
    (1, 2, 1, 2, "matched"), (0, 2, 1, 2, "different"),
    (1, 2, 0, 2, "different"), (0, 2, 0, 1, "different"),
])
def test_reconcile_counts_and_portfolio_blockers(parked, pending, audited_parked, audited_pending, status):
    now = 10000
    observations = {"source": SOURCE, "status": "observed", "observed_at": now - 10,
                    "parked_count": parked, "pending_fleet": {"total": pending, "maintenance": pending, "unclassified": 0}}
    coverage = {"source": "game_roster_and_route_audit", "observed_at": now - 5,
                "roster_observed_at": now - 30, "total": 10 + audited_parked + audited_pending,
                "routes": 10, "parked": audited_parked, "pending": audited_pending}
    result = reconcile_route_coverage(observations, coverage, now=now)
    assert result == {"status": status, "identity_status": "unverified", "native_parked_count": parked, "native_pending_count": pending,
                      "audited_parked_count": audited_parked, "audited_pending_count": audited_pending,
                      "unrouted_or_pending_count": audited_parked + audited_pending}
    report = {"partial_fleet": False, "available_cash": 100, "fleet_route_reconciliation": result}
    blockers = compare_portfolio(report, research_coverage_verified=True)["blocking_reasons"]
    assert ("aeronaves_sem_rota_a_resolver" in blockers) == (max(parked, audited_parked) > 0)
    assert ("contagens_frota_divergentes" in blockers) == (status == "different")
    assert "pedidos_pendentes_a_conciliar" in blockers


def test_reconciliation_rejects_stale_partial_and_noncontemporaneous_evidence():
    now = 10000
    observations = {"source": SOURCE, "status": "observed", "observed_at": now - 10,
                    "parked_count": 1, "pending_fleet": {"total": 2, "maintenance": 2, "unclassified": 0}}
    coverage = {"source": "game_roster_and_route_audit", "observed_at": now - 5,
                "roster_observed_at": now - 30, "total": 13, "routes": 10, "parked": 1, "pending": 2}
    for invalid in (None, {**coverage, "parked": True}, {**coverage, "total": 14},
                    {**coverage, "roster_observed_at": now - 901}, {**coverage, "observed_at": now + 1}):
        result = reconcile_route_coverage(observations, invalid, now=now)
        assert result["status"] == "native_only"
        assert result["audited_parked_count"] is None
        blockers = compare_portfolio({"fleet_route_reconciliation": result})["blocking_reasons"]
        assert "aeronaves_sem_rota_a_resolver" in blockers
        assert "aeronaves_sem_rota_a_confirmar" in blockers
    assert reconcile_route_coverage(observations, {**coverage, "roster_observed_at": now - 200}, now=now)["status"] == "not_contemporaneous"
    for invalid in ({}, {**observations, "observed_at": now - 901}, {**observations, "parked_count": False}):
        result = reconcile_route_coverage(invalid, coverage, now=now)
        assert result["status"] != "matched"
        assert result["native_parked_count"] is None
        assert result["audited_parked_count"] == 1
    assert reconcile_route_coverage({}, None, now=now)["status"] == "unverified"


def test_hub_snapshot_only_reconciles_verified_current_roster(tmp_path):
    now = 10000
    (tmp_path / FILENAME).write_text(json.dumps({"source": SOURCE, "observed_at": now - 10,
        "parked_count": 0, "pending_fleet": {"total": 1, "maintenance": 1, "unclassified": 0}}), encoding="utf-8")
    coverage = {"source": "game_roster_and_route_audit", "observed_at": now - 5,
                "roster_observed_at": now - 30, "total": 2, "routes": 1, "parked": 0, "pending": 1}
    routes = {"current_roster_available": True, "current_fleet_coverage_verified": True,
              "current_relations": [{"aircraft_id": "12345678"}, {"aircraft_id": "23456789"}], "fleet_coverage": coverage}
    registry = HubRegistry(tmp_path / "hubs.json")
    snapshot = registry.snapshot(routes, now=now)
    assert snapshot["fleet_route_reconciliation"]["status"] == "matched"
    assert snapshot["partial_fleet"] is True
    assert "12345678" not in json.dumps(snapshot["fleet_route_reconciliation"])
    snapshot = registry.snapshot({**routes, "current_fleet_coverage_verified": False}, now=now)
    assert snapshot["fleet_route_reconciliation"]["status"] == "native_only"


def test_long_audit_requires_native_read_bracketed_near_final_roster():
    now = 10000
    observations = {"source": SOURCE, "status": "observed", "observed_at": now - 35,
                    "observed_until": now - 10, "parked_count": 0,
                    "pending_fleet": {"total": 2, "maintenance": 2, "unclassified": 0}}
    coverage = {"source": "game_roster_and_route_audit", "observed_at": now - 5,
                "roster_observed_at": now - 600, "total": 12, "routes": 10, "parked": 0, "pending": 2}
    assert reconcile_route_coverage(observations, coverage, now=now)["status"] == "matched"
    for changes in ({"observed_at": now - 150, "observed_until": now - 50},
                    {"observed_at": now - 4, "observed_until": now - 1},
                    {"observed_until": now - 2}):
        assert reconcile_route_coverage({**observations, **changes}, coverage, now=now)["status"] == "not_contemporaneous"
    for changes in ({"observed_until": True}, {"observed_until": now + 1}, {"observed_until": now - 36}):
        assert reconcile_route_coverage({**observations, **changes}, coverage, now=now)["status"] == "audit_only"


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
const openParked = new Function(""" + json.dumps(_OPEN_PARKED_JS) + """);
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
const navigation = [];
const button = {get textContent(){return `${kind} (${total})`},
  getAttribute:()=>`Ajax('fleet_${kind}.php','routesContainer',this);`,
  getClientRects:()=>[{}], click:()=>navigation.push('clicked')};
const statusCell = label => ({childNodes:[{nodeType:3,textContent:label}],
  querySelectorAll:selector=>selector==='span.hasCountdown'?[{}]:[]});
const pendingRow = (id, ...labels) => ({id:`routeMainPendingList${id}`,
  querySelectorAll:selector=>selector==='.row.p-2 > .col-6'?labels.map(statusCell):[]});
const panel = {querySelector:()=>null, children:[cell('2 AIRCRAFT'),
  pendingRow('101','Pending maintenance:'), pendingRow('102','Pending delivery:'), {tagName:'SCRIPT'}],
  replaceChildren:()=>navigation.push('cleared')};
global.window = {jQuery:{active:0}};
global.document = {querySelectorAll:key=>({'#maintAction':[hg], '#routesContainer':[panel],
  '#popup #routesContainer':[panel], '#popup #routeAction button.listBtns[onclick]':[button],
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
assert.deepEqual(pending(), {total:2,rows:[{id:'101',status:'maintenance'},{id:'102',status:'delivery'}]});
panel.children[2]=pendingRow('102','Entrega pendente:');
assert.equal(pending().rows[1].status,'delivery');
panel.children[2]=pendingRow('102','Pending delivery:','Pending maintenance:');
assert.equal(pending().rows[1].status,'unclassified');
panel.children[2]=pendingRow('102','Other status');
assert.equal(pending().rows[1].status,'unclassified');
total=3; assert.equal(pending(),null);
assert.equal(openParked(),false);
kind='parked'; total=0; panel.children=[cell('0 AIRCRAFT'),cell('THERE ARE NO PARKED AIRCRAFT'),{tagName:'SCRIPT'}];
assert.equal(openParked(),true);
assert.deepEqual(navigation,['cleared','clicked']);
assert.deepEqual(parked(), {total:0,rows:[]});
panel.children=[cell('0 AIRCRAFT')]; assert.equal(parked(),null);
window.jQuery.active=1; assert.equal(hangar(),null); assert.equal(parked(),null);
""", encoding="utf-8")
    subprocess.run(["node", str(script)], check=True)
