"""CIK 规范化与输入校验。"""

from __future__ import annotations

import re

from thirteenf.filer_delete import normalize_cik

__all__ = ["normalize_cik", "parse_cik_input", "validate_cik_input"]


def parse_cik_input(raw: str) -> str | None:
    """仅数字 CIK → 10 位；含字母或其它字符则 None。"""
    s = (raw or "").strip()
    if not s:
        return None
    if not re.fullmatch(r"\d{1,10}", s):
        return None
    cik10 = normalize_cik(s)
    if not cik10 or cik10 == "0000000000":
        return None
    return cik10


def validate_cik_input(raw: str) -> tuple[bool, str | None, str]:
    cik10 = parse_cik_input(raw)
    if cik10:
        return True, cik10, ""
    s = (raw or "").strip()
    if not s:
        return False, None, "请输入 CIK（1–10 位数字）。"
    if re.search(r"[A-Za-z]", s):
        return False, None, "CIK 只能包含数字，不能含字母或其它符号。"
    if re.search(r"\D", s):
        return False, None, "CIK 格式无效：仅允许 1–10 位数字（可带前导零）。"
    return False, None, "CIK 无效或为空。"
