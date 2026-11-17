"""Read-only classification of the native AM4 departure response."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from fleet_single_depart import _confirm_inflight
from routes_list_depart import _DEPART_FEEDBACK_JS, _reply_observer


@pytest.mark.parametrize("reply,reason", [
    ("Not enough CO2 quotas to depart", "co2_insuficiente"),
    ("Not enough fuel in storage", "combustivel_insuficiente"),
    ("Aircraft needs maintenance before departure", "manutencao"),
    ("The company is subject to audit", "auditoria"),
    ("Insufficient funds to depart", "saldo_insuficiente"),
    ("Too many requests, please try again", "limite_temporario"),
    ("Unable to depart the aircraft", "recusa_generica"),
    ("Departure processed successfully", "nao_informado"),
    ("", "nao_informado"),
])
def test_response_is_categorized_without_returning_raw_text(reply, reason):
    if not shutil.which("node"):
        pytest.skip("Node.js not installed")
    code = (
        "const txt = " + json.dumps(reply) + ";\n"
        "const document = {getElementById: n => n === 'runme' ? "
        "{id:'runme',innerText:txt} : null, querySelectorAll: () => []};\n"
        "console.log(JSON.stringify(new Function(" + json.dumps(_DEPART_FEEDBACK_JS) +
        ")()));\n"
    )
    r = subprocess.run(["node", "-"], input=code, capture_output=True,
                       text=True, check=False)
    assert r.returncode == 0, r.stderr
    parsed = json.loads(r.stdout)
    assert parsed["reason"] == reason
    assert "text" not in parsed
    if reply:
        assert reply not in str(parsed)


def test_poll_ignores_old_game_message_and_remembers_new_one():
    class Bot:
        def js(self, script):
            return {"fingerprint": "original", "reason": "manutencao"}

    class Driver:
        def __init__(self):
            self.response = {
                "fingerprint": "original",
                "reason": "manutencao",
            }

        def execute_script(self, script):
            return self.response

    hint, sample = _reply_observer(Bot())
    d = Driver()
    sample(d)
    assert hint["reason"] == "nao_informado"
    d.response = {"fingerprint": "novo", "reason": "combustivel_insuficiente"}
    sample(d)
    assert hint["reason"] == "combustivel_insuficiente"


def test_inflight_confirmation_can_observe_readonly_feedback():
    seen = []

    class Driver:
        def execute_script(self, script, *args):
            assert "inflightList" in script
            assert args == ("101",)
            return True

    class Bot:
        driver = Driver()

    assert _confirm_inflight(
        Bot(), "101", on_poll=lambda driver: seen.append(driver)
    )
    assert len(seen) == 1
