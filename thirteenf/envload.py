"""从项目目录或当前工作目录加载 .env（仅首次；不覆盖已在环境中设置的变量）。"""

from __future__ import annotations

from pathlib import Path

_loaded: bool = False


def load_dotenv_if_present() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # thirteenf/envload.py -> 仓库根目录
    repo_root = Path(__file__).resolve().parent.parent
    for base in (Path.cwd(), repo_root):
        env_path = base / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            return
    load_dotenv(override=False)
