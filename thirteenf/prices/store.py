"""price_daily / price_fetch_meta 读写。"""

from __future__ import annotations

import sqlite3
from datetime import date

from thirteenf.prices.bars import DailyBar

SOURCE_YFINANCE = "yfinance"

def quarter_price_provenance(
    conn: sqlite3.Connection,
    ticker: str,
    q_start: date,
    q_end: date,
) -> tuple[str | None, int | None, str | None]:
    """
    本季行情来源：优先 ``price_fetch_meta`` 最近一次成功记录，否则按 ``price_daily`` 行数最多的 source。
    返回 (source_id, bar_count, fetched_at)。
    """
    sym = str(ticker).strip().upper()
    row = conn.execute(
        """
        SELECT source, row_count, fetched_at
        FROM price_fetch_meta
        WHERE ticker = ? AND from_date = ? AND to_date = ? AND status = 'ok'
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (sym, q_start.isoformat(), q_end.isoformat()),
    ).fetchone()
    if row and row[0]:
        return str(row[0]), int(row[1] or 0) or None, str(row[2]) if row[2] else None

    agg = conn.execute(
        """
        SELECT source, COUNT(DISTINCT trade_date) AS n, MAX(fetched_at) AS fa
        FROM price_daily
        WHERE ticker = ? AND trade_date >= ? AND trade_date <= ?
        GROUP BY source
        ORDER BY n DESC, fa DESC
        LIMIT 1
        """,
        (sym, q_start.isoformat(), q_end.isoformat()),
    ).fetchone()
    if agg and agg[0]:
        return str(agg[0]), int(agg[1] or 0), str(agg[2]) if agg[2] else None
    return None, None, None


def upsert_daily_bars(
    conn: sqlite3.Connection,
    ticker: str,
    bars: list[DailyBar],
    *,
    source: str = SOURCE_YFINANCE,
) -> int:
    sym = str(ticker).strip().upper()
    if not sym or not bars:
        return 0
    conn.executemany(
        """
        INSERT INTO price_daily (
          ticker, trade_date, open, high, low, close, volume, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, trade_date, source) DO UPDATE SET
          open=excluded.open,
          high=excluded.high,
          low=excluded.low,
          close=excluded.close,
          volume=excluded.volume,
          fetched_at=datetime('now')
        """,
        [
            (
                sym,
                b.trade_date,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
                source,
            )
            for b in bars
        ],
    )
    return len(bars)


def record_fetch_meta(
    conn: sqlite3.Connection,
    ticker: str,
    from_date: date,
    to_date: date,
    *,
    status: str,
    row_count: int = 0,
    error_note: str | None = None,
    source: str = SOURCE_YFINANCE,
) -> None:
    sym = str(ticker).strip().upper()
    conn.execute(
        """
        INSERT INTO price_fetch_meta (
          ticker, from_date, to_date, source, status, row_count, error_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, from_date, to_date, source) DO UPDATE SET
          status=excluded.status,
          row_count=excluded.row_count,
          error_note=excluded.error_note,
          fetched_at=datetime('now')
        """,
        (
            sym,
            from_date.isoformat(),
            to_date.isoformat(),
            source,
            status,
            int(row_count),
            error_note,
        ),
    )


def quarter_ohlc_stats(
    conn: sqlite3.Connection,
    ticker: str,
    q_start: date,
    q_end: date,
    *,
    source: str | None = None,
) -> tuple[int, str | None, str | None, float | None, float | None, float | None]:
    """
    返回 (count, min_date, max_date, low_min, high_max, close_on_or_before_end)。
    close_on_or_before_end：<= q_end 的最后一个交易日收盘价。
    source 为 None 时合并所有数据源（按 DISTINCT trade_date 计）。
    """
    sym = str(ticker).strip().upper()
    if source:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   MIN(trade_date) AS dmin,
                   MAX(trade_date) AS dmax,
                   MIN(low) AS lo,
                   MAX(high) AS hi
            FROM price_daily
            WHERE ticker = ? AND source = ?
              AND trade_date >= ? AND trade_date <= ?
            """,
            (sym, source, q_start.isoformat(), q_end.isoformat()),
        ).fetchone()
        close_sql = """
            SELECT close FROM price_daily
            WHERE ticker = ? AND source = ? AND trade_date <= ?
            ORDER BY trade_date DESC LIMIT 1
        """
        close_params = (sym, source, q_end.isoformat())
    else:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT trade_date) AS n,
                   MIN(trade_date) AS dmin,
                   MAX(trade_date) AS dmax,
                   MIN(low) AS lo,
                   MAX(high) AS hi
            FROM price_daily
            WHERE ticker = ?
              AND trade_date >= ? AND trade_date <= ?
            """,
            (sym, q_start.isoformat(), q_end.isoformat()),
        ).fetchone()
        close_sql = """
            SELECT close FROM price_daily
            WHERE ticker = ? AND trade_date <= ?
            ORDER BY trade_date DESC LIMIT 1
        """
        close_params = (sym, q_end.isoformat())

    if not row or int(row[0] or 0) == 0:
        return 0, None, None, None, None, None

    close_row = conn.execute(close_sql, close_params).fetchone()
    close_end = float(close_row[0]) if close_row and close_row[0] is not None else None
    return (
        int(row[0]),
        str(row[1]) if row[1] else None,
        str(row[2]) if row[2] else None,
        float(row[3]) if row[3] is not None else None,
        float(row[4]) if row[4] is not None else None,
        close_end,
    )
