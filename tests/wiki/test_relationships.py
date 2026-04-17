from pathlib import Path

from kimi_cli.wiki.layout import ensure_wiki_dirs
from kimi_cli.wiki.relationships import (
    MACHINE_RELATIONSHIP_BLOCK_START,
    WikiRelationshipParseError,
    discover_pages,
    rebuild_relationships,
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


def test_discover_pages_raises_clear_error_for_malformed_frontmatter_syntax(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "broken.md"
    page.write_text(
        "---\n"
        "source_title: broken\n"
        "page_kind: concept\n"
        "page_slug retrieval-augmented-generation--abcd1234\n"
        "---\n\n"
        "# Broken\n",
        encoding="utf-8",
    )

    try:
        discover_pages(root)
    except WikiRelationshipParseError as exc:
        assert exc.path == page
        assert "frontmatter" in str(exc)
        assert "malformed" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected WikiRelationshipParseError")


def test_discover_pages_raises_clear_error_for_unterminated_frontmatter(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "broken.md"
    page.write_text(
        "---\n"
        "source_title: broken\n"
        "source_identity: note://broken\n"
        "page_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n"
        "\n"
        "# Broken\n",
        encoding="utf-8",
    )

    try:
        discover_pages(root)
    except WikiRelationshipParseError as exc:
        assert exc.path == page
        assert "unterminated" in str(exc)
        assert "frontmatter" in str(exc)
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


def test_rebuild_relationships_writes_links_backlinks_relations_and_audit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    (root / "concepts" / "retrieval-augmented-generation--abcd1234.md").write_text(
        "---\nsource_title: rag\nsource_identity: note://rag\npage_kind: concept\n"
        "page_slug: retrieval-augmented-generation--abcd1234\n---\n\n"
        "# Retrieval Augmented Generation\n\n"
        "## Summary\n\n"
        "- Agent Memory improves long-running systems.\n",
        encoding="utf-8",
    )
    (root / "concepts" / "agent-memory--ef567890.md").write_text(
        "---\nsource_title: memory\nsource_identity: note://memory\npage_kind: concept\n"
        "page_slug: agent-memory--ef567890\n---\n\n"
        "# Agent Memory\n\n"
        "## Summary\n\n"
        "- Retrieval Augmented Generation can cite sources.\n",
        encoding="utf-8",
    )

    result = rebuild_relationships(root)

    first_page = (root / "concepts" / "retrieval-augmented-generation--abcd1234.md").read_text(
        encoding="utf-8"
    )
    relations_text = (root / "RELATIONS.md").read_text(encoding="utf-8")
    audit_text = (root / "audit.md").read_text(encoding="utf-8")

    assert "## Links" in first_page
    assert "[[agent-memory--ef567890]]" in first_page
    assert "## Backlinks" in first_page
    assert MACHINE_RELATIONSHIP_BLOCK_START in first_page
    assert "retrieval-augmented-generation--abcd1234" in relations_text
    assert "No issues found." in audit_text
    assert result.page_count == 2


def test_rebuild_relationships_preserves_user_authored_link_headings_outside_machine_block(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    (root / "concepts" / "alpha--aaaa1111.md").write_text(
        "---\nsource_title: alpha\nsource_identity: note://alpha\npage_kind: concept\n"
        "page_slug: alpha--aaaa1111\n---\n\n"
        "# Alpha\n\n"
        "## Summary\n\n"
        "- Beta is mentioned here to create a relationship.\n\n"
        "## Links\n\n"
        "- user-authored link note\n\n"
        "## Backlinks\n\n"
        "- user-authored backlink note\n",
        encoding="utf-8",
    )
    (root / "concepts" / "beta--bbbb2222.md").write_text(
        "---\nsource_title: beta\nsource_identity: note://beta\npage_kind: concept\n"
        "page_slug: beta--bbbb2222\n---\n\n"
        "# Beta\n\n## Summary\n\n- Nothing else.\n",
        encoding="utf-8",
    )

    result = rebuild_relationships(root)
    alpha_text = (root / "concepts" / "alpha--aaaa1111.md").read_text(encoding="utf-8")

    assert "- user-authored link note" in alpha_text
    assert "- user-authored backlink note" in alpha_text
    assert MACHINE_RELATIONSHIP_BLOCK_START in alpha_text
    assert "[[beta--bbbb2222]]" in alpha_text
    assert result.rewritten_pages


def test_rebuild_relationships_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    (root / "concepts" / "alpha--aaaa1111.md").write_text(
        "---\nsource_title: alpha\nsource_identity: note://alpha\npage_kind: concept\n"
        "page_slug: alpha--aaaa1111\n---\n\n"
        "# Alpha\n\n## Summary\n\n- Beta is mentioned here.\n",
        encoding="utf-8",
    )
    (root / "concepts" / "beta--bbbb2222.md").write_text(
        "---\nsource_title: beta\nsource_identity: note://beta\npage_kind: concept\n"
        "page_slug: beta--bbbb2222\n---\n\n"
        "# Beta\n\n## Summary\n\n- Nothing else.\n",
        encoding="utf-8",
    )

    first_result = rebuild_relationships(root)
    alpha_path = root / "concepts" / "alpha--aaaa1111.md"
    first_text = alpha_path.read_text(encoding="utf-8")

    second_result = rebuild_relationships(root)
    second_text = alpha_path.read_text(encoding="utf-8")

    assert first_result.rewritten_pages
    assert second_result.rewritten_pages == tuple()
    assert second_text == first_text


def test_rebuild_relationships_treats_page_with_backlinks_but_no_outgoing_as_not_isolated(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    (root / "concepts" / "alpha--aaaa1111.md").write_text(
        "---\nsource_title: alpha\nsource_identity: note://alpha\npage_kind: concept\n"
        "page_slug: alpha--aaaa1111\n---\n\n"
        "# Alpha\n\n## Summary\n\n- No outgoing links here.\n",
        encoding="utf-8",
    )
    (root / "concepts" / "beta--bbbb2222.md").write_text(
        "---\nsource_title: beta\nsource_identity: note://beta\npage_kind: concept\n"
        "page_slug: beta--bbbb2222\n---\n\n"
        "# Beta\n\n## Summary\n\n- Alpha is mentioned here.\n",
        encoding="utf-8",
    )

    rebuild_relationships(root)

    relations_text = (root / "RELATIONS.md").read_text(encoding="utf-8")
    audit_text = (root / "audit.md").read_text(encoding="utf-8")

    assert "- [[alpha--aaaa1111]] | out=0 | in=1 | isolated=no" in relations_text
    assert "No issues found." in audit_text


def test_rebuild_relationships_accepts_exact_slug_after_ambiguous_title_candidate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    (root / "concepts" / "alpha--aaaa1111.md").write_text(
        "---\nsource_title: alpha-one\nsource_identity: note://alpha-one\npage_kind: concept\n"
        "page_slug: alpha--aaaa1111\n---\n\n"
        "# Alpha\n\n## Summary\n\n- Exact reference alpha--aaaa1111 appears here.\n",
        encoding="utf-8",
    )
    (root / "concepts" / "alpha--bbbb2222.md").write_text(
        "---\nsource_title: alpha-two\nsource_identity: note://alpha-two\npage_kind: concept\n"
        "page_slug: alpha--bbbb2222\n---\n\n"
        "# Alpha\n\n## Summary\n\n- Duplicate title keeps the title ambiguous.\n",
        encoding="utf-8",
    )
    (root / "concepts" / "source--cccc3333.md").write_text(
        "---\nsource_title: source\nsource_identity: note://source\npage_kind: concept\n"
        "page_slug: source--cccc3333\n---\n\n"
        "# Source\n\n## Summary\n\n- Alpha and alpha--aaaa1111 are both mentioned.\n",
        encoding="utf-8",
    )

    rebuild_relationships(root)

    source_text = (root / "concepts" / "source--cccc3333.md").read_text(encoding="utf-8")
    relations_text = (root / "RELATIONS.md").read_text(encoding="utf-8")

    assert "[[alpha--aaaa1111]]" in source_text
    assert "- [[source--cccc3333]] | out=1 | in=0 | isolated=no" in relations_text
