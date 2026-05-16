"""季内行情区间展示。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceRange:
    low: float
    high: float
    close_end: float | None = None


def fmt_price(px: float) -> str:
    x = float(px)
    if x >= 1000:
        return f"${x:,.0f}"
    if x >= 1:
        return f"${x:.2f}"
    return f"${x:.4f}"


def format_price_range_label(rng: PriceRange) -> str:
    base = f"{fmt_price(rng.low)}–{fmt_price(rng.high)}"
    if rng.close_end is not None and rng.close_end > 0:
        return f"{base}（收 {fmt_price(rng.close_end)}）"
    return base
