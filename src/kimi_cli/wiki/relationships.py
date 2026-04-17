from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import WIKI_PAGE_DIRECTORIES, WikiPageKind


@dataclass(frozen=True)
class WikiPageRecord:
    path: Path
    slug: str
    title: str
    page_kind: WikiPageKind
    body: str
    normalized_keys: frozenset[str]


def discover_pages(root: Path) -> list[WikiPageRecord]:
    pages: list[WikiPageRecord] = []
    for directory in WIKI_PAGE_DIRECTORIES.values():
        for page_path in sorted((root / directory).glob("*.md")):
            text = page_path.read_text(encoding="utf-8")
            frontmatter, body = split_frontmatter(text)
            slug = str(frontmatter["page_slug"])
            title = extract_page_title(body, slug)
            normalized_keys = frozenset(
                {
                    normalize_link_key(slug),
                    normalize_link_key(title),
                    normalize_link_key(slug.split("--")[0]),
                }
            )
            pages.append(
                WikiPageRecord(
                    path=page_path,
                    slug=slug,
                    title=title,
                    page_kind=WikiPageKind(str(frontmatter["page_kind"])),
                    body=body,
                    normalized_keys=normalized_keys,
                )
            )
    return pages


def normalize_link_key(value: str) -> str:
    lowered = value.lower().strip()
    collapsed = re.sub(r"[\s_-]+", " ", lowered)
    return re.sub(r"[^a-z0-9 ]+", "", collapsed).strip()


def resolve_link_target(candidate: str, pages: list[WikiPageRecord]) -> str | None:
    normalized = normalize_link_key(candidate)
    matches = [page.slug for page in pages if normalized in page.normalized_keys]
    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return None


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        frontmatter_lines = lines[1:index]
        body = "\n".join(lines[index + 1 :])
        return _parse_frontmatter(frontmatter_lines), body

    return {}, text


def extract_page_title(body: str, slug: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return slug.replace("-", " ").title()


def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        data[key.strip()] = value.strip()
    return data
