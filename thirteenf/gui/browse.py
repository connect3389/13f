"""
Streamlit：13F 分析笔记。

Tab：
- **机构录入**：输入 CIK（及可选中文名/简介）→ SEC 抓取入库。
- **机构报送数据管理**：filer_registry、ingest_record（选机构后筛选）。
- **报表分析**：当前机构 + complete 报送 → KPI、Top10、变动、GICS 行业流、持仓表。
- **原始数据**：所选报送的 warnings_json、名称校验明细等长字段只读查看。

运行：uv run streamlit run thirteenf/gui/browse.py
"""

from __future__ import annotations

import streamlit as st

from thirteenf.db import init_db
from thirteenf.envload import load_dotenv_if_present
from thirteenf.gui.connection import cached_conn, default_db_path
from thirteenf.gui import tab_holdings, tab_ingest, tab_raw_data, tab_registry

# st.tabs 标签前用 emoji 作图标（Streamlit 原生 Tab 不支持独立 icon 参数）
_TAB_LABELS = (
    "📥 机构录入",
    "🗂️ 机构报送数据管理",
    "📊 报表分析",
    "📄 原始数据",
)


def main() -> None:
    load_dotenv_if_present()
    st.set_page_config(page_title="13F 分析笔记", layout="wide")
    st.markdown(
        """
<style>
/* 下拉无搜索框时，避免残留 input 在触摸端获得焦点 */
div[data-baseweb="select"] input[aria-autocomplete="list"] {
  caret-color: transparent;
}
</style>
""",
        unsafe_allow_html=True,
    )
    st.title("13F 分析笔记")

    db = default_db_path()
    if not db.is_file():
        st.error(f"数据库不存在：{db}（请在项目根目录运行，或设置环境变量 THIRTEENF_DB）")
        st.stop()
    init_db(db)

    from thirteenf.prices.fetch import price_fetch_available

    if not price_fetch_available():
        st.error(
            "当前运行环境无法加载 yfinance。请确认已安装依赖并 **Reboot** 应用："
            "本地 `uv sync`；在线部署需 `requirements.txt` 含 yfinance 或 `pip install .` 后重建。"
        )
        st.stop()

    conn = cached_conn(str(db))

    tab_ing, tab_a, tab_b, tab_c = st.tabs(list(_TAB_LABELS))

    with tab_ing:
        tab_ingest.render(conn, db)

    with tab_a:
        tab_registry.render(conn)

    with tab_b:
        tab_holdings.render(conn, db)

    with tab_c:
        tab_raw_data.render(conn)


if __name__ == "__main__":
    main()
