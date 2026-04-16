from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kimi_cli.knowledge.models import RawSessionRecord
from kimi_cli.wiki.models import RawSourceKind, WikiSourceRef


@dataclass(slots=True)
class ImportedRawSession:
    metadata: RawSessionRecord
    raw_path: Path


def archive_raw_session(root: Path, source: Path, session_id: str) -> ImportedRawSession:
    sessions_dir = root / "raw" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    raw_path = sessions_dir / f"{session_id}.jsonl"
    raw_path.write_bytes(source.read_bytes())

    metadata = RawSessionRecord(
        source=WikiSourceRef(
            kind=RawSourceKind.SESSION,
            source_id=session_id,
            original_path=str(source),
        )
    )
    return ImportedRawSession(metadata=metadata, raw_path=raw_path)
