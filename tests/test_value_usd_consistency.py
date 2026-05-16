"""全库：持仓表换算美元后应与 KPI 总市值一致。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from thirteenf.db import init_db
from thirteenf.gui.analytics import compute_kpis_for_filing
from thirteenf.gui.institutions import apply_value_to_usd_column, ingest_value_sum_usd
from thirteenf.value_scale import value_usd_multiplier


@pytest.fixture(scope="module")
def conn():
    db = Path("data/13f_history.sqlite")
    if not db.is_file():
        pytest.skip("no local db")
    init_db(db)
    cx = sqlite3.connect(db)
    cx.row_factory = sqlite3.Row
    yield cx
    cx.close()


def test_holdings_sum_matches_kpi_aum(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, filer_cik FROM ingest_record WHERE status='complete'"
    ).fetchall()
    assert rows, "need at least one complete ingest"
    tol = 1.0  # USD
    for row in rows:
        iid = int(row["id"])
        cik = str(row["filer_cik"])
        df = conn.execute(
            "SELECT value_as_reported FROM holding_line WHERE ingest_id=?",
            (iid,),
        ).fetchall()
        if not df:
            continue
        import pandas as pd

        holdings = pd.DataFrame([{"value_as_reported": r[0]} for r in df])
        holdings_usd = apply_value_to_usd_column(holdings, conn, iid)
        sum_lines = float(holdings_usd["value_as_reported"].sum())
        sum_fn = ingest_value_sum_usd(conn, iid)
        assert abs(sum_lines - sum_fn) <= tol, f"ingest {iid} line sum vs ingest_value_sum_usd"
        k = compute_kpis_for_filing(conn, cik, iid)
        if k.get("ok") and k.get("aum_usd") is not None:
            assert abs(sum_fn - float(k["aum_usd"])) <= tol, f"ingest {iid} aum vs sum"


def test_berkshire_alphabet_net_buy_is_billions_not_trillions(
    conn: sqlite3.Connection,
) -> None:
    row = conn.execute(
        """
        SELECT id FROM ingest_record
        WHERE filer_cik='0001067983' AND report_date='2026-03-31' AND status='complete'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        pytest.skip("berkshire 2026-03-31 not in db")
    k = compute_kpis_for_filing(conn, "0001067983", int(row["id"]))
    buy = k.get("buy_usd")
    assert buy is not None
    assert 1e9 <= buy <= 50e9, f"expected ~10B net buy, got {buy}"
