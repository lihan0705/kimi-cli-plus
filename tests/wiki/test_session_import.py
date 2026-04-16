from pathlib import Path

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


def test_imported_session_keeps_original_path_for_reimport_dedup(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source = tmp_path / "legacy.jsonl"
    source.write_text('{"role":"assistant","content":"done"}\n', encoding="utf-8")

    archived = import_session_file(root, source, session_id="sess_002")

    assert archived.metadata.source.original_path == str(source)
