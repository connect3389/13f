"""13F 报告期（日历年季度）解析，供 GUI / 行情等共用。"""

from __future__ import annotations

from datetime import date

import pandas as pd


def parse_report_date(raw: object) -> date | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, pd.Timestamp):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def calendar_quarter_bounds(end: date) -> tuple[date, date]:
    """按报告期末日所在自然月，映射到日历年季度起止日。"""
    month = end.month
    year = end.year
    if month <= 3:
        return date(year, 1, 1), date(year, 3, 31)
    if month <= 6:
        return date(year, 4, 1), date(year, 6, 30)
    if month <= 9:
        return date(year, 7, 1), date(year, 9, 30)
    return date(year, 10, 1), date(year, 12, 31)


def calendar_quarter_label(end: date) -> str:
    q = (end.month - 1) // 3 + 1
    return f"{end.year} Q{q}"
