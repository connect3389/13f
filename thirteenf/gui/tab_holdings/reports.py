"""持仓明细 Tab 内的分析报告区块（KPI / Top10 / 变动 / 行业流）。"""

from __future__ import annotations

import html
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from thirteenf.gui.analytics import (
    cached_kpis_for_filing,
    cached_sector_flow,
    cached_top_holdings_change,
    cached_top_new_positions,
)
from thirteenf.gui.columns import (
    HELP_END_MARKET_VALUE,
    HELP_HOLDINGS_CHANGE_SECTION,
    KPI_HELP_AUM,
    KPI_HELP_NCUSIP,
    KPI_HELP_NET_BUY,
    KPI_HELP_NET_SELL,
    column_config_left_align,
    render_heading_with_help,
    zh_df,
)
from thirteenf.gui.formatters import fmt_signed_usd, fmt_usd_compact
from thirteenf.gui.styles import inject_holdings_change_styles, inject_kpi_metric_styles
from thirteenf.gui.ticker import merge_tickers_from_ref


def render_kpi_banner(
    db: Path,
    filer_cik: str,
    ingest_id: int,
    *,
    institution_name: str,
    period_label: str,
) -> None:
    inject_kpi_metric_styles()
    st.markdown(f"##### {institution_name} · {period_label} KPI")
    mtime = db.stat().st_mtime
    k = cached_kpis_for_filing(str(db), mtime, str(filer_cik).strip(), int(ingest_id))

    c1, c2, c3, c4 = st.columns(4)
    if not k.get("ok"):
        with c1:
            st.metric("持仓标的数", "—", help=f"Distinct CUSIPs\n\n{KPI_HELP_NCUSIP}")
        with c2:
            st.metric("申报总市值", "—", help=f"Filing value\n\n{KPI_HELP_AUM}")
        with c3:
            st.metric("最大净买入", "—", help=f"Largest net buy\n\n{KPI_HELP_NET_BUY}")
        with c4:
            st.metric("最大净卖出", "—", help=f"Largest net sell\n\n{KPI_HELP_NET_SELL}")
        return

    dcur = k["date_cur"] or "—"
    dprev = k.get("date_prev")
    iid = k.get("ingest_id")
    period_hint = f"报告期末 **{dcur}** · ingest_id={iid}"
    if k.get("has_prior") and dprev:
        period_hint += f" · 环比对比上一 complete **{dprev}**"
    else:
        period_hint += " · **无上季 complete**，无总值环比与最大净买卖"
    st.caption(period_hint)

    with c1:
        st.metric(
            "持仓标的数",
            f"{k['n_cusips']}",
            help=f"Distinct CUSIPs\n\n{KPI_HELP_NCUSIP}",
        )
    with c2:
        aum = k["aum_usd"]
        dlt = None
        dct = "off"
        if k["aum_qoq_pct"] is not None:
            p = k["aum_qoq_pct"]
            dlt = f"{p:+.2f}%"
            dct = "inverse" if p < 0 else "normal"
        st.metric(
            "申报总市值",
            fmt_usd_compact(aum) if aum is not None else "—",
            delta=dlt,
            delta_color=dct,
            help=(
                "Filing value (USD)\n\n"
                f"{KPI_HELP_AUM}\n\n"
                "Delta：相对该机构上一份 **complete** 总申报市值。"
            ),
        )
    with c3:
        if k.get("has_prior") and k["buy_label"] and k["buy_usd"] is not None:
            st.metric(
                "最大净买入",
                str(k["buy_label"]),
                delta="+" + fmt_usd_compact(k["buy_usd"]),
                delta_color="normal",
                help=f"Largest net buy\n\n{KPI_HELP_NET_BUY}\n\nCUSIP: {k['buy_cusip']}",
            )
        else:
            st.metric(
                "最大净买入",
                "—",
                help=f"Largest net buy\n\n{KPI_HELP_NET_BUY}",
            )
    with c4:
        if k.get("has_prior") and k["sell_label"] and k["sell_usd"] is not None:
            st.metric(
                "最大净卖出",
                str(k["sell_label"]),
                delta="−" + fmt_usd_compact(abs(k["sell_usd"])),
                delta_color="inverse",
                help=f"Largest net sell\n\n{KPI_HELP_NET_SELL}\n\nCUSIP: {k['sell_cusip']}",
            )
        else:
            st.metric(
                "最大净卖出",
                "—",
                help=f"Largest net sell\n\n{KPI_HELP_NET_SELL}",
            )


def render_top10_new_positions(
    conn: sqlite3.Connection,
    db: Path,
    filer_cik: str,
    ingest_id: int,
) -> None:
    st.markdown("##### Top 10 新建仓（本机构）")
    st.caption(
        "与本机构上一份 **complete** 对比，本期新出现的 CUSIP；按季末申报市值降序取前 10。"
        "Ticker 来自 `cusip_ref`。"
    )
    mtime = db.stat().st_mtime
    df = cached_top_new_positions(
        str(db), mtime, str(filer_cik).strip(), int(ingest_id), 10
    )
    if df.empty:
        st.info(
            "该机构对当前报送**无上季 complete 可比**，或无非新建仓 / 无满足条件的持仓。"
        )
        return
    d = merge_tickers_from_ref(conn, df.copy(), "cusip")
    d["value_label"] = d["total_value_usd"].map(fmt_usd_compact)
    d = d.drop(columns=["total_value_usd"])
    d = d[["rank", "ticker", "cusip", "issuer", "title_of_class", "value_label"]]
    d = zh_df(d)
    col_cfg = column_config_left_align(d)
    col_cfg["季末申报市值"] = st.column_config.TextColumn(
        alignment="left",
        help=HELP_END_MARKET_VALUE,
    )
    st.dataframe(
        d,
        width="stretch",
        hide_index=True,
        column_config=col_cfg,
    )


def _build_holdings_change_card_html(
    conn: sqlite3.Connection, df: pd.DataFrame, *, variant: str
) -> str:
    if df.empty:
        return '<p class="holdings-chg-empty">—</p>'
    d = merge_tickers_from_ref(conn, df.copy(), "cusip")
    rows: list[str] = []
    for _, r in d.iterrows():
        sym = r.get("ticker")
        label = html.escape(
            str(sym).strip() if sym is not None and str(sym).strip() else str(r["cusip"])
        )
        amt = html.escape(str(r["change_label"]))
        tag = str(r.get("tag") or "").strip()
        tag_html = (
            f'<span class="holdings-chg-tag">{html.escape(tag)}</span>'
            if tag
            else ""
        )
        rows.append(
            f'<div class="holdings-chg-row holdings-chg-row--{variant}">'
            f'<span class="holdings-chg-dot"></span>'
            f'<span class="holdings-chg-ticker">{label}</span>'
            f'<span class="holdings-chg-amt">{amt}</span>{tag_html}</div>'
        )
    inner = "".join(rows)
    return f'<div class="holdings-chg-card"><div class="holdings-chg-grid">{inner}</div></div>'


def render_top_holdings_change(
    conn: sqlite3.Connection,
    db: Path,
    filer_cik: str,
    ingest_id: int,
) -> None:
    render_heading_with_help(
        "持仓变动 Top",
        HELP_HOLDINGS_CHANGE_SECTION,
        key=f"holdings_chg_help_{ingest_id}",
    )
    st.caption("左：申报市值增加最多的 10 只；右：减少最多的 10 只。Ticker 来自 `cusip_ref`。")
    inject_holdings_change_styles()
    mtime = db.stat().st_mtime
    df_inc, df_dec = cached_top_holdings_change(
        str(db), mtime, str(filer_cik).strip(), int(ingest_id), 10
    )
    if df_inc.empty and df_dec.empty:
        st.info("该报送无上季 **complete** 可比，或本期相对上季无市值变动。")
        return

    col_inc, col_dec = st.columns(2)
    with col_inc:
        st.markdown('<p class="holdings-chg-panel-title">增持 Top</p>', unsafe_allow_html=True)
        st.markdown(
            _build_holdings_change_card_html(conn, df_inc, variant="inc"),
            unsafe_allow_html=True,
        )
    with col_dec:
        st.markdown(
            '<p class="holdings-chg-panel-title holdings-chg-panel-title--dec">'
            "减持 / 清仓 Top</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            _build_holdings_change_card_html(conn, df_dec, variant="dec"),
            unsafe_allow_html=True,
        )


def render_sector_flow(
    conn: sqlite3.Connection,
    db: Path,
    filer_cik: str,
    ingest_id: int,
) -> None:
    st.markdown("##### 行业资金流向（GICS 一级）")
    st.caption(
        "相对本机构上一份 **complete**，按 **MSCI/S&P GICS 官方一级行业（Sector）** 汇总申报市值变动；"
        "中文为 GICS 标准译名，非自定义主题板块。"
        "需先运行 `thirteenf-sync-cusip-refs` 与 `thirteenf-sync-gics-sectors`（Yahoo sector → GICS L1）。"
    )
    mtime = db.stat().st_mtime
    summary, detail = cached_sector_flow(
        str(db), mtime, str(filer_cik).strip(), int(ingest_id)
    )
    if summary.empty:
        st.info(
            "无法绘制：无上季可比、无市值变动，或持仓 CUSIP 尚未映射 GICS 行业。"
            "请先同步 ticker 与 GICS。"
        )
        return

    try:
        import altair as alt
    except ImportError:
        st.warning("需要安装 altair：`uv sync --extra gui`")
        st.dataframe(zh_df(summary), hide_index=True)
        return

    chart = (
        alt.Chart(summary)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y(
                "sector_zh:N",
                title=None,
                sort=alt.EncodingSortField(field="flow_usd", order="descending"),
            ),
            x=alt.X(
                "flow_usd:Q",
                title="净流入 / 流出（美元）",
                axis=alt.Axis(format="~s"),
            ),
            color=alt.condition(
                "datum.flow_usd > 0",
                alt.value("#22c55e"),
                alt.value("#ef4444"),
            ),
            tooltip=[
                alt.Tooltip("sector_zh", title="GICS 行业"),
                alt.Tooltip("sector_en", title="GICS (EN)"),
                alt.Tooltip("gics_sector_code", title="代码"),
                alt.Tooltip("flow_usd:Q", title="变动（USD）", format=",.0f"),
                alt.Tooltip("flow_b:Q", title="变动（十亿美元）", format=".2f"),
            ],
        )
        .properties(height=max(240, 32 * len(summary)))
    )
    st.altair_chart(chart, width="stretch")

    unmapped = conn.execute(
        """
        SELECT COUNT(DISTINCT TRIM(h.cusip)) FROM holding_line h
        JOIN ingest_record ir ON ir.id = h.ingest_id
        LEFT JOIN cusip_ref r ON r.cusip = TRIM(h.cusip)
        WHERE ir.id = ? AND (r.gics_sector_code IS NULL OR TRIM(r.gics_sector_code) = '')
        """,
        (int(ingest_id),),
    ).fetchone()
    if unmapped and unmapped[0]:
        st.caption(f"另有 {unmapped[0]} 个 CUSIP 尚无 GICS 映射，未计入上图。")

    if not detail.empty:
        d = detail.copy()
        d["change_label"] = d["change_usd"].map(fmt_signed_usd)
        d = d[["sector_zh", "ticker", "change_label", "gics_sector_code"]]
        with st.expander("各 GICS 板块个股贡献"):
            st.dataframe(
                zh_df(d),
                width="stretch",
                hide_index=True,
                column_config=column_config_left_align(zh_df(d)),
            )
