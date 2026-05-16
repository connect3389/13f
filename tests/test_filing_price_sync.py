"""报送级季内行情同步状态。"""

from __future__ import annotations

import sqlite3

from thirteenf.prices.filing_sync import (
    list_filing_tickers,
    mark_filing_prices_synced,
    needs_filing_price_sync,
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE ingest_record (
          id INTEGER PRIMARY KEY,
          filer_cik TEXT NOT NULL,
          report_date TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'complete',
          prices_synced_at TEXT,
          prices_sync_report_date TEXT
        );
        CREATE TABLE holding_line (
          ingest_id INTEGER NOT NULL,
          cusip TEXT
        );
        CREATE TABLE cusip_ref (
          cusip TEXT PRIMARY KEY,
          ticker TEXT
        );
        """
    )
    return conn


def test_needs_sync_when_never_synced() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO ingest_record (id, filer_cik, report_date, status)
        VALUES (1, '0001', '2026-03-31', 'complete')
        """
    )
    conn.commit()
    assert needs_filing_price_sync(conn, 1) is True


def test_needs_sync_when_report_date_changes() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO ingest_record
          (id, filer_cik, report_date, status, prices_synced_at, prices_sync_report_date)
        VALUES (1, '0001', '2026-06-30', 'complete', datetime('now'), '2026-03-31')
        """
    )
    conn.commit()
    assert needs_filing_price_sync(conn, 1) is True


def test_no_sync_needed_when_dates_match() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO ingest_record
          (id, filer_cik, report_date, status, prices_synced_at, prices_sync_report_date)
        VALUES (1, '0001', '2026-03-31', 'complete', datetime('now'), '2026-03-31')
        """
    )
    conn.commit()
    assert needs_filing_price_sync(conn, 1) is False


def test_mark_synced_stores_report_date_key() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO ingest_record (id, filer_cik, report_date, status)
        VALUES (2, '0001', '2026-03-31', 'complete')
        """
    )
    conn.commit()
    mark_filing_prices_synced(conn, 2)
    conn.commit()
    row = conn.execute(
        "SELECT prices_synced_at, prices_sync_report_date FROM ingest_record WHERE id=2"
    ).fetchone()
    assert row[0] is not None
    assert row[1] == "2026-03-31"
    assert needs_filing_price_sync(conn, 2) is False


def test_list_filing_tickers_distinct() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO ingest_record (id, filer_cik, report_date, status)
        VALUES (1, '0001', '2026-03-31', 'complete')
        """
    )
    conn.executemany(
        "INSERT INTO holding_line (ingest_id, cusip) VALUES (?, ?)",
        [(1, "037833100"), (1, "037833100"), (1, "594918104")],
    )
    conn.executemany(
        "INSERT INTO cusip_ref (cusip, ticker) VALUES (?, ?)",
        [("037833100", "AAPL"), ("594918104", "MSFT")],
    )
    conn.commit()
    assert list_filing_tickers(conn, 1) == ["AAPL", "MSFT"]


def test_list_filing_tickers_includes_prior_quarter_for_liquidated() -> None:
    conn = _db()
    conn.executescript(
        """
        INSERT INTO ingest_record (id, filer_cik, report_date, status) VALUES
        (1, '0001', '2025-12-31', 'complete');
        INSERT INTO ingest_record (id, filer_cik, report_date, status) VALUES
        (2, '0001', '2026-03-31', 'complete');
        """
    )
    conn.executemany(
        "INSERT INTO holding_line (ingest_id, cusip) VALUES (?, ?)",
        [(1, "111111111"), (2, "037833100")],
    )
    conn.executemany(
        "INSERT INTO cusip_ref (cusip, ticker) VALUES (?, ?)",
        [("111111111", "OLD"), ("037833100", "AAPL")],
    )
    conn.commit()
    assert list_filing_tickers(conn, 2) == ["AAPL", "OLD"]  # ORDER BY ticker
