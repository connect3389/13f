"""Tab：报表分析（机构 + complete 报送 → 分析报告 + 持仓表）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from thirteenf.gui.columns import (
    HELP_HOLDINGS_TABLE_SECTION,
    render_heading_with_help_toggle,
    zh_df,
)
from thirteenf.gui.institutions import (
    filer_display_name_from_inst,
    filing_label_short,
    ingest_rows_for_cik,
    ingest_status_counts,
    institution_picker_df,
    institution_picker_label,
    load_holding_lines_for_table,
    prepare_holdings_display_df,
)
from thirteenf.value_scale import value_usd_multiplier
from thirteenf.gui.periods import report_period_display
from thirteenf.gui.styles import inject_holdings_select_panel_styles
from thirteenf.gui.filing_price_sync import render_analysis_report_heading
from thirteenf.gui.institution_delete import (
    institution_ui_revision,
    render_institution_delete_panel,
)
from thirteenf.gui.tab_holdings.reports import (
    render_kpi_banner,
    render_sector_flow,
    render_top_holdings_change,
    render_top10_new_positions,
)
from thirteenf.gui.ticker import merge_tickers_from_ref
from thirteenf.gui.widgets import pick_selectbox


def render(conn: sqlite3.Connection, db: Path) -> None:
    df_inst_b = institution_picker_df(conn)
    if df_inst_b.empty:
        st.info("尚无机构。请配置 watchlist 并运行抓取。")
        return

    inject_holdings_select_panel_styles()

    with st.container(border=True, key="holdings_tab_selectors"):
        st.markdown("##### 1. 选择机构")
        st.caption(
            "含 watchlist 与库内全部机构；**本地无 complete** = 本库尚无成功入库报送（与 SEC 是否披露无关）。"
        )
        inst_rev = institution_ui_revision()
        ib = pick_selectbox(
            "机构",
            range(len(df_inst_b)),
            format_func=lambda i: institution_picker_label(df_inst_b.iloc[int(i)]),
            label_visibility="collapsed",
            key=f"tab_b_inst_{inst_rev}",
        )
        row_inst_b = df_inst_b.iloc[int(ib)]
        cik_b = str(row_inst_b["cik"])
        disp_b = row_inst_b.get("display_name")
        render_institution_delete_panel(
            conn,
            cik_b,
            str(disp_b) if disp_b is not None and str(disp_b).strip() else None,
            key_prefix="tab_b",
        )

        df_filings = ingest_rows_for_cik(conn, cik_b, statuses=["complete"])
        st.markdown("##### 2. 选择报送（complete）")
        if df_filings.empty:
            counts = ingest_status_counts(conn, cik_b)
            if not counts:
                st.warning("该机构尚未入库任何报送，请运行 `uv run thirteenf-scrape`。")
            else:
                parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                st.warning(
                    f"该机构没有 **complete** 报送（当前：{parts}）。"
                    "常见原因：名称校验未通过或抓取失败，可在「原始数据」Tab 查看 "
                    "`warnings_json`，修正后带 `--force` 重抓。"
                )
            return

        ifi = pick_selectbox(
            "报送",
            range(len(df_filings)),
            format_func=lambda i: filing_label_short(df_filings.iloc[int(i)]),
            label_visibility="collapsed",
            key=f"tab_b_filing_{inst_rev}_{cik_b}",
        )
        filing_row = df_filings.iloc[int(ifi)]
        ingest_id = int(filing_row["id"])
        period_label = report_period_display(filing_row.get("report_date"))
        inst_name = filer_display_name_from_inst(df_inst_b.iloc[int(ib)])

    with st.container(border=True, key="holdings_tab_report"):
        render_analysis_report_heading(conn, ingest_id)
        render_kpi_banner(
            db, cik_b, ingest_id,
            institution_name=inst_name,
            period_label=period_label,
        )
        st.divider()
        render_top10_new_positions(conn, db, cik_b, ingest_id)
        st.divider()
        render_top_holdings_change(conn, db, cik_b, ingest_id)
        st.divider()
        render_sector_flow(conn, db, cik_b, ingest_id)
        st.divider()

        aggregate = render_heading_with_help_toggle(
            "持仓表",
            HELP_HOLDINGS_TABLE_SECTION,
            heading_key=f"holdings_tbl_help_{ingest_id}",
            toggle_label="按 CUSIP 汇总",
            toggle_key="tab_b_agg_cusip",
            toggle_help="默认开启：同一 CUSIP 合并股数与市值并重算权重。",
        )
        c1, c2 = st.columns(2)
        with c1:
            q = st.text_input("发行人 / 标的 关键词（可选）", key="tab_b_kw")
        with c2:
            min_pct = st.number_input(
                "最小持仓权重 %（0 表示不过滤）",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=0.05,
                key="tab_b_minw",
            )

        df_raw = load_holding_lines_for_table(
            conn,
            ingest_id,
            issuer_keyword=q,
            min_weight_pct=min_pct,
            apply_min_weight_before_aggregate=not aggregate,
        )
        if df_raw.empty:
            st.warning("该记录下没有持仓行，或与筛选条件无匹配。")
            return

        value_mult = value_usd_multiplier(conn, ingest_id)
        n_xml = len(df_raw)
        d = prepare_holdings_display_df(
            df_raw,
            conn,
            cik_b,
            ingest_id,
            aggregate_by_cusip=aggregate,
            min_weight_pct=min_pct,
        )
        if d.empty:
            st.warning("汇总或筛选后无持仓行。")
            return

        d = merge_tickers_from_ref(conn, d, "cusip")
        if aggregate:
            show_cols = [
                "issuer",
                "title_of_class",
                "cusip",
                "ticker",
                "shares",
                "qoq_shares_pct",
                "value_as_reported",
                "weight_pct",
                "xml_line_count",
            ]
        else:
            show_cols = [
                "line_no",
                "issuer",
                "title_of_class",
                "cusip",
                "ticker",
                "shares",
                "qoq_shares_pct",
                "value_as_reported",
                "weight_pct",
                "investment_discretion",
                "other_manager",
            ]
        show_cols = [c for c in show_cols if c in d.columns]
        if "ticker" in show_cols and "cusip" in show_cols:
            show_cols = [c for c in show_cols if c != "ticker"]
            ins_at = show_cols.index("cusip") + 1
            show_cols = show_cols[:ins_at] + ["ticker"] + show_cols[ins_at:]
        d = d[show_cols]
        d = zh_df(d)
        st.dataframe(
            d,
            width="stretch",
            hide_index=True,
            column_config={
                "权重": st.column_config.NumberColumn(format="%.4f"),
                "权重（%）": st.column_config.NumberColumn(format="%.4f"),
                "较上季股数变动（%）": st.column_config.NumberColumn(format="%.2f"),
                "申报市值（USD）": st.column_config.NumberColumn(format="%d"),
                "持股数量": st.column_config.NumberColumn(format="%.0f"),
                "原文行数": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        mode = "按 CUSIP 汇总" if aggregate else "SEC 原文拆行"
        st.caption(
            f"{inst_name} · {mode} · 展示 {len(d)} 行"
            f"（原文 {n_xml} 行）· ingest_id={ingest_id} · "
            f"申报市值已换算为美元（本条报送识别乘数 ×{value_mult:g}）。"
            "「较上季股数变动」为同机构上一份 **complete** 报送、按 CUSIP 汇总股数的环比；"
            "最早一期或上季无该 CUSIP 时为空。"
        )
