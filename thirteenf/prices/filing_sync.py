"""按报送批量同步季内行情，并记录报送级同步状态。"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from thirteenf.report_period import parse_report_date
from thirteenf.prices.fetch import price_fetch_available
from thirteenf.prices.sync import fetch_and_store_quarter_prices

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilingPriceSyncResult:
    ingest_id: int
    ticker_total: int
    ok: int
    failed: int


def _report_date_key(raw: object) -> str | None:
    d = parse_report_date(raw)
    return d.isoformat() if d else None


def _prior_complete_ingest_id(
    conn: sqlite3.Connection, filer_cik: str, current_ingest_id: int
) -> int | None:
    rows = conn.execute(
        """
        SELECT id FROM ingest_record
        WHERE filer_cik = ? AND status = 'complete'
        ORDER BY report_date ASC, id ASC
        """,
        (str(filer_cik).strip(),),
    ).fetchall()
    ids = [int(r[0]) for r in rows]
    cur = int(current_ingest_id)
    if cur not in ids:
        return None
    pos = ids.index(cur)
    if pos == 0:
        return None
    return ids[pos - 1]


def list_filing_tickers(conn: sqlite3.Connection, ingest_id: int) -> list[str]:
    """本期与上季 complete 持仓中的唯一 Ticker（含已清仓、仅上季有的 CUSIP）。"""
    row = conn.execute(
        "SELECT filer_cik FROM ingest_record WHERE id = ?",
        (int(ingest_id),),
    ).fetchone()
    ingest_ids = [int(ingest_id)]
    if row and row[0]:
        pid = _prior_complete_ingest_id(conn, str(row[0]), int(ingest_id))
        if pid is not None:
            ingest_ids.append(int(pid))
    ph = ",".join("?" * len(ingest_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT UPPER(TRIM(r.ticker))
        FROM holding_line h
        INNER JOIN cusip_ref r ON r.cusip = TRIM(h.cusip)
        WHERE h.ingest_id IN ({ph})
          AND r.ticker IS NOT NULL
          AND TRIM(r.ticker) != ''
        ORDER BY 1
        """,
        ingest_ids,
    ).fetchall()
    out: list[str] = []
    for (sym,) in rows:
        s = str(sym or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def needs_filing_price_sync(conn: sqlite3.Connection, ingest_id: int) -> bool:
    """尚未同步，或报送 report_date 与上次同步记录不一致时需再次同步。"""
    row = conn.execute(
        """
        SELECT report_date, prices_synced_at, prices_sync_report_date
        FROM ingest_record WHERE id = ?
        """,
        (int(ingest_id),),
    ).fetchone()
    if not row:
        return False
    report_date, synced_at, synced_report_date = row[0], row[1], row[2]
    if not synced_at:
        return True
    cur = _report_date_key(report_date)
    prev = _report_date_key(synced_report_date)
    if cur is None:
        return True
    return prev is None or cur != prev


def mark_filing_prices_synced(conn: sqlite3.Connection, ingest_id: int) -> None:
    row = conn.execute(
        "SELECT report_date FROM ingest_record WHERE id = ?",
        (int(ingest_id),),
    ).fetchone()
    rd_key = _report_date_key(row[0]) if row else None
    conn.execute(
        """
        UPDATE ingest_record
        SET prices_synced_at = datetime('now'),
            prices_sync_report_date = ?
        WHERE id = ?
        """,
        (rd_key, int(ingest_id)),
    )


def sync_filing_quarter_prices(
    conn: sqlite3.Connection,
    ingest_id: int,
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> FilingPriceSyncResult:
    """拉取本报送全部 Ticker 的季内日线；失败跳过，最后标记报送已处理。"""
    row = conn.execute(
        "SELECT report_date FROM ingest_record WHERE id = ?",
        (int(ingest_id),),
    ).fetchone()
    if not row:
        return FilingPriceSyncResult(
            ingest_id=int(ingest_id), ticker_total=0, ok=0, failed=0
        )
    if not price_fetch_available():
        return FilingPriceSyncResult(
            ingest_id=int(ingest_id), ticker_total=0, ok=0, failed=0
        )
    report_date = row[0]
    tickers = list_filing_tickers(conn, ingest_id)
    total = len(tickers)
    ok_n = 0
    fail_n = 0

    for i, sym in enumerate(tickers, start=1):
        if on_progress:
            on_progress(i, total, sym)
        result = fetch_and_store_quarter_prices(conn, sym, report_date)
        if result.ok:
            ok_n += 1
        else:
            fail_n += 1
            _log.warning(
                "filing price sync skip %s ingest=%s: %s",
                sym,
                ingest_id,
                result.error_note,
            )

    mark_filing_prices_synced(conn, ingest_id)
    conn.commit()
    return FilingPriceSyncResult(
        ingest_id=int(ingest_id),
        ticker_total=total,
        ok=ok_n,
        failed=fail_n,
    )
