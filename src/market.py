"""Fuel / CO2 price history and the smart-buy rule.

Prices change every 30 minutes. The market popup embeds the last 10 prices in a
chart call (``fuel_startFuelChart([..])`` / ``co2_startCo2Chart([..])``), so every
visit adds up to 5 hours of history even if the bot was off. The history is kept
in ``data/prices.json`` keyed by 30-minute window.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import paths

WINDOW_SECONDS = 1800
MIN_SAMPLES = 12  # half a day of prices before the percentile rule is trusted


@dataclass(frozen=True)
class MarketQuote:
    price: int
    observed_at: float
    expires_at: float

    def evidence(self, now: float) -> Optional[dict]:
        if not self.observed_at <= now < self.expires_at:
            return None
        return {"price": self.price, "observed_at": self.observed_at,
                "expires_at": self.expires_at, "unit": "USD/1000",
                "source": "game_market"}


def observed_market_quote(price_text: Optional[str], timer_before: Optional[str],
                          timer_after: Optional[str], started: float,
                          finished: float) -> Optional[MarketQuote]:
    """Accept a selected current price only inside a consistent countdown window."""
    price_match = re.fullmatch(r"\s*\$\s*(\d{1,3}(?:,\d{3})+|\d+)\s*", price_text or "")
    if not price_match:
        return None
    price = int(price_match[1].replace(",", ""))
    if not 0 < price < 100000:
        return None

    def countdown(value: Optional[str]) -> Optional[int]:
        match = re.fullmatch(r"\s*(\d{1,2}):([0-5]\d):([0-5]\d)\s*", value or "")
        if not match:
            return None
        h, m, s = map(int, match.groups())
        return h * 3600 + m * 60 + s

    before, after = countdown(timer_before), countdown(timer_after)
    elapsed = finished - started
    if (before is None or after is None or not 1 < after <= before <= WINDOW_SECONDS
            or not 0 <= elapsed < before - 1 or before - after > elapsed + 2
            or elapsed - (before - after) > 2):
        return None
    expires_at = min(started + before - 1, finished + after - 1, started + 900)
    return MarketQuote(price, finished, expires_at) if expires_at > finished else None


def recent_market_quotes(stats: object, now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    return {kind: quote.evidence(now) if isinstance(quote, MarketQuote) else None
            for kind in ("fuel", "co2")
            for quote in (getattr(stats, f"{kind}_quote", None),)}

_CHART_RE = {
    "fuel": re.compile(r"fuel_startFuelChart\(\s*\[([\d,\s]*)\]"),
    "co2": re.compile(r"co2_startCo2Chart\(\s*\[([\d,\s]*)\]"),
}


def chart_prices(html: str, kind: str) -> list[int]:
    """The price series embedded in the market popup, oldest first (last item = current window)."""
    match = _CHART_RE[kind].search(html or "")
    if not match:
        return []
    return [int(item) for item in match.group(1).split(",") if item.strip().isdigit()]


def history_file() -> Path:
    """data/prices.json of the active profile."""
    return paths.current().data / "prices.json"


def percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    index = round(max(0.0, min(100.0, pct)) / 100 * (len(ordered) - 1))
    return ordered[index]


def buy_thresholds(fixed: int, history: Optional[int] = None, top: Optional[int] = None) -> tuple[int, Optional[int]]:
    """(buy at, exceptional at) for one market.

    *fixed* is the configured good price, *history* the buy percentile of the recent prices and *top* the
    exceptional percentile. The buy threshold is the fixed price raised to the history percentile. An
    exceptional price (it may spend all the cash and buy twice in a window) must also beat the fixed good
    price, and it only exists while it is strictly below the buy threshold: with equal percentiles, or in
    a week of expensive fuel, every ordinary purchase would otherwise count as exceptional.
    """
    buy_at = max(fixed, history) if history is not None else fixed
    if top is None:
        return buy_at, None
    excellent_at = min(top, fixed) if fixed > 0 else top
    return buy_at, excellent_at if excellent_at < buy_at else None


class PriceHistory:
    def __init__(self, path: Optional[Path] = None, keep_days: int = 14):
        self.path = Path(path or history_file())
        self.keep_days = keep_days
        self._data: dict[str, dict[str, int]] = {"fuel": {}, "co2": {}}
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for kind in self._data:
            entries = raw.get(kind, {}) if isinstance(raw, dict) else {}
            self._data[kind] = {str(key): int(value) for key, value in entries.items() if str(key).isdigit()}

    def save(self) -> None:
        cutoff = int((time.time() - self.keep_days * 86400) // WINDOW_SECONDS)
        for kind in self._data:
            self._data[kind] = {key: value for key, value in self._data[kind].items() if int(key) >= cutoff}
        try:
            paths.write_atomic(self.path, json.dumps(self._data, indent=0, sort_keys=True))
        except OSError:
            pass

    # ------------------------------------------------------------------ updates
    def add(self, kind: str, price: int, at: Optional[float] = None) -> None:
        key = str(int((at if at is not None else time.time()) // WINDOW_SECONDS))
        self._data[kind][key] = int(price)

    def add_series(self, kind: str, prices: list[int], last_window_start: float) -> None:
        """Store a chart series whose last value belongs to the window starting at *last_window_start*."""
        for offset, price in enumerate(reversed(prices)):
            self.add(kind, price, last_window_start - offset * WINDOW_SECONDS)

    # ------------------------------------------------------------------ queries
    def series(self, kind: str, days: Optional[float] = None) -> list[tuple[int, int]]:
        """[(window start timestamp, price)] oldest first; all of it when *days* is None."""
        cutoff = -1 if days is None else int((time.time() - days * 86400) // WINDOW_SECONDS)
        return sorted((int(key) * WINDOW_SECONDS, price) for key, price in self._data[kind].items() if int(key) >= cutoff)

    def recent(self, kind: str, days: float) -> list[int]:
        cutoff = int((time.time() - days * 86400) // WINDOW_SECONDS)
        return [price for key, price in self._data[kind].items() if int(key) >= cutoff]

    def summary(self, kind: str, days: float, pct: float) -> Optional[dict]:
        prices = self.recent(kind, days)
        if len(prices) < MIN_SAMPLES:
            return None
        return {
            "samples": len(prices),
            "min": min(prices),
            "max": max(prices),
            "median": percentile(prices, 50),
            "threshold": percentile(prices, pct),
        }
