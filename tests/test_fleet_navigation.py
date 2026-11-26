"""Fleet management restores the routes screen after duplicate research."""

import fleet
import fleet_commitment_observations
import parked_route_quote
import pytest
import route_registry
from route_registry import RouteRegistry


def test_route_creation_restores_routes_screen_after_duplicate_research(monkeypatch):
    class Config:
        def get_int(self, section, key, default):
            return 2

        def get_bool(self, section, key, default=False):
            return key == "auto_route"

    class Bot:
        config = Config()
        screen = None

        def open_popup(self, url, title, selector):
            assert (url, title, selector) == ("routes_main.php", "Routes", "nav_routes")
            self.screen = "routes"

        def js(self, script):
            return "1" if "hParked" in script else "0"

        def update_stats(self, **kwargs):
            pass

        def close_popup(self):
            self.screen = None

    bot = Bot()
    monkeypatch.setattr(fleet, "measure_load", lambda bot: None)
    monkeypatch.setattr(fleet, "audit_routes", lambda bot, registry: None)
    monkeypatch.setattr(fleet, "RouteRegistry", lambda: object())

    def research(bot, registry, budget, *, reroute_ready):
        assert reroute_ready
        assert bot.screen == "routes"
        bot.screen = "aircraft_details"
        return 0

    def create(bot, budget):
        assert bot.screen == "routes", "parked aircraft require the routes container"
        assert budget == 2
        return 0

    monkeypatch.setattr(fleet, "resolve_duplicate_routes", research)
    monkeypatch.setattr(fleet, "create_routes", create)
    fleet.manage_fleet(bot)


@pytest.mark.parametrize(
    "changed, reroute_ready, verified, collect_quotes, observation_only, pending_creation", [
        (False, True, True, True, False, False),
        (False, True, True, False, False, False),
        (True, True, False, True, False, False),
        (True, True, False, False, False, False),
        (False, False, False, True, False, False),
        (False, False, False, False, False, False),
        (False, True, True, False, True, False),
        (False, False, False, False, True, False),
        (False, False, False, False, True, True),
])
def test_planning_cycle_correlates_live_route_roster_before_and_after_audit(
        tmp_path, monkeypatch, changed, reroute_ready, verified, collect_quotes, observation_only, pending_creation):
    registry = RouteRegistry(tmp_path / "routes.json")

    class Config:
        def get_bool(self, section, key, default=False):
            return {"planning_enabled": not observation_only, "collect_market_observations": collect_quotes,
                    "auto_route": observation_only, "autobuy_aircraft": observation_only,
                    "allow_duplicate_routes": not observation_only}.get(key, default)

        def get_int(self, section, key, default):
            return default

    class Bot:
        config = Config()
        stopping = False
        roster_reads = 0
        events = []
        screen = None

        def open_popup(self, *args):
            self.screen = args[0]

        def close_popup(self):
            self.screen = None

        def _guard(self, action, what):
            action()

        def update_stats(self, **kwargs):
            pass

        def js(self, script):
            if script == fleet._GAME_FLEET_COUNTS_JS:
                return {"routes": 1, "parked": 1, "pending": 0}
            if script == fleet._GAME_ROSTER_JS:
                assert self.screen == "routes_main.php"
                self.events.append("roster")
                self.roster_reads += 1
                route_id = 999 if changed and self.roster_reads == 2 else 801
                return [{"aircraft_id": "101", "registration": "PP-101", "route_id": route_id},
                        {"aircraft_id": "102", "registration": "PP-102", "route_id": 0}]
            if script == fleet._ROUTE_AUDIT_JS:
                return [{"aircraft_id": "101", "registration": "PP-101", "route_id": 801,
                         "model": "A320", "origin_code": "XAP", "destination_code": "GRU",
                         "scan_page": 1, "scan_total_pages": 1, "scan_route_count": 1}]
            raise AssertionError("unexpected game observation")

    monkeypatch.setattr(route_registry, "registry_file", lambda: registry.path)
    monkeypatch.setattr(fleet, "measure_load", lambda bot: None)
    def unexpected(*args, **kwargs):
        pytest.fail("observation mode reached a fleet write path")

    if observation_only:
        monkeypatch.setattr(fleet, "recover_pending_creation", unexpected)
        monkeypatch.setattr(fleet, "recover_pending", unexpected)
        monkeypatch.setattr(fleet, "_manage_fleet_actions", unexpected)
    else:
        monkeypatch.setattr(fleet, "recover_pending", lambda bot, registry: reroute_ready)
    monkeypatch.setattr(fleet, "has_pending_reroute", lambda: not reroute_ready and not pending_creation)
    monkeypatch.setattr(fleet, "has_pending_creation", lambda: pending_creation)
    monkeypatch.setattr(RouteRegistry, "next_flight_read_ids", lambda self, **kwargs: [])

    def collect(bot, *, identity_evidence):
        assert bot.events == ["roster"]
        bot.events.append("native_lists")
        identity_evidence["parked_ids"] = frozenset({"102"})
        bot.close_popup()
        return True

    def quote(bot, parked_ids, *, refresh_demand):
        assert parked_ids == {"102"}
        assert bot.screen == "routes_main.php"
        assert refresh_demand is observation_only
        bot.events.append("quote")

    monkeypatch.setattr(fleet_commitment_observations, "collect_fleet_commitment_observations", collect)
    monkeypatch.setattr(parked_route_quote, "collect_parked_route_quote", quote)
    bot = Bot()
    fleet.manage_fleet(bot, observation_only=observation_only)
    assert registry.snapshot()["current_fleet_coverage_verified"] is verified
    assert bot.roster_reads == (2 if reroute_ready else 1)
    expected = ["roster", "native_lists"]
    if reroute_ready:
        expected.append("roster")
        if collect_quotes or observation_only:
            expected.append("quote")
    assert bot.events == expected
