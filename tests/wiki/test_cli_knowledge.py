from pathlib import Path

from typer.testing import CliRunner

from kimi_cli.cli.knowledge import cli


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
