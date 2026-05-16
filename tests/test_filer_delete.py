"""删除机构：库记录与 raw 目录。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from thirteenf.db import SCHEMA, init_db
from thirteenf.filer_delete import delete_filer, normalize_cik


def test_delete_filer_removes_db_and_raw_dir(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute(
        """
        INSERT INTO filer_registry (cik, display_name) VALUES ('0001697748', 'ARK')
        """
    )
    conn.execute(
        """
        INSERT INTO ingest_record
          (id, filer_cik, report_date, source_channel, status, accession_number, raw_path)
        VALUES (1, '0001697748', '2026-03-31', 'edgar_xml', 'complete', '0001', ?)
        """,
        (str(tmp_path / "raw" / "0001697748" / "a.xml"),),
    )
    conn.execute(
        """
        INSERT INTO holding_line (ingest_id, line_no, cusip, value_as_reported)
        VALUES (1, 1, '037833100', 1000)
        """
    )
    conn.commit()

    raw_dir = tmp_path / "raw" / "0001697748"
    raw_dir.mkdir(parents=True)
    xml = raw_dir / "a.xml"
    xml.write_text("<xml/>", encoding="utf-8")

    result = delete_filer(
        conn, "1697748", raw_root=tmp_path / "raw", cwd=tmp_path
    )
    assert result.cik == "0001697748"
    assert result.ingest_deleted == 1
    assert result.registry_deleted is True
    assert result.raw_dir_removed is True
    assert conn.execute("SELECT COUNT(*) FROM ingest_record").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM holding_line").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM filer_registry").fetchone()[0] == 0
    assert not raw_dir.exists()
    conn.close()


def test_normalize_cik() -> None:
    assert normalize_cik("1697748") == "0001697748"
