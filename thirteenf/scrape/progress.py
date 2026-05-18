from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ProgressCallback = Callable[[str, str], None]


@dataclass
class FilerScrapeResult:
    cik: str
    sec_name: str | None = None
    filings_seen: int = 0
    filings_processed: int = 0
    complete: int = 0
    failed: int = 0
    skipped_existing: int = 0
    log: list[str] = field(default_factory=list)
    fatal_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.fatal_error is None and (self.complete > 0 or self.filings_processed > 0)
