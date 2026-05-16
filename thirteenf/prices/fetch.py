"""日线拉取（Yahoo Finance / yfinance）。"""

from __future__ import annotations

import logging
import os
from datetime import date

from thirteenf.prices.bars import DailyBar
from thirteenf.prices.yfinance_provider import (
    fetch_daily_candles_yfinance,
    yfinance_available,
)

_log = logging.getLogger(__name__)


def price_debug_enabled() -> bool:
    return (os.environ.get("PRICE_DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def price_fetch_available() -> bool:
    return yfinance_available()


def fetch_daily_bars(
    ticker: str,
    start: date,
    end: date,
) -> tuple[list[DailyBar], str | None, str | None]:
    """返回 (bars, error_note, source)。成功时 source 为 ``yfinance``。"""
    if not yfinance_available():
        return [], "yfinance_not_installed", None

    sym = str(ticker).strip().upper()
    bars, err = fetch_daily_candles_yfinance(sym, start, end)
    if err:
        if price_debug_enabled():
            _log.warning("yfinance failed %s: %s", sym, err)
        return [], err, None

    if price_debug_enabled():
        _log.info("yfinance ok %s %s..%s rows=%d", sym, start, end, len(bars))
    return bars, None, "yfinance"
