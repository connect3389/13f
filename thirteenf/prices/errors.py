"""行情拉取错误解析（用户可见文案）。"""

from __future__ import annotations


def user_message_for_fetch_error(error_note: str | None) -> str:
    if not error_note:
        return "未知错误"

    note = str(error_note)

    if note == "yfinance_not_installed":
        return (
            "未安装 yfinance（本地：uv sync --extra gui；"
            "在线部署：requirements.txt 需含 yfinance）"
        )

    if note.startswith("yfinance_error:"):
        return f"Yahoo 行情拉取失败：{note.split(':', 1)[-1]}"

    if note == "no_data":
        return "该标的在季窗内无日线数据（可能 Ticker 错误或未上市）。"

    if note == "empty_ticker":
        return "无可用 Ticker，无法拉取行情。"

    if note == "invalid_input":
        return "报送或标的信息无效。"

    return note


def short_message_for_fetch_error(error_note: str | None) -> str:
    """表格单元格内一行展示的短文案。"""
    if not error_note:
        return "行情错误"

    note = str(error_note)

    if note == "yfinance_not_installed":
        return "需 yfinance"
    if note.startswith("yfinance_error:"):
        return "拉取失败"
    if note == "no_data":
        return "无季内数据"
    if note == "empty_ticker":
        return "无 Ticker"
    if note == "invalid_input":
        return "输入无效"

    return "行情错误"
