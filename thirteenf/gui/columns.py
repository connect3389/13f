"""表头中文化与 Streamlit 列配置。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

KPI_HELP_NCUSIP = """中文：当前这条 **complete** 报送中，有持仓行的 **不同 CUSIP** 数量（按行汇总后去重）。

English: Count of distinct **CUSIPs** in this **selected** complete filing (after line-level aggregation by CUSIP)."""

KPI_HELP_AUM = """中文：**仅本条报送**：`holding_line` 申报市值按报送自动识别单位后换算为美元合计（历史 XML 多为千美元，近年部分 filer 为美元）。若有上一份 **complete**，delta 为相对该期的总值环比 %。

English: **This filing only**: sum of reported position values (USD, per-filing unit detection). **QoQ %** compares total vs this filer’s **prior** complete filing, if any."""

KPI_HELP_NET_BUY = """中文：相对**该机构上一份 complete**，按 CUSIP 的申报市值差额（美元）；**单机构**本期净增加最大的标的。

English: **This filer only**: largest **positive** per-CUSIP dollar change vs its **prior** complete filing."""

KPI_HELP_NET_SELL = """中文：同上，**单机构**本期净减少最大（最负）的 CUSIP。

English: **This filer only**: largest **negative** per-CUSIP dollar change vs prior complete."""

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
    "issuer": "发行人",
    "title_of_class": "证券类别",
    "cusip": "CUSIP",
    "ticker": "Ticker",
    "figi": "FIGI",
    "shares": "持股数量",
    "value_as_reported": "申报市值",
    "weight": "权重",
    "weight_pct": "权重（%）",
    "qoq_shares_pct": "较上季股数变动（%）",
    "source": "数据来源",
    "ingest_id": "报送记录 ID",
    "ingested_at": "写入时间",
    "rank": "排名",
    "value_label": "合计市值",
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
