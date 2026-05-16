"""
Streamlit：13F 本地库界面。

Tab：
- **机构与报送**：filer_registry、ingest_record（选机构后筛选）。
- **报表分析**：当前机构 + complete 报送 → KPI、Top10、变动、GICS 行业流、持仓表。
- **原始数据**：所选报送的 warnings_json、名称校验明细等长字段只读查看。

运行：uv run streamlit run thirteenf/gui/browse.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from thirteenf.db import init_db
from thirteenf.envload import load_dotenv_if_present
from thirteenf.gui.connection import cached_conn, resolve_db
from thirteenf.gui import tab_holdings, tab_raw_data, tab_registry


def main() -> None:
    load_dotenv_if_present()
    st.set_page_config(page_title="13F 本地库", layout="wide")
    st.title("13F 本地库")

    with st.sidebar:
        st.subheader("数据库")
        default = Path.cwd() / "data" / "13f_history.sqlite"
        db_in = st.text_input(
            "路径",
            value=str(default),
            help="相对于当前工作目录或绝对路径",
        )
        db = resolve_db(db_in)
        if not db.is_file():
            st.error(f"文件不存在：{db}")
            st.stop()
        init_db(db)

    conn = cached_conn(str(db))

    tab_a, tab_b, tab_c = st.tabs(["机构与报送", "报表分析", "原始数据"])

    with tab_a:
        tab_registry.render(conn)

    with tab_b:
        tab_holdings.render(conn, db)

    with tab_c:
        tab_raw_data.render(conn)


if __name__ == "__main__":
    main()
