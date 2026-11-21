"""Overview indicators distinguish the current game roster from historical records."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


HTML = (Path(__file__).resolve().parents[1] / "assets/web/index.html").read_text(encoding="utf-8")


def test_overview_has_compact_events_and_operational_metrics():
    for indicator in ("insightIncome", "insightRoutes", "insightDuplicates",
                      "insightDepartures", "insightCycle", "insightTrust"):
        assert HTML.count(f'id="{indicator}"') == 1
    assert 'msg.className = "log-message"' in HTML
    assert 'msg.setAttribute("aria-expanded", String(expanded))' in HTML
    assert "#log > div { display: flex;" in HTML
    assert "#log > div.expanded .log-message" in HTML
    assert 'Date.now() - lastOverviewRouteFetch > 60000' in HTML


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js indisponível")
def test_overview_only_shows_route_counts_from_verified_game_roster(tmp_path):
    logic = "let overviewRouteReport = null;" + HTML.split("let overviewRouteReport = null;", 1)[1].split(
        "// ------------------------------------------------------------------ log", 1
    )[0]
    harness = r"""
const assert = require('node:assert/strict');
const elements = new Map();
const $ = id => {
  if (!elements.has(id)) elements.set(id, {
    textContent: '', classList: {toggle: (name, on) => { elements.get(id).highlight = on; }}
  });
  return elements.get(id);
};
const nf = {format: value => String(value)};
const airportLabel = value => value && value.code || '—';
const tr = (message, value) => value === undefined ? message : message.replace('{x}', value);
const timeText = value => String(value);
"""
    assertions = r"""
const rows = [
  {game_route_id: 2, origin: {code: 'XAP'}, destination: {code: 'GRU'}, route_data_stale: false},
  {game_route_id: 3, origin: {code: 'GRU'}, destination: {code: 'DTW'}, route_data_stale: true},
  {game_route_id: 0, route_data_stale: false}
];
const report = {
  current_roster_verified: false, current_roster_available: true,
  current_roster_observed_at: 1740000000, current_relations: rows,
  current_duplicate_routes: 1, current_affected_aircraft: 2, total: 255,
  last_dispatch: {departed: 3, at: 1740000000, simulation: false}
};
renderOverviewRoutes(report);
assert.equal($('insightRoutes').textContent, '—');
assert.equal($('insightDuplicates').textContent, '—');
assert.equal($('insightDuplicates').highlight, false);
assert.match($('insightTrust').textContent, /desatualizada/);
assert.match($('insightTrust').textContent, /255 registros/);
report.current_roster_verified = true;
renderOverviewRoutes(report);
assert.equal($('insightRoutes').textContent, '1');
assert.equal($('insightRoutesDetail').textContent, 'de 2 aeronaves com rota');
assert.equal($('insightDuplicates').textContent, '1');
assert.equal($('insightDuplicates').highlight, true);
assert.equal($('insightDepartures').textContent, '3');
assert.match($('insightTrust').textContent, /Rotas dependem da auditoria/);
"""
    path = tmp_path / "overview-test.cjs"
    path.write_text(harness + logic + assertions, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr
