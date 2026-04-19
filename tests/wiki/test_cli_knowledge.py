from pathlib import Path

import pytest
from typer.testing import CliRunner

from kimi_cli.cli.knowledge import cli
from kimi_cli.wiki import ensure_wiki_dirs


def _write_page(root: Path, slug: str, title: str, *, page_kind: str = "concept") -> None:
    (root / f"{page_kind}s" / f"{slug}.md").write_text(
        "---\n"
        f"source_title: {title}\n"
        f"source_identity: note://{slug}\n"
        f"page_kind: {page_kind}\n"
        f"page_slug: {slug}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Summary\n\n"
        "- Summary line.\n",
        encoding="utf-8",
    )


def test_wiki_ingest_reports_file_read_error_without_stack_trace(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "wiki"
    source = tmp_path / "bad.txt"
    source.write_bytes(b"\xff\xfe\xfd")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["ingest", str(source)])

    assert result.exit_code == 0
    assert "Error: Failed to read file" in result.stdout
    assert "Traceback" not in result.stdout
    assert not list((root / "concepts").glob("*.md"))


def test_wiki_relink_rebuilds_relationship_artifacts(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["relink"])

    assert result.exit_code == 0
    assert "Relationship rebuild complete." in result.stdout
    assert (root / "RELATIONS.md").exists()
    assert (root / "audit.md").exists()


def test_wiki_audit_prints_summary(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["audit"])

    assert result.exit_code == 0
    assert "Audit updated at" in result.stdout


def test_wiki_audit_does_not_mutate_pages_or_relations(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    page = root / "concepts" / "alpha--aaaa1111.md"
    page.write_text(
        "---\n"
        "source_title: alpha\n"
        "source_identity: note://alpha\n"
        "page_kind: concept\n"
        "page_slug: alpha--aaaa1111\n"
        "---\n\n"
        "# Alpha\n\n"
        "Existing body.\n",
        encoding="utf-8",
    )
    relations = root / "RELATIONS.md"
    relations.write_text("# preexisting relations\n", encoding="utf-8")

    page_before = page.read_text(encoding="utf-8")
    relations_before = relations.read_text(encoding="utf-8")

    result = CliRunner().invoke(cli, ["audit"])

    assert result.exit_code == 0
    assert "Audit updated at" in result.stdout
    assert page.read_text(encoding="utf-8") == page_before
    assert relations.read_text(encoding="utf-8") == relations_before


def test_wiki_list_prints_page_titles(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["list"])

    assert result.exit_code == 0
    assert "alpha--aaaa1111" in result.stdout
    assert "Alpha" in result.stdout


def test_wiki_read_prints_page_content(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["read", "alpha--aaaa1111"])

    assert result.exit_code == 0
    assert "# Alpha" in result.stdout


def test_wiki_delete_removes_page_and_refreshes_reports(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    result = CliRunner().invoke(cli, ["delete", "alpha--aaaa1111"])

    assert result.exit_code == 0
    assert not (root / "concepts" / "alpha--aaaa1111.md").exists()
    assert (root / "index.md").exists()
    assert (root / "RELATIONS.md").exists()


def test_wiki_import_session_archives_and_distills_page(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    session = tmp_path / "session.jsonl"
    session.write_text(
        '{"role":"user","content":"Summarize wiki ingest."}\n'
        '{"role":"assistant","content":"We should improve source normalization."}\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["import-session", "--session-id", "sess_100", str(session)])

    assert result.exit_code == 0
    assert "Archived session to" in result.stdout
    assert "Distilled session into wiki page" in result.stdout
    pages = list((root / "queries").glob("*.md"))
    assert len(pages) == 1
    page_text = pages[0].read_text(encoding="utf-8")
    assert "# Session sess_100" in page_text
    assert "## Summary" in page_text
    assert "## Section Map" in page_text


@pytest.mark.parametrize("command", ["relink", "audit"])
def test_wiki_relationship_commands_report_malformed_pages_cleanly(
    tmp_path: Path, monkeypatch, command: str
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    broken = root / "concepts" / "broken.md"
    broken.write_text(
        "---\nsource_title: broken\npage_kind: concept\n---\n\n# Broken\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, [command])

    assert result.exit_code == 0
    assert "Error:" in result.stdout
    assert "Traceback" not in result.stdout
