from pathlib import Path

from kimi_cli.wiki.catalog import delete_pages, list_pages, read_page
from kimi_cli.wiki.layout import ensure_wiki_dirs


def _write_page(root: Path, kind: str, slug: str, title: str, *, include_h1: bool = True) -> Path:
    page = root / f"{kind}s" / f"{slug}.md"
    body = ""
    if include_h1:
        body += f"# {title}\n\n"
    body += "## Summary\n\n- Summary line.\n"
    page.write_text(
        "---\n"
        f"source_title: {title}\n"
        f"source_identity: note://{slug}\n"
        f"page_kind: {kind}\n"
        f"page_slug: {slug}\n"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return page


def test_list_pages_returns_kind_slug_and_title(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "concept", "alpha--aaaa1111", "Alpha")

    pages = list_pages(root)

    assert [page.slug for page in pages] == ["alpha--aaaa1111"]
    assert pages[0].page_kind == "concept"
    assert pages[0].title == "Alpha"
    assert pages[0].summary_preview == "Summary line."


def test_list_pages_uses_base_slug_title_when_h1_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "concept", "alpha--aaaa1111", "Alpha", include_h1=False)

    pages = list_pages(root)

    assert pages[0].title == "Alpha"


def test_read_page_resolves_by_slug(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "concept", "alpha--aaaa1111", "Alpha")

    page = read_page(root, "alpha--aaaa1111")

    assert page.slug == "alpha--aaaa1111"
    assert "# Alpha" in page.content


def test_delete_pages_removes_file_and_reports_missing(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "concept", "alpha--aaaa1111", "Alpha")

    result = delete_pages(root, ["alpha--aaaa1111", "missing-page"])

    assert result.deleted_slugs == ["alpha--aaaa1111"]
    assert result.missing_slugs == ["missing-page"]
    assert not (root / "concepts" / "alpha--aaaa1111.md").exists()


def test_delete_pages_treats_duplicate_slug_as_missing_after_first_delete(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "concept", "alpha--aaaa1111", "Alpha")

    result = delete_pages(root, ["alpha--aaaa1111", "alpha--aaaa1111", "missing-page"])

    assert result.deleted_slugs == ["alpha--aaaa1111"]
    assert result.missing_slugs == ["alpha--aaaa1111", "missing-page"]
    assert not (root / "concepts" / "alpha--aaaa1111.md").exists()


def test_list_pages_uses_dash_when_summary_section_missing(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    page = root / "concepts" / "alpha--aaaa1111.md"
    page.write_text(
        "---\n"
        "source_title: Alpha\n"
        "source_identity: note://alpha--aaaa1111\n"
        "page_kind: concept\n"
        "page_slug: alpha--aaaa1111\n"
        "---\n\n"
        "# Alpha\n\n"
        "No summary section here.\n",
        encoding="utf-8",
    )

    pages = list_pages(root)

    assert pages[0].summary_preview == "-"


def test_list_pages_truncates_summary_preview(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    long_line = "A" * 120
    page = root / "concepts" / "alpha--aaaa1111.md"
    page.write_text(
        "---\n"
        "source_title: Alpha\n"
        "source_identity: note://alpha--aaaa1111\n"
        "page_kind: concept\n"
        "page_slug: alpha--aaaa1111\n"
        "---\n\n"
        "# Alpha\n\n"
        "## Summary\n\n"
        f"- {long_line}\n",
        encoding="utf-8",
    )

    pages = list_pages(root)

    assert pages[0].summary_preview.endswith("...")
    assert len(pages[0].summary_preview) == 80
