from types import SimpleNamespace
from threading import Lock
from unittest.mock import Mock

import pytest

from market import buy_thresholds, observed_market_quote, percentile, recent_market_quotes
from bot import Bot, Stats


def test_observe_only_trade_never_reaches_purchase_logic():
    bot = Bot.__new__(Bot)
    bot._stats = Stats()
    bot._stats_lock = Lock()
    bot._sel = lambda key: key
    bot._find = Mock(return_value=SimpleNamespace(text=""))
    bot._text = lambda key, **kwargs: {"fuel_price": "$ 500", "fuel_timer": "00:10:00",
                                       "fuel_holding": "1000", "fuel_free": "9000"}.get(key)
    bot.note_event = Mock()
    bot.config = Mock()
    bot._trade("fuel", allow_purchase=False)
    assert bot.stats().fuel_quote.price == 500
    assert bot.stats().fuel_capacity == 10000
    assert not bot.config.mock_calls
    bot._find.return_value = None
    bot._trade("fuel", allow_purchase=False)
    assert bot.stats().fuel_quote is None


@pytest.mark.parametrize("fuel,co2", [(False, False), (True, False), (False, True), (True, True)])
def test_planning_reads_both_markets_and_respects_purchase_options(monkeypatch, fuel, co2):
    bot = Bot.__new__(Bot)
    bot._stats = Stats()
    bot._stats_lock = Lock()
    settings = {"planning_enabled": True, "collect_market_observations": True,
                "autobuy_fuel": fuel, "autobuy_co2": co2}
    bot.config = SimpleNamespace(get_bool=lambda section, key: settings[key])
    bot.open_popup = Mock()
    bot.close_popup = Mock()
    bot._trade = Mock()
    bot._click = Mock()
    bot._sel = lambda key: key
    bot.driver = Mock()
    monkeypatch.setattr("bot.WebDriverWait", Mock())
    bot._check_market()
    assert [(call.args, call.kwargs) for call in bot._trade.call_args_list] == [
        (("fuel",), {"allow_purchase": fuel}), (("co2",), {"allow_purchase": co2})]
    bot.close_popup.assert_called_once()


def test_current_quote_expires_independently_and_never_uses_purchase_threshold():
    fuel = observed_market_quote("$ 1,234", "00:20:00", "00:19:59", 100, 101)
    co2 = observed_market_quote("$ 105", "00:00:20", "00:00:19", 105, 106)
    stats = SimpleNamespace(fuel_quote=fuel, co2_quote=co2, fuel_buy_at=650, co2_price=10)
    evidence = recent_market_quotes(stats, 107)
    assert evidence["fuel"] == {"price": 1234, "observed_at": 101, "expires_at": 1000,
                                "source": "game_market", "unit": "USD/1000"}
    assert evidence["co2"]["price"] == 105
    assert recent_market_quotes(stats, 124)["co2"] is None
    assert recent_market_quotes(stats, 1000) == {"fuel": None, "co2": None}
    assert recent_market_quotes(SimpleNamespace(fuel_price=700, co2_buy_at=100), 107) == {
        "fuel": None, "co2": None}


@pytest.mark.parametrize("price,before,after,finished", [
    ("$ 100", "00:00:01", "00:29:59", 102),
    ("$ 100", None, "00:01:00", 101),
    ("$ 100", "00:00:02", "00:00:01", 101),
    ("$ 100", "00:01:00", "00:00:59", 160),
    ("$ 100", "00:00:61", "00:00:59", 101),
    ("Price $100 / $200", "00:01:00", "00:00:59", 101),
    ("$ 0", "00:01:00", "00:00:59", 101),
    ("$ 100000", "00:01:00", "00:00:59", 101),
])
def test_ambiguous_or_expired_observations_rejected(price, before, after, finished):
    assert observed_market_quote(price, before, after, 100, finished) is None


def test_percentile_picks_the_nearest_rank():
    prices = [500, 400, 300, 200, 100]
    assert percentile(prices, 0) == 100
    assert percentile(prices, 50) == 300
    assert percentile(prices, 100) == 500


def test_fixed_price_only():
    assert buy_thresholds(650) == (650, None)
    assert buy_thresholds(650, None, 400) == (650, 400)


def test_history_raises_the_buy_threshold_but_not_the_exceptional_one():
    # A week of expensive fuel: buy at the percentile, exceptional only below the fixed good price.
    assert buy_thresholds(650, 900, 850) == (900, 650)


def test_cheap_history_keeps_the_fixed_price_as_buy_threshold():
    assert buy_thresholds(650, 500, 480) == (650, 480)


def test_equal_percentiles_never_make_every_purchase_exceptional():
    # buy_percentile == excellent_percentile used to give buy_at == excellent_at.
    buy_at, excellent_at = buy_thresholds(650, 700, 700)
    assert buy_at == 700
    assert excellent_at == 650
    buy_at, excellent_at = buy_thresholds(650, 650, 650)
    assert (buy_at, excellent_at) == (650, None)


def test_exceptional_is_always_strictly_below_the_buy_threshold():
    for fixed in (0, 100, 650, 1000):
        for history in (None, 50, 650, 900):
            for top in (None, 40, 650, 900):
                buy_at, excellent_at = buy_thresholds(fixed, history, top)
                assert excellent_at is None or excellent_at < buy_at
                assert excellent_at is None or fixed <= 0 or excellent_at <= fixed


def test_without_fixed_price_the_history_alone_decides():
    assert buy_thresholds(0, 900, 800) == (900, 800)
