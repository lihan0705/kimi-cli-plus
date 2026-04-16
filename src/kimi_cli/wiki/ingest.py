from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .index import rebuild_wiki_index
from .layout import ensure_wiki_dirs
from .log import WikiLogEntry, append_wiki_log
from .models import WIKI_PAGE_DIRECTORIES, WikiPageKind


@dataclass(frozen=True)
class DistilledPageResult:
    page_path: Path
    page_kind: WikiPageKind
    page_slug: str
    index_path: Path
    log_entry: WikiLogEntry


def distill_source_to_page(
    *,
    root: Path,
    source_text: str,
    source_title: str,
    page_kind: str | WikiPageKind,
    page_slug: str,
) -> DistilledPageResult:
    ensure_wiki_dirs(root)
    normalized_kind = WikiPageKind(page_kind)
    normalized_slug = _slugify(page_slug)
    page_path = root / WIKI_PAGE_DIRECTORIES[normalized_kind] / f"{normalized_slug}.md"

    page_path.write_text(
        _render_page(
            source_text=source_text,
            source_title=source_title,
            page_kind=normalized_kind,
            page_slug=normalized_slug,
        ),
        encoding="utf-8",
    )
    index_path = rebuild_wiki_index(root)
    log_entry = append_wiki_log(
        root,
        action="distilled",
        source_title=source_title,
        page_slug=normalized_slug,
        page_kind=normalized_kind.value,
    )
    return DistilledPageResult(
        page_path=page_path,
        page_kind=normalized_kind,
        page_slug=normalized_slug,
        index_path=index_path,
        log_entry=log_entry,
    )


def _render_page(
    *,
    source_text: str,
    source_title: str,
    page_kind: WikiPageKind,
    page_slug: str,
) -> str:
    body = source_text.strip()
    if not body:
        body = "No source content provided."
    return (
        "---\n"
        f"source_title: {source_title}\n"
        f"page_kind: {page_kind.value}\n"
        f"page_slug: {page_slug}\n"
        "---\n\n"
        f"# {page_slug.replace('-', ' ').title()}\n\n"
        "## Distilled Notes\n\n"
        f"{body}\n"
    )


def _slugify(value: str) -> str:
    slug = value.strip().lower().replace("_", "-").replace(" ", "-")
    collapsed: list[str] = []
    previous_was_dash = False
    for char in slug:
        is_valid = char.isalnum() or char == "-"
        if not is_valid:
            char = "-"
        if char == "-":
            if previous_was_dash:
                continue
            previous_was_dash = True
        else:
            previous_was_dash = False
        collapsed.append(char)
    normalized = "".join(collapsed).strip("-")
    return normalized or "untitled"
