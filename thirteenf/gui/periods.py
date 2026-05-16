"""13F 报告期（日历年季度）展示。"""

from __future__ import annotations

from datetime import date

import pandas as pd


def _parse_report_date(raw: object) -> date | None:
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


def report_period_display(raw: object) -> str:
    """
    13F 持仓报告期为日历年季度末；展示为「Qx · 季初 – 季末」。

    例：report_date=2026-03-31 → ``2026 Q1 · 2026-01-01 – 2026-03-31``
    """
    end = _parse_report_date(raw)
    if end is None:
        s = str(raw).strip() if raw is not None else ""
        return s if s and s.lower() != "nan" else "—"
    start, quarter_end = calendar_quarter_bounds(end)
    # 季末以库中 report_date 为准（应与 quarter_end 一致；不一致时仍显示实际期末）
    period_end = end
    label = calendar_quarter_label(end)
    return f"{label} · {start.isoformat()} – {period_end.isoformat()}"
