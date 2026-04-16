from pathlib import Path

from kimi_cli.wiki.layout import ensure_wiki_dirs, get_wiki_root


def test_ensure_wiki_dirs_creates_hermes_style_structure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(tmp_path / "wiki"))

    root = get_wiki_root()
    ensure_wiki_dirs(root)

    assert (root / "SCHEMA.md").exists()
    assert (root / "index.md").exists()
    assert (root / "log.md").exists()
    assert (root / "raw" / "sessions").is_dir()
    assert (root / "raw" / "sources").is_dir()
    assert (root / "entities").is_dir()
    assert (root / "concepts").is_dir()
    assert (root / "comparisons").is_dir()
    assert (root / "queries").is_dir()
