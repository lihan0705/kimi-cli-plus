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
    page_text = result.page_path.read_text(encoding="utf-8")
    assert page_text.startswith(
        "---\nsource_title: rag-note\nsource_identity: "
    )
    assert f"page_slug: {result.page_slug}\n" in page_text
    assert result.page_slug.startswith("retrieval-augmented-generation--")
    assert f"[[{result.page_slug}]]" in (root / "index.md").read_text(encoding="utf-8")
    assert "rag-note" in (root / "log.md").read_text(encoding="utf-8")


def test_distill_source_to_page_uses_source_identity_to_avoid_slug_collisions(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    first = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG helps with retrieval.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )
    second = distill_source_to_page(
        root=root,
        source_text="# Note\n\nAgents can use tools.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/b/index.md",
    )

    assert first.page_path != second.page_path
    assert first.page_path.exists()
    assert second.page_path.exists()
    index_text = (root / "index.md").read_text(encoding="utf-8")
    assert f"[[{first.page_slug}]]" in index_text
    assert f"[[{second.page_slug}]]" in index_text


def test_distill_source_to_page_updates_existing_page_for_same_source_identity(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    first = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG retrieves.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )
    second = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG retrieves and generates grounded answers.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )

    assert first.page_path == second.page_path
    page_text = second.page_path.read_text(encoding="utf-8")
    assert "grounded answers" in page_text
    assert "source_identity: /notes/a/index.md" in page_text


def test_distill_source_to_page_writes_distilled_summary_not_full_source_dump(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source_text = (
        "# Raw Note\n\n"
        "RAG combines retrieval and generation to ground answers in relevant documents. "
        "It can improve factuality when the retriever is high quality.\n\n"
        "Systems usually need chunking, ranking, and citation handling.\n\n"
        "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE."
    )

    result = distill_source_to_page(
        root=root,
        source_text=source_text,
        source_title="rag-note",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="note://rag-note",
    )

    page_text = result.page_path.read_text(encoding="utf-8")
    assert "## Summary" in page_text
    assert "## Source Excerpt" not in page_text
    assert "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE." not in page_text
