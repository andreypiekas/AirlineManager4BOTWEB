"""Hub acquisition decisions require a recent, game-observed balance."""
from types import SimpleNamespace

from dashboard import recent_verified_money
from web import WebDashboard


class CashBot:
    def __init__(self, money, observed_at):
        self._stats = SimpleNamespace(money=money, money_read_at=observed_at)

    def stats(self):
        return self._stats


def test_recent_game_balance_overrides_saved_sample():
    bot = CashBot(10000, 2000)
    assert recent_verified_money(bot, {"money_samples": [[1990, 40000]]}, now=2100) == (10000, 2000.0)


def test_saved_money_sample_is_usable_only_while_recent():
    bot = CashBot(None, None)
    state = {"money_samples": [[1000, 15000], [2000, 22000]]}
    assert recent_verified_money(bot, state, now=2100) == (22000, 2000.0)
    assert recent_verified_money(bot, state, now=3000) == (None, None)


def test_future_or_unverified_money_is_not_available_for_investment():
    now = 2000
    bot = CashBot(40000, 3000)
    state = {"money_samples": [[1990, True], [1990, float("inf")], [2200, 10000]]}
    assert recent_verified_money(bot, state, now=now) == (None, None)
    assert recent_verified_money(CashBot(50000, None), {}, now=now) == (None, None)


def test_hub_api_exposes_cash_verification_time_and_omits_stale_money(monkeypatch):
    import web

    called = {}

    class Registry:
        def snapshot(self, **kwargs):
            called.update(kwargs)
            return {"candidates": []}

    monkeypatch.setattr(web, "HubExpansionRegistry", Registry)
    monkeypatch.setattr(web, "load_state", lambda: {"money_samples": []})
    monkeypatch.setattr("dashboard.time.time", lambda: 3000)
    fake = SimpleNamespace(bot=CashBot(10000, 1000),
                           hubs=lambda: {"hubs": [{"id": "1"}]},
                           cfg=SimpleNamespace(get_int=lambda *args: 2000))

    response = WebDashboard.hub_expansion(fake)
    assert called == {"cash": None, "reserve": 2000, "owned_hub_ids": {"1"},
                      "external_ownership_verified": False}
    assert response["cash_observed_at"] is None

    WebDashboard.hub_expansion(fake, owned_inventory={"hubs": [{"id": "1"}], "hub_catalog_fresh": True})
    assert called["external_ownership_verified"] is True
