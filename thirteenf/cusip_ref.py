"""
CUSIP → 美股 ticker / 名称：通过 OpenFIGI `/v3/mapping` 写入 `cusip_ref`。

环境变量（可选）：
- `OPENFIGI_API_KEY`：提高限流；无密钥也可用（建议设置 User-Agent 含联系方式）。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Literal

import requests

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_SOURCE_V2 = "openfigi_v2"
DEFAULT_UA = "thirteenf/0.1 (local 13F; contact: local-dev)"


class SyncMode(str, Enum):
    """从 holding_line 决定要同步哪些 CUSIP。"""

    MISSING = "missing"
    """仅库中尚无 cusip_ref 行的 CUSIP（默认，最省 API）。"""

    REFRESH_GAPS = "refresh-gaps"
    """无记录、无 ticker、或曾标记 error 的 CUSIP（推荐抓取后执行）。"""

    FORCE_ALL = "force-all"
    """holding_line 中全部 DISTINCT CUSIP，覆盖已有映射。"""


def lookup_ticker(conn: sqlite3.Connection, cusip: str) -> str | None:
    """返回已缓存的 ticker；无记录或未解析则 None。"""
    c = _normalize_cusip(cusip)
    if not c:
        return None
    row = conn.execute(
        "SELECT ticker FROM cusip_ref WHERE cusip = ?",
        (c,),
    ).fetchone()
    if not row:
        return None
    t = row[0]
    return str(t).strip().upper() if t else None


def _pick_best_mapping(items: list[dict]) -> dict | None:
    if not items:
        return None
    pref_exch = frozenset({"UN", "UW", "UA", "UP", "UF", "UD", "UM"})

    def score(d: dict) -> tuple[int, int]:
        st = (d.get("securityType") or "") + " " + (d.get("securityDescription") or "")
        st2 = ((d.get("securityType2") or "") + " " + (d.get("securityDescription") or "")).lower()
        st_l = st.lower()
        exch = d.get("exchCode") or ""
        ms = (d.get("marketSector") or "").lower()
        s = 0
        if ms == "equity":
            s += 10
        if "common stock" in st_l or (d.get("securityType") == "Common Stock"):
            s += 12
        elif "common" in st_l:
            s += 6
        debt_kw = (" note", " bond", "debenture", "preferred stock", " warrant", " cd ", " muni")
        if any(k in st2 for k in debt_kw):
            s -= 25
        if "%" in (d.get("securityDescription") or "") and any(
            ch.isdigit() for ch in (d.get("ticker") or "")
        ):
            s -= 8
        if exch in pref_exch:
            s += 6
        if exch == "US":
            s += 1
        has_t = 1 if (d.get("ticker") or "").strip() else 0
        return (s, has_t)

    return max(items, key=lambda d: score(d))


def _normalize_cusip(raw: str) -> str:
    return str(raw).strip().upper()


def _openfigi_map_batch(
    cusips: list[str],
    *,
    api_key: str | None,
    id_type: str = "ID_CUSIP",
    timeout: float = 60.0,
) -> list[dict | None]:
    jobs = [{"idType": id_type, "idValue": c} for c in cusips]
    headers = {
        "Content-Type": "application/json",
        "User-Agent": os.environ.get("OPENFIGI_USER_AGENT", DEFAULT_UA),
    }
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    last_err: Exception | None = None
    for attempt in range(4):
        r = requests.post(
            OPENFIGI_MAPPING_URL,
            json=jobs,
            headers=headers,
            timeout=timeout,
        )
        if r.status_code == 429:
            last_err = RuntimeError(
                "OpenFIGI 429 — 请降低批量频率或配置 OPENFIGI_API_KEY"
            )
            time.sleep(2.0 * (attempt + 1))
            continue
        r.raise_for_status()
        last_err = None
        break
    else:
        assert last_err is not None
        raise last_err
    body = r.json()
    if not isinstance(body, list) or len(body) != len(cusips):
        raise RuntimeError(f"OpenFIGI 响应长度异常: {str(body)[:200]!r}")

    out: list[dict | None] = []
    for block in body:
        if not isinstance(block, dict):
            out.append(None)
            continue
        if block.get("error"):
            out.append(None)
            continue
        data = block.get("data")
        if not data or not isinstance(data, list):
            out.append(None)
            continue
        picked = _pick_best_mapping([x for x in data if isinstance(x, dict)])
        out.append(picked)
    return out


def _openfigi_map_cusips_with_fallback(
    cusips: list[str],
    *,
    api_key: str | None,
) -> list[dict | None]:
    """先 ID_CUSIP；未命中再对同一批用 ID_CINS（境外/以色列等 CUSIP 常需此类型）。"""
    primary = _openfigi_map_batch(cusips, api_key=api_key, id_type="ID_CUSIP")
    miss_idx = [i for i, m in enumerate(primary) if m is None]
    if not miss_idx:
        return primary
    retry_vals = [cusips[i] for i in miss_idx]
    secondary = _openfigi_map_batch(retry_vals, api_key=api_key, id_type="ID_CINS")
    for i, meta in zip(miss_idx, secondary):
        if meta is not None:
            primary[i] = meta
    return primary


def _sql_holdings_distinct_cusip() -> str:
    return """
        SELECT DISTINCT UPPER(TRIM(h.cusip)) AS c
        FROM holding_line h
        WHERE h.cusip IS NOT NULL AND TRIM(h.cusip) != ''
    """


def collect_cusips_for_sync(
    conn: sqlite3.Connection,
    mode: SyncMode | Literal["missing", "refresh-gaps", "force-all"],
) -> list[str]:
    """按模式从 holding_line 汇总待同步 CUSIP（大写、去重、保序）。"""
    if isinstance(mode, str):
        mode = SyncMode(mode)

    if mode == SyncMode.FORCE_ALL:
        sql = _sql_holdings_distinct_cusip() + " ORDER BY c"
        rows = conn.execute(sql).fetchall()
    elif mode == SyncMode.MISSING:
        sql = (
            _sql_holdings_distinct_cusip()
            + """
          AND NOT EXISTS (
            SELECT 1 FROM cusip_ref r WHERE r.cusip = UPPER(TRIM(h.cusip))
          )
          ORDER BY c
        """
        )
        rows = conn.execute(sql).fetchall()
    else:
        sql = (
            _sql_holdings_distinct_cusip()
            + """
          AND (
            NOT EXISTS (
              SELECT 1 FROM cusip_ref r WHERE r.cusip = UPPER(TRIM(h.cusip))
            )
            OR EXISTS (
              SELECT 1 FROM cusip_ref r
              WHERE r.cusip = UPPER(TRIM(h.cusip))
                AND (
                  r.ticker IS NULL OR TRIM(r.ticker) = ''
                  OR r.error_note IS NOT NULL
                )
            )
          )
          ORDER BY c
        """
        )
        rows = conn.execute(sql).fetchall()

    seen: set[str] = set()
    ordered: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        c = _normalize_cusip(r[0])
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def cusip_ref_coverage(conn: sqlite3.Connection) -> dict[str, int]:
    """holding_line 中 DISTINCT CUSIP 的映射覆盖统计。"""
    row = conn.execute(
        """
        WITH h AS (
          SELECT DISTINCT UPPER(TRIM(cusip)) AS c
          FROM holding_line
          WHERE cusip IS NOT NULL AND TRIM(cusip) != ''
        )
        SELECT
          (SELECT COUNT(*) FROM h) AS holdings_cusips,
          (SELECT COUNT(*) FROM h x
             JOIN cusip_ref r ON r.cusip = x.c
            WHERE r.ticker IS NOT NULL AND TRIM(r.ticker) != '') AS with_ticker,
          (SELECT COUNT(*) FROM cusip_ref) AS ref_rows
        """
    ).fetchone()
    if not row:
        return {"holdings_cusips": 0, "with_ticker": 0, "ref_rows": 0}
    return {
        "holdings_cusips": int(row[0] or 0),
        "with_ticker": int(row[1] or 0),
        "ref_rows": int(row[2] or 0),
    }


def _upsert_mapping(
    conn: sqlite3.Connection,
    cusip: str,
    meta: dict | None,
) -> bool:
    """写入单条；返回 True 表示解析到 ticker。"""
    if meta is None:
        conn.execute(
            """
            INSERT INTO cusip_ref (cusip, ticker, name, exch_code, security_type,
              figi, composite_figi, source, error_note, fetched_at)
            VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, ?, 'not_found', datetime('now'))
            ON CONFLICT(cusip) DO UPDATE SET
              ticker = NULL,
              name = NULL,
              exch_code = NULL,
              security_type = NULL,
              figi = NULL,
              composite_figi = NULL,
              source = excluded.source,
              error_note = excluded.error_note,
              fetched_at = excluded.fetched_at
            """,
            (cusip, OPENFIGI_SOURCE_V2),
        )
        return False

    ticker = (meta.get("ticker") or "").strip().upper() or None
    name = (meta.get("name") or "").strip() or None
    exch = (meta.get("exchCode") or "").strip() or None
    st = (meta.get("securityType") or "").strip() or None
    figi = (meta.get("figi") or "").strip() or None
    cfigi = (meta.get("compositeFIGI") or "").strip() or None
    conn.execute(
        """
        INSERT INTO cusip_ref (cusip, ticker, name, exch_code, security_type,
          figi, composite_figi, source, error_note, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, datetime('now'))
        ON CONFLICT(cusip) DO UPDATE SET
          ticker = excluded.ticker,
          name = excluded.name,
          exch_code = excluded.exch_code,
          security_type = excluded.security_type,
          figi = excluded.figi,
          composite_figi = excluded.composite_figi,
          source = excluded.source,
          error_note = NULL,
          fetched_at = excluded.fetched_at
        """,
        (cusip, ticker, name, exch, st, figi, cfigi, OPENFIGI_SOURCE_V2),
    )
    return bool(ticker)


def sync_cusip_refs_from_holdings(
    db_path: Path,
    *,
    mode: SyncMode | Literal["missing", "refresh-gaps", "force-all"] = SyncMode.MISSING,
    batch_size: int = 10,
    sleep_s: float = 1.0,
    limit: int | None = None,
    verbose: bool = True,
) -> tuple[int, int]:
    """
    从 `holding_line` 汇总 CUSIP，调用 OpenFIGI 写入 `cusip_ref`。
    返回 (解析到 ticker 条数, 未找到或批次失败条数)。
    """
    if isinstance(mode, str):
        mode = SyncMode(mode)

    api_key = (os.environ.get("OPENFIGI_API_KEY") or "").strip() or None
    max_per_request = 100 if api_key else 10
    batch_size = max(1, min(int(batch_size), max_per_request))

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        before = cusip_ref_coverage(conn)
        ordered = collect_cusips_for_sync(conn, mode)

    if limit is not None:
        ordered = ordered[: int(limit)]

    total = len(ordered)
    if verbose:
        print(
            f"mode={mode.value} holdings_cusips={before['holdings_cusips']} "
            f"ticker_before={before['with_ticker']}/{before['holdings_cusips']} "
            f"to_sync={total}",
            flush=True,
        )
    if not ordered:
        if verbose:
            print("nothing to sync.", flush=True)
        return 0, 0

    ok = 0
    bad = 0
    n_batches = (total + batch_size - 1) // batch_size
    for bi in range(0, total, batch_size):
        chunk = ordered[bi : bi + batch_size]
        batch_no = bi // batch_size + 1
        try:
            mapped = _openfigi_map_cusips_with_fallback(chunk, api_key=api_key)
        except Exception as e:
            print(f"batch {batch_no}/{n_batches} failed: {e}", file=sys.stderr)
            bad += len(chunk)
            time.sleep(sleep_s * 2)
            continue

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for cusip, meta in zip(chunk, mapped):
                if _upsert_mapping(conn, cusip, meta):
                    ok += 1
                else:
                    bad += 1
            conn.commit()

        if verbose:
            print(
                f"batch {batch_no}/{n_batches} ok_cum={ok} miss_cum={bad}",
                flush=True,
            )
        time.sleep(sleep_s)

    if verbose:
        with sqlite3.connect(db_path) as conn:
            after = cusip_ref_coverage(conn)
        print(
            f"coverage: {after['with_ticker']}/{after['holdings_cusips']} holdings CUSIPs have ticker "
            f"(cusip_ref rows={after['ref_rows']})",
            flush=True,
        )

    return ok, bad


def cli_main(argv: list[str] | None = None) -> int:
    from thirteenf.envload import load_dotenv_if_present

    load_dotenv_if_present()
    p = argparse.ArgumentParser(
        description="从 holding_line 同步 CUSIP→ticker 到 cusip_ref（OpenFIGI v2）"
    )
    p.add_argument("--db", type=Path, default=Path("data/13f_history.sqlite"))
    mode_g = p.add_mutually_exclusive_group()
    mode_g.add_argument(
        "--force-all",
        action="store_true",
        help="重拉 holding_line 中全部 DISTINCT CUSIP（覆盖已有 ticker）",
    )
    mode_g.add_argument(
        "--refresh-gaps",
        action="store_true",
        help="补无记录、无 ticker、或有 error_note 的 CUSIP（抓取后推荐）",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="每请求 CUSIP 数量（无 API 密钥时 OpenFIGI 上限为 10；有密钥可达 100）",
    )
    p.add_argument("--sleep", type=float, default=1.0, help="批次间隔秒数")
    p.add_argument("--limit", type=int, default=None, help="仅处理前 N 个 CUSIP（调试）")
    p.add_argument("-q", "--quiet", action="store_true", help="少输出进度")
    args = p.parse_args(argv)

    from thirteenf.db import init_db

    init_db(args.db)
    if args.force_all:
        mode = SyncMode.FORCE_ALL
    elif args.refresh_gaps:
        mode = SyncMode.REFRESH_GAPS
    else:
        mode = SyncMode.MISSING

    print(f"syncing CUSIP refs → {args.db.resolve()} ({mode.value})", flush=True)
    api_key = (os.environ.get("OPENFIGI_API_KEY") or "").strip() or None
    cap = 100 if api_key else 10
    ok, bad = sync_cusip_refs_from_holdings(
        args.db,
        mode=mode,
        batch_size=max(1, min(args.batch_size, cap)),
        sleep_s=max(0.0, args.sleep),
        limit=args.limit,
        verbose=not args.quiet,
    )
    print(f"done: resolved={ok} missing_or_failed={bad}", flush=True)
    return 0
