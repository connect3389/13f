"""判断季内行情缓存是否覆盖当前 report_date 所在季度。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from thirteenf.report_period import calendar_quarter_bounds, parse_report_date
from thirteenf.prices.fetch import price_fetch_available
from thirteenf.prices.ranges import PriceRange
from thirteenf.prices.store import quarter_ohlc_stats

# 季初/季末允许缺口（日历日）；换季后旧缓存常只覆盖到上季末
_EDGE_BUFFER_DAYS = 7
# 约 63 个交易日/季，低于此比例视为不完整
_MIN_BARS_RATIO = 0.75
_EXPECTED_BARS_PER_QUARTER = 63


class QuarterPriceStatus(StrEnum):
    READY = "ready"
    MISSING = "missing"
    STALE_RANGE = "stale_range"
    NO_TICKER = "no_ticker"
    NO_API_KEY = "no_api_key"


@dataclass(frozen=True)
class QuarterPriceCheck:
    status: QuarterPriceStatus
    range: PriceRange | None = None
    ticker: str | None = None
    q_start: date | None = None
    q_end: date | None = None
    detail: str | None = None


def _parse_bounds(report_date: date) -> tuple[date, date]:
    start, end = calendar_quarter_bounds(report_date)
    return start, end


def quarter_price_range_from_db(
    conn: sqlite3.Connection,
    ticker: str,
    report_date: date,
    *,
    source: str | None = None,
) -> PriceRange | None:
    q_start, q_end = _parse_bounds(report_date)
    _n, _dmin, _dmax, lo, hi, close_end = quarter_ohlc_stats(
        conn, ticker, q_start, q_end, source=source
    )
    if lo is None or hi is None:
        return None
    return PriceRange(low=lo, high=hi, close_end=close_end)


def quarter_price_status(
    conn: sqlite3.Connection,
    ticker: str | None,
    report_date_raw: object,
    *,
    source: str | None = None,
) -> QuarterPriceCheck:
    report_date = parse_report_date(report_date_raw)
    if report_date is None:
        return QuarterPriceCheck(
            status=QuarterPriceStatus.MISSING,
            detail="invalid_report_date",
        )

    if not price_fetch_available():
        return QuarterPriceCheck(
            status=QuarterPriceStatus.NO_API_KEY,
            q_start=None,
            q_end=None,
            detail="yfinance_not_installed",
        )

    sym = str(ticker or "").strip().upper()
    if not sym or sym in ("—", "NAN"):
        return QuarterPriceCheck(
            status=QuarterPriceStatus.NO_TICKER,
            detail="no_ticker",
        )

    q_start, q_end = _parse_bounds(report_date)
    count, dmin, dmax, lo, hi, close_end = quarter_ohlc_stats(
        conn, sym, q_start, q_end, source=None
    )

    if count == 0:
        return QuarterPriceCheck(
            status=QuarterPriceStatus.MISSING,
            ticker=sym,
            q_start=q_start,
            q_end=q_end,
            detail="no_rows",
        )

    edge = timedelta(days=_EDGE_BUFFER_DAYS)
    if dmin:
        dmin_d = date.fromisoformat(dmin[:10])
        if dmin_d > q_start + edge:
            return QuarterPriceCheck(
                status=QuarterPriceStatus.STALE_RANGE,
                ticker=sym,
                q_start=q_start,
                q_end=q_end,
                detail=f"min_date={dmin}",
            )
    if dmax:
        dmax_d = date.fromisoformat(dmax[:10])
        if dmax_d < q_end - edge:
            return QuarterPriceCheck(
                status=QuarterPriceStatus.STALE_RANGE,
                ticker=sym,
                q_start=q_start,
                q_end=q_end,
                detail=f"max_date={dmax}",
            )

    min_expected = int(_EXPECTED_BARS_PER_QUARTER * _MIN_BARS_RATIO)
    if count < min_expected:
        return QuarterPriceCheck(
            status=QuarterPriceStatus.STALE_RANGE,
            ticker=sym,
            q_start=q_start,
            q_end=q_end,
            detail=f"count={count}",
        )

    if lo is None or hi is None:
        return QuarterPriceCheck(
            status=QuarterPriceStatus.MISSING,
            ticker=sym,
            q_start=q_start,
            q_end=q_end,
            detail="null_ohlc",
        )

    return QuarterPriceCheck(
        status=QuarterPriceStatus.READY,
        ticker=sym,
        q_start=q_start,
        q_end=q_end,
        range=PriceRange(low=lo, high=hi, close_end=close_end),
    )
