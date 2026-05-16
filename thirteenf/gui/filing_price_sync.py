"""分析报告标题行：报送级季内行情批量同步。"""

from __future__ import annotations

import sqlite3

import streamlit as st

from thirteenf.prices.fetch import price_fetch_available
from thirteenf.prices.filing_sync import (
    needs_filing_price_sync,
    sync_filing_quarter_prices,
)
from thirteenf.gui.styles import inject_section_heading_styles


def render_analysis_report_heading(
    conn: sqlite3.Connection,
    ingest_id: int,
) -> None:
    inject_section_heading_styles()
    need_sync = needs_filing_price_sync(conn, ingest_id)
    btn_key = f"sync_filing_prices_{ingest_id}"

    col_title, col_btn = st.columns([4, 1.35], vertical_alignment="center")
    with col_title:
        st.markdown(
            '<span class="gui-section-heading">分析报告</span>',
            unsafe_allow_html=True,
        )
    with col_btn:
        clicked = st.button(
            "同步行情开启计算",
            key=btn_key,
            type="primary",
            disabled=not need_sync,
            use_container_width=True,
        )

    if need_sync:
        st.caption(
            "尚未为本报送同步季内行情，或 **report_date** 已变更。"
            "点击右侧按钮将拉取本报送全部持仓 Ticker。"
        )
    else:
        st.caption(
            "本报送季内行情已同步；**report_date** 变更后可再次同步。"
        )

    if clicked and need_sync:
        if not price_fetch_available():
            st.error("未安装 yfinance，请执行：uv sync --extra gui")
            return
        prog = st.progress(0.0, text="准备同步…")

        def _on_progress(done: int, total: int, sym: str) -> None:
            if total <= 0:
                prog.progress(1.0, text="无可用 Ticker")
                return
            prog.progress(
                done / total,
                text=f"正在拉取 {sym}（{done}/{total}）",
            )

        with st.spinner("同步本报送季内行情…"):
            summary = sync_filing_quarter_prices(
                conn, ingest_id, on_progress=_on_progress
            )
        prog.empty()
        st.success(
            f"已处理本报送：共 {summary.ticker_total} 个 Ticker，"
            f"成功 {summary.ok}，跳过 {summary.failed}。"
        )
        st.rerun()
