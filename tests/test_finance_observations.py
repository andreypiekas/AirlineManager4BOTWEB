import json
import shutil
import subprocess
import time

import pytest

import game_observations
import paths
from expansion_metrics import build_expansion_metrics
from finance_observations import (
    FILENAME, SOURCE, SUMMARY_JS, TRANSACTIONS_JS, collect_finance_observations, finance_snapshot,
    read_aircraft_cash_observation, validate_summary,
)
from hub_registry import HubRegistry
from investment_journal import InvestmentJournal


SAMPLE = {"window_hours": 24, "expenses": 1500, "income": 1000, "result": -500,
          "fuel_expenses": 100, "quota_expenses": 50, "route_fees": 200,
          "aircraft_orders": 900, "hubs": 0, "ticket_income": 1000}


@pytest.mark.parametrize("change", [
    {"window_hours": 48}, {"result": 500}, {"fuel_expenses": -1},
    {"hubs": 300}, {"ticket_income": 1001}, {"hubs": False},
    {"hubs": 0.0}, {"income": 2**53}, {"window_hours": 24.0},
])
def test_invalid_summary(change):
    assert validate_summary({**SAMPLE, **change}) is None


def test_summary_strips_private_fields():
    assert validate_summary({**SAMPLE, "account": "private", "id": "123"}) == SAMPLE


class Bot:
    stopping = False
    _observation_company_id = "123"

    def __init__(self):
        self.calls = []

    def open_popup(self, url, *_):
        self.calls.append(url)

    def ajax(self, url, target):
        self.calls.append((url, target))

    def close_popup(self, quiet):
        self.calls.append("close")


def test_aircraft_cash_observation_distinguishes_maintenance_from_order_receipt(monkeypatch):
    bot = Bot()
    now = time.time()
    pending = {"profile_id": paths.current().label, "company_id": "123",
               "observed_at": now, "observed_until": now, "pending": {"total": 4, "rows": [
                   {"id": "11", "status": "maintenance", "registration": "PP-220"},
                   {"id": "12", "status": "maintenance", "registration": "PP-121-2"},
                   {"id": "13", "status": "delivery", "registration": "PP-254"},
                   {"id": "14", "status": "unclassified"},
               ]}}
    history = [
        {"debit": True, "label": "PP-121-2 Repair", "amount": "-250,929"},
        {"debit": True, "label": "PP-2200 Repair", "amount": "-140"},
        {"debit": True, "label": "Some unrelated expense", "amount": "-51,000"},
        {"debit": False, "label": "Private label", "amount": "910"},
    ]
    monkeypatch.setattr(game_observations, "_stable_read", lambda _, script: {
        TRANSACTIONS_JS: history, SUMMARY_JS: SAMPLE,
    }[script])
    assert read_aircraft_cash_observation(bot, pending, 51000) == {
        "status": "observed", "pending_counts": {"total": 4, "maintenance": 2, "delivery": 1, "unclassified": 1},
        "pending_maintenance": [
            {"registration": "PP-220", "recent_debits": []},
            {"registration": "PP-121-2", "recent_debits": [{"type": "repair", "amount_usd": 250929}]},
        ],
        "recent_transaction_count": 4, "recent_debit_count": 3, "recent_debits_equal_to_checkout": 1,
        "aircraft_order_expenses_24h": 900, "other_expenses_24h": 250,
        "receipt_verified": False, "cash_commitments_verified": False,
    }
    assert bot.calls == ["finances.php", ("transactions.php?mode=summary", "transactionSummaryContainer"), "close"]
    assert read_aircraft_cash_observation(bot, {**pending, "company_id": "789"}, 51000)["pending_counts"] is None
    history[0]["amount"] = "250,929"
    partial = read_aircraft_cash_observation(bot, pending, 51000)
    assert partial["status"] == "partial" and partial["recent_debit_count"] is None
    assert all(row["recent_debits"] is None for row in partial["pending_maintenance"])
    assert partial["receipt_verified"] is False


def test_collector_and_profile_isolation(tmp_path, monkeypatch):
    path = tmp_path / FILENAME
    bot = Bot()
    monkeypatch.setattr(game_observations, "_stable_read", lambda _, script: {
        SUMMARY_JS: {**SAMPLE, "account": "private-account"},
    }[script])
    assert collect_finance_observations(bot, path=path)
    assert bot.calls == ["finances.php", ("transactions.php?mode=summary", "transactionSummaryContainer"), "close"]
    assert "private-account" not in path.read_text(encoding="utf-8")
    report = HubRegistry(tmp_path / "hubs.json").snapshot({"relations": []})["finance_observations"]
    assert report["status"] == "observed"
    assert report["source"] == SOURCE
    assert report["profile_id"] == paths.current().label
    assert report["summary"] == SAMPLE
    assert report["historical_only"] is True
    assert finance_snapshot(path, now=time.time() + 901)["summary"] is None
    assert finance_snapshot(tmp_path / "other" / FILENAME)["summary"] is None
    with monkeypatch.context() as other:
        other.setattr(paths, "current", lambda: paths.Profile("other"))
        assert finance_snapshot(path)["status"] == "unverified"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved.pop("profile_id")
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert finance_snapshot(path)["status"] == "unverified"
    monkeypatch.setattr(game_observations, "_stable_read", lambda *_: None)
    assert not collect_finance_observations(bot, path=path)
    assert finance_snapshot(path)["status"] == "unverified"


def test_metrics_preserve_historical_scope(tmp_path):
    now = time.time()
    journal = InvestmentJournal(tmp_path / "game.sqlite3", profile_id="principal", simulation=False)
    report = {"finance_observations": {"source": SOURCE, "status": "observed", "profile_id": "principal",
                                     "observed_at": now, "summary": SAMPLE}}
    metrics = build_expansion_metrics(journal, now=now, opportunity_report=report)
    assert metrics["company_finance_24h"]["summary"] == SAMPLE
    assert metrics["company_finance_24h"]["historical_only"] is True
    assert metrics["actual_spend"] is None
    assert metrics["verified_deliveries"] is None
    assert metrics["forecast"]["mean_absolute_daily_error"] is None
    expired = build_expansion_metrics(journal, now=now + 901, opportunity_report=report)
    assert expired["company_finance_24h"]["summary"] is None
    simulated = InvestmentJournal(tmp_path / "sim.sqlite3", profile_id="principal", simulation=True)
    assert build_expansion_metrics(simulated, now=now, opportunity_report=report)["company_finance_24h"]["summary"] is None
    report["finance_observations"]["profile_id"] = "other"
    assert build_expansion_metrics(journal, now=now, opportunity_report=report)["company_finance_24h"]["summary"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required for DOM contract")
def test_native_summary_dom(tmp_path):
    script = tmp_path / "finance.js"
    script.write_text("""
const assert = require('node:assert/strict');
const read = new Function(""" + json.dumps(SUMMARY_JS) + """);
const cell = (label, value) => ({firstElementChild:{tagName:'SPAN',textContent:label,
  classList:{contains:key=>key==='text-secondary'}},lastElementChild:{textContent:value}});
const title = {firstElementChild:{textContent:'private-account'},
  lastElementChild:{textContent:'SUMMARY FOR THE LAST 24 HOURS'}};
const cells = [title,cell('Expenses','$ 1,500'),cell('Income','$ 1,000'),cell('Result','$ -500'),
  cell('Fuel expenses','$ 100'),cell('Quota expenses','$ 50'),cell('Route fees','$ 200'),
  cell('A/C Orders','$ 900'),cell('Hubs','$ 0'),cell('Ticket income','$ 1,000')];
const row = {classList:{contains:key=>key==='row'},children:cells};
const root = {getClientRects:()=>[{}],children:[row],firstElementChild:row,querySelector:()=>null};
global.window = {jQuery:{active:0}};
global.document = {querySelectorAll:key=>key==='#financeAction #transactionSummaryContainer'?[root]:[]};
const expected = """ + json.dumps(SAMPLE) + """;
assert.deepEqual(read(),expected);
cells[3].lastElementChild.textContent='- $ 500'; assert.deepEqual(read(),expected);
cells[3].lastElementChild.textContent='$ - 500'; assert.deepEqual(read(),expected);
cells[3].lastElementChild.textContent='$ 500'; assert.equal(read().result,500);
cells[3].lastElementChild.textContent='$ -500';
cells[7].lastElementChild.textContent='$ 9,00'; assert.equal(read(),null);
cells[7].lastElementChild.textContent='$ 900';
cells[7].firstElementChild.textContent='Hubs'; assert.equal(read(),null);
cells[7].firstElementChild.textContent='A/C Orders';
title.lastElementChild.textContent='SUMMARY FOR THE LAST 48 HOURS'; assert.equal(read(),null);
title.lastElementChild.textContent='SUMMARY FOR THE LAST 24 HOURS';
window.jQuery.active=1; assert.equal(read(),null);
window.jQuery.active=0; root.getClientRects=()=>[]; assert.equal(read(),null);
""", encoding="utf-8")
    subprocess.run(["node", str(script)], check=True, capture_output=True, text=True)
