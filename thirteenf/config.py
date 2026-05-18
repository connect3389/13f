from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FilerEntry:
    cik: str
    display_name: str | None
    extra: dict[str, Any]

    @property
    def cik10(self) -> str:
        return self.cik.zfill(10)


def load_watchlist(path: Path) -> tuple[dict[str, Any], list[FilerEntry]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    rows = raw.get("filers") or []
    entries: list[FilerEntry] = []
    for row in rows:
        entries.append(
            FilerEntry(
                cik=str(row["cik"]).strip().zfill(10) if row.get("cik") else "",
                display_name=row.get("display_name"),
                extra={
                    k: v
                    for k, v in row.items()
                    if k not in ("cik", "display_name")
                },
            )
        )
    return defaults, entries


def watchlist_content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def effective_name_verify_mode(cli: str, defaults: dict[str, Any], filer: FilerEntry) -> str:
    """
    CLI --name-verify 优先；否则 defaults.name_verify；
    再否则 warn：抓取已按 CIK 定向，display_name 不参与拦截；fail 时仅 SEC vs 封面 Name。
    """
    if cli and cli != "auto":
        return cli
    d = defaults.get("name_verify")
    if d is not None:
        v = str(d).lower().strip()
        if v in ("off", "warn", "fail"):
            return v
    return "warn"
