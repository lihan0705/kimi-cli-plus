from pathlib import Path

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
