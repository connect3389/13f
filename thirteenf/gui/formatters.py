"""金额等展示格式。"""

from __future__ import annotations


def fmt_usd_compact(dollars: float) -> str:
    x = abs(float(dollars))
    if x >= 1e12:
        return f"${x / 1e12:.2f}T"
    if x >= 1e9:
        return f"${x / 1e9:.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:.2f}M"
    if x >= 1e3:
        return f"${x / 1e3:.2f}K"
    return f"${x:,.0f}"


def fmt_signed_usd(dollars: float) -> str:
    d = float(dollars)
    if d >= 0:
        return f"+{fmt_usd_compact(d)}"
    return f"−{fmt_usd_compact(abs(d))}"
