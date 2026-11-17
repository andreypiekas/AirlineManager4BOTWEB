"""Regression tests for audit-aware AM4 dispatch and safe Fleet diagnostics."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from bot import Bot
from fleet_single_depart import control_diagnostics
from game_audit import _AUDIT_JS, audit_active
from route_registry import RouteRegistry


@pytest.mark.parametrize("visible_text,expected", [
    (
        "AUDIT - Your company is subject to audit. "
        "You will not be able to operate your fleet while being audited.",
        True,
    ),
    ("Welcome back! Your airline is active. All departures are allowed.", False),
    ("Your company is subject to audit. The rules of the airline are available.", False),
])
def test_am4_audit_banner_determined_from_visible_page_text(visible_text, expected):
    if not shutil.which("node"):
        pytest.skip("Node.js required for validating the in-game JS expression")
    code = (
        "const document = {body:{innerText:" + json.dumps(visible_text) + "}};\n"
        "console.log(JSON.stringify(new Function(" + json.dumps(_AUDIT_JS) + ")()));"
    )
    result = subprocess.run(["node", "-"], input=code, capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) is expected


def test_audit_detection_without_a_browser_is_conservative():
    assert audit_active(SimpleNamespace()) is False
    assert audit_active(SimpleNamespace(js=lambda script: True)) is True


def test_audit_blocks_dispatch_before_even_loading_routes(tmp_path, monkeypatch, caplog):
    import bot as module

    registry = RouteRegistry(tmp_path / "routes.json")
    monkeypatch.setattr(module, "RouteRegistry", lambda: registry)

    class Stub:
        dry_run = False

        def js(self, script):
            assert "subject to audit" in script
            return True

        def config(self):
            raise AssertionError("Do not read route rules while under audit")

        def open_popup(self, *args):
            raise AssertionError("Cannot operate Fleet during audit")

    with caplog.at_level("WARNING", logger="am4bot.vuelos"):
        Bot._depart_all(Stub())
    report = registry.snapshot()["last_dispatch"]
    assert report["status"] == "auditoria_ativa"
    assert report["mode"] == "bloqueado_pelo_jogo"
    assert "AUDITORIA ATIVA" in caplog.text


def test_depart_button_diagnostics_redact_signed_urls_and_identify_rejection():
    private = "sensitive-secret-should-not-appear"
    controls = [
        {"label": "Depart", "visible": True, "disabled": True,
         "action": f"Ajax('route_depart.php?mode=all&ids=x&fbSig={private}')"},
        {"label": "Depart", "visible": True, "disabled": False,
         "action": f"Ajax('route_depart.php?mode=single&ids=123&fbSig={private}')"},
        {"label": "Sell", "visible": True, "disabled": False,
         "action": f"other.php?token={private}"},
    ]
    report = control_diagnostics("123", controls)
    assert len(report) == 2
    assert report[0] == {
        "rotulo": "Depart", "visivel": True, "desabilitado": True,
        "modo": "all", "escopo": "alvo_divergente_ou_geral",
    }
    assert report[1]["escopo"] == "alvo_correto"
    assert report[1]["modo"] == "single"
    assert private not in str(report)
