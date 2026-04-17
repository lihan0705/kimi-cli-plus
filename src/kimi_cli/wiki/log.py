from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class WikiLogEntry:
    action: str
    source_title: str
    page_slug: str
    page_kind: str
    timestamp: datetime


def append_wiki_log(
    root: Path,
    *,
    action: str,
    source_title: str,
    page_slug: str,
    page_kind: str,
    timestamp: datetime | None = None,
) -> WikiLogEntry:
    entry = WikiLogEntry(
        action=action,
        source_title=source_title,
        page_slug=page_slug,
        page_kind=page_kind,
        timestamp=timestamp or datetime.now(),
    )
    line = (
        f"- [{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.action}: "
        f"{entry.source_title} -> [[{entry.page_slug}]] ({entry.page_kind})\n"
    )
    log_path = root / "log.md"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return entry
