"""13F XML ``value`` 字段单位推断（千美元 vs 美元）。"""

from __future__ import annotations

import sqlite3
import statistics
from typing import Iterable

# 按股数推算单价时的合理区间（美元）
_MIN_IMPLIED_PRICE = 0.5
_MAX_IMPLIED_PRICE = 25_000.0


def infer_value_usd_multiplier(
    holdings: Iterable[tuple[float, float]],
) -> float:
    """
    根据 ``(value_as_reported, shares)`` 样本推断乘数。

    返回 ``1.0``（XML 已是美元）或 ``1000.0``（XML 为千美元）。
    """
    ratios_d: list[float] = []
    ratios_k: list[float] = []
    for value, shares in holdings:
        v = float(value or 0)
        s = float(shares or 0)
        if v <= 0 or s <= 0:
            continue
        ratios_d.append(v / s)
        ratios_k.append(v * 1000.0 / s)
    if not ratios_d:
        return 1000.0

    med_d = statistics.median(ratios_d)
    med_k = statistics.median(ratios_k)

    def _ok(med: float) -> bool:
        return _MIN_IMPLIED_PRICE <= med <= _MAX_IMPLIED_PRICE

    d_ok, k_ok = _ok(med_d), _ok(med_k)
    if d_ok and not k_ok:
        return 1.0
    if k_ok and not d_ok:
        return 1000.0
    if d_ok and k_ok:
        import math

        target = 150.0
        score_d = abs(math.log(max(med_d, 1.0)) - math.log(target))
        score_k = abs(math.log(max(med_k, 1.0)) - math.log(target))
        return 1.0 if score_d <= score_k else 1000.0
    return 1000.0


def infer_multiplier_from_parsed_rows(rows: list[dict]) -> float:
    pairs = [
        (float(r.get("value") or 0), float(r.get("shares") or 0))
        for r in rows
    ]
    return infer_value_usd_multiplier(pairs)


def load_holdings_pairs(
    conn: sqlite3.Connection, ingest_id: int
) -> list[tuple[float, float]]:
    cur = conn.execute(
        """
        SELECT value_as_reported, shares FROM holding_line
        WHERE ingest_id = ? AND value_as_reported > 0 AND shares > 0
        """,
        (int(ingest_id),),
    )
    return [(float(r[0]), float(r[1])) for r in cur.fetchall()]


def value_usd_multiplier(conn: sqlite3.Connection, ingest_id: int) -> float:
    """优先读 ``ingest_record.value_usd_multiplier``，否则现场推断并回写。"""
    row = conn.execute(
        "SELECT value_usd_multiplier FROM ingest_record WHERE id = ?",
        (int(ingest_id),),
    ).fetchone()
    if row and row[0] is not None:
        m = float(row[0])
        if m in (1.0, 1000.0):
            return m
    pairs = load_holdings_pairs(conn, ingest_id)
    mult = infer_value_usd_multiplier(pairs)
    try:
        conn.execute(
            "UPDATE ingest_record SET value_usd_multiplier = ? WHERE id = ?",
            (mult, int(ingest_id)),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    return mult
