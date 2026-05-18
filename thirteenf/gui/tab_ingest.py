"""Tab：机构录入与 SEC 抓取。"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import streamlit as st

from thirteenf.cik import validate_cik_input
from thirteenf.config import FilerEntry, load_watchlist
from thirteenf.db import connect
from thirteenf.gui.connection import cached_conn
from thirteenf.gui.institution_delete import institution_ui_revision
from thirteenf.gui.institutions import institution_picker_df, institution_picker_label
from thirteenf.scrape.runner import run_edgar_for_filer


_DEFAULT_WATCHLIST = Path("config/filers_watchlist.yaml")
_DEFAULT_RAW = Path("data/raw")
_MAX_FILINGS = 8


def _bump_institution_list() -> None:
    st.session_state["_inst_ui_rev"] = institution_ui_revision() + 1
    cached_conn.clear()


def _progress_line(level: str, message: str) -> str:
    icons = {
        "info": "ℹ️",
        "ok": "✅",
        "warn": "⚠️",
        "error": "❌",
        "skip": "⏭️",
    }
    return f"{icons.get(level, '·')} {message}"


def render(conn: sqlite3.Connection, db: Path) -> None:
    st.markdown(
        "通过 **CIK** 从 SEC 拉取 13F 并写入本地库。"
        " `config/filers_watchlist.yaml` 提供部署时的默认机构；此处录入的机构保存在 "
        "`filer_registry`，供所有访问者自行扩展分析对象。"
    )

    wl_path = _DEFAULT_WATCHLIST
    if not wl_path.is_file():
        wl_path = Path.cwd() / wl_path
    defaults: dict = {}
    if wl_path.is_file():
        defaults, _ = load_watchlist(wl_path)

    with st.form("filer_ingest_form", clear_on_submit=False):
        cik_raw = st.text_input(
            "CIK",
            placeholder="0001697748 或 1697748（仅数字，1–10 位）",
            help="仅允许数字；提交前会自动补齐为 10 位。",
        )
        name_zh = st.text_input("中文名（可选）", placeholder="例如：方舟投资")
        intro = st.text_area(
            "一句话简介（可选）",
            placeholder="例如：Cathie Wood 旗下主动型资管…",
            height=80,
        )
        max_filings = st.number_input(
            "最多抓取最近几份 13F",
            min_value=1,
            max_value=40,
            value=_MAX_FILINGS,
            step=1,
        )
        submitted = st.form_submit_button("开始抓取", type="primary", width="stretch")

    if not submitted:
        _render_institution_preview(conn)
        return

    ok, cik10, err = validate_cik_input(cik_raw)
    if not ok or not cik10:
        st.error(err or "CIK 无效")
        return

    log_lines: list[str] = []
    progress_bar = st.progress(0.0, text="准备抓取…")
    log_placeholder = st.empty()
    progress_steps = [0]
    progress_denom = max(int(max_filings) + 3, 4)

    def on_progress(level: str, message: str) -> None:
        log_lines.append(_progress_line(level, message))
        log_placeholder.code("\n".join(log_lines[-50:]), language=None)
        if level in ("ok", "error", "warn", "skip", "info"):
            progress_steps[0] += 1
            progress_bar.progress(
                min(0.95, progress_steps[0] / progress_denom),
                text=message[:120],
            )

    name_zh_val = (name_zh or "").strip() or None
    intro_val = (intro or "").strip() or None
    filer = FilerEntry(
        cik=cik10,
        display_name=None,
        name_zh=name_zh_val,
        intro=intro_val,
        extra={"source": "gui"},
    )

    run_id = str(uuid.uuid4())
    raw_root = _DEFAULT_RAW
    if not raw_root.is_absolute():
        raw_root = Path.cwd() / raw_root

    with st.status(f"正在抓取 {cik10}…", expanded=True) as status:
        try:
            with connect(db) as scrape_conn:
                scrape_conn.execute(
                    """
                    INSERT INTO ingest_run (run_id, hostname, watchlist_hash)
                    VALUES (?, 'streamlit-gui', NULL)
                    """,
                    (run_id,),
                )
                scrape_conn.commit()
                result = run_edgar_for_filer(
                    scrape_conn,
                    filer,
                    raw_root,
                    run_id=run_id,
                    force=False,
                    max_filings_per_filer=int(max_filings),
                    defaults=defaults,
                    name_verify_cli="auto",
                    on_progress=on_progress,
                )
                scrape_conn.execute(
                    "UPDATE ingest_run SET finished_at=datetime('now') WHERE run_id=?",
                    (run_id,),
                )
                scrape_conn.commit()
        except Exception as e:
            status.update(label="抓取异常", state="error")
            st.error(f"抓取过程异常：{e}")
            return

        if result.fatal_error:
            status.update(label="抓取未完成", state="error")
            st.error(result.fatal_error)
        elif result.complete > 0:
            label = result.sec_name or cik10
            status.update(label=f"抓取完成 · {label}", state="complete")
            st.success(
                f"**{cik10}** · {result.sec_name or '—'}："
                f"{result.complete} 份 complete，{result.failed} 份 failed，"
                f"{result.skipped_existing} 份已跳过。"
            )
        elif result.failed > 0:
            status.update(label="部分失败", state="error")
            st.warning(
                f"未产生 complete 报送（failed {result.failed}）。"
                "可在「原始数据」查看 `warnings_json`。"
            )
        else:
            status.update(label="无新报送", state="complete")
            st.info("未发现需要新抓取的 13F（可能均已入库）。")

    progress_bar.progress(1.0, text="完成")
    _bump_institution_list()
    st.divider()
    _render_institution_preview(conn)


def _render_institution_preview(conn: sqlite3.Connection) -> None:
    st.markdown("##### 当前追踪机构")
    df = institution_picker_df(conn)
    if df.empty:
        st.caption("尚无机构。请录入 CIK 或配置 watchlist 后抓取。")
        return
    lines = [institution_picker_label(df.iloc[i]) for i in range(len(df))]
    st.caption(f"共 {len(lines)} 家")
    st.code("\n".join(lines), language=None)
