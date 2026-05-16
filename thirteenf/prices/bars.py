"""日线 OHLCV 行（与数据源无关）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyBar:
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
