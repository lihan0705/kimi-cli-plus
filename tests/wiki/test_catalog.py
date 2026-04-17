from pathlib import Path

from kimi_cli.wiki.catalog import delete_pages, list_pages, read_page
from kimi_cli.wiki.layout import ensure_wiki_dirs


def _write_page(root: Path, kind: str, slug: str, title: str) -> Path:
    page = root / f"{kind}s" / f"{slug}.md"
    page.write_text(
        "---\n"
        f"source_title: {title}\n"
        f"source_identity: note://{slug}\n"
        f"page_kind: {kind}\n"
        f"page_slug: {slug}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Summary\n\n"
        "- Summary line.\n",
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
