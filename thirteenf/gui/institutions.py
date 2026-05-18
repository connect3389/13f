"""机构、报送与持仓行查询（无 Streamlit UI）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from thirteenf.value_scale import value_usd_multiplier

_DEFAULT_WATCHLIST = Path("config/filers_watchlist.yaml")


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


def _complete_ciks(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT filer_cik FROM ingest_record
        WHERE status = 'complete'
        """
    ).fetchall()
    return {str(r[0]).strip() for r in rows if r[0]}


def _merge_watchlist_meta(
    rows: list[dict[str, object]], meta: dict[str, dict[str, str | None]]
) -> None:
    for row in rows:
        cik = str(row["cik"]).strip()
        m = meta.get(cik)
        if not m:
            continue
        if not row.get("display_name") and m.get("display_name"):
            row["display_name"] = m["display_name"]
        if m.get("name_zh"):
            row["name_zh"] = m["name_zh"]
        if m.get("intro"):
            row["intro"] = m["intro"]


def institution_picker_df(
    conn: sqlite3.Connection,
    watchlist_path: Path | None = _DEFAULT_WATCHLIST,
) -> pd.DataFrame:
    """
    机构下拉：``filer_registry`` + 库内报送 + watchlist 中尚未入库的 CIK。
    """
    base = tab_a_institution_list(conn)
    complete = _complete_ciks(conn)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()

    if not base.empty:
        for _, r in base.iterrows():
            cik = str(r["cik"]).strip()
            if not cik or cik in seen:
                continue
            seen.add(cik)
            rows.append(
                {
                    "cik": cik,
                    "display_name": r.get("display_name"),
                    "has_complete": cik in complete,
                    "in_db": True,
                }
            )

    wl_path = watchlist_path
    if wl_path is not None and not Path(wl_path).is_file():
        wl_path = Path.cwd() / wl_path
    wl_meta: dict[str, dict[str, str | None]] = {}
    if wl_path is not None and Path(wl_path).is_file():
        from thirteenf.config import load_watchlist

        _, filers = load_watchlist(Path(wl_path))
        wl_meta = {
            f.cik10: {
                "display_name": f.display_name,
                "name_zh": f.name_zh,
                "intro": f.intro,
            }
            for f in filers
            if f.cik10
        }
        for f in filers:
            cik = f.cik10
            if not cik or cik in seen:
                continue
            seen.add(cik)
            rows.append(
                {
                    "cik": cik,
                    "display_name": f.display_name,
                    "name_zh": f.name_zh,
                    "intro": f.intro,
                    "has_complete": False,
                    "in_db": False,
                }
            )

    if wl_meta:
        _merge_watchlist_meta(rows, wl_meta)

    if not rows:
        return pd.DataFrame(
            columns=["cik", "display_name", "name_zh", "intro", "has_complete", "in_db"]
        )
    out = pd.DataFrame(rows)
    out["_sort_name"] = out["display_name"].fillna("").astype(str).str.lower()
    out = out.sort_values(["_sort_name", "cik"]).drop(columns="_sort_name")
    return out.reset_index(drop=True)


def institution_picker_label(row: pd.Series) -> str:
    base = institution_label_row(row)
    if bool(row.get("has_complete")):
        return base
    if bool(row.get("in_db", True)):
        return f"{base} · 本地无 complete"
    return f"{base} · 未抓取"


def ingest_status_counts(conn: sqlite3.Connection, cik: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) FROM ingest_record
        WHERE filer_cik = ?
        GROUP BY status
        """,
        (str(cik).strip(),),
    ).fetchall()
    return {str(s): int(n) for s, n in rows}


def institution_label_row(row: pd.Series) -> str:
    cik = row["cik"]
    zh = row.get("name_zh")
    d = row.get("display_name")
    parts: list[str] = []
    if zh is not None and str(zh).strip():
        parts.append(str(zh).strip())
    if d is not None and str(d).strip():
        parts.append(str(d).strip())
    if parts:
        return f"{' · '.join(parts)} · {cik}"
    return str(cik)


def render_institution_intro(row: pd.Series) -> None:
    intro = row.get("intro")
    if intro is not None and str(intro).strip():
        st.caption(str(intro).strip())


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
    zh = df_inst.get("name_zh")
    d = df_inst.get("display_name")
    z = str(zh).strip() if zh is not None and str(zh).strip() else ""
    e = str(d).strip() if d is not None and str(d).strip() else ""
    if z and e:
        return f"{z}（{e}）"
    if z:
        return z
    if e:
        return e
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


def ingest_value_sum_raw(conn: sqlite3.Connection, ingest_id: int) -> float:
    r = conn.execute(
        """
        SELECT COALESCE(SUM(value_as_reported), 0)
        FROM holding_line
        WHERE ingest_id = ?
        """,
        (ingest_id,),
    ).fetchone()
    return float(r[0] or 0)


def ingest_value_sum_usd(conn: sqlite3.Connection, ingest_id: int) -> float:
    return ingest_value_sum_raw(conn, ingest_id) * value_usd_multiplier(
        conn, ingest_id
    )


def ingest_value_sum_thousands(conn: sqlite3.Connection, ingest_id: int) -> float:
    """兼容旧名：返回库内原始 value 合计（未乘单位）。"""
    return ingest_value_sum_raw(conn, ingest_id)


def value_by_cusip_raw(conn: sqlite3.Connection, ingest_id: int) -> pd.Series:
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


def value_by_cusip_kusd(conn: sqlite3.Connection, ingest_id: int) -> pd.Series:
    """兼容旧名：按 CUSIP 汇总的库内原始 value（未乘单位）。"""
    return value_by_cusip_raw(conn, ingest_id)


def value_by_cusip_usd(conn: sqlite3.Connection, ingest_id: int) -> pd.Series:
    mult = value_usd_multiplier(conn, ingest_id)
    return value_by_cusip_raw(conn, ingest_id) * mult


def apply_value_to_usd_column(
    df: pd.DataFrame, conn: sqlite3.Connection, ingest_id: int
) -> pd.DataFrame:
    """将 DataFrame 中的 ``value_as_reported`` 按报送乘数换算为美元。"""
    if df.empty or "value_as_reported" not in df.columns:
        return df
    mult = value_usd_multiplier(conn, ingest_id)
    out = df.copy()
    out["value_as_reported"] = pd.to_numeric(
        out["value_as_reported"], errors="coerce"
    ) * mult
    return out


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

    cur_v = value_by_cusip_usd(conn, cid)
    prev_v = value_by_cusip_usd(conn, pid)
    changes: list[dict] = []
    for cusip in set(cur_v.index) | set(prev_v.index):
        c = str(cusip).strip()
        if not c:
            continue
        cur_usd = float(cur_v.get(cusip, 0) or 0)
        prev_usd = float(prev_v.get(cusip, 0) or 0)
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


def load_holding_lines_for_table(
    conn: sqlite3.Connection,
    ingest_id: int,
    *,
    issuer_keyword: str = "",
    min_weight_pct: float = 0.0,
    apply_min_weight_before_aggregate: bool = False,
) -> pd.DataFrame:
    """读取单条报送的持仓行（含 discretion / otherManager）。"""
    sql = """
SELECT h.line_no, h.issuer, h.title_of_class, h.cusip, r.ticker, h.shares,
       h.value_as_reported, h.weight, h.investment_discretion, h.other_manager
FROM holding_line h
LEFT JOIN cusip_ref r ON r.cusip = TRIM(h.cusip)
WHERE h.ingest_id = ?
"""
    params: list = [int(ingest_id)]
    kw = issuer_keyword.strip()
    if kw:
        sql += " AND h.issuer LIKE ? ESCAPE '\\'"
        params.append(f"%{kw.replace('%', '\\%').replace('_', '\\_')}%")
    if apply_min_weight_before_aggregate and min_weight_pct > 0:
        sql += " AND h.weight >= ?"
        params.append(min_weight_pct / 100.0)
    sql += " ORDER BY h.weight DESC, h.value_as_reported DESC"
    return pd.read_sql(sql, conn, params=params)


def aggregate_holdings_by_cusip(df: pd.DataFrame) -> pd.DataFrame:
    """按 CUSIP 汇总股数与申报市值；发行人/类别取市值最大行，并记录原文行数。"""
    if df.empty:
        return df
    out = df.copy()
    out["_cusip_k"] = out["cusip"].map(
        lambda x: str(x).strip().upper() if x is not None else ""
    )
    out = out[out["_cusip_k"] != ""].copy()
    if out.empty:
        return out

    rows: list[dict] = []
    for _, g in out.groupby("_cusip_k", sort=False):
        val = pd.to_numeric(g["value_as_reported"], errors="coerce").fillna(0)
        pick = g.loc[val.idxmax()] if not val.empty else g.iloc[0]
        row = {k: pick[k] for k in pick.index if k not in ("_cusip_k", "_sort_val")}
        row["shares"] = float(pd.to_numeric(g["shares"], errors="coerce").sum())
        row["value_as_reported"] = float(val.sum())
        row["xml_line_count"] = int(len(g))
        row.pop("line_no", None)
        row.pop("investment_discretion", None)
        row.pop("other_manager", None)
        if "title_of_class" in g.columns:
            uniq = {
                str(x).strip()
                for x in g["title_of_class"]
                if x is not None and str(x).strip()
            }
            if len(uniq) > 1:
                row["title_of_class"] = "; ".join(sorted(uniq))
        rows.append(row)
    return pd.DataFrame(rows)


def recalculate_holdings_weight(df: pd.DataFrame) -> pd.DataFrame:
    """按当前表内申报市值重算 weight / weight_pct。"""
    if df.empty or "value_as_reported" not in df.columns:
        return df
    out = df.copy()
    val = pd.to_numeric(out["value_as_reported"], errors="coerce").fillna(0)
    total = float(val.sum())
    if total > 0:
        out["weight"] = val / total
    else:
        out["weight"] = np.nan
    return out


def prepare_holdings_display_df(
    df: pd.DataFrame,
    conn: sqlite3.Connection,
    filer_cik: str,
    ingest_id: int,
    *,
    aggregate_by_cusip: bool,
    min_weight_pct: float = 0.0,
) -> pd.DataFrame:
    """换算美元、可选 CUSIP 汇总、重算权重、过滤最小权重、补环比。"""
    if df.empty:
        return df
    d = df.copy()
    if aggregate_by_cusip:
        d = aggregate_holdings_by_cusip(d)
        d = apply_value_to_usd_column(d, conn, ingest_id)
        d = recalculate_holdings_weight(d)
        if min_weight_pct > 0 and "weight" in d.columns:
            d = d[d["weight"] >= min_weight_pct / 100.0].copy()
    else:
        if min_weight_pct > 0 and "weight" in d.columns:
            d = d[d["weight"] >= min_weight_pct / 100.0].copy()
        d = apply_value_to_usd_column(d, conn, ingest_id)
    if "weight" in d.columns:
        d["weight_pct"] = (pd.to_numeric(d["weight"], errors="coerce") * 100).round(4)
    return append_qoq_shares_pct(d, conn, filer_cik, ingest_id)
