"""机构、报送与持仓行查询（无 Streamlit UI）。"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def tab_a_institution_list(conn: sqlite3.Connection) -> pd.DataFrame:
    reg = pd.read_sql(
        """
        SELECT cik, display_name FROM filer_registry
        ORDER BY COALESCE(display_name, ''), cik
        """,
        conn,
    )
    orphans = pd.read_sql(
        """
        SELECT DISTINCT ir.filer_cik AS cik,
               (
                 SELECT i2.verified_sec_name FROM ingest_record i2
                 WHERE i2.filer_cik = ir.filer_cik
                   AND i2.verified_sec_name IS NOT NULL
                   AND TRIM(i2.verified_sec_name) != ''
                 ORDER BY i2.filing_date DESC, i2.id DESC LIMIT 1
               ) AS display_name
        FROM ingest_record ir
        WHERE ir.filer_cik NOT IN (SELECT cik FROM filer_registry)
        ORDER BY ir.filer_cik
        """,
        conn,
    )
    if reg.empty and orphans.empty:
        return pd.DataFrame(columns=["cik", "display_name"])
    return pd.concat([reg, orphans], ignore_index=True)


def institution_label_row(row: pd.Series) -> str:
    d = row.get("display_name")
    cik = row["cik"]
    if d is not None and str(d).strip():
        return f"{d} · {cik}"
    return str(cik)


def institution_options_df(
    conn: sqlite3.Connection, statuses: list[str] | None
) -> pd.DataFrame:
    if statuses:
        ph = ",".join("?" * len(statuses))
        status_sql = f" AND ir.status IN ({ph})"
        params: list = list(statuses)
    else:
        status_sql = ""
        params = []
    sql = f"""
    SELECT DISTINCT ir.filer_cik AS cik,
           COALESCE(
             NULLIF(TRIM(fr.display_name), ''),
             (SELECT i2.verified_sec_name FROM ingest_record i2
              WHERE i2.filer_cik = ir.filer_cik
                AND i2.verified_sec_name IS NOT NULL
                AND TRIM(i2.verified_sec_name) != ''
              ORDER BY i2.filing_date DESC, i2.id DESC LIMIT 1)
           ) AS display_name
    FROM ingest_record ir
    LEFT JOIN filer_registry fr ON fr.cik = ir.filer_cik
    WHERE 1=1 {status_sql}
    ORDER BY COALESCE(display_name, ''), ir.filer_cik
    """
    return pd.read_sql(sql, conn, params=params)


def institution_label(row: pd.Series) -> str:
    return institution_label_row(row)


def filer_display_name_from_inst(df_inst: pd.Series) -> str:
    d = df_inst.get("display_name")
    if d is not None and str(d).strip():
        return str(d).strip()
    return "（未登记名称）"


def filing_label_short(row: pd.Series, *, show_status: bool = False) -> str:
    acc = row.get("accession_number") or "—"
    nrows = row.get("row_count")
    rc = f"{int(nrows)} 行" if pd.notna(nrows) and nrows is not None else "— 行"
    base = f"报告期 {row['report_date']} · {acc} · {rc} · #{row['id']}"
    if show_status and "status" in row.index and pd.notna(row.get("status")):
        return f"[{row['status']}] {base}"
    return base


def ingest_rows_for_cik(
    conn: sqlite3.Connection,
    cik: str,
    *,
    statuses: list[str] | None,
) -> pd.DataFrame:
    if statuses:
        ph = ",".join("?" * len(statuses))
        st_sql = f" AND ir.status IN ({ph})"
        params: list = [cik] + list(statuses)
    else:
        st_sql = ""
        params = [cik]
    sql = f"""
    SELECT ir.id, ir.filer_cik, ir.report_date, ir.status, ir.accession_number,
           ir.row_count, ir.filing_date, ir.is_amendment,
           ir.verified_sec_name, fr.display_name AS registry_display_name
    FROM ingest_record ir
    LEFT JOIN filer_registry fr ON fr.cik = ir.filer_cik
    WHERE ir.filer_cik = ? {st_sql}
    ORDER BY ir.filing_date DESC, ir.id DESC
    """
    return pd.read_sql(sql, conn, params=params)


def prior_complete_ingest_id(
    conn: sqlite3.Connection, filer_cik: str, current_ingest_id: int
) -> int | None:
    df = pd.read_sql(
        """
        SELECT id, report_date FROM ingest_record
        WHERE filer_cik = ? AND status = 'complete'
        ORDER BY report_date ASC, id ASC
        """,
        conn,
        params=[filer_cik],
    )
    if df.empty:
        return None
    matched = df[df["id"] == current_ingest_id]
    if matched.empty:
        return None
    pos = int(matched.index[0])
    if pos == 0:
        return None
    return int(df.iloc[pos - 1]["id"])


def shares_by_cusip(conn: sqlite3.Connection, ingest_id: int) -> pd.Series:
    df = pd.read_sql(
        """
        SELECT TRIM(cusip) AS cusip, SUM(shares) AS shares
        FROM holding_line
        WHERE ingest_id = ? AND cusip IS NOT NULL AND TRIM(cusip) != ''
        GROUP BY TRIM(cusip)
        """,
        conn,
        params=[ingest_id],
    )
    if df.empty:
        return pd.Series(dtype=float)
    return df.set_index("cusip")["shares"]


def append_qoq_shares_pct(
    d: pd.DataFrame,
    conn: sqlite3.Connection,
    filer_cik: str,
    ingest_id: int,
) -> pd.DataFrame:
    prev_id = prior_complete_ingest_id(conn, filer_cik, ingest_id)
    out = d.copy()
    if prev_id is None:
        out["qoq_shares_pct"] = np.nan
        return out
    prev_s = shares_by_cusip(conn, prev_id)

    def _prev_shares(cusip: object) -> float:
        if cusip is None or (isinstance(cusip, float) and np.isnan(cusip)):
            return np.nan
        k = str(cusip).strip()
        if not k or k not in prev_s.index:
            return np.nan
        return float(prev_s.loc[k])

    prev_shares_s = out["cusip"].map(_prev_shares)
    curr = pd.to_numeric(out["shares"], errors="coerce")
    out["qoq_shares_pct"] = np.where(
        prev_shares_s.notna() & (prev_shares_s != 0),
        (curr - prev_shares_s) / prev_shares_s * 100.0,
        np.nan,
    )
    return out


def ingest_value_sum_thousands(conn: sqlite3.Connection, ingest_id: int) -> float:
    r = conn.execute(
        """
        SELECT COALESCE(SUM(value_as_reported), 0)
        FROM holding_line
        WHERE ingest_id = ?
        """,
        (ingest_id,),
    ).fetchone()
    return float(r[0] or 0)


def value_by_cusip_kusd(conn: sqlite3.Connection, ingest_id: int) -> pd.Series:
    df = pd.read_sql(
        """
        SELECT TRIM(cusip) AS cusip, SUM(value_as_reported) AS val
        FROM holding_line
        WHERE ingest_id = ? AND cusip IS NOT NULL AND TRIM(cusip) != ''
        GROUP BY TRIM(cusip)
        """,
        conn,
        params=[ingest_id],
    )
    if df.empty:
        return pd.Series(dtype=float)
    return df.set_index("cusip")["val"].astype(float)


def cusip_changes_for_filing(
    conn: sqlite3.Connection, filer_cik: str, ingest_id: int
) -> tuple[list[dict], int, int] | None:
    cik = str(filer_cik).strip()
    cid = int(ingest_id)
    if not cik:
        return None
    pid = prior_complete_ingest_id(conn, cik, cid)
    if pid is None:
        return None

    cur_v = value_by_cusip_kusd(conn, cid)
    prev_v = value_by_cusip_kusd(conn, pid)
    changes: list[dict] = []
    for cusip in set(cur_v.index) | set(prev_v.index):
        c = str(cusip).strip()
        if not c:
            continue
        cur_usd = float(cur_v.get(cusip, 0) or 0) * 1000.0
        prev_usd = float(prev_v.get(cusip, 0) or 0) * 1000.0
        chg = cur_usd - prev_usd
        if abs(chg) < 1e-6 and cur_usd <= 0 and prev_usd <= 0:
            continue
        tag = ""
        if prev_usd <= 0 and cur_usd > 0:
            tag = "新建"
        elif cur_usd <= 0 and prev_usd > 0:
            tag = "清仓"
        changes.append(
            {
                "cusip": c,
                "change_usd": chg,
                "cur_usd": cur_usd,
                "prev_usd": prev_usd,
                "tag": tag,
            }
        )
    return changes, cid, pid


def issuer_for_cusip(
    conn: sqlite3.Connection, cusip: str, ingest_ids: list[int]
) -> str:
    if not ingest_ids:
        return cusip
    ph = ",".join("?" * len(ingest_ids))
    row = conn.execute(
        f"""
        SELECT issuer FROM holding_line
        WHERE TRIM(cusip) = TRIM(?) AND ingest_id IN ({ph})
          AND issuer IS NOT NULL AND TRIM(issuer) != ''
        LIMIT 1
        """,
        [cusip, *ingest_ids],
    ).fetchone()
    return str(row[0]).strip() if row and row[0] else cusip
