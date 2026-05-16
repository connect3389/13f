"""持仓分析计算与 Streamlit 缓存（无 UI 布局）。"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

import pandas as pd
import streamlit as st

from thirteenf.gui.formatters import fmt_signed_usd, fmt_usd_compact
from thirteenf.gui.institutions import (
    cusip_changes_for_filing,
    ingest_value_sum_usd,
    issuer_for_cusip,
    prior_complete_ingest_id,
    value_by_cusip_usd,
)


def compute_kpis_for_filing(
    conn: sqlite3.Connection, filer_cik: str, ingest_id: int
) -> dict:
    empty: dict = {
        "ok": False,
        "ingest_id": None,
        "date_cur": None,
        "date_prev": None,
        "n_cusips": 0,
        "aum_usd": None,
        "aum_qoq_pct": None,
        "buy_cusip": None,
        "buy_label": None,
        "buy_usd": None,
        "sell_cusip": None,
        "sell_label": None,
        "sell_usd": None,
        "has_prior": False,
    }
    cik = str(filer_cik).strip()
    cid = int(ingest_id)
    if not cik:
        return empty

    meta = conn.execute(
        """
        SELECT id, report_date, status FROM ingest_record
        WHERE id = ? AND filer_cik = ?
        """,
        (cid, cik),
    ).fetchone()
    if not meta or str(meta[2]) != "complete":
        return {**empty, "ingest_id": cid}

    date_cur = str(meta[1]).strip() if meta[1] else None
    cur_v = value_by_cusip_usd(conn, cid)
    n_cusips = len([x for x in cur_v.index if str(x).strip()])
    aum_usd = ingest_value_sum_usd(conn, cid)

    pid = prior_complete_ingest_id(conn, cik, cid)
    if pid is None:
        return {
            **empty,
            "ok": True,
            "ingest_id": cid,
            "date_cur": date_cur,
            "n_cusips": n_cusips,
            "aum_usd": aum_usd,
            "has_prior": False,
        }

    prow = conn.execute(
        "SELECT report_date FROM ingest_record WHERE id = ?",
        (pid,),
    ).fetchone()
    date_prev = str(prow[0]).strip() if prow and prow[0] else None
    prev_usd = ingest_value_sum_usd(conn, pid)

    aum_qoq_pct: float | None = None
    if prev_usd > 0:
        aum_qoq_pct = (aum_usd - prev_usd) / prev_usd * 100.0

    flow_pack = cusip_changes_for_filing(conn, cik, cid)
    flow: dict[str, float] = {}
    ids_lookup = [cid, pid]
    if flow_pack:
        for row in flow_pack[0]:
            flow[row["cusip"]] = row["change_usd"]

    buy_cusip = buy_label = buy_usd = None
    sell_cusip = sell_label = sell_usd = None
    if flow:
        pos = [(k, v) for k, v in flow.items() if v > 0]
        neg = [(k, v) for k, v in flow.items() if v < 0]
        if pos:
            buy_cusip, buy_usd = max(pos, key=lambda x: x[1])
            buy_label = issuer_for_cusip(conn, buy_cusip, ids_lookup)
        if neg:
            sell_cusip, sell_usd = min(neg, key=lambda x: x[1])
            sell_label = issuer_for_cusip(conn, sell_cusip, ids_lookup)

    return {
        "ok": True,
        "ingest_id": cid,
        "date_cur": date_cur,
        "date_prev": date_prev,
        "n_cusips": n_cusips,
        "aum_usd": aum_usd,
        "aum_qoq_pct": aum_qoq_pct,
        "buy_cusip": buy_cusip,
        "buy_label": buy_label,
        "buy_usd": buy_usd,
        "sell_cusip": sell_cusip,
        "sell_label": sell_label,
        "sell_usd": sell_usd,
        "has_prior": True,
    }


@st.cache_data(ttl=30)
def cached_kpis_for_filing(
    db_path: str, db_mtime: float, filer_cik: str, ingest_id: int
) -> dict:
    del db_mtime
    with sqlite3.connect(db_path) as cx:
        cx.row_factory = sqlite3.Row
        return compute_kpis_for_filing(cx, str(filer_cik).strip(), int(ingest_id))


def compute_top_new_positions(
    conn: sqlite3.Connection,
    filer_cik: str,
    ingest_id: int,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    cik = str(filer_cik).strip()
    cid = int(ingest_id)
    if not cik:
        return pd.DataFrame()

    pid = prior_complete_ingest_id(conn, cik, cid)
    if pid is None:
        return pd.DataFrame()

    cur_v = value_by_cusip_usd(conn, cid)
    prev_v = value_by_cusip_usd(conn, pid)
    prev_set = set(prev_v.index)

    items: list[tuple[str, float]] = []
    for cusip, val_usd in cur_v.items():
        c = str(cusip).strip()
        if not c or c in prev_set:
            continue
        vu = float(val_usd or 0)
        if vu <= 0:
            continue
        items.append((c, vu))

    items.sort(key=lambda x: -x[1])
    items = items[: int(top_n)]

    rows: list[dict] = []
    for rank, (cusip, usd) in enumerate(items, start=1):
        issuer = issuer_for_cusip(conn, cusip, [cid])
        r2 = conn.execute(
            """
            SELECT title_of_class FROM holding_line
            WHERE TRIM(cusip) = TRIM(?) AND ingest_id = ?
            ORDER BY COALESCE(value_as_reported, 0) DESC
            LIMIT 1
            """,
            (cusip, cid),
        ).fetchone()
        toc = str(r2[0]).strip() if r2 and r2[0] else ""
        rows.append(
            {
                "rank": rank,
                "cusip": cusip,
                "issuer": issuer,
                "title_of_class": toc,
                "total_value_usd": usd,
            }
        )
    return pd.DataFrame(rows)


def compute_top_holdings_change(
    conn: sqlite3.Connection,
    filer_cik: str,
    ingest_id: int,
    *,
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pack = cusip_changes_for_filing(conn, filer_cik, ingest_id)
    if pack is None:
        return pd.DataFrame(), pd.DataFrame()
    changes, cid, pid = pack

    inc = sorted(
        [r for r in changes if r["change_usd"] > 0],
        key=lambda r: -r["change_usd"],
    )[: int(top_n)]
    dec = sorted(
        [r for r in changes if r["change_usd"] < 0],
        key=lambda r: r["change_usd"],
    )[: int(top_n)]

    def _to_df(rows: list[dict]) -> pd.DataFrame:
        out_rows: list[dict] = []
        for r in rows:
            cusip = r["cusip"]
            issuer = issuer_for_cusip(conn, cusip, [cid, pid])
            out_rows.append(
                {
                    "cusip": cusip,
                    "issuer": issuer,
                    "change_usd": r["change_usd"],
                    "change_label": fmt_signed_usd(r["change_usd"]),
                    "tag": r["tag"],
                }
            )
        return pd.DataFrame(out_rows)

    return _to_df(inc), _to_df(dec)


@st.cache_data(ttl=30)
def cached_top_holdings_change(
    db_path: str,
    db_mtime: float,
    filer_cik: str,
    ingest_id: int,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del db_mtime
    with sqlite3.connect(db_path) as cx:
        cx.row_factory = sqlite3.Row
        return compute_top_holdings_change(
            cx, filer_cik, ingest_id, top_n=int(top_n)
        )


@st.cache_data(ttl=30)
def cached_top_new_positions(
    db_path: str,
    db_mtime: float,
    filer_cik: str,
    ingest_id: int,
    top_n: int,
) -> pd.DataFrame:
    del db_mtime
    with sqlite3.connect(db_path) as cx:
        cx.row_factory = sqlite3.Row
        return compute_top_new_positions(
            cx, filer_cik, ingest_id, top_n=int(top_n)
        )


def compute_sector_flow(
    conn: sqlite3.Connection,
    filer_cik: str,
    ingest_id: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pack = cusip_changes_for_filing(conn, filer_cik, ingest_id)
    if pack is None:
        return pd.DataFrame(), pd.DataFrame()
    changes, _cid, _pid = pack

    flow_by_code: defaultdict[str, float] = defaultdict(float)
    meta_by_code: dict[str, tuple[str, str]] = {}
    contrib: list[dict] = []

    for row in changes:
        cusip = row["cusip"]
        chg = float(row["change_usd"])
        ref = conn.execute(
            """
            SELECT ticker, gics_sector_code, gics_sector_zh, gics_sector_en
            FROM cusip_ref WHERE cusip = ?
            """,
            (cusip,),
        ).fetchone()
        if not ref or not ref[1]:
            continue
        code = str(ref[1]).strip()
        zh = str(ref[2] or "").strip()
        en = str(ref[3] or "").strip()
        flow_by_code[code] += chg
        meta_by_code[code] = (zh, en)
        sym = ref[0]
        ticker = str(sym).strip() if sym else cusip
        contrib.append(
            {
                "gics_sector_code": code,
                "sector_zh": zh,
                "ticker": ticker,
                "change_usd": chg,
            }
        )

    if not flow_by_code:
        return pd.DataFrame(), pd.DataFrame()

    summary_rows = []
    for code, flow in flow_by_code.items():
        zh, en = meta_by_code.get(code, ("", ""))
        summary_rows.append(
            {
                "gics_sector_code": code,
                "sector_zh": zh,
                "sector_en": en,
                "flow_usd": flow,
                "flow_b": flow / 1e9,
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("flow_usd", ascending=False)
    detail = pd.DataFrame(contrib)
    if not detail.empty:
        detail = detail.sort_values(
            ["sector_zh", "change_usd"], ascending=[True, False]
        )
    return summary, detail


@st.cache_data(ttl=30)
def cached_sector_flow(
    db_path: str,
    db_mtime: float,
    filer_cik: str,
    ingest_id: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del db_mtime
    with sqlite3.connect(db_path) as cx:
        cx.row_factory = sqlite3.Row
        return compute_sector_flow(cx, filer_cik, ingest_id)
