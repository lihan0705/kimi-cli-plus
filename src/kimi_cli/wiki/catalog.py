from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import WIKI_PAGE_DIRECTORIES
from .relationships import base_slug_from_page_slug, extract_page_title, split_frontmatter


@dataclass(frozen=True)
class WikiPageSummary:
    page_kind: str
    slug: str
    title: str
    summary_preview: str
    path: Path


@dataclass(frozen=True)
class WikiPageDocument(WikiPageSummary):
    content: str


@dataclass(frozen=True)
class DeletePagesResult:
    deleted_slugs: list[str]
    missing_slugs: list[str]


def list_pages(root: Path) -> list[WikiPageSummary]:
    pages: list[WikiPageSummary] = []
    for page_kind, directory in WIKI_PAGE_DIRECTORIES.items():
        for path in sorted((root / directory).glob("*.md")):
            text = path.read_text(encoding="utf-8")
            frontmatter, body = split_frontmatter(text, path)
            slug = str(frontmatter["page_slug"]).strip()
            title = extract_page_title(body, base_slug_from_page_slug(slug))
            pages.append(
                WikiPageSummary(
                    page_kind=page_kind.value,
                    slug=slug,
                    title=title,
                    summary_preview=extract_summary_preview(body),
                    path=path,
                )
            )
    return pages


def read_page(root: Path, slug: str) -> WikiPageDocument:
    for page in list_pages(root):
        if page.slug == slug:
            text = page.path.read_text(encoding="utf-8")
            _, body = split_frontmatter(text, page.path)
            return WikiPageDocument(**page.__dict__, content=body.lstrip())
    raise FileNotFoundError(f"Wiki page not found: {slug}")


def delete_pages(root: Path, slugs: list[str]) -> DeletePagesResult:
    deleted: list[str] = []
    missing: list[str] = []
    by_slug = {page.slug: page for page in list_pages(root)}
    for slug in slugs:
        page = by_slug.get(slug)
        if page is None or not page.path.exists():
            missing.append(slug)
            continue
        page.path.unlink()
        deleted.append(slug)
    return DeletePagesResult(deleted_slugs=deleted, missing_slugs=missing)


def extract_summary_preview(body: str, *, limit: int = 80) -> str:
    lines = body.splitlines()
    in_summary = False
    for raw in lines:
        line = raw.strip()
        if not in_summary:
            if line.lower() == "## summary":
                in_summary = True
            continue
        if not line:
            continue
        if line.startswith("#"):
            break
        if line.startswith("- "):
            candidate = _clean_preview_text(line[2:].strip())
            if _is_preview_noise_text(candidate):
                continue
            return _truncate_summary(candidate, limit=limit)
        candidate = _clean_preview_text(line)
        if _is_preview_noise_text(candidate):
            continue
        return _truncate_summary(candidate, limit=limit)
    return "-"


def _truncate_summary(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _clean_preview_text(value: str) -> str:
    cleaned = value
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _is_preview_noise_text(value: str) -> bool:
    lowered = value.lower()
    if re.search(r"\b(qmd|curl|python|uv|pip)\b", lowered):
        return True
    return re.search(r"\b(line:\d+|\w+://|localhost:\d+)\b", lowered) is not None
