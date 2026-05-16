"""Top 10 新建仓表（季内行情只读展示）。"""

from __future__ import annotations

import html as html_lib
import sqlite3

import pandas as pd
import streamlit as st

from thirteenf.gui.columns import HELP_END_MARKET_VALUE, HELP_QUARTER_PRICE_RANGE
from thirteenf.gui.formatters import fmt_usd_compact
from thirteenf.gui.styles import inject_top10_table_styles
from thirteenf.gui.ticker import merge_tickers_from_ref, ticker_symbol_for_cusip
from thirteenf.prices.coverage import QuarterPriceStatus, quarter_price_status
from thirteenf.prices.ranges import format_price_range_label

_COL_WEIGHTS = [0.45, 0.85, 1.05, 2.0, 0.95, 1.15, 1.45]


def _top10_html(
    text: object,
    *,
    nowrap: bool = False,
    header: bool = False,
    muted: bool = False,
) -> str:
    classes = ["top10-cell"]
    if nowrap:
        classes.append("top10-cell--nowrap")
    if header:
        classes.append("top10-cell--hdr")
    if muted:
        classes.append("top10-cell--muted")
    return (
        f'<span class="{" ".join(classes)}">'
        f"{html_lib.escape(str(text))}</span>"
    )


def _top10_cell(
    container,
    text: object,
    *,
    nowrap: bool = False,
    header: bool = False,
    muted: bool = False,
) -> None:
    container.html(
        _top10_html(text, nowrap=nowrap, header=header, muted=muted)
    )


def _render_price_display(
    conn: sqlite3.Connection,
    ticker: str | None,
    report_date_raw: object,
) -> None:
    check = quarter_price_status(conn, ticker, report_date_raw)
    if check.status == QuarterPriceStatus.READY and check.range is not None:
        _top10_cell(st, format_price_range_label(check.range), nowrap=True)
        return
    if check.status == QuarterPriceStatus.NO_TICKER:
        _top10_cell(st, "—", muted=True)
        return
    if check.status == QuarterPriceStatus.NO_API_KEY:
        _top10_cell(st, "需 yfinance", muted=True)
        return
    _top10_cell(st, "—", muted=True)


def render_top10_new_positions_table(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    *,
    ingest_id: int,
    report_date_raw: object,
) -> None:
    del ingest_id  # 行情在报送标题栏批量同步
    if df.empty:
        return

    inject_top10_table_styles()
    d = merge_tickers_from_ref(conn, df.copy(), "cusip")
    d["value_label"] = d["total_value_usd"].map(fmt_usd_compact)

    headers = [
        "排名",
        "Ticker",
        "CUSIP",
        "发行人",
        "证券类别",
        "季末申报市值",
        "季内行情区间",
    ]
    hdr = st.columns(_COL_WEIGHTS)
    for col, label in zip(hdr, headers):
        if label == "季内行情区间":
            col.markdown(f"**{label}**", help=HELP_QUARTER_PRICE_RANGE)
        elif label == "季末申报市值":
            col.markdown(f"**{label}**", help=HELP_END_MARKET_VALUE)
        else:
            _top10_cell(col, label, header=True)

    for _, row in d.iterrows():
        cusip = str(row.get("cusip", "")).strip()
        sym = ticker_symbol_for_cusip(conn, cusip)
        cols = st.columns(_COL_WEIGHTS)
        _top10_cell(cols[0], int(row["rank"]))
        _top10_cell(cols[1], row.get("ticker", "—"))
        _top10_cell(cols[2], cusip or "—")
        _top10_cell(cols[3], row.get("issuer", ""))
        _top10_cell(cols[4], row.get("title_of_class", ""))
        _top10_cell(cols[5], row.get("value_label", ""))
        with cols[6]:
            _render_price_display(conn, sym, report_date_raw)
