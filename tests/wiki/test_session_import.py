from pathlib import Path
from unittest.mock import patch

from kimi_cli.knowledge.models import RawSessionRecord
from kimi_cli.wiki.layout import ensure_wiki_dirs
from kimi_cli.wiki.session_import import discover_legacy_sessions, import_session_file


def test_discover_legacy_sessions_returns_matching_files(tmp_path: Path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "a.jsonl").write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")

    found = discover_legacy_sessions([legacy])
    assert [p.name for p in found] == ["a.jsonl"]


def test_discover_legacy_sessions_ignores_modern_and_archived_jsonl(tmp_path: Path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "a.jsonl").write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")

    modern_session = legacy / "session_001"
    modern_session.mkdir()
    (modern_session / "context.jsonl").write_text(
        '{"role":"user","content":"modern"}\n',
        encoding="utf-8",
    )

    archived_sessions = tmp_path / "wiki" / "raw" / "sessions"
    archived_sessions.mkdir(parents=True)
    (archived_sessions / "sess_001.jsonl").write_text(
        '{"role":"user","content":"archived"}\n',
        encoding="utf-8",
    )

    found = discover_legacy_sessions([legacy, archived_sessions])

    assert [p.name for p in found] == ["a.jsonl"]


def test_import_session_file_archives_raw_session(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    raw_content = b'{"role":"user","content":"What is RAG?"}\n'
    source.write_bytes(raw_content)

    archived = import_session_file(root, source, session_id="sess_001")

    assert archived.metadata.source.kind == "session"
    assert archived.metadata.source.source_id == "sess_001"
    assert archived.raw_path.parent.name == "sessions"
    assert archived.raw_path.suffix == ".jsonl"
    assert archived.raw_path.read_bytes() == raw_content
    assert archived.metadata_path.name == "sess_001.metadata.json"
    assert archived.metadata_path.exists()
    assert RawSessionRecord.model_validate_json(
        archived.metadata_path.read_text(encoding="utf-8")
    ) == archived.metadata


def test_imported_session_keeps_original_path_for_reimport_dedup(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "legacy.jsonl"
    source.write_text('{"role":"assistant","content":"done"}\n', encoding="utf-8")

    archived = import_session_file(root, source, session_id="sess_002")

    assert archived.metadata.source.original_path == str(source)


def test_import_session_file_normalizes_provenance_path(tmp_path: Path, monkeypatch):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    source.write_bytes(b'{"role":"user","content":"same"}\n')

    relative_source = Path(source.relative_to(tmp_path))
    monkeypatch.chdir(tmp_path)

    archived_from_relative = import_session_file(root, relative_source, session_id="sess_003")
    archived_from_absolute = import_session_file(root, source, session_id="sess_003")

    assert archived_from_relative.metadata.source.original_path == str(source.resolve())
    assert archived_from_absolute.metadata.source.original_path == str(source.resolve())
    assert archived_from_relative.metadata == archived_from_absolute.metadata


def test_import_session_file_is_idempotent_for_matching_reimport(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    raw_content = b'{"role":"user","content":"same"}\n'
    source.write_bytes(raw_content)

    archived = import_session_file(root, source, session_id="sess_003")

    with patch("pathlib.Path.write_bytes") as mock_write_bytes:
        archived_again = import_session_file(root, source, session_id="sess_003")

    assert archived_again.raw_path == archived.raw_path
    assert archived_again.metadata == archived.metadata
    assert archived_again.metadata_path == archived.metadata_path
    mock_write_bytes.assert_not_called()
    assert archived.raw_path.read_bytes() == raw_content


def test_import_session_file_rejects_conflicting_reimport(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    source.write_bytes(b'{"role":"user","content":"first"}\n')

    archived = import_session_file(root, source, session_id="sess_004")

    conflicting = tmp_path / "session-conflict.jsonl"
    conflicting.write_bytes(b'{"role":"user","content":"second"}\n')

    with patch("pathlib.Path.write_bytes") as mock_write_bytes:
        try:
            import_session_file(root, conflicting, session_id="sess_004")
        except ValueError as err:
            assert "sess_004" in str(err)
        else:  # pragma: no cover
            raise AssertionError("Expected ValueError for conflicting reimport")

    mock_write_bytes.assert_not_called()
    assert archived.raw_path.read_bytes() == b'{"role":"user","content":"first"}\n'
    assert archived.metadata_path.exists()


def test_import_session_file_refuses_to_rebuild_missing_archive(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    source.write_bytes(b'{"role":"user","content":"first"}\n')

    archived = import_session_file(root, source, session_id="sess_005")
    archived.raw_path.unlink()

    with patch("pathlib.Path.write_bytes") as mock_write_bytes:
        try:
            import_session_file(root, source, session_id="sess_005")
        except ValueError as err:
            assert "missing archived raw session" in str(err).lower()
        else:  # pragma: no cover
            raise AssertionError("Expected ValueError for missing raw archive")

    mock_write_bytes.assert_not_called()
    assert not archived.raw_path.exists()
    assert archived.metadata_path.exists()


def test_import_session_file_refuses_to_rebuild_missing_metadata(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "session.jsonl"
    source.write_bytes(b'{"role":"user","content":"first"}\n')

    archived = import_session_file(root, source, session_id="sess_006")
    archived.metadata_path.unlink()

    with patch("pathlib.Path.write_text") as mock_write_text:
        try:
            import_session_file(root, source, session_id="sess_006")
        except ValueError as err:
            assert "missing archived provenance" in str(err).lower()
        else:  # pragma: no cover
            raise AssertionError("Expected ValueError for missing metadata")

    mock_write_text.assert_not_called()
    assert archived.raw_path.exists()
    assert not archived.metadata_path.exists()
