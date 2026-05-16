"""Yahoo Finance 日线（yfinance）。"""

from __future__ import annotations

from datetime import date, timedelta

from thirteenf.prices.bars import DailyBar


def yfinance_available() -> bool:
    try:
        import yfinance  # noqa: F401

        return True
    except ImportError:
        return False


def fetch_daily_candles_yfinance(
    ticker: str,
    start: date,
    end: date,
) -> tuple[list[DailyBar], str | None]:
    try:
        import yfinance as yf
    except ImportError:
        return [], "yfinance_not_installed"

    symbol = str(ticker).strip().upper()
    if not symbol:
        return [], "empty_ticker"

    try:
        df = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
    except Exception as exc:
        return [], f"yfinance_error:{exc}"

    if df is None or df.empty:
        return [], "no_data"

    bars: list[DailyBar] = []
    for idx, row in df.iterrows():
        try:
            td = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        except (TypeError, ValueError):
            continue
        if td < start or td > end:
            continue
        try:
            bars.append(
                DailyBar(
                    trade_date=td.isoformat(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0) or 0),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not bars:
        return [], "no_data"
    bars.sort(key=lambda b: b.trade_date)
    return bars, None
