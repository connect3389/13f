"""Streamlit 控件封装（触摸设备友好）。"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

import streamlit as st

T = TypeVar("T")


def pick_selectbox(
    label: str,
    options: Any,
    index: int | None = 0,
    format_func: Callable[[Any], str] = str,
    key: str | None = None,
    help: str | None = None,
    *,
    label_visibility: str = "visible",
    disabled: bool = False,
    placeholder: str | None = None,
    on_change: Any = None,
    args: Any = None,
    kwargs: Any = None,
    width: Any = "stretch",
) -> Any:
    """
    点选式下拉：``filter_mode=None``，无搜索输入框，触摸设备不会拉起键盘。
    """
    return st.selectbox(
        label,
        options,
        index=index,
        format_func=format_func,
        key=key,
        help=help,
        label_visibility=label_visibility,
        disabled=disabled,
        placeholder=placeholder,
        on_change=on_change,
        args=args,
        kwargs=kwargs,
        accept_new_options=False,
        filter_mode=None,
        width=width,
    )
