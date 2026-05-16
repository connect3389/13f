from __future__ import annotations

import argparse
import sys
from pathlib import Path

from thirteenf.config import load_watchlist, watchlist_content_hash
from thirteenf.db import init_db
from thirteenf.envload import load_dotenv_if_present
from thirteenf.scrape.runner import run_edgar_for_watchlist


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    p = argparse.ArgumentParser(description="13F 抓取：SEC EDGAR → SQLite")
    p.add_argument("--config", type=Path, default=Path("config/filers_watchlist.yaml"))
    p.add_argument("--db", type=Path, default=Path("data/13f_history.sqlite"))
    p.add_argument("--force", action="store_true", help="忽略本地 complete 记录强制重拉同一 accession")
    p.add_argument("--max-per-filer", type=int, default=8, help="每个 CIK 最多处理最近 N 份 13F-HR(/A)")
    p.add_argument(
        "--name-verify",
        choices=("auto", "off", "warn", "fail"),
        default="auto",
        help="机构名校验：auto=读 config defaults 或「有 display_name 则 fail 否则 warn」；off 不拦截",
    )
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--init-db-only", action="store_true")
    args = p.parse_args(argv)

    init_db(args.db)
    if args.init_db_only:
        print(f"initialized {args.db}")
        return 0

    defaults, filers = load_watchlist(args.config)
    w_hash = watchlist_content_hash(args.config)

    run_edgar_for_watchlist(
        args.db,
        filers,
        args.raw_dir,
        force=args.force,
        max_filings_per_filer=args.max_per_filer,
        watchlist_hash=w_hash,
        defaults=defaults,
        name_verify_cli=args.name_verify,
    )
    print(f"done. db={args.db} watchlist_hash={w_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
