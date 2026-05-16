"""
本地浏览 SQLite 中的 13F 数据（Streamlit）。

模块结构：
- ``browse`` — 入口（``streamlit run thirteenf/gui/browse.py``）
- ``connection`` — 数据库路径与连接缓存
- ``columns`` / ``formatters`` — 表头中文化与金额格式
- ``institutions`` — 机构、报送、持仓行 SQL
- ``analytics`` — KPI / Top10 / 变动 / 行业流计算（``@st.cache_data``）
- ``ticker`` — CUSIP → Ticker 展示
- ``styles`` — 页面 CSS 注入
- ``tab_registry`` — 「机构与报送」Tab
- ``tab_holdings`` — 「报表分析」Tab（``reports`` 为分析区块）
- ``tab_raw_data`` — 「原始数据」Tab（JSON / 长文本字段）
"""
