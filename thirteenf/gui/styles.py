"""Streamlit 页面注入样式。"""

from __future__ import annotations

import streamlit as st


def inject_kpi_metric_styles() -> None:
    st.markdown(
        """
<style>
/* 本报送 KPI 四列：无 delta 时仍保持等高 */
div[data-testid="stHorizontalBlock"]:has(
    > div[data-testid="column"]:nth-child(4):last-child
) {
    align-items: stretch !important;
}
div[data-testid="stHorizontalBlock"]:has(
    > div[data-testid="column"]:nth-child(4):last-child
) > div[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}
div[data-testid="stHorizontalBlock"]:has(
    > div[data-testid="column"]:nth-child(4):last-child
) > div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
    flex: 1 1 auto !important;
    width: 100% !important;
}
div[data-testid="stHorizontalBlock"]:has(
    > div[data-testid="column"]:nth-child(4):last-child
) [data-testid="stMetric"] {
    flex: 1 1 auto !important;
    min-height: 7.25rem !important;
    height: 100% !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stMetric"] {
    padding: 0.35rem 0.45rem 0.5rem 0.45rem;
    background: rgba(0,0,0,0.02);
    border-radius: 6px;
}
[data-testid="stMetric"] label p {
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    line-height: 1.25 !important;
    white-space: normal !important;
    word-break: break-word !important;
    max-width: 100% !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 0.98rem !important;
    line-height: 1.3 !important;
    white-space: normal !important;
    word-break: break-word !important;
    flex: 0 0 auto !important;
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.7rem !important;
    min-height: 1.35rem !important;
    margin-top: auto !important;
}
[data-testid="stMetric"]:not(:has([data-testid="stMetricDelta"]))::after {
    content: "";
    display: block;
    min-height: 1.35rem;
    margin-top: auto;
    flex: 0 0 1.35rem;
}
div.stMetric > label div {
    font-size: 0.72rem !important;
    line-height: 1.25 !important;
    white-space: normal !important;
    word-break: break-word !important;
}
div.stMetric [data-testid="stMetricValue"] {
    font-size: 0.98rem !important;
    white-space: normal !important;
    word-break: break-word !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_section_heading_styles() -> None:
    st.markdown(
        """
<style>
.gui-section-heading {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.25rem;
  margin: 0;
  padding: 0;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_holdings_select_panel_styles() -> None:
    st.markdown(
        """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
  background-color: rgba(250, 251, 253, 1) !important;
  border-radius: 12px !important;
  padding: 0.85rem 1rem 0.75rem 1rem !important;
  border: 1px solid rgba(0, 0, 0, 0.09) !important;
  margin-bottom: 0.15rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
html[data-theme="dark"] div[data-testid="stVerticalBlockBorderWrapper"] {
  background-color: rgba(255, 255, 255, 0.06) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  box-shadow: none;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_top10_table_styles() -> None:
    """Top 10 新建仓自定义表：统一字号与字体，避免 $ 被 Markdown 当成公式导致换行。"""
    st.markdown(
        """
<style>
.top10-cell {
  font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
  font-size: 0.8125rem !important;
  font-weight: 400 !important;
  line-height: 1.35 !important;
  font-variant-numeric: tabular-nums;
  letter-spacing: normal !important;
}
.top10-cell--hdr {
  font-weight: 600 !important;
}
.top10-cell--nowrap {
  white-space: nowrap !important;
}
.top10-cell--muted {
  opacity: 0.72;
  font-size: 0.75rem !important;
}
.top10-cell--ok {
  color: rgb(21, 128, 61);
  font-weight: 500;
  white-space: nowrap !important;
}
html[data-theme="dark"] .top10-cell--ok {
  color: #4ade80;
}
.top10-cell--err {
  color: #b45309;
  font-size: 0.75rem !important;
  white-space: nowrap !important;
  cursor: help;
}
html[data-theme="dark"] .top10-cell--err {
  color: #fbbf24;
}
</style>
""",
        unsafe_allow_html=True,
    )


def inject_holdings_change_styles() -> None:
    st.markdown(
        """
<style>
.holdings-chg-card {
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  padding: 0.65rem 0.75rem 0.55rem;
  min-height: 4.5rem;
  overflow: visible;
}
html[data-theme="dark"] .holdings-chg-card {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}
.holdings-chg-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem 1rem;
  overflow: visible;
}
.holdings-chg-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  line-height: 1.35;
  padding: 0.12rem 0;
}
.holdings-chg-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.holdings-chg-row--inc .holdings-chg-dot { background: #22c55e; }
.holdings-chg-row--dec .holdings-chg-dot { background: #ef4444; }
.holdings-chg-ticker {
  font-weight: 600;
  min-width: 3.2rem;
  flex-shrink: 0;
}
.holdings-chg-tip-wrap {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  cursor: help;
  min-width: 3.2rem;
}
.holdings-chg-tip-wrap .holdings-chg-ticker {
  text-decoration: underline dotted;
  text-underline-offset: 2px;
  text-decoration-color: rgba(0, 0, 0, 0.35);
}
html[data-theme="dark"] .holdings-chg-tip-wrap .holdings-chg-ticker {
  text-decoration-color: rgba(255, 255, 255, 0.45);
}
.holdings-chg-tip-wrap--new .holdings-chg-ticker {
  text-decoration-color: #16a34a;
}
html[data-theme="dark"] .holdings-chg-tip-wrap--new .holdings-chg-ticker {
  text-decoration-color: #4ade80;
}
.holdings-chg-tip-wrap--out .holdings-chg-ticker {
  text-decoration-color: #dc2626;
}
html[data-theme="dark"] .holdings-chg-tip-wrap--out .holdings-chg-ticker {
  text-decoration-color: #f87171;
}
.holdings-chg-tip-bubble {
  visibility: hidden;
  opacity: 0;
  position: absolute;
  left: calc(100% + 6px);
  top: 50%;
  transform: translateY(-50%);
  z-index: 9999;
  padding: 0.35rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 400;
  line-height: 1.3;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: inherit;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.14);
  border-radius: 6px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
  pointer-events: none;
  transition: opacity 0.12s ease, visibility 0.12s ease;
}
html[data-theme="dark"] .holdings-chg-tip-bubble {
  background: #262730;
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
}
.holdings-chg-tip-wrap:hover .holdings-chg-tip-bubble,
.holdings-chg-tip-wrap:focus-within .holdings-chg-tip-bubble {
  visibility: visible;
  opacity: 1;
}
.holdings-chg-amt {
  font-weight: 600;
  margin-left: auto;
  white-space: nowrap;
}
.holdings-chg-row--inc .holdings-chg-amt { color: #16a34a; }
.holdings-chg-row--dec .holdings-chg-amt { color: #dc2626; }
html[data-theme="dark"] .holdings-chg-row--inc .holdings-chg-amt { color: #4ade80; }
html[data-theme="dark"] .holdings-chg-row--dec .holdings-chg-amt { color: #f87171; }
.holdings-chg-tag {
  font-size: 0.68rem;
  opacity: 0.75;
  flex-shrink: 0;
}
.holdings-chg-empty {
  font-size: 0.85rem;
  opacity: 0.55;
  margin: 0.25rem 0 0;
}
.holdings-chg-panel-title {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0 0 0.45rem 0;
}
.holdings-chg-panel-title--dec::before {
  content: "";
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  margin-right: 0.35rem;
  vertical-align: middle;
}
</style>
""",
        unsafe_allow_html=True,
    )
