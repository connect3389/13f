"""按需拉取并写入季内日线。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from thirteenf.report_period import calendar_quarter_bounds, parse_report_date
from thirteenf.prices.coverage import QuarterPriceStatus, quarter_price_status
from thirteenf.prices.fetch import fetch_daily_bars, price_fetch_available
from thirteenf.prices.ranges import PriceRange
from thirteenf.prices.store import record_fetch_meta, upsert_daily_bars


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    ticker: str
    row_count: int = 0
    error_note: str | None = None
    range: PriceRange | None = None
    source: str | None = None


def fetch_and_store_quarter_prices(
    conn: sqlite3.Connection,
    ticker: str,
    report_date_raw: object,
) -> FetchResult:
    sym = str(ticker or "").strip().upper()
    report_date = parse_report_date(report_date_raw)
    if not sym or report_date is None:
        return FetchResult(ok=False, ticker=sym or "", error_note="invalid_input")

    if not price_fetch_available():
        return FetchResult(ok=False, ticker=sym, error_note="missing_api_key")

    q_start, q_end = calendar_quarter_bounds(report_date)
    bars, err, source = fetch_daily_bars(sym, q_start, q_end)
    if err or not source:
        record_fetch_meta(
            conn,
            sym,
            q_start,
            q_end,
            status="error",
            row_count=0,
            error_note=err,
            source=source or "yfinance",
        )
        conn.commit()
        return FetchResult(ok=False, ticker=sym, error_note=err, source=source)

    n = upsert_daily_bars(conn, sym, bars, source=source)
    record_fetch_meta(
        conn,
        sym,
        q_start,
        q_end,
        status="ok",
        row_count=n,
        error_note=None,
        source=source,
    )
    conn.commit()

    check = quarter_price_status(conn, sym, report_date)
    if check.status == QuarterPriceStatus.READY and check.range:
        return FetchResult(
            ok=True, ticker=sym, row_count=n, range=check.range, source=source
        )
    return FetchResult(
        ok=n > 0,
        ticker=sym,
        row_count=n,
        error_note=check.detail or "coverage_still_incomplete",
        range=check.range,
        source=source,
    )
