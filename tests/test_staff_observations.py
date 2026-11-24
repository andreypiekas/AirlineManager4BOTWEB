import json
import shutil
import subprocess
import time

import pytest

import game_observations
from hub_registry import HubRegistry
from staff_observations import (
    FILENAME, SOURCE, STAFF_JS, collect_staff_observations, parse_staff, salary_reference,
    staff_snapshot, validate_staff,
)


RAW = {"pilot_main": {"header": "10 PILOTS", "salary": "$ 100 / $ 1,000"},
       "crew_main": {"header": "20 CREW", "salary": "$ 200 / $ 4,000"},
       "engineer_main": {"header": "5 ENGINEERS", "salary": "$ 300 / $ 1,500"},
       "tech_main": {"header": "0 TECHNICIANS", "salary": "$ 400 / $ 0"}}
STAFF = {role: {"count": count, "daily_rate": rate, "daily_total": count * rate}
         for role, count, rate in (("pilots", 10, 100), ("cabin_crew", 20, 200),
                                   ("engineers", 5, 300), ("technicians", 0, 400))}


def test_strict_staff_parsing():
    assert parse_staff(RAW) == STAFF
    assert parse_staff({**RAW, "pilot_main": {"header": "10 PILOTOS", "salary": "$ 100 / $ 1.000"}}) == STAFF
    for header, salary in (("10 CREW", "$ 100 / $ 1,000"), ("10 PILOTS", "$ 100 / $ 100"),
                           ("10 PILOTS", "$ 100 / $ 1,00"), ("10 PILOTS", "$ -100 / $ 1,000")):
        assert parse_staff({**RAW, "pilot_main": {"header": header, "salary": salary}}) is None
    assert parse_staff({key: value for key, value in RAW.items() if key != "tech_main"}) is None
    assert validate_staff({**STAFF, "technicians": {"count": False, "daily_rate": 400, "daily_total": 0}}) is None


def test_reference_is_conditional_and_expires():
    now = 1800000000
    observed = {"status": "observed", "source": SOURCE, "observed_at": now - 20, "staff": STAFF}
    detail = {"model_identity_verified": True, "observed_at": now - 30,
              "operational_requirements": {"delivery_seconds": 30, "pilots": 2, "cabin_crew": 4,
                                           "engineers": 2, "technicians": 1}}
    assert salary_reference(observed, detail, now=now) == {
        "source": SOURCE, "observed_at": now - 20, "expires_at": now + 880,
        "daily_salary_if_all_additional": 2000, "incremental_cost_verified": False}
    assert salary_reference(observed, detail, now=now + 881) is None
    assert salary_reference(observed, {**detail, "model_identity_verified": False}, now=now) is None
    assert salary_reference(observed, {**detail, "observed_at": now - 259201}, now=now) is None


class Bot:
    stopping = False

    def __init__(self):
        self.calls = []

    def open_popup(self, url, *_):
        self.calls.append(url)

    def close_popup(self, quiet):
        self.calls.append("close")


def test_collection_is_private_profile_local_and_invalidates_old_observation(tmp_path, monkeypatch):
    path = tmp_path / FILENAME
    bot = Bot()
    monkeypatch.setattr(game_observations, "_stable_read", lambda _, script: {STAFF_JS: RAW}[script])
    assert collect_staff_observations(bot, path=path)
    assert bot.calls == ["staff.php?nav=1", "close"]
    assert staff_snapshot(path)["staff"] == STAFF
    assert HubRegistry(tmp_path / "hubs.json").snapshot({"relations": []})["staff_observations"]["staff"] == STAFF
    assert staff_snapshot(path, now=time.time() + 901)["staff"] is None
    assert staff_snapshot(tmp_path / "other" / FILENAME)["staff"] is None
    monkeypatch.setattr(game_observations, "_stable_read", lambda *_: None)
    assert not collect_staff_observations(bot, path=path)
    assert staff_snapshot(path)["status"] == "unverified"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required for DOM contract")
def test_native_staff_dom(tmp_path):
    script = tmp_path / "staff.js"
    script.write_text("const read = new Function(" + json.dumps(STAFF_JS) + ");\n" + r"""
const assert = require('node:assert/strict');
const raw = """ + json.dumps(RAW) + r""";
const visible = () => [{}];
const cards = Object.fromEntries(Object.entries(raw).map(([key,value]) => {
  const row = {children:[{innerText:'Salary'},{innerText:value.salary}],getClientRects:visible};
  return [key,{getClientRects:visible,previousElementSibling:{innerText:value.header,
    classList:{contains:key=>key==='font-weight-bold'},getClientRects:visible},
    querySelectorAll:key=>key==='table tr'?[row]:[]}];
}));
const root = {innerText:'Daily salary',getClientRects:visible,querySelector:()=>null,
  querySelectorAll:key=>cards[key.slice(1)]?[cards[key.slice(1)]]:[]};
global.document = {querySelectorAll:key=>key==='#popup'?[root]:[]};
global.window = {jQuery:{active:0}};
assert.deepEqual(read(),raw);
window.jQuery.active=1; assert.equal(read(),null);
window.jQuery.active=0; root.innerText='Company'; assert.equal(read(),null);
root.innerText='Daily salary'; cards.crew_main.getClientRects=()=>[]; assert.equal(read(),null);
""", encoding="utf-8")
    subprocess.run(["node", str(script)], check=True, capture_output=True, text=True)
