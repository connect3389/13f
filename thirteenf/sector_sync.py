"""
为 `cusip_ref` 同步 GICS 一至四级官方代码（Sector / Industry Group / Industry / Sub-Industry）。

流程：
1. 将 `data/ref/gics_hierarchy_march2023.csv` 载入 `gics_hierarchy` 参考表（可复用）。
2. 对每个 equity ticker 调 Yahoo Finance，L1 经官方 GICS Sector 映射，L2–L4 经层级表匹配。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sqlite3
import sys
import time
from pathlib import Path

from thirteenf.gics_hierarchy import (
    DEFAULT_HIERARCHY_CSV,
    _is_equity_ticker,
    hierarchy_row_count,
    load_gics_hierarchy_csv,
    resolve_gics_from_yahoo,
)


def _fetch_yahoo_info(ticker: str) -> dict:
    """拉取 Yahoo quoteSummary；抑制 404 等无效代码在终端上的 HTTP 报错输出。"""
    import yfinance as yf

    yfl = logging.getLogger("yfinance")
    prev_level = yfl.level
    yfl.setLevel(logging.CRITICAL)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    finally:
        yfl.setLevel(prev_level)


def ensure_gics_hierarchy_loaded(
    conn: sqlite3.Connection,
    csv_path: Path | None = None,
    *,
    force_reload: bool = False,
) -> int:
    if force_reload or hierarchy_row_count(conn) == 0:
        return load_gics_hierarchy_csv(conn, csv_path, replace=True)
    return hierarchy_row_count(conn)


def sync_gics_sectors_for_refs(
    db_path: Path,
    *,
    force_all: bool = False,
    force_reload_hierarchy: bool = False,
    csv_path: Path | None = None,
    sleep_s: float = 0.35,
    limit: int | None = None,
) -> tuple[int, int, int, int]:
    """
    返回 (L1成功, L2-L4完整匹配, 无法映射, 跳过非equity ticker)。
    """
    try:
        import yfinance as yf  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "需要安装 yfinance：uv sync --extra gui  或  uv pip install yfinance"
        ) from e

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        n_h = ensure_gics_hierarchy_loaded(
            conn, csv_path, force_reload=force_reload_hierarchy
        )
        conn.commit()
        print(f"gics_hierarchy rows: {n_h}", flush=True)

        if force_all:
            rows = conn.execute(
                """
                SELECT cusip, ticker FROM cusip_ref
                WHERE ticker IS NOT NULL AND TRIM(ticker) != ''
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT cusip, ticker FROM cusip_ref
                WHERE ticker IS NOT NULL AND TRIM(ticker) != ''
                  AND (
                    gics_sector_code IS NULL OR TRIM(gics_sector_code) = ''
                    OR sector_fetched_at IS NULL
                  )
                """
            ).fetchall()

    tickers = [(str(r[0]).strip(), str(r[1]).strip().upper()) for r in rows if r[1]]
    if limit is not None:
        tickers = tickers[: int(limit)]

    ok_l1 = full_match = unmapped = skipped = 0
    total = len(tickers)

    for n, (cusip, ticker) in enumerate(tickers, start=1):
        if not _is_equity_ticker(ticker):
            skipped += 1
            continue

        if n == 1 or n % 25 == 0 or n == total:
            print(f"  yahoo {n}/{total} …", flush=True)

        info = _fetch_yahoo_info(ticker)

        y_sector = info.get("sector")
        y_industry = info.get("industry")
        y_sector_s = str(y_sector).strip() if y_sector else None
        y_industry_s = str(y_industry).strip() if y_industry else None

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            gics = resolve_gics_from_yahoo(
                conn,
                yahoo_sector=y_sector_s,
                yahoo_industry=y_industry_s,
            )

        time.sleep(sleep_s)

        if gics is None:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE cusip_ref SET
                      gics_sector_code = NULL,
                      gics_sector_en = NULL,
                      gics_sector_zh = NULL,
                      gics_industry_group_code = NULL,
                      gics_industry_group_en = NULL,
                      gics_industry_code = NULL,
                      gics_industry_en = NULL,
                      gics_subindustry_code = NULL,
                      gics_subindustry_en = NULL,
                      yahoo_sector = ?,
                      yahoo_industry = ?,
                      sector_source = 'yfinance_unmapped',
                      sector_fetched_at = datetime('now')
                    WHERE cusip = ?
                    """,
                    (y_sector_s, y_industry_s, cusip),
                )
                conn.commit()
            unmapped += 1
            continue

        has_full = bool(gics.get("gics_subindustry_code"))
        source = (
            "gics_hierarchy+yfinance"
            if has_full
            else "yfinance_gics_l1_only"
        )

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE cusip_ref SET
                  gics_sector_code = ?,
                  gics_sector_en = ?,
                  gics_sector_zh = ?,
                  gics_industry_group_code = ?,
                  gics_industry_group_en = ?,
                  gics_industry_code = ?,
                  gics_industry_en = ?,
                  gics_subindustry_code = ?,
                  gics_subindustry_en = ?,
                  yahoo_sector = ?,
                  yahoo_industry = ?,
                  sector_source = ?,
                  sector_fetched_at = datetime('now')
                WHERE cusip = ?
                """,
                (
                    gics["gics_sector_code"],
                    gics["gics_sector_en"],
                    gics["gics_sector_zh"],
                    gics.get("gics_industry_group_code"),
                    gics.get("gics_industry_group_en"),
                    gics.get("gics_industry_code"),
                    gics.get("gics_industry_en"),
                    gics.get("gics_subindustry_code"),
                    gics.get("gics_subindustry_en"),
                    gics.get("yahoo_sector"),
                    gics.get("yahoo_industry"),
                    source,
                    cusip,
                ),
            )
            conn.commit()

        ok_l1 += 1
        if has_full:
            full_match += 1

    return ok_l1, full_match, unmapped, skipped


def cli_main(argv: list[str] | None = None) -> int:
    from thirteenf.envload import load_dotenv_if_present

    load_dotenv_if_present()
    p = argparse.ArgumentParser(
        description="同步 GICS 一至四级到 cusip_ref（官方层级表 + Yahoo）"
    )
    p.add_argument("--db", type=Path, default=Path("data/13f_history.sqlite"))
    p.add_argument("--csv", type=Path, default=DEFAULT_HIERARCHY_CSV)
    p.add_argument("--force-all", action="store_true", help="覆盖已有 GICS 字段")
    p.add_argument(
        "--reload-hierarchy",
        action="store_true",
        help="强制重载 gics_hierarchy 参考表",
    )
    p.add_argument("--sleep", type=float, default=0.35)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    from thirteenf.db import init_db

    init_db(args.db)
    print(f"syncing GICS L1–L4 → {args.db.resolve()}", flush=True)
    print(
        "（无效 Yahoo 代码会静默跳过；OpenFIGI 错映射如 1B2 不会刷屏 404）",
        flush=True,
    )
    ok_l1, full, bad, skip = sync_gics_sectors_for_refs(
        args.db,
        force_all=args.force_all,
        force_reload_hierarchy=args.reload_hierarchy,
        csv_path=args.csv,
        sleep_s=max(0.0, args.sleep),
        limit=args.limit,
    )
    print(
        f"done: l1_ok={ok_l1} l2_l4_full={full} unmapped={bad} "
        f"skipped_non_equity_ticker={skip}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
