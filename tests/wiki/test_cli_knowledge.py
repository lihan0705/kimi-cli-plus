from pathlib import Path

import pytest
from typer.testing import CliRunner

from kimi_cli.cli.knowledge import cli
from kimi_cli.wiki import ensure_wiki_dirs


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
