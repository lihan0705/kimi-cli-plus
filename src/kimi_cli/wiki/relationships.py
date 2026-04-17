from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import WIKI_PAGE_DIRECTORIES, WikiPageKind

MACHINE_RELATIONSHIP_BLOCK_START = "<!-- kimi-cli:wiki-relationships:start -->"
MACHINE_RELATIONSHIP_BLOCK_END = "<!-- kimi-cli:wiki-relationships:end -->"


class WikiRelationshipParseError(ValueError):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


@dataclass(frozen=True)
class WikiPageRecord:
    path: Path
    slug: str
    title: str
    page_kind: WikiPageKind
    body: str
    normalized_keys: frozenset[str]


@dataclass(frozen=True)
class RelationshipBuildResult:
    page_count: int
    rewritten_pages: tuple[Path, ...]
    relations_path: Path
    audit_path: Path


def discover_pages(root: Path) -> list[WikiPageRecord]:
    pages: list[WikiPageRecord] = []
    for directory in WIKI_PAGE_DIRECTORIES.values():
        for page_path in sorted((root / directory).glob("*.md")):
            try:
                text = page_path.read_text(encoding="utf-8")
                frontmatter, body = split_frontmatter(text, page_path)
                slug = str(frontmatter["page_slug"]).strip()
                if not slug:
                    raise ValueError("page_slug is missing or empty")
                base_slug = base_slug_from_page_slug(slug)
                title = extract_page_title(body, base_slug)
                normalized_keys = frozenset(
                    {
                        normalize_link_key(slug),
                        normalize_link_key(title),
                        normalize_link_key(base_slug),
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
            except (KeyError, ValueError) as exc:
                raise WikiRelationshipParseError(page_path, str(exc)) from exc
    return pages


def rebuild_relationships(root: Path) -> RelationshipBuildResult:
    pages = discover_pages(root)
    links_by_slug: dict[str, list[str]] = {}
    backlinks_by_slug: dict[str, list[str]] = {page.slug: [] for page in pages}

    for page in pages:
        links = collect_page_links(page, pages)
        links_by_slug[page.slug] = links
        for target_slug in links:
            if target_slug in backlinks_by_slug:
                backlinks_by_slug[target_slug].append(page.slug)

    rewritten_pages: list[Path] = []
    for page in pages:
        updated = rewrite_page_relationship_sections(
            page.path,
            outgoing_slugs=links_by_slug[page.slug],
            backlink_slugs=sorted(backlinks_by_slug[page.slug]),
        )
        if updated:
            rewritten_pages.append(page.path)

    relations_path = root / "RELATIONS.md"
    audit_path = root / "audit.md"
    relations_path.write_text(
        render_relations_report(pages, links_by_slug, backlinks_by_slug),
        encoding="utf-8",
    )
    audit_path.write_text(
        render_audit_report(pages, links_by_slug, backlinks_by_slug),
        encoding="utf-8",
    )
    return RelationshipBuildResult(
        page_count=len(pages),
        rewritten_pages=tuple(rewritten_pages),
        relations_path=relations_path,
        audit_path=audit_path,
    )


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


def collect_page_links(page: WikiPageRecord, pages: list[WikiPageRecord]) -> list[str]:
    normalized_body = normalize_link_key(_body_without_machine_relationship_block(page.body))
    links: list[str] = []
    for target in pages:
        if target.slug == page.slug:
            continue
        if target.slug in links:
            continue
        for candidate in (target.title, base_slug_from_page_slug(target.slug), target.slug):
            normalized_candidate = normalize_link_key(candidate)
            if not normalized_candidate:
                continue
            if _contains_normalized_phrase(normalized_body, normalized_candidate):
                if resolve_link_target(normalized_candidate, pages) == target.slug:
                    links.append(target.slug)
                break
    return links


def rewrite_page_relationship_sections(
    path: Path,
    *,
    outgoing_slugs: list[str],
    backlink_slugs: list[str],
) -> bool:
    original_text = path.read_text(encoding="utf-8")
    frontmatter_text, body = _split_frontmatter_text(original_text, path)
    rewritten_body = _rewrite_relationship_body(body, outgoing_slugs, backlink_slugs)
    rewritten_text = frontmatter_text + rewritten_body
    if rewritten_text == original_text:
        return False
    path.write_text(rewritten_text, encoding="utf-8")
    return True


def render_links_section(links: list[str]) -> str:
    if not links:
        return "## Links\n\n- (none)\n"
    lines = ["## Links", ""]
    lines.extend(f"- [[{slug}]]" for slug in links)
    return "\n".join(lines) + "\n"


def render_backlinks_section(backlinks: list[str]) -> str:
    if not backlinks:
        return "## Backlinks\n\n- (none)\n"
    lines = ["## Backlinks", ""]
    lines.extend(f"- [[{slug}]]" for slug in backlinks)
    return "\n".join(lines) + "\n"


def render_relations_report(
    pages: list[WikiPageRecord],
    links_by_slug: dict[str, list[str]],
    backlinks_by_slug: dict[str, list[str]],
) -> str:
    lines = ["# Wiki Relationships", ""]
    for page in pages:
        outgoing = len(links_by_slug[page.slug])
        incoming = len(backlinks_by_slug[page.slug])
        isolated = "yes" if _is_isolated(outgoing, incoming) else "no"
        lines.append(f"- [[{page.slug}]] | out={outgoing} | in={incoming} | isolated={isolated}")
    return "\n".join(lines).rstrip() + "\n"


def render_audit_report(
    pages: list[WikiPageRecord],
    links_by_slug: dict[str, list[str]],
    backlinks_by_slug: dict[str, list[str]],
) -> str:
    isolated_pages = [
        page.slug
        for page in pages
        if _is_isolated(len(links_by_slug[page.slug]), len(backlinks_by_slug[page.slug]))
    ]
    lines = ["# Wiki Audit", "", "## Isolated Pages", ""]
    if isolated_pages:
        lines.extend(f"- [[{slug}]]" for slug in isolated_pages)
    else:
        lines.append("No issues found.")
    return "\n".join(lines).rstrip() + "\n"


def split_frontmatter(text: str, path: Path | None = None) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        frontmatter_lines = lines[1:index]
        body = "\n".join(lines[index + 1 :])
        return _parse_frontmatter(frontmatter_lines, path), body

    message = "unterminated frontmatter"
    if path is None:
        raise ValueError(message)
    raise WikiRelationshipParseError(path, message)


def extract_page_title(body: str, slug: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            title = stripped[2:].strip()
            if title:
                return title
    return slug.replace("-", " ").title()


def base_slug_from_page_slug(slug: str) -> str:
    base_slug, _, _ = slug.partition("--")
    return base_slug or slug


def _parse_frontmatter(lines: list[str], path: Path | None) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            message = f"malformed frontmatter syntax: {stripped!r}"
            if path is None:
                raise ValueError(message)
            raise WikiRelationshipParseError(path, message)
        key, value = stripped.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _split_frontmatter_text(text: str, path: Path) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        frontmatter_text = "".join(lines[: index + 1])
        body_text = "".join(lines[index + 1 :])
        return frontmatter_text, body_text

    raise WikiRelationshipParseError(path, "unterminated frontmatter")


def _body_without_machine_relationship_block(body: str) -> str:
    return re.sub(
        _machine_relationship_block_pattern(),
        "",
        body,
    ).rstrip()


def _rewrite_relationship_body(
    body: str,
    outgoing_slugs: list[str],
    backlink_slugs: list[str],
) -> str:
    machine_block = render_relationship_block(outgoing_slugs, backlink_slugs)
    rewritten_body, replacements = _machine_relationship_block_pattern().subn(machine_block, body)
    if replacements:
        return rewritten_body.rstrip() + "\n"

    stripped_body = _body_without_machine_relationship_block(body)
    if not stripped_body:
        return machine_block
    return stripped_body.rstrip() + "\n\n" + machine_block


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def render_relationship_block(outgoing_slugs: list[str], backlink_slugs: list[str]) -> str:
    lines = [
        MACHINE_RELATIONSHIP_BLOCK_START,
        "",
        render_links_section(outgoing_slugs).rstrip(),
        "",
        render_backlinks_section(backlink_slugs).rstrip(),
        "",
        MACHINE_RELATIONSHIP_BLOCK_END,
    ]
    return "\n".join(lines).rstrip() + "\n"


def _machine_relationship_block_pattern() -> re.Pattern[str]:
    start = re.escape(MACHINE_RELATIONSHIP_BLOCK_START)
    end = re.escape(MACHINE_RELATIONSHIP_BLOCK_END)
    return re.compile(rf"(?ms)^[ \t]*{start}\n.*?^[ \t]*{end}\n?")


def _is_isolated(outgoing: int, incoming: int) -> bool:
    return outgoing == 0 and incoming == 0
