"""表头中文化与 Streamlit 列配置。"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from thirteenf.gui.styles import inject_section_heading_styles

KPI_HELP_NCUSIP = """中文：当前这条 **complete** 报送中，有持仓行的 **不同 CUSIP** 数量（按行汇总后去重）。

English: Count of distinct **CUSIPs** in this **selected** complete filing (after line-level aggregation by CUSIP)."""

KPI_HELP_AUM = """中文：**仅本条报送**：`holding_line` 申报市值按报送自动识别单位后换算为美元合计（历史 XML 多为千美元，近年部分 filer 为美元）。若有上一份 **complete**，delta 为相对该期的总值环比 %。

English: **This filing only**: sum of reported position values (USD, per-filing unit detection). **QoQ %** compares total vs this filer’s **prior** complete filing, if any."""

KPI_HELP_NET_BUY = """中文：相对**该机构上一份 complete**，按 CUSIP 的申报市值差额（美元）；**单机构**本期净增加最大的标的。

English: **This filer only**: largest **positive** per-CUSIP dollar change vs its **prior** complete filing."""

KPI_HELP_NET_SELL = """中文：同上，**单机构**本期净减少最大（最负）的 CUSIP。

English: **This filer only**: largest **negative** per-CUSIP dollar change vs prior complete."""

HELP_END_MARKET_VALUE = """中文：该 **CUSIP** 在本期报告期末的**申报持仓市值**（同代码多行则加总），已换算为美元。
即季末该新建仓位的总市值，**不是**本季买入金额或建仓成本。

English: **End-of-quarter reported market value** for this new CUSIP (USD, aggregated). Not purchase cost or total fund AUM."""

HELP_HOLDINGS_CHANGE_SECTION = """【13F 口径】每季报送的是季末**全盘持仓**快照，无交易的标的也会出现在表里，不是「只报买卖」。

【本页计算】与同机构上一份 complete 对比；按 CUSIP 汇总后：
变动 = 本期季末申报市值 − 上期季末申报市值（美元）。
含股价波动：股数不变、股价上涨也会进「增持 Top」。

【左右栏】左：变动>0 的前 10；右：变动<0 的前 10（含减仓与清仓）。
标签「新建」= 上季无持仓；「清仓」= 本季已无持仓（同步时会含上季 CUSIP 拉行情）。
有缓存的 Ticker 均可悬停看季内区间。
未进 Top 的标的可能两期都有、变动较小；KPI 总市值仍含全部持仓。

【注意】缺上季 complete、CUSIP 变更或单位识别错误时，对比可能偏差。"""

HELP_QUARTER_PRICE_RANGE = """中文：该 **CUSIP** 对应 Ticker 在**本条报送报告期所在自然季**内的日线最低价–最高价（Yahoo Finance / yfinance），括号内为季末附近收盘价参考。
**不是**机构真实买入成本或 13F 申报市值。

English: Intra-quarter daily low–high via yfinance; not cost basis."""

HELP_HOLDINGS_TABLE_SECTION = """【默认视图】按 **CUSIP 汇总**：同一 CUSIP 的股数、申报市值相加，权重按汇总后市值重算，与上方 KPI / Top 口径一致。

【为何会多行】SEC 13F XML 中，同一 CUSIP 可因 **otherManager**（子公司/账户编号）、**investmentDiscretion**（投资裁量权）等拆成多行；并非重复抓取。

【原文拆行】关闭「按 CUSIP 汇总」可查看每条 infoTable 及 **投资裁量权 / 其他管理人** 字段。"""

COL_ZH: dict[str, str] = {
    "id": "记录 ID",
    "cik": "CIK",
    "filer_cik": "CIK",
    "slug": "别名 ID（预留）",
    "display_name": "机构名称",
    "registry_display_name": "观察清单名称",
    "extra_json": "扩展信息（JSON）",
    "updated_at": "最近更新",
    "report_date": "报告期末",
    "status": "入库状态",
    "accession_number": "SEC 访问号",
    "is_amendment": "是否修订件",
    "filing_date": "递交日期",
    "row_count": "持仓行数",
    "verified_sec_name": "SEC 登记名称",
    "verified_cover_name": "封面管理人名称",
    "name_verify_status": "名称校验状态",
    "name_verify_detail": "名称校验明细",
    "warnings_preview": "处理告警（摘要）",
    "warnings_json": "处理告警（JSON）",
    "line_no": "序号",
    "xml_line_count": "原文行数",
    "issuer": "发行人",
    "title_of_class": "证券类别",
    "investment_discretion": "投资裁量权",
    "other_manager": "其他管理人",
    "cusip": "CUSIP",
    "ticker": "Ticker",
    "figi": "FIGI",
    "shares": "持股数量",
    "value_as_reported": "申报市值（USD）",
    "weight": "权重",
    "weight_pct": "权重（%）",
    "qoq_shares_pct": "较上季股数变动（%）",
    "source": "数据来源",
    "ingest_id": "报送记录 ID",
    "ingested_at": "写入时间",
    "rank": "排名",
    "value_label": "季末申报市值",
    "sector_zh": "GICS 行业",
    "sector_en": "GICS (EN)",
    "gics_sector_code": "GICS 代码",
    "change_label": "市值变动",
    "flow_usd": "变动（USD）",
    "flow_b": "变动（十亿美元）",
    "parser_version": "解析版本",
    "raw_path": "原始文件路径",
    "raw_sha256": "文件指纹",
    "downloaded_at": "下载时间",
    "primary_document": "主文档文件名",
    "run_id": "抓取批次 ID",
    "created_at": "创建时间",
}


def humanize_col(name: str) -> str:
    if not name or not isinstance(name, str):
        return str(name)
    parts = name.split("_")
    return " ".join(p.capitalize() for p in parts)


def zh_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [COL_ZH.get(str(c), humanize_col(str(c))) for c in out.columns]
    return out


def _heading_help_css(safe_key: str, *, popover_nudge_px: int = -7) -> str:
    return f"""
div[data-testid="stHorizontalBlock"]:has(.st-key-{safe_key}) {{
  width: fit-content !important;
  max-width: 100%;
  align-items: center !important;
  margin: 0.65rem 0 0.3rem 0 !important;
  min-height: 0 !important;
  height: auto !important;
  gap: 0.2rem !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{safe_key}) > div[data-testid="stVerticalBlock"] {{
  flex: 0 0 auto !important;
  align-self: center !important;
  justify-content: center !important;
  min-height: 0 !important;
  height: auto !important;
  padding: 0 !important;
  margin: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{safe_key}) [data-testid="stElementContainer"] {{
  margin: 0 !important;
  padding: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{safe_key})
  [data-testid="stMarkdownContainer"] {{
  display: flex !important;
  align-items: center !important;
  padding: 0 !important;
  margin: 0 !important;
  min-height: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{safe_key})
  .gui-section-heading {{
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1.3 !important;
  display: inline-block !important;
}}
.st-key-{safe_key} {{
  display: flex !important;
  align-items: center !important;
  margin: 0 !important;
  padding: 0 !important;
  min-height: 0 !important;
  transform: translateY({popover_nudge_px}px);
}}
.st-key-{safe_key} button {{
  padding: 0 0.25rem !important;
  min-height: 0 !important;
  height: auto !important;
  line-height: 1 !important;
  font-size: 0.92rem !important;
  border: none !important;
  box-shadow: none !important;
  opacity: 0.72;
  display: inline-flex !important;
  align-items: center !important;
}}
.st-key-{safe_key} button:hover {{
  opacity: 1;
}}
"""


def render_heading_with_help(title: str, help_text: str, *, key: str) -> None:
    """区块标题 + ℹ️：悬停 popover 触发器见原生 help；点击展开全文。"""
    inject_section_heading_styles()
    safe_key = "".join(c if c.isalnum() or c in "_-" else "_" for c in key)
    st.markdown(
        f"<style>{_heading_help_css(safe_key)}</style>",
        unsafe_allow_html=True,
    )
    with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center"):
        st.markdown(
            f'<span class="gui-section-heading">{html.escape(title)}</span>',
            unsafe_allow_html=True,
        )
        with st.popover("ℹ️", help=help_text, type="tertiary", key=key):
            st.markdown(help_text)


def render_heading_with_help_toggle(
    title: str,
    help_text: str,
    *,
    heading_key: str,
    toggle_label: str,
    toggle_key: str,
    toggle_default: bool = True,
    toggle_help: str | None = None,
) -> bool:
    """标题行左侧：标题 + ℹ️；右侧：开关（整行两端对齐）。"""
    inject_section_heading_styles()
    help_safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in heading_key)
    toggle_safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in toggle_key)
    st.markdown(
        f"""
<style>
div[data-testid="stHorizontalBlock"]:has(.st-key-{help_safe}):has(.st-key-{toggle_safe}) {{
  width: 100% !important;
  max-width: 100% !important;
  align-items: center !important;
  margin: 0.65rem 0 0.35rem 0 !important;
  gap: 0.75rem !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{help_safe}):has(.st-key-{toggle_safe})
  > div[data-testid="stVerticalBlock"]:first-child {{
  flex: 0 1 auto !important;
  min-width: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(.st-key-{help_safe}):has(.st-key-{toggle_safe})
  > div[data-testid="stVerticalBlock"]:last-child {{
  flex: 0 0 auto !important;
  margin-left: auto !important;
}}
{_heading_help_css(help_safe, popover_nudge_px=-6)}
.st-key-{toggle_safe} {{
  display: flex !important;
  align-items: center !important;
  margin: 0 !important;
  padding: 0 !important;
}}
.st-key-{toggle_safe} label {{
  margin: 0 !important;
}}
.st-key-{toggle_safe} label p {{
  font-size: 0.9rem !important;
  line-height: 1.3 !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center"):
            st.markdown(
                f'<span class="gui-section-heading">{html.escape(title)}</span>',
                unsafe_allow_html=True,
            )
            with st.popover("ℹ️", help=help_text, type="tertiary", key=heading_key):
                st.markdown(help_text)
        return st.toggle(
            toggle_label,
            value=toggle_default,
            key=toggle_key,
            help=toggle_help,
        )


def column_config_left_align(df: pd.DataFrame) -> dict:
    cfg: dict = {}
    for col in df.columns:
        c = str(col)
        s = df[col]
        if pd.api.types.is_bool_dtype(s):
            cfg[c] = st.column_config.CheckboxColumn(alignment="left")
        elif pd.api.types.is_integer_dtype(s):
            cfg[c] = st.column_config.NumberColumn(alignment="left", format="%d")
        elif pd.api.types.is_float_dtype(s):
            cfg[c] = st.column_config.NumberColumn(alignment="left")
        else:
            cfg[c] = st.column_config.TextColumn(alignment="left")
    return cfg
