"""季内行情覆盖判断与区间格式。"""

from __future__ import annotations

import sqlite3
from datetime import date

from thirteenf.db import init_db
from thirteenf.prices.coverage import QuarterPriceStatus, quarter_price_status
from thirteenf.prices.ranges import PriceRange, format_price_range_label
from thirteenf.prices.bars import DailyBar
from thirteenf.prices.store import SOURCE_YFINANCE, upsert_daily_bars


def _mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE price_daily (
          ticker TEXT NOT NULL,
          trade_date TEXT NOT NULL,
          open REAL, high REAL, low REAL, close REAL, volume REAL,
          source TEXT NOT NULL DEFAULT 'yfinance',
          fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (ticker, trade_date, source)
        );
        CREATE TABLE price_fetch_meta (
          id INTEGER PRIMARY KEY,
          ticker TEXT NOT NULL,
          from_date TEXT NOT NULL,
          to_date TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'yfinance',
          status TEXT NOT NULL,
          row_count INTEGER,
          error_note TEXT,
          fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(ticker, from_date, to_date, source)
        );
        """
    )
    return conn


def _seed_q1_2026(conn: sqlite3.Connection, ticker: str = "AAPL") -> None:
    bars = []
    d = date(2026, 1, 2)
    end = date(2026, 3, 28)
    while d <= end:
        if d.weekday() < 5:
            bars.append(
                DailyBar(
                    trade_date=d.isoformat(),
                    open=100.0,
                    high=110.0,
                    low=90.0,
                    close=105.0,
                    volume=1e6,
                )
            )
        d = date.fromordinal(d.toordinal() + 1)
    upsert_daily_bars(conn, ticker, bars, source=SOURCE_YFINANCE)


def test_quarter_ready_when_covers_report_date() -> None:
    from unittest.mock import patch

    conn = _mem_db()
    _seed_q1_2026(conn)
    with patch("thirteenf.prices.coverage.price_fetch_available", return_value=True):
        check = quarter_price_status(conn, "AAPL", date(2026, 3, 31))
    assert check.status == QuarterPriceStatus.READY
    assert check.range is not None
    assert check.range.low == 90.0
    assert check.range.high == 110.0


def test_stale_when_quarter_end_not_covered() -> None:
    """仅有季初数据、缺季末（换季后仍用旧缓存时）应要求重新拉取。"""
    from unittest.mock import patch

    conn = _mem_db()
    upsert_daily_bars(
        conn,
        "AAPL",
        [
            DailyBar("2026-01-05", 1, 2, 1, 1.5, 1),
            DailyBar("2026-02-10", 1, 2, 1, 1.5, 1),
        ],
    )
    with patch("thirteenf.prices.coverage.price_fetch_available", return_value=True):
        check = quarter_price_status(conn, "AAPL", date(2026, 3, 31))
    assert check.status == QuarterPriceStatus.STALE_RANGE


def test_missing_when_no_rows_in_quarter() -> None:
    from unittest.mock import patch

    conn = _mem_db()
    upsert_daily_bars(
        conn,
        "AAPL",
        [DailyBar("2025-12-30", 1, 2, 1, 1.5, 1)],
    )
    with patch("thirteenf.prices.coverage.price_fetch_available", return_value=True):
        check = quarter_price_status(conn, "AAPL", date(2026, 3, 31))
    assert check.status == QuarterPriceStatus.MISSING


def test_format_price_range_label() -> None:
    s = format_price_range_label(PriceRange(180.5, 220.0, close_end=215.0))
    assert "$180.50" in s
    assert "$220.00" in s
    assert "收" in s
