"""Fleet management restores the routes screen after duplicate research."""

import fleet


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
