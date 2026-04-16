from pathlib import Path

from kimi_cli.wiki.ingest import distill_source_to_page
from kimi_cli.wiki.layout import ensure_wiki_dirs


def test_distill_source_to_concept_page_writes_page_index_and_log(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    result = distill_source_to_page(
        root=root,
        source_text="# Raw Note\n\nRAG combines retrieval and generation.",
        source_title="rag-note",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
    )

    assert result.page_path.exists()
    assert result.page_path.read_text(encoding="utf-8").startswith(
        "---\nsource_title: rag-note\npage_kind: concept\npage_slug: retrieval-augmented-generation\n"
    )
    assert "[[retrieval-augmented-generation]]" in (root / "index.md").read_text(encoding="utf-8")
    assert "rag-note" in (root / "log.md").read_text(encoding="utf-8")
