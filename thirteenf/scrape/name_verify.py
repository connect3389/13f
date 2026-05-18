"""CIK 与报送名称二次校验：submissions.name 与 primary 封面管理人名称。"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field


def normalize_filer_name(s: str) -> str:
    """去大小写、标点、多余空白，便于比对。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower().strip()
    s = re.sub(r"[\s\u00a0]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def names_align(a: str, b: str) -> bool:
    na, nb = normalize_filer_name(a), normalize_filer_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def extract_filing_manager_name_from_primary_html(content: bytes) -> str | None:
    """
    从 13F primary_doc（HTML 封面）抽取「Filing Manager Information」下的 Name。
    """
    text = content.decode("utf-8", errors="ignore")
    m = re.search(
        r'summary="Filing Manager Information"[^>]*>[\s\S]*?'
        r'FormText">Name:</td>\s*<td[^>]*class="FormData"[^>]*>([^<]+)</td>',
        text,
        re.I,
    )
    if m:
        raw = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())
        return raw
    return None


@dataclass
class NameVerifyResult:
    ok: bool
    allow_ingest: bool
    status: str
    messages: list[str] = field(default_factory=list)

    def detail_json(self) -> str:
        return json.dumps(
            {"status": self.status, "messages": self.messages, "ok": self.ok},
            ensure_ascii=False,
        )


def verify_filer_identity(
    *,
    expected_display: str | None,
    sec_submissions_name: str,
    cover_primary_name: str | None,
    mode: str,
) -> NameVerifyResult:
    """
    mode:
    - off: 仅记录 SEC / 封面解析结果，不拦截
    - warn: 不一致时写入告警，仍入库
    - fail: 不一致时不写入持仓（ingest 标记 failed）
    """
    messages: list[str] = []
    mode = (mode or "off").lower()
    sec = (sec_submissions_name or "").strip()

    if not sec:
        return NameVerifyResult(
            ok=False,
            allow_ingest=mode != "fail",
            status="missing_sec_name",
            messages=["data.sec.gov submissions 缺少顶层 name"],
        )

    messages.append(f"SEC submissions.name = {sec!r}")

    blocking: list[str] = []

    exp = (expected_display or "").strip()
    if exp:
        if names_align(exp, sec):
            messages.append(f"watchlist display_name 与 SEC 一致 ({exp!r})")
        else:
            messages.append(
                f"watchlist display_name 与 SEC 不同（仅展示标签，不拦截）— 清单 {exp!r} vs SEC {sec!r}"
            )

    if cover_primary_name:
        if names_align(cover_primary_name, sec):
            messages.append(f"primary 封面管理人与 SEC 一致 ({cover_primary_name!r})")
        else:
            blocking.append("cover")
            messages.append(
                f"primary 封面 Name 与 SEC 不符 — 封面 {cover_primary_name!r} vs SEC {sec!r}"
            )
    else:
        messages.append("primary 封面未解析到管理人 Name（略过封面交叉项）")

    if mode == "off":
        return NameVerifyResult(True, True, "off", messages)

    if not blocking:
        return NameVerifyResult(True, True, "ok", messages)

    if mode == "warn":
        return NameVerifyResult(False, True, "warn_" + "_".join(blocking), messages)

    return NameVerifyResult(False, False, "fail_" + "_".join(blocking), messages)
