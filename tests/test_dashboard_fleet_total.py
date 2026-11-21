"""The game fleet total includes routed, parked and undelivered aircraft."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from dashboard import fleet_summary
from fleet import _GAME_FLEET_COUNTS_JS
from web import WebDashboard


def stats(**overrides):
    values = {
        "fleet_size": 204, "route_count": 204, "fleet_count_read_at": 1000,
        "parked": 0, "pending": 14, "inflight": 202,
        "hangar_free": 3, "hangar_capacity": 221,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_total_includes_aircraft_awaiting_delivery():
    report = fleet_summary(stats(), now=1001)
    assert report["size"] == 218
    assert report["routes"] == 204
    assert report["pending"] == 14
    assert report["count_verified"] is True
    assert report["count_stale"] is False


def test_parked_aircraft_are_distinct_from_routed_and_pending():
    report = fleet_summary(stats(route_count=197, parked=7, pending=14), now=1001)
    assert report["size"] == 218


def test_missing_or_unreadable_game_counts_remain_partial():
    for changes in ({"route_count": None}, {"fleet_count_read_at": None},
                    {"parked": None}, {"pending": None}, {"route_count": True}):
        report = fleet_summary(stats(**changes), now=1001)
        assert report["size"] == (204 if "pending" in changes and changes["pending"] is None else 218)
        assert report["count_verified"] is False
        assert report["routes"] is None


def test_old_game_read_is_labeled_stale():
    report = fleet_summary(stats(), now=2000)
    assert report["size"] == 218
    assert report["count_stale"] is True


def test_hubs_api_shows_current_fleet_separately_from_historical_routes(monkeypatch):
    import web

    class Registry:
        def snapshot(self, routes):
            assert routes == {"total": 254}
            return {"known_aircraft": 254, "hubs": [], "unconfirmed_aircraft": []}

    monkeypatch.setattr(web, "HubRegistry", Registry)
    dashboard = WebDashboard.__new__(WebDashboard)
    dashboard.bot = SimpleNamespace(stats=lambda: stats())
    dashboard.routes = lambda: {"total": 254}

    report = dashboard.hubs()
    assert report["known_aircraft"] == 254
    assert report["fleet_counts"]["size"] == 218
    assert report["fleet_counts"]["count_verified"] is True


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js indisponível")
def test_game_route_popup_counts_are_read_as_one_snapshot():
    js = r"""
let routeLabel = '204 Routes';
let parkedText = '0';
let pendingText = '14';
const root = {
  querySelectorAll: () => [{get textContent() {return routeLabel;}}],
  querySelector: selector => {
    if (selector === '#hParked') return {get textContent() {return parkedText;}};
    if (selector === '#hPending') return {get textContent() {return pendingText;}};
    return null;
  }
};
globalThis.document = {querySelector: () => root};
const read = new Function(process.argv[1]);
const normal = read();
routeLabel = '0 Rotas';
parkedText = '3';
pendingText = '0';
const parked = read();
routeLabel = 'Indefinido';
const unknown = read();
console.log(JSON.stringify({normal, parked, unknown}));
"""
    output = subprocess.run(["node", "-e", js, _GAME_FLEET_COUNTS_JS],
                            capture_output=True, text=True, check=True, timeout=8)
    values = json.loads(output.stdout)
    assert values == {"normal": {"routes": 204, "parked": 0, "pending": 14},
                      "parked": {"routes": 0, "parked": 3, "pending": 0},
                      "unknown": None}
