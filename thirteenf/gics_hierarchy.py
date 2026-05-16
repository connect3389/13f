"""
官方 GICS 层级表（Sub-Industry → Sector）加载与按 Yahoo industry 匹配。

数据源：`data/ref/gics_hierarchy_march2023.csv`（MSCI GICS 2023-03 结构，gist/uknj）。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from thirteenf.gics import GICS_SECTORS, sector_from_yahoo_label

DEFAULT_HIERARCHY_CSV = (
    Path(__file__).resolve().parent.parent / "data/ref/gics_hierarchy_march2023.csv"
)
HIERARCHY_VERSION = "202303"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _is_equity_ticker(ticker: str) -> bool:
    """Yahoo 可用的美股/ADR 代码；排除债、ETP 描述符与 OpenFIGI 常见错映射。"""
    t = str(ticker).strip().upper()
    if not t or " " in t or "%" in t:
        return False
    # 如 Bitfarms → 1B2：Yahoo 无此代码，只会 404
    if re.fullmatch(r"[0-9][A-Z0-9]{0,4}", t):
        return False
    return True


def load_gics_hierarchy_csv(
    conn: sqlite3.Connection,
    csv_path: Path | None = None,
    *,
    replace: bool = True,
) -> int:
    path = csv_path or DEFAULT_HIERARCHY_CSV
    if not path.is_file():
        raise FileNotFoundError(f"GICS 层级 CSV 不存在: {path}")

    df = pd.read_csv(path, dtype=str)
    required = {
        "Sub-Industry Code",
        "Sub-Industry",
        "Industry Code",
        "Industry",
        "Industry Group Code",
        "Industry Group",
        "Sector Code",
        "Sector",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"GICS CSV 缺列: {missing}")

    if replace:
        conn.execute("DELETE FROM gics_hierarchy")

    rows = []
    for _, r in df.iterrows():
        sc = str(r["Sector Code"]).strip().zfill(2)
        rows.append(
            (
                str(r["Sub-Industry Code"]).strip(),
                str(r["Sub-Industry"]).strip(),
                str(r["Industry Code"]).strip(),
                str(r["Industry"]).strip(),
                str(r["Industry Group Code"]).strip(),
                str(r["Industry Group"]).strip(),
                sc,
                str(r["Sector"]).strip(),
                (str(r.get("Definition") or "").strip() or None),
                HIERARCHY_VERSION,
            )
        )
    conn.executemany(
        """
        INSERT OR REPLACE INTO gics_hierarchy (
          subindustry_code, subindustry_en, industry_code, industry_en,
          industry_group_code, industry_group_en, sector_code, sector_en,
          definition, hierarchy_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def hierarchy_row_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM gics_hierarchy").fetchone()
    return int(row[0] or 0)


def match_hierarchy_row(
    conn: sqlite3.Connection,
    *,
    sector_code: str,
    yahoo_industry: str | None,
) -> sqlite3.Row | None:
    """在已定 L1 下，用 Yahoo industry 文本匹配官方 Sub-Industry / Industry。"""
    sc = str(sector_code).strip().zfill(2)
    rows = conn.execute(
        """
        SELECT * FROM gics_hierarchy WHERE sector_code = ?
        """,
        (sc,),
    ).fetchall()
    if not rows:
        return None
    if not yahoo_industry or not str(yahoo_industry).strip():
        return None

    yn = _norm(yahoo_industry)
    # 精确匹配 Sub-Industry / Industry
    for row in rows:
        if _norm(row["subindustry_en"]) == yn or _norm(row["industry_en"]) == yn:
            return row
    # 包含匹配（Yahoo 文案与 GICS 名不完全一致时）
    for row in rows:
        for col in ("subindustry_en", "industry_en"):
            gn = _norm(row[col])
            if gn and (yn in gn or gn in yn):
                return row
    return None


def resolve_gics_from_yahoo(
    conn: sqlite3.Connection,
    *,
    yahoo_sector: str | None,
    yahoo_industry: str | None,
) -> dict | None:
    """
    返回写入 cusip_ref 的 GICS 字段 dict；至少含 L1，匹配成功时含 L2/L3/L4 官方英文名与代码。
    """
    l1 = sector_from_yahoo_label(yahoo_sector)
    if l1 is None:
        return None

    out: dict = {
        "gics_sector_code": l1.code,
        "gics_sector_en": l1.name_en,
        "gics_sector_zh": l1.name_zh,
        "yahoo_sector": yahoo_sector,
        "yahoo_industry": yahoo_industry,
        "gics_industry_group_code": None,
        "gics_industry_group_en": None,
        "gics_industry_code": None,
        "gics_industry_en": None,
        "gics_subindustry_code": None,
        "gics_subindustry_en": None,
    }

    row = match_hierarchy_row(
        conn, sector_code=l1.code, yahoo_industry=yahoo_industry
    )
    if row is not None:
        out.update(
            {
                "gics_industry_group_code": row["industry_group_code"],
                "gics_industry_group_en": row["industry_group_en"],
                "gics_industry_code": row["industry_code"],
                "gics_industry_en": row["industry_en"],
                "gics_subindustry_code": row["subindustry_code"],
                "gics_subindustry_en": row["subindustry_en"],
            }
        )
    elif yahoo_industry:
        # 仅 L1 官方；L3 保留 Yahoo industry 作参考（非 GICS 官方名）
        out["gics_industry_en"] = str(yahoo_industry).strip()

    return out
