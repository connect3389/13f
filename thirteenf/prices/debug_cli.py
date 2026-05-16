"""调试 yfinance 日线：uv run python -m thirteenf.prices.debug_cli AVGO 2026-01-01 2026-03-31"""

from __future__ import annotations

import sys
from datetime import date

from thirteenf.envload import load_dotenv_if_present
from thirteenf.prices.errors import user_message_for_fetch_error
from thirteenf.prices.fetch import fetch_daily_bars, price_fetch_available
from thirteenf.prices.yfinance_provider import yfinance_available


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 3:
        print(
            "用法: python -m thirteenf.prices.debug_cli TICKER START END\n"
            "例: python -m thirteenf.prices.debug_cli AVGO 2026-01-01 2026-03-31"
        )
        return 1

    ticker = args[0].upper()
    start = date.fromisoformat(args[1])
    end = date.fromisoformat(args[2])

    print(f"yfinance_installed={yfinance_available()}")
    print(f"price_fetch_available={price_fetch_available()}")

    bars, err, source = fetch_daily_bars(ticker, start, end)
    if err:
        print(f"FAIL: {err}")
        print(f"提示: {user_message_for_fetch_error(err)}")
        return 2
    print(f"OK source={source} rows={len(bars)}")
    if bars:
        print(f"  first={bars[0].trade_date} last={bars[-1].trade_date}")
        lows = [b.low for b in bars]
        highs = [b.high for b in bars]
        print(f"  low={min(lows):.2f} high={max(highs):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
