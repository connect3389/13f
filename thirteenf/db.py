from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS filer_registry (
  id INTEGER PRIMARY KEY,
  cik TEXT NOT NULL UNIQUE,
  slug TEXT,
  display_name TEXT,
  extra_json TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingest_run (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  hostname TEXT,
  watchlist_hash TEXT
);

CREATE TABLE IF NOT EXISTS ingest_record (
  id INTEGER PRIMARY KEY,
  run_id TEXT,
  filer_cik TEXT NOT NULL,
  report_date TEXT NOT NULL,
  source_channel TEXT NOT NULL,
  status TEXT NOT NULL,
  accession_number TEXT,
  is_amendment INTEGER NOT NULL DEFAULT 0,
  filing_date TEXT,
  primary_document TEXT,
  raw_path TEXT,
  raw_sha256 TEXT,
  downloaded_at TEXT,
  parser_version TEXT,
  row_count INTEGER,
  warnings_json TEXT,
  verified_sec_name TEXT,
  verified_cover_name TEXT,
  name_verify_status TEXT,
  name_verify_detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES ingest_run(run_id),
  UNIQUE(filer_cik, report_date, source_channel, accession_number)
);

CREATE INDEX IF NOT EXISTS idx_ingest_lookup
  ON ingest_record(filer_cik, report_date, source_channel, status);

CREATE TABLE IF NOT EXISTS holding_line (
  id INTEGER PRIMARY KEY,
  ingest_id INTEGER NOT NULL,
  line_no INTEGER,
  issuer TEXT,
  title_of_class TEXT,
  cusip TEXT,
  figi TEXT,
  shares REAL,
  value_as_reported REAL,
  weight REAL,
  source TEXT,
  ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (ingest_id) REFERENCES ingest_record(id) ON DELETE CASCADE,
  UNIQUE(ingest_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_holding_cusip ON holding_line(cusip);

CREATE TABLE IF NOT EXISTS cusip_ref (
  cusip TEXT NOT NULL PRIMARY KEY,
  ticker TEXT,
  name TEXT,
  exch_code TEXT,
  security_type TEXT,
  figi TEXT,
  composite_figi TEXT,
  source TEXT NOT NULL DEFAULT 'openfigi',
  error_note TEXT,
  fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
  gics_sector_code TEXT,
  gics_sector_en TEXT,
  gics_sector_zh TEXT,
  gics_industry_group_code TEXT,
  gics_industry_group_en TEXT,
  gics_industry_code TEXT,
  gics_industry_en TEXT,
  gics_subindustry_code TEXT,
  gics_subindustry_en TEXT,
  yahoo_sector TEXT,
  yahoo_industry TEXT,
  sector_source TEXT,
  sector_fetched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cusip_ref_ticker ON cusip_ref(ticker);

CREATE TABLE IF NOT EXISTS gics_hierarchy (
  subindustry_code TEXT NOT NULL PRIMARY KEY,
  subindustry_en TEXT NOT NULL,
  industry_code TEXT NOT NULL,
  industry_en TEXT NOT NULL,
  industry_group_code TEXT NOT NULL,
  industry_group_en TEXT NOT NULL,
  sector_code TEXT NOT NULL,
  sector_en TEXT NOT NULL,
  definition TEXT,
  hierarchy_version TEXT NOT NULL DEFAULT '202303'
);

CREATE INDEX IF NOT EXISTS idx_gics_h_sector ON gics_hierarchy(sector_code);
CREATE INDEX IF NOT EXISTS idx_gics_h_igroup ON gics_hierarchy(industry_group_code);
CREATE INDEX IF NOT EXISTS idx_gics_h_industry ON gics_hierarchy(industry_code);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_ingest_record(conn)
        _migrate_cusip_ref(conn)
        backfill_value_usd_multipliers(conn)
        conn.commit()


def _migrate_cusip_ref(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(cusip_ref)")}
    for col, typ in (
        ("gics_sector_code", "TEXT"),
        ("gics_sector_en", "TEXT"),
        ("gics_sector_zh", "TEXT"),
        ("gics_industry_group_code", "TEXT"),
        ("gics_industry_group_en", "TEXT"),
        ("gics_industry_code", "TEXT"),
        ("gics_industry_en", "TEXT"),
        ("gics_subindustry_code", "TEXT"),
        ("gics_subindustry_en", "TEXT"),
        ("yahoo_sector", "TEXT"),
        ("yahoo_industry", "TEXT"),
        ("sector_source", "TEXT"),
        ("sector_fetched_at", "TEXT"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE cusip_ref ADD COLUMN {col} {typ}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cusip_ref_gics ON cusip_ref(gics_sector_code)"
    )


def _migrate_ingest_record(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(ingest_record)")}
    for col, typ in (
        ("verified_sec_name", "TEXT"),
        ("verified_cover_name", "TEXT"),
        ("name_verify_status", "TEXT"),
        ("name_verify_detail", "TEXT"),
        ("value_usd_multiplier", "REAL"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE ingest_record ADD COLUMN {col} {typ}")


def backfill_value_usd_multipliers(conn: sqlite3.Connection) -> int:
    """为缺少乘数的 complete 报送推断并写入。返回更新行数。"""
    from thirteenf.value_scale import infer_value_usd_multiplier, load_holdings_pairs

    rows = conn.execute(
        """
        SELECT id FROM ingest_record
        WHERE status = 'complete'
          AND (value_usd_multiplier IS NULL OR value_usd_multiplier NOT IN (1, 1000))
        """
    ).fetchall()
    n = 0
    for (iid,) in rows:
        pairs = load_holdings_pairs(conn, int(iid))
        if not pairs:
            continue
        mult = infer_value_usd_multiplier(pairs)
        conn.execute(
            "UPDATE ingest_record SET value_usd_multiplier = ? WHERE id = ?",
            (mult, int(iid)),
        )
        n += 1
    return n


@contextmanager
def connect(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
