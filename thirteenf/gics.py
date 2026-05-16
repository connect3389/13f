"""
MSCI / S&P GICS 一级行业（Sector，11 个官方板块）。

行业中文名为 GICS 官方英文名的标准译法，非自定义主题（如「半导体/AI」）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GicsSector:
    code: str
    name_en: str
    name_zh: str


# GICS Sector 官方代码与英文名称（MSCI/S&P Global GICS 结构）
GICS_SECTORS: dict[str, GicsSector] = {
    "10": GicsSector("10", "Energy", "能源"),
    "15": GicsSector("15", "Materials", "材料"),
    "20": GicsSector("20", "Industrials", "工业"),
    "25": GicsSector("25", "Consumer Discretionary", "非必需消费品"),
    "30": GicsSector("30", "Consumer Staples", "必需消费品"),
    "35": GicsSector("35", "Health Care", "医疗保健"),
    "40": GicsSector("40", "Financials", "金融"),
    "45": GicsSector("45", "Information Technology", "信息技术"),
    "50": GicsSector("50", "Communication Services", "通信服务"),
    "55": GicsSector("55", "Utilities", "公用事业"),
    "60": GicsSector("60", "Real Estate", "房地产"),
}

# Yahoo Finance `info["sector"]` 等字段 → GICS 一级代码（仅作 L1 归并，非 GICS 官方 API）
YAHOO_SECTOR_TO_GICS_CODE: dict[str, str] = {
    "Basic Materials": "15",
    "Materials": "15",
    "Communication Services": "50",
    "Consumer Cyclical": "25",
    "Consumer Defensive": "30",
    "Energy": "10",
    "Financial Services": "40",
    "Financials": "40",
    "Healthcare": "35",
    "Health Care": "35",
    "Industrials": "20",
    "Real Estate": "60",
    "Technology": "45",
    "Information Technology": "45",
    "Utilities": "55",
}


def sector_from_yahoo_label(label: str | None) -> GicsSector | None:
    if not label or not str(label).strip():
        return None
    key = str(label).strip()
    code = YAHOO_SECTOR_TO_GICS_CODE.get(key)
    if not code:
        # 大小写不敏感再试一次
        for k, c in YAHOO_SECTOR_TO_GICS_CODE.items():
            if k.lower() == key.lower():
                code = c
                break
    if not code:
        return None
    return GICS_SECTORS.get(code)


def lookup_gics_sector(conn, cusip: str) -> GicsSector | None:
    import sqlite3

    row = conn.execute(
        """
        SELECT gics_sector_code FROM cusip_ref
        WHERE cusip = ? AND gics_sector_code IS NOT NULL
        """,
        (str(cusip).strip(),),
    ).fetchone()
    if not row or not row[0]:
        return None
    return GICS_SECTORS.get(str(row[0]).strip())
