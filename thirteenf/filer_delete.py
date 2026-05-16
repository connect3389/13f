"""删除机构：SQLite 报送/持仓 + 本地 raw XML 目录。"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)


def normalize_cik(cik: str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(10)


def _resolve_raw_path(raw_path: str, *, cwd: Path | None = None) -> Path | None:
    p = Path(raw_path)
    if p.is_file():
        return p
    base = cwd or Path.cwd()
    alt = base / raw_path
    if alt.is_file():
        return alt
    return None


@dataclass
class FilerDeleteResult:
    cik: str
    ingest_deleted: int = 0
    registry_deleted: bool = False
    files_removed: int = 0
    raw_dir_removed: bool = False
    errors: list[str] = field(default_factory=list)


def delete_filer(
    conn: sqlite3.Connection,
    cik: str,
    *,
    raw_root: Path | None = None,
    cwd: Path | None = None,
) -> FilerDeleteResult:
    """
    删除指定 CIK 的全部 ``ingest_record``（级联 ``holding_line``）、
    ``filer_registry`` 登记，以及 ``data/raw/{cik}`` 目录与库内记录的路径文件。
    """
    cik10 = normalize_cik(cik)
    if not cik10:
        return FilerDeleteResult(cik=str(cik), errors=["invalid_cik"])

    result = FilerDeleteResult(cik=cik10)
    base = cwd or Path.cwd()
    root = raw_root or (base / "data" / "raw")

    rows = conn.execute(
        """
        SELECT id, raw_path FROM ingest_record
        WHERE filer_cik = ?
        """,
        (cik10,),
    ).fetchall()

    paths: set[Path] = set()
    for _iid, raw_path in rows:
        if not raw_path or not str(raw_path).strip():
            continue
        resolved = _resolve_raw_path(str(raw_path).strip(), cwd=base)
        if resolved:
            paths.add(resolved)

    cur = conn.execute("DELETE FROM ingest_record WHERE filer_cik = ?", (cik10,))
    result.ingest_deleted = int(cur.rowcount or 0)
    cur_reg = conn.execute("DELETE FROM filer_registry WHERE cik = ?", (cik10,))
    result.registry_deleted = bool(cur_reg.rowcount)

    conn.commit()

    for path in paths:
        try:
            if path.is_file():
                path.unlink()
                result.files_removed += 1
        except OSError as e:
            msg = f"unlink {path}: {e}"
            result.errors.append(msg)
            _log.warning("%s", msg)

    cik_dir = root / cik10
    if cik_dir.is_dir():
        try:
            shutil.rmtree(cik_dir)
            result.raw_dir_removed = True
        except OSError as e:
            msg = f"rmtree {cik_dir}: {e}"
            result.errors.append(msg)
            _log.warning("%s", msg)

    return result
