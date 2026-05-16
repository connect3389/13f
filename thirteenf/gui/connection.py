"""Streamlit 与 SQLite 连接。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import streamlit as st


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_resource
def cached_conn(db_resolved: str) -> sqlite3.Connection:
    return connect(Path(db_resolved))


def resolve_db(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def default_db_path() -> Path:
    """固定本地库路径；可用环境变量 ``THIRTEENF_DB`` 覆盖（无 GUI 切换）。"""
    raw = os.environ.get("THIRTEENF_DB", "").strip()
    if raw:
        return resolve_db(raw)
    return resolve_db(str(Path.cwd() / "data" / "13f_history.sqlite"))
