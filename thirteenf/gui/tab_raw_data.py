"""Tab：原始数据（warnings_json、名称校验明细等长字段只读查看）。"""

from __future__ import annotations

import json
import sqlite3

import streamlit as st

from thirteenf.gui.institutions import (
    filing_label_short,
    ingest_rows_for_cik,
    institution_picker_df,
    institution_picker_label,
)
from thirteenf.gui.widgets import pick_selectbox


def _render_json_or_text(title: str, raw: str | None) -> None:
    st.markdown(f"**{title}**")
    text = raw or ""
    if text.strip().startswith(("{", "[")):
        try:
            st.json(json.loads(text))
        except json.JSONDecodeError:
            st.code(text)
    else:
        st.code(text or "—")


def render(conn: sqlite3.Connection) -> None:
    df_inst = institution_picker_df(conn)
    if df_inst.empty:
        st.info("尚无机构。请先配置 watchlist 并运行抓取。")
        return

    st.markdown("##### 1. 选择机构")
    st.caption("含 watchlist 与库内全部机构。")
    ic = pick_selectbox(
        "机构",
        range(len(df_inst)),
        format_func=lambda i: institution_picker_label(df_inst.iloc[int(i)]),
        label_visibility="collapsed",
        key="tab_raw_inst",
    )
    cik = str(df_inst.iloc[int(ic)]["cik"])

    df_raw = ingest_rows_for_cik(conn, cik, statuses=None)
    st.markdown("##### 2. 选择报送")
    if df_raw.empty:
        st.warning("该机构下没有报送记录。")
        return

    ici = pick_selectbox(
        "报送",
        range(len(df_raw)),
        format_func=lambda i: filing_label_short(df_raw.iloc[int(i)], show_status=True),
        label_visibility="collapsed",
        key="tab_raw_filing",
    )
    rid = int(df_raw.iloc[int(ici)]["id"])

    st.markdown("##### 3. 原始字段")
    row = conn.execute(
        "SELECT warnings_json, name_verify_detail FROM ingest_record WHERE id = ?",
        (rid,),
    ).fetchone()
    if not row:
        st.warning("未找到该报送记录。")
        return

    _render_json_or_text("处理告警（warnings_json）", row["warnings_json"])
    st.divider()
    _render_json_or_text("名称校验明细（name_verify_detail）", row["name_verify_detail"])
