from pathlib import Path

from kimi_cli.wiki.layout import ensure_wiki_dirs
from kimi_cli.wiki.relationships import (
    WikiRelationshipParseError,
    discover_pages,
    resolve_link_target,
)


def test_discover_pages_indexes_slug_title_and_aliases(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "retrieval-augmented-generation--abcd1234.md"
    page.write_text(
        "---\n"
        "source_title: rag-note\n"
        "source_identity: note://rag\n"
        "page_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n"
        "---\n\n"
        "# Retrieval Augmented Generation\n\n"
        "## Summary\n\n"
        "- Uses external retrieval.\n",
        encoding="utf-8",
    )

    pages = discover_pages(root)

    assert len(pages) == 1
    assert pages[0].slug == "retrieval-augmented-generation--abcd1234"
    assert pages[0].title == "Retrieval Augmented Generation"
    assert "retrieval augmented generation" in pages[0].normalized_keys


def test_resolve_link_target_returns_unique_slug_only_for_safe_match(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    first = root / "concepts" / "retrieval-augmented-generation--abcd1234.md"
    first.write_text(
        "---\nsource_title: rag\nsource_identity: note://a\npage_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n---\n\n"
        "# Retrieval Augmented Generation\n\n## Summary\n\n- One.\n",
        encoding="utf-8",
    )
    second = root / "concepts" / "agent-memory--ef567890.md"
    second.write_text(
        "---\nsource_title: memory\nsource_identity: note://b\npage_kind: concept\n"
        "page_slug: agent-memory--ef567890\n---\n\n"
        "# Agent Memory\n\n## Summary\n\n- Two.\n",
        encoding="utf-8",
    )

    pages = discover_pages(root)

    assert resolve_link_target("retrieval augmented generation", pages) == (
        "retrieval-augmented-generation--abcd1234"
    )
    assert resolve_link_target("missing target", pages) is None


def test_resolve_link_target_returns_none_for_ambiguous_matches(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    first = root / "concepts" / "retrieval-augmented-generation--abcd1234.md"
    first.write_text(
        "---\nsource_title: rag\nsource_identity: note://a\npage_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n---\n\n"
        "# Retrieval Augmented Generation\n\n## Summary\n\n- One.\n",
        encoding="utf-8",
    )
    second = root / "concepts" / "retrieval-augmented-generation--ef567890.md"
    second.write_text(
        "---\nsource_title: rag-dup\nsource_identity: note://b\npage_kind: concept\n"
        "page_slug: retrieval-augmented-generation--ef567890\n---\n\n"
        "# Retrieval Augmented Generation\n\n## Summary\n\n- Two.\n",
        encoding="utf-8",
    )

    pages = discover_pages(root)

    assert resolve_link_target("retrieval augmented generation", pages) is None


def test_discover_pages_raises_clear_error_for_malformed_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "broken.md"
    page.write_text(
        "---\nsource_title: broken\npage_kind: concept\n---\n\n# Broken\n",
        encoding="utf-8",
    )

    try:
        discover_pages(root)
    except WikiRelationshipParseError as exc:
        assert exc.path == page
        assert "page_slug" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected WikiRelationshipParseError")


def test_discover_pages_raises_clear_error_for_empty_page_slug(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "broken.md"
    page.write_text(
        "---\n"
        "source_title: broken\n"
        "source_identity: note://broken\n"
        "page_kind: concept\n"
        "page_slug:\n"
        "---\n\n"
        "# Broken\n",
        encoding="utf-8",
    )

    try:
        discover_pages(root)
    except WikiRelationshipParseError as exc:
        assert exc.path == page
        assert "page_slug" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected WikiRelationshipParseError")


def test_discover_pages_falls_back_to_base_slug_title_without_hash_suffix(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "retrieval-augmented-generation--abcd1234.md"
    page.write_text(
        "---\n"
        "source_title: rag-note\n"
        "source_identity: note://rag\n"
        "page_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n"
        "---\n\n"
        "## Summary\n\n"
        "- Uses external retrieval.\n",
        encoding="utf-8",
    )

    pages = discover_pages(root)

    assert pages[0].title == "Retrieval Augmented Generation"
