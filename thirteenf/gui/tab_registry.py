"""Tab：机构与报送（注册表 + ingest 列表，无聚合计算）。"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from thirteenf.gui.columns import column_config_left_align, zh_df
from thirteenf.gui.institutions import institution_label_row, tab_a_institution_list


def render(conn: sqlite3.Connection) -> None:
    df_inst = tab_a_institution_list(conn)
    if df_inst.empty:
        st.info("尚无注册机构且无报送记录。请先配置 watchlist 并运行抓取。")
        with st.expander("filer_registry 全表"):
            df_all_reg = pd.read_sql(
                "SELECT cik, display_name, updated_at FROM filer_registry ORDER BY cik",
                conn,
            )
            if df_all_reg.empty:
                st.caption("filer_registry 为空。")
            else:
                d_reg = zh_df(df_all_reg)
                st.dataframe(
                    d_reg,
                    width="stretch",
                    hide_index=True,
                    column_config=column_config_left_align(d_reg),
                )
        return

    ia = st.selectbox(
        "选择机构",
        range(len(df_inst)),
        format_func=lambda i: institution_label_row(df_inst.iloc[int(i)]),
        key="tab_a_inst",
    )
    cik_a = str(df_inst.iloc[int(ia)]["cik"])

    reg_row = pd.read_sql(
        """
        SELECT id, cik, display_name, updated_at
        FROM filer_registry WHERE cik = ?
        """,
        conn,
        params=[cik_a],
    )
    st.markdown("**注册信息**")
    if reg_row.empty:
        st.caption("该 CIK 未在 filer_registry 中登记（可能仅见于历史报送）。")
    else:
        d_reg = zh_df(reg_row)
        st.dataframe(
            d_reg,
            width="stretch",
            hide_index=True,
            column_config=column_config_left_align(d_reg),
        )

    st.markdown("**报送记录**")
    df_ing = pd.read_sql(
        """
        SELECT ir.id, ir.report_date, ir.status, ir.accession_number,
               ir.is_amendment, ir.filing_date, ir.row_count,
               ir.verified_sec_name, ir.name_verify_status,
               fr.display_name AS registry_display_name,
               substr(ir.warnings_json, 1, 120) AS warnings_preview
        FROM ingest_record ir
        LEFT JOIN filer_registry fr ON fr.cik = ir.filer_cik
        WHERE ir.filer_cik = ?
        ORDER BY ir.filing_date DESC, ir.id DESC
        """,
        conn,
        params=[cik_a],
    )
    if df_ing.empty:
        st.caption("该 CIK 尚无 ingest_record。")
    else:
        d_ing = zh_df(df_ing)
        st.dataframe(
            d_ing,
            width="stretch",
            hide_index=True,
            column_config=column_config_left_align(d_ing),
        )

    with st.expander("filer_registry 全表（速查）"):
        df_all_reg = pd.read_sql(
            "SELECT cik, display_name, updated_at FROM filer_registry ORDER BY cik",
            conn,
        )
        if df_all_reg.empty:
            st.caption("filer_registry 为空。")
        else:
            d_all = zh_df(df_all_reg)
            st.dataframe(
                d_all,
                width="stretch",
                hide_index=True,
                column_config=column_config_left_align(d_all),
            )
