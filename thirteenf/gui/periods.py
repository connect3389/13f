"""13F 报告期（日历年季度）展示。"""

from __future__ import annotations

from thirteenf.report_period import (
    calendar_quarter_bounds,
    calendar_quarter_label,
    parse_report_date,
)


def _parse_report_date(raw: object):
    """兼容旧名。"""
    return parse_report_date(raw)


def report_period_display(raw: object) -> str:
    """
    13F 持仓报告期为日历年季度末；展示为「Qx · 季初 – 季末」。

    例：report_date=2026-03-31 → ``2026 Q1 · 2026-01-01 – 2026-03-31``
    """
    end = parse_report_date(raw)
    if end is None:
        s = str(raw).strip() if raw is not None else ""
        return s if s and s.lower() != "nan" else "—"
    start, _quarter_end = calendar_quarter_bounds(end)
    period_end = end
    label = calendar_quarter_label(end)
    return f"{label} · {start.isoformat()} – {period_end.isoformat()}"
