"""Streamlit 与 SQLite 连接。"""

from __future__ import annotations

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
