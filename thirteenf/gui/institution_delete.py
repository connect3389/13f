"""机构选择区：删除机构及关联数据。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from thirteenf.filer_delete import delete_filer, normalize_cik
from thirteenf.gui.institutions import institution_label_row


def institution_ui_revision() -> int:
    """删除机构后递增，用于重置 selectbox 等 widget 的 key。"""
    return int(st.session_state.get("_inst_ui_rev", 0))


def _reset_ui_after_filer_delete() -> int:
    """清空机构/报送相关 session，刷新缓存，返回新 UI 版本号。"""
    drop_prefixes = (
        "tab_a_",
        "tab_b_",
        "tab_raw_",
        "holdings_chg_help_",
        "holdings_tbl_help_",
        "sync_filing_prices_",
        "price_fetch_",
    )
    for key in list(st.session_state.keys()):
        if key == "_inst_ui_rev":
            continue
        if any(key.startswith(p) for p in drop_prefixes):
            st.session_state.pop(key, None)
        if key.endswith("_del_confirm") or key.endswith("_del_btn"):
            st.session_state.pop(key, None)

    rev = institution_ui_revision() + 1
    st.session_state["_inst_ui_rev"] = rev
    st.session_state[f"tab_a_inst_{rev}"] = 0
    st.session_state[f"tab_b_inst_{rev}"] = 0

    st.cache_data.clear()
    st.cache_resource.clear()
    return rev


def render_institution_delete_panel(
    conn: sqlite3.Connection,
    cik: str,
    display_name: str | None,
    *,
    key_prefix: str,
    raw_root: Path | None = None,
) -> None:
    """在「选择机构」区域展示删除入口（需勾选确认）。"""
    cik10 = normalize_cik(cik)
    label = institution_label_row(
        pd.Series({"cik": cik10, "display_name": display_name or ""})
    )

    with st.expander("删除该机构", expanded=False):
        st.warning(
            f"将永久删除 **{label}** 在本库中的全部报送、持仓行，"
            f"并删除 `data/raw/{cik10}/` 下原始 XML（不可恢复）。"
            "不会修改 `config/filers_watchlist.yaml`。"
        )
        n_ing = conn.execute(
            "SELECT COUNT(*) FROM ingest_record WHERE filer_cik = ?",
            (cik10,),
        ).fetchone()[0]
        st.caption(f"当前库内报送 {int(n_ing or 0)} 条。")
        confirm = st.checkbox(
            "我了解上述后果，确认删除",
            key=f"{key_prefix}_del_confirm",
        )
        if st.button(
            "删除机构及全部数据",
            type="primary",
            disabled=not confirm,
            key=f"{key_prefix}_del_btn",
        ):
            result = delete_filer(conn, cik10, raw_root=raw_root)
            if result.errors:
                st.error("部分文件删除失败：" + "；".join(result.errors))
            parts = [
                f"报送 {result.ingest_deleted} 条",
                "已删注册" if result.registry_deleted else "无注册行",
            ]
            if result.raw_dir_removed:
                parts.append("已删 raw 目录")
            elif result.files_removed:
                parts.append(f"已删文件 {result.files_removed} 个")
            st.success("已删除：" + "，".join(parts))
            _reset_ui_after_filer_delete()
            st.rerun()
