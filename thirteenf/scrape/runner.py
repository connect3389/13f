from __future__ import annotations

import json
import socket
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from thirteenf import PARSER_VERSION
from thirteenf.config import FilerEntry, effective_name_verify_mode
from thirteenf.db import connect
from thirteenf.scrape import edgar
from thirteenf.value_scale import infer_multiplier_from_parsed_rows
from thirteenf.scrape.name_verify import (
    extract_filing_manager_name_from_primary_html,
    verify_filer_identity,
)
from thirteenf.scrape.progress import FilerScrapeResult, ProgressCallback


def _filer_extra_payload(f: FilerEntry) -> dict[str, Any]:
    payload: dict[str, Any] = dict(f.extra)
    if f.name_zh:
        payload["name_zh"] = f.name_zh
    if f.intro:
        payload["intro"] = f.intro
    return payload


def _upsert_filer_registry(conn: sqlite3.Connection, f: FilerEntry) -> None:
    row = conn.execute(
        "SELECT extra_json FROM filer_registry WHERE cik = ?", (f.cik10,)
    ).fetchone()
    merged: dict[str, Any] = {}
    if row and row["extra_json"]:
        try:
            merged = json.loads(row["extra_json"])
        except json.JSONDecodeError:
            merged = {}
    merged.update(_filer_extra_payload(f))
    conn.execute(
        """
        INSERT INTO filer_registry (cik, slug, display_name, extra_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cik) DO UPDATE SET
          slug=excluded.slug,
          display_name=COALESCE(excluded.display_name, filer_registry.display_name),
          extra_json=excluded.extra_json,
          updated_at=datetime('now')
        """,
        (
            f.cik10,
            None,
            f.display_name,
            json.dumps(merged, ensure_ascii=False) if merged else None,
        ),
    )


def _emit(on_progress: ProgressCallback | None, level: str, message: str) -> None:
    if on_progress:
        on_progress(level, message)


def run_edgar_for_filer(
    conn: sqlite3.Connection,
    f: FilerEntry,
    raw_root: Path,
    *,
    run_id: str,
    force: bool = False,
    max_filings_per_filer: int = 8,
    defaults: dict[str, Any] | None = None,
    name_verify_cli: str = "auto",
    on_progress: ProgressCallback | None = None,
) -> FilerScrapeResult:
    """拉取单个 CIK 的 13F-HR(/A) 并写入当前连接上的 SQLite。"""
    defaults = defaults or {}
    result = FilerScrapeResult(cik=f.cik10)
    if not f.cik10.strip("0"):
        result.fatal_error = "CIK 无效"
        _emit(on_progress, "error", result.fatal_error)
        return result

    _upsert_filer_registry(conn, f)
    _emit(on_progress, "info", f"已登记机构 {f.cik10}")

    try:
        sub = edgar.fetch_submissions(f.cik10)
    except Exception as e:
        err = str(e).strip() or type(e).__name__
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 404 or "404" in err:
            result.fatal_error = f"CIK 在 SEC 不存在或无效：{f.cik10}"
        else:
            result.fatal_error = f"网络或 SEC 请求失败：{err}"
        _emit(on_progress, "error", result.fatal_error)
        result.log.append(result.fatal_error)
        return result

    sec_name = str(sub.get("name") or "").strip()
    result.sec_name = sec_name or None
    if sec_name:
        _emit(on_progress, "info", f"SEC 登记名：{sec_name}")
        if not (f.display_name and str(f.display_name).strip()):
            conn.execute(
                "UPDATE filer_registry SET display_name = ? WHERE cik = ?",
                (sec_name, f.cik10),
            )
            conn.commit()

    filings = edgar.iter_13f_filings(sub, f.cik10)
    if not filings:
        msg = "该 CIK 在 SEC submissions 中未找到 13F-HR 报送（可能非 13F 申报主体）。"
        result.fatal_error = msg
        _emit(on_progress, "warn", msg)
        result.log.append(msg)
        return result

    result.filings_seen = len(filings)
    _emit(on_progress, "info", f"发现 {len(filings)} 份近期 13F，最多处理 {max_filings_per_filer} 份")

    n_done = 0
    for filing in filings:
        if n_done >= max_filings_per_filer:
            break
        rd = filing.get("reportDate")
        acc = filing.get("accessionNumber")
        fd = filing.get("filingDate")
        if not rd or not acc:
            continue
        if _existing_complete(conn, f.cik10, rd, "edgar_xml", acc, force):
            result.skipped_existing += 1
            _emit(on_progress, "skip", f"已存在 complete：报告期 {rd} · {acc}")
            n_done += 1
            continue
        url = edgar.resolve_edgar_xml_url(f.cik10, filing)
        if not url:
            _emit(on_progress, "warn", f"无法解析 XML 地址：{acc}")
            continue

        _emit(on_progress, "info", f"抓取报告期 {rd} · {acc}")
        conn.execute(
            """
            INSERT INTO ingest_record (
              run_id, filer_cik, report_date, source_channel, status,
              accession_number, is_amendment, filing_date, primary_document,
              parser_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(filer_cik, report_date, source_channel, accession_number)
            DO UPDATE SET
              run_id=excluded.run_id,
              status='pending',
              parser_version=excluded.parser_version,
              is_amendment=excluded.is_amendment,
              filing_date=excluded.filing_date,
              primary_document=excluded.primary_document
            """,
            (
                run_id,
                f.cik10,
                rd,
                "edgar_xml",
                "pending",
                acc,
                1 if filing.get("is_amendment") else 0,
                fd,
                filing.get("primaryDocument"),
                PARSER_VERSION,
            ),
        )
        row_id = conn.execute(
            """
            SELECT id FROM ingest_record
            WHERE filer_cik=? AND report_date=? AND source_channel=? AND accession_number=?
            """,
            (f.cik10, rd, "edgar_xml", acc),
        ).fetchone()
        if not row_id:
            conn.commit()
            continue
        ingest_id = int(row_id["id"])
        conn.commit()
        rel_raw = raw_root / f.cik10 / f"{edgar.accession_to_nd(acc)}.xml"
        nv_messages: list[str] = []
        try:
            primary = edgar.fetch_primary_doc(url)
            sha = _write_raw(rel_raw, primary)
            nv_mode = effective_name_verify_mode(name_verify_cli, defaults, f)
            cover_nm = extract_filing_manager_name_from_primary_html(primary)
            nv = verify_filer_identity(
                expected_display=f.display_name,
                sec_submissions_name=sec_name,
                cover_primary_name=cover_nm,
                mode=nv_mode,
            )
            nv_messages = nv.messages
            conn.execute(
                """
                UPDATE ingest_record SET raw_path=?, raw_sha256=?, downloaded_at=datetime('now'),
                  verified_sec_name=?, verified_cover_name=?, name_verify_status=?, name_verify_detail=?
                WHERE id=?
                """,
                (
                    str(rel_raw),
                    sha,
                    sec_name or None,
                    cover_nm,
                    nv.status,
                    nv.detail_json(),
                    ingest_id,
                ),
            )
            conn.commit()
            if not nv.allow_ingest:
                conn.execute(
                    "UPDATE ingest_record SET status=?, warnings_json=? WHERE id=?",
                    (
                        "failed",
                        json.dumps(nv.messages, ensure_ascii=False),
                        ingest_id,
                    ),
                )
                conn.commit()
                result.failed += 1
                result.filings_processed += 1
                _emit(on_progress, "warn", f"名称校验未通过：报告期 {rd}")
                n_done += 1
                continue
            body, rows, warns = edgar.try_parse_or_find_infotable(
                f.cik10, filing, primary, primary_url=url
            )
            warns = nv.messages + list(warns)
            if body is not primary:
                rel_raw = raw_root / f.cik10 / f"{edgar.accession_to_nd(acc)}-effective.xml"
                sha = _write_raw(rel_raw, body)
        except Exception as e:
            err = str(e).strip() or type(e).__name__
            conn.execute(
                "UPDATE ingest_record SET status=?, warnings_json=? WHERE id=?",
                (
                    "failed",
                    json.dumps(
                        nv_messages + [err] if nv_messages else [err],
                        ensure_ascii=False,
                    ),
                    ingest_id,
                ),
            )
            conn.commit()
            result.failed += 1
            result.filings_processed += 1
            _emit(on_progress, "error", f"报告期 {rd} 失败：{err}")
            result.log.append(f"{rd}: {err}")
            continue
        if not rows:
            conn.execute(
                """
                UPDATE ingest_record SET status=?, raw_path=?, raw_sha256=?,
                  row_count=0, warnings_json=?, downloaded_at=datetime('now')
                WHERE id=?
                """,
                (
                    "failed",
                    str(rel_raw),
                    sha,
                    json.dumps(warns, ensure_ascii=False),
                    ingest_id,
                ),
            )
            result.failed += 1
            _emit(on_progress, "warn", f"报告期 {rd}：无持仓行")
        else:
            conn.execute("DELETE FROM holding_line WHERE ingest_id=?", (ingest_id,))
            _save_holdings(conn, ingest_id, rows, "edgar_xml")
            value_mult = infer_multiplier_from_parsed_rows(rows)
            conn.execute(
                """
                UPDATE ingest_record SET status=?, raw_path=?, raw_sha256=?,
                  row_count=?, warnings_json=?, downloaded_at=datetime('now'),
                  value_usd_multiplier=?
                WHERE id=?
                """,
                (
                    "complete",
                    str(rel_raw),
                    sha,
                    len(rows),
                    json.dumps(warns, ensure_ascii=False),
                    value_mult,
                    ingest_id,
                ),
            )
            result.complete += 1
            _emit(on_progress, "ok", f"报告期 {rd}：complete，{len(rows)} 行")
        conn.commit()
        result.filings_processed += 1
        n_done += 1

    summary = (
        f"完成：{result.complete} 份 complete，{result.failed} 份 failed，"
        f"{result.skipped_existing} 份已跳过"
    )
    _emit(on_progress, "info", summary)
    result.log.append(summary)
    return result


def _existing_complete(
    conn: sqlite3.Connection,
    cik: str,
    report_date: str,
    source: str,
    accession: str,
    force: bool,
) -> bool:
    if force:
        return False
    row = conn.execute(
        """
        SELECT id, accession_number, parser_version, status
        FROM ingest_record
        WHERE filer_cik=? AND report_date=? AND source_channel=?
        ORDER BY filing_date DESC, id DESC
        LIMIT 1
        """,
        (cik, report_date, source),
    ).fetchone()
    if not row:
        return False
    if row["status"] != "complete":
        return False
    if row["parser_version"] != PARSER_VERSION:
        return False
    return row["accession_number"] == accession


def _write_raw(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _save_holdings(
    conn: sqlite3.Connection,
    ingest_id: int,
    parsed: list[dict],
    source: str,
) -> None:
    conn.executemany(
        """
        INSERT INTO holding_line (
          ingest_id, line_no, issuer, title_of_class, cusip, figi,
          shares, value_as_reported, weight, investment_discretion, other_manager,
          source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(ingest_id, line_no) DO UPDATE SET
          issuer=excluded.issuer,
          title_of_class=excluded.title_of_class,
          cusip=excluded.cusip,
          figi=excluded.figi,
          shares=excluded.shares,
          value_as_reported=excluded.value_as_reported,
          investment_discretion=excluded.investment_discretion,
          other_manager=excluded.other_manager
        """,
        [
            (
                ingest_id,
                r.get("line_no"),
                r.get("nameOfIssuer"),
                r.get("titleOfClass"),
                r.get("cusip"),
                r.get("figi"),
                r.get("shares"),
                r.get("value"),
                r.get("investmentDiscretion"),
                r.get("otherManager"),
                source,
            )
            for r in parsed
        ],
    )
    conn.execute(
        """
        WITH t AS (
          SELECT id, value_as_reported FROM holding_line WHERE ingest_id=?
        ), s AS (SELECT SUM(value_as_reported) AS v FROM t)
        UPDATE holding_line SET weight = (
          CASE WHEN (SELECT v FROM s) > 0 THEN value_as_reported / (SELECT v FROM s) ELSE NULL END
        ) WHERE ingest_id=?
        """,
        (ingest_id, ingest_id),
    )


def run_edgar_for_watchlist(
    db_path: Path,
    filers: list[FilerEntry],
    raw_root: Path,
    *,
    run_id: str | None = None,
    force: bool = False,
    max_filings_per_filer: int = 8,
    watchlist_hash: str | None = None,
    defaults: dict[str, Any] | None = None,
    name_verify_cli: str = "auto",
) -> None:
    """从 SEC EDGAR 拉取 13F-HR(/A)，写入 SQLite。"""
    defaults = defaults or {}
    run_id = run_id or str(uuid.uuid4())
    hostname = socket.gethostname()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ingest_run (run_id, hostname, watchlist_hash) VALUES (?,?,?)",
            (run_id, hostname, watchlist_hash),
        )
        for f in filers:
            run_edgar_for_filer(
                conn,
                f,
                raw_root,
                run_id=run_id,
                force=force,
                max_filings_per_filer=max_filings_per_filer,
                defaults=defaults,
                name_verify_cli=name_verify_cli,
                on_progress=lambda _lvl, msg: print(f"[{f.cik10}] {msg}", flush=True),
            )

        conn.execute(
            "UPDATE ingest_run SET finished_at=datetime('now') WHERE run_id=?",
            (run_id,),
        )
        conn.commit()
