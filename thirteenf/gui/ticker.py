"""CUSIP → Ticker 展示（cusip_ref）。"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def merge_tickers_from_ref(
    conn: sqlite3.Connection, df: pd.DataFrame, cusip_col: str = "cusip"
) -> pd.DataFrame:
    if df.empty or cusip_col not in df.columns:
        return df
    keys = [
        str(x).strip().upper()
        for x in df[cusip_col].dropna().tolist()
        if str(x).strip()
    ]
    keys_u = list(dict.fromkeys(keys))
    if not keys_u:
        out = df.copy()
        out["ticker"] = None
        return out
    ph = ",".join("?" * len(keys_u))
    tdf = pd.read_sql(
        f"SELECT cusip, ticker FROM cusip_ref WHERE cusip IN ({ph})",
        conn,
        params=keys_u,
    )

    def _norm_ticker_val(raw: object) -> str | None:
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            return None
        s = str(raw).strip()
        if not s or s.lower() == "nan":
            return None
        return s.upper()

    m = {
        str(r["cusip"]).strip().upper(): _norm_ticker_val(r["ticker"])
        for _, r in tdf.iterrows()
        if r["cusip"]
    }

    def _t(v: object) -> str | None:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        k = str(v).strip().upper()
        return m.get(k)

    out = df.copy()
    out["ticker"] = out[cusip_col].map(_t)

    def _display_ticker(row: pd.Series) -> str:
        t = row.get("ticker")
        if t is not None and not (isinstance(t, float) and np.isnan(t)):
            s = str(t).strip()
            if s and s.lower() != "nan":
                return s.upper()
        c = row.get(cusip_col)
        if c is not None and not (isinstance(c, float) and np.isnan(c)):
            cs = str(c).strip()
            if cs and cs.lower() != "nan":
                return f"({cs.upper()})"
        return "—"

    out["ticker"] = out.apply(_display_ticker, axis=1)
    return out
