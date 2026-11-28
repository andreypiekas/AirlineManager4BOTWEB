"""Hub acquisition decisions require a recent, game-observed balance."""
from types import SimpleNamespace

import pytest

from dashboard import last_money, recent_verified_money
from web import WebDashboard


class CashBot:
    def __init__(self, money, observed_at):
        self._stats = SimpleNamespace(money=money, money_read_at=observed_at)

    def stats(self):
        return self._stats


def test_recent_game_balance_is_available():
    bot = CashBot(10000, 2000)
    assert recent_verified_money(bot, now=2100) == (10000, 2000.0)


def test_saved_money_sample_is_visible_but_cannot_qualify_investments():
    bot = CashBot(None, None)
    state = {"money_samples": [[1000, 15000], [2000, 22000]]}
    assert last_money(bot, state) == 22000
    assert recent_verified_money(bot, now=2100) == (None, None)


@pytest.mark.parametrize("money,observed_at", [
    (40000, 3000), (50000, None), (50000, 1000), (True, 1990),
    (50000.0, 1990), (50000.5, 1990), (-1, 1990), (float("inf"), 1990),
    (50000, True), (50000, float("inf")),
])
def test_invalid_or_unverified_money_is_not_available_for_investment(money, observed_at):
    assert recent_verified_money(CashBot(money, observed_at), now=2000) == (None, None)


def test_verified_zero_cash_is_valid():
    assert recent_verified_money(CashBot(0, 1990), now=2000) == (0, 1990.0)


def test_hub_api_exposes_cash_verification_time_and_omits_stale_money(monkeypatch):
    import web

    called = {}

    class Registry:
        def snapshot(self, **kwargs):
            called.update(kwargs)
            return {"candidates": []}

    monkeypatch.setattr(web, "HubExpansionRegistry", Registry)
    snapshot_id = "sha256:" + "a" * 64
    monkeypatch.setattr(web, "snapshot_summary", lambda: {"status": "parcial", "snapshot_id": snapshot_id})
    monkeypatch.setattr(web, "load_state", lambda: {"money_samples": [[2990, 90000]]})
    monkeypatch.setattr("dashboard.time.time", lambda: 3000)
    fake = SimpleNamespace(bot=CashBot(10000, 1000),
                           hubs=lambda: {"hubs": [{"id": "1"}]},
                           cfg=SimpleNamespace(get_int=lambda *args: 2000))

    response = WebDashboard.hub_expansion(fake)
    assert called == {"cash": None, "reserve": 2000, "owned_hub_ids": {"1"},
                      "external_ownership_verified": False}
    assert response["cash_observed_at"] is None
    assert response["planning_snapshot_id"] == snapshot_id
    assert response["expansion_decision"]["status"] == "inconclusivo"
    assert "snapshot_produtivo_hubs_proprios_nao_comprovado" in response["expansion_decision"]["blocking_reasons"]

    fake.bot = CashBot(8000, None)
    response = WebDashboard.hub_expansion(fake)
    assert called["cash"] is None
    assert response["cash_observed_at"] is None

    WebDashboard.hub_expansion(fake, owned_inventory={"hubs": [{"id": "1"}], "hub_catalog_fresh": True})
    assert called["external_ownership_verified"] is True


@pytest.mark.parametrize("live_ids,live_fresh,expected_ids,reconciled", [
    (("11",), True, {"11"}, True),
    (("12",), False, {"11"}, True),
    (("12",), True, {"11", "12"}, False),
])
def test_expansion_uses_captured_ownership_until_fresh_inventory_disagrees(
    monkeypatch, live_ids, live_fresh, expected_ids, reconciled,
):
    import web

    snapshot_id = "sha256:" + "b" * 64
    profile_id = web.paths.current().label
    scope = {"profile_id": profile_id, "snapshot_id": snapshot_id}
    captured = {**scope, "source": "game_hub_select", "observed_at": 2980,
                "hubs": [{"id": "11"}], "hub_catalog_fresh": True, "partial_fleet": True}
    live = {"hubs": [{"id": hub_id} for hub_id in live_ids], "hub_catalog_fresh": live_fresh}
    research = {**scope, "portfolio": scope, "opportunity_coverage": scope}
    monkeypatch.setattr(web, "snapshot_summary", lambda: {
        "status": "parcial", "snapshot_id": snapshot_id, "owned_inventory": captured,
    })
    monkeypatch.setattr("dashboard.time.time", lambda: 3000)
    called = {}

    def expansion_snapshot(**kwargs):
        called.update(kwargs)
        return {"candidates": []}

    monkeypatch.setattr(web, "HubExpansionRegistry", lambda: SimpleNamespace(snapshot=expansion_snapshot))
    fake = SimpleNamespace(bot=CashBot(8000, 2990), cfg=SimpleNamespace(get_int=lambda *args: 2000))

    result = WebDashboard.hub_expansion(fake, owned_inventory=live, owned_research=research)

    assert called["owned_hub_ids"] == expected_ids
    assert called["external_ownership_verified"] is reconciled
    assert result["planning_snapshot_id"] == snapshot_id
    assert result["planning_owned_inventory"] == (captured if reconciled else None)
    decision = result["expansion_decision"]
    assert decision["status"] == "inconclusivo"
    assert "cobertura_frota_incompleta" in decision["blocking_reasons"]
    assert ("inventario_hubs_proprios_a_confirmar" not in decision["blocking_reasons"]) is reconciled
