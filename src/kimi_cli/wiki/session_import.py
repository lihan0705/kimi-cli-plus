from __future__ import annotations

from pathlib import Path

from kimi_cli.wiki.raw_store import ImportedRawSession, archive_raw_session


def discover_legacy_sessions(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        found.extend(sorted(root.rglob("*.jsonl")))
    return found


def import_session_file(root: Path, source: Path, session_id: str) -> ImportedRawSession:
    return archive_raw_session(root, source, session_id)
