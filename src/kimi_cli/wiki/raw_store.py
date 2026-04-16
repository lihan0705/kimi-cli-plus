from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kimi_cli.knowledge.models import RawSessionRecord
from kimi_cli.wiki.models import RawSourceKind, WikiSourceRef


@dataclass(slots=True)
class ImportedRawSession:
    metadata: RawSessionRecord
    raw_path: Path
    metadata_path: Path


def _session_raw_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.jsonl"


def _session_metadata_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.metadata.json"


def _load_raw_session_record(metadata_path: Path) -> RawSessionRecord:
    return RawSessionRecord.model_validate_json(metadata_path.read_text(encoding="utf-8"))


def _write_raw_session_record(metadata_path: Path, metadata: RawSessionRecord) -> None:
    metadata_path.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _build_raw_session_record(source: Path, session_id: str) -> RawSessionRecord:
    normalized_source = source.expanduser().resolve()
    return RawSessionRecord(
        source=WikiSourceRef(
            kind=RawSourceKind.SESSION,
            source_id=session_id,
            original_path=str(normalized_source),
        )
    )


def archive_raw_session(root: Path, source: Path, session_id: str) -> ImportedRawSession:
    sessions_dir = root / "raw" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    raw_path = _session_raw_path(sessions_dir, session_id)
    metadata_path = _session_metadata_path(sessions_dir, session_id)

    if metadata_path.exists() and not raw_path.exists():
        raise ValueError(f"Missing archived raw session for {session_id}")

    incoming_bytes = source.read_bytes()
    incoming_metadata = _build_raw_session_record(source, session_id)

    if raw_path.exists():
        if not metadata_path.exists():
            raise ValueError(f"Missing archived provenance for {session_id}")
        if raw_path.read_bytes() != incoming_bytes:
            raise ValueError(f"Conflicting raw session archive for {session_id}")
        existing_metadata = _load_raw_session_record(metadata_path)
        if existing_metadata != incoming_metadata:
            raise ValueError(f"Conflicting raw session metadata for {session_id}")
        return ImportedRawSession(
            metadata=existing_metadata,
            raw_path=raw_path,
            metadata_path=metadata_path,
        )

    if metadata_path.exists():
        existing_metadata = _load_raw_session_record(metadata_path)
        if existing_metadata != incoming_metadata:
            raise ValueError(f"Conflicting raw session metadata for {session_id}")

    raw_path.write_bytes(incoming_bytes)
    if not metadata_path.exists():
        _write_raw_session_record(metadata_path, incoming_metadata)
        metadata = incoming_metadata
    else:
        metadata = _load_raw_session_record(metadata_path)
    return ImportedRawSession(metadata=metadata, raw_path=raw_path, metadata_path=metadata_path)
