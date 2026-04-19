from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse
from urllib.request import urlopen

import pypdf
import trafilatura

from kimi_cli.utils.logging import logger

from .index import rebuild_wiki_index
from .layout import ensure_wiki_dirs
from .log import WikiLogEntry, append_wiki_log
from .models import WIKI_PAGE_DIRECTORIES, WikiPageKind


class WikiSourceLoadError(ValueError):
    pass


@dataclass(frozen=True)
class SourceMaterial:
    source_kind: str
    source_identity: str
    source_text: str
    source_title: str
    parser_name: str = "markdown"
    quality_flags: list[str] | None = None


@dataclass(frozen=True)
class DistilledPageResult:
    page_path: Path
    page_kind: WikiPageKind
    page_slug: str
    index_path: Path
    log_entry: WikiLogEntry
    source_identity: str


@dataclass(frozen=True)
class SourceAnalysis:
    title: str
    aliases: list[str]
    summary_lines: list[str]
    key_terms: list[str]
    entities: list[str]
    sections: list[SectionSummary]
    parser_name: str
    quality_flags: list[str]
    session_topics: list[str]
    session_decisions: list[str]
    session_open_questions: list[str]
    session_action_items: list[str]


def distill_source_to_page(
    *,
    root: Path,
    source_text: str,
    source_title: str,
    page_kind: str | WikiPageKind,
    page_slug: str,
    source_identity: str | None = None,
    source_kind: str = "file",
    parser_name: str | None = None,
    quality_flags: list[str] | None = None,
) -> DistilledPageResult:
    ensure_wiki_dirs(root)
    normalized_kind = WikiPageKind(page_kind)
    resolved_source_identity = source_identity or _default_source_identity(
        source_title=source_title,
        source_text=source_text,
    )
    normalized_slug = _resolve_page_slug(page_slug, resolved_source_identity)
    page_path = root / WIKI_PAGE_DIRECTORIES[normalized_kind] / f"{normalized_slug}.md"
    analysis = analyze_source_text(
        source_text=source_text,
        source_title=source_title,
        page_slug=normalized_slug,
        source_kind=source_kind,
        parser_name=parser_name,
        quality_flags=quality_flags,
    )

    page_path.write_text(
        _render_page(
            analysis=analysis,
            source_title=source_title,
            source_identity=resolved_source_identity,
            source_kind=source_kind,
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
        source_identity=resolved_source_identity,
    )


def load_source_material(source: str) -> SourceMaterial:
    if source.startswith(("http://", "https://")):
        try:
            content = _convert_url_to_markdown(source)
        except Exception as exc:  # pragma: no cover - converter-specific failures
            raise WikiSourceLoadError(
                f"Failed to extract content from URL: {source}: {exc}"
            ) from exc
        if not content:
            raise WikiSourceLoadError(f"Failed to extract content from URL: {source}")
        return SourceMaterial(
            source_kind="url",
            source_identity=source,
            source_text=content,
            source_title=_source_title_from_url(source),
            parser_name="markdown",
            quality_flags=[],
        )

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise WikiSourceLoadError(f"File not found: {source}")

    try:
        if path.suffix.lower() == ".pdf":
            content, parser_name, quality_flags = _extract_pdf_content(path)
            source_kind = "pdf"
        else:
            content = path.read_text(encoding="utf-8")
            source_kind = "file"
            parser_name = "markdown"
            quality_flags = []
    except UnicodeDecodeError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc
    except OSError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - converter-specific failures
        raise WikiSourceLoadError(f"Failed to extract content from file: {source}: {exc}") from exc

    if not content:
        raise WikiSourceLoadError(f"Failed to extract content from file: {source}")

    return SourceMaterial(
        source_kind=source_kind,
        source_identity=str(path),
        source_text=content,
        source_title=path.stem,
        parser_name=parser_name,
        quality_flags=quality_flags,
    )


def load_session_material(source: Path, *, session_id: str) -> SourceMaterial:
    path = source.expanduser().resolve()
    if not path.exists():
        raise WikiSourceLoadError(f"File not found: {source}")

    try:
        session_lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc
    except OSError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc

    normalized_text = _normalize_session_lines(session_lines, session_id=session_id)
    return SourceMaterial(
        source_kind="session",
        source_identity=str(path),
        source_text=normalized_text,
        source_title=f"session-{session_id}",
        parser_name="session",
        quality_flags=[],
    )


def analyze_source_text(
    *,
    source_text: str,
    source_title: str,
    page_slug: str,
    source_kind: str = "file",
    parser_name: str | None = None,
    quality_flags: list[str] | None = None,
) -> SourceAnalysis:
    analysis_text = _prepare_source_text_for_analysis(source_text, source_kind=source_kind)
    title = _display_title(
        analysis_text,
        page_slug,
        source_title=source_title,
        source_kind=source_kind,
    )
    summary_lines = [
        line
        for line in _build_summary_lines_from_text(analysis_text)
        if line.strip() != title.strip()
    ]
    if not summary_lines:
        summary_lines = [title]
    sections = _distill_sections(analysis_text, source_kind=source_kind, title=title)
    if source_kind == "pdf":
        entity_source = "\n".join([title, *[section.heading for section in sections]])
        key_term_source = "\n".join(
            [title, *summary_lines, *[section.summary for section in sections[:3]]]
        )
    else:
        entity_source = analysis_text
        key_term_source = analysis_text
    is_session = source_kind == "session"
    return SourceAnalysis(
        title=title,
        aliases=_build_aliases(title=title, source_title=source_title),
        summary_lines=summary_lines[:3],
        key_terms=_extract_key_terms(key_term_source),
        entities=_extract_entities(entity_source),
        sections=sections,
        parser_name=parser_name or _default_parser_name(source_kind),
        quality_flags=list(quality_flags or []),
        session_topics=_extract_session_topics(analysis_text) if is_session else [],
        session_decisions=_extract_session_decisions(analysis_text) if is_session else [],
        session_open_questions=_extract_session_open_questions(analysis_text) if is_session else [],
        session_action_items=_extract_session_action_items(analysis_text) if is_session else [],
    )


def _render_page(
    *,
    analysis: SourceAnalysis,
    source_title: str,
    source_identity: str,
    source_kind: str,
    page_kind: WikiPageKind,
    page_slug: str,
) -> str:
    section_map = [section.heading for section in analysis.sections]
    return "".join(
        [
            "---\n",
            f"title: {analysis.title}\n",
            _render_frontmatter_list("aliases", analysis.aliases),
            f"source_title: {source_title}\n",
            f"source_identity: {source_identity}\n",
            f"source_kind: {source_kind}\n",
            f"parser: {analysis.parser_name}\n",
            _render_frontmatter_list("quality_flags", analysis.quality_flags),
            f"page_kind: {page_kind.value}\n",
            f"page_slug: {page_slug}\n",
            "---\n\n",
            f"# {analysis.title}\n\n",
            "## Summary\n\n",
            "\n".join(f"- {line}" for line in analysis.summary_lines),
            "\n\n",
            _render_bullet_section("Key Terms", analysis.key_terms),
            _render_bullet_section("Entities", analysis.entities),
            _render_optional_bullet_section("Topics", analysis.session_topics),
            _render_optional_bullet_section("Decisions", analysis.session_decisions),
            _render_optional_bullet_section("Open Questions", analysis.session_open_questions),
            _render_optional_bullet_section("Action Items", analysis.session_action_items),
            _render_bullet_section("Section Map", section_map),
            _render_outline_section(analysis.sections),
            _render_notes_section(analysis),
        ]
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


def _resolve_page_slug(page_slug: str, source_identity: str) -> str:
    base_slug = _slugify(page_slug)
    identity_hash = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()[:8]
    return f"{base_slug}--{identity_hash}"


def _default_source_identity(*, source_title: str, source_text: str) -> str:
    content_hash = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()[:16]
    return f"{_slugify(source_title)}:{content_hash}"


def _display_title(
    source_text: str,
    page_slug: str,
    *,
    source_title: str,
    source_kind: str,
) -> str:
    if source_kind == "session":
        return _display_session_title(source_text, page_slug)
    if source_kind == "pdf":
        return _display_pdf_title(source_text, source_title, page_slug)
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 4:
            return stripped.lstrip("#").strip()
    return page_slug.replace("-", " ").title()


def _display_session_title(source_text: str, page_slug: str) -> str:
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# Session "):
            return stripped.lstrip("#").strip()
    return page_slug.replace("-", " ").title()


def _display_pdf_title(source_text: str, source_title: str, page_slug: str) -> str:
    candidates: list[str] = []
    title_lines = source_text.splitlines()[:20]
    for raw_line in title_lines:
        line = _normalize_pdf_line(raw_line)
        if not _is_pdf_title_candidate(line):
            continue
        candidates.append(line)
    if candidates:
        best_title = max(
            candidates,
            key=lambda item: _score_pdf_title_candidate(item, title_lines.index(item)),
        )
        return str(best_title)
    if source_title.strip():
        return source_title.strip()
    return page_slug.replace("-", " ").title()


@dataclass(frozen=True)
class SectionSummary:
    heading: str
    summary: str


def _distill_sections(
    source_text: str,
    *,
    source_kind: str = "file",
    title: str | None = None,
) -> list[SectionSummary]:
    if source_kind == "session":
        return _distill_markdown_sections(source_text)
    if source_kind == "pdf":
        return _distill_pdf_sections(source_text, title=title)
    return _distill_markdown_sections(source_text)


def _distill_markdown_sections(source_text: str) -> list[SectionSummary]:
    paragraphs: list[str] = []
    current_paragraph: list[str] = []
    sections: list[SectionSummary] = []
    current_heading = ""
    current_section_lines: list[str] = []
    saw_document_title = False

    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            if current_section_lines:
                current_section_lines.append("")
            continue
        if line.startswith("#"):
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            if current_heading:
                sections.append(
                    SectionSummary(
                        heading=current_heading,
                        summary=_summarize_section_lines(current_section_lines),
                    )
                )
                current_section_lines = []
            heading_level = len(line) - len(line.lstrip("#"))
            heading = line.lstrip("#").strip()
            if heading:
                if heading_level == 1 and not saw_document_title:
                    saw_document_title = True
                    current_heading = ""
                    continue
                current_heading = heading
            continue
        cleaned = line.lstrip("-*").strip()
        if cleaned and not cleaned.startswith("```"):
            current_paragraph.append(cleaned)
            if current_heading:
                current_section_lines.append(cleaned)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))
    if current_heading:
        sections.append(
            SectionSummary(
                heading=current_heading,
                summary=_summarize_section_lines(current_section_lines),
            )
        )
    return sections[:8]


def _distill_pdf_sections(source_text: str, *, title: str | None) -> list[SectionSummary]:
    sections: list[SectionSummary] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for raw_line in source_text.splitlines():
        line = _normalize_pdf_line(raw_line)
        if not line:
            continue
        if title is not None and line == title:
            continue
        section_heading = _parse_pdf_section_heading(line)
        if section_heading is not None:
            if current_heading is not None:
                sections.append(
                    SectionSummary(
                        heading=current_heading,
                        summary=_summarize_section_lines(current_lines),
                    )
                )
            current_heading = section_heading
            current_lines = []
            continue
        if current_heading is None:
            continue
        if _is_pdf_noise_line(line):
            continue
        current_lines.append(line)

    if current_heading is not None:
        sections.append(
            SectionSummary(
                heading=current_heading,
                summary=_summarize_section_lines(current_lines),
            )
        )

    return sections[:8]


def _build_summary_lines(paragraphs: list[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for paragraph in paragraphs[:6]:
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            normalized = sentence.strip().strip("-*").strip()
            if len(normalized) < 24:
                continue
            if _is_summary_noise_line(normalized):
                continue
            dedupe_key = normalized.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append(normalized)

    if candidates:
        ranked = sorted(
            candidates,
            key=_score_summary_candidate,
            reverse=True,
        )
        return [_truncate_text(line, limit=140) for line in ranked[:3]]

    if not paragraphs:
        return ["No source content provided."]
    fallback = [
        _truncate_text(paragraph, limit=140)
        for paragraph in paragraphs
        if paragraph and not _is_summary_noise_line(paragraph)
    ]
    return fallback[:3] or ["No source content provided."]


def _build_summary_lines_from_text(source_text: str) -> list[str]:
    paragraphs: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        cleaned = line.lstrip("-*").strip()
        if cleaned and not cleaned.startswith("```"):
            paragraphs.append(cleaned)
    return _build_summary_lines(paragraphs)


def _summarize_section_lines(lines: list[str]) -> str:
    candidates = _section_summary_candidates(lines)
    if candidates:
        best = max(candidates, key=_score_section_summary_candidate)
        return _truncate_text(best, limit=140)

    normalized = " ".join(
        part for part in lines if part and not _is_section_noise_line(part)
    ).strip()
    if not normalized:
        return "No details extracted."
    return _truncate_text(normalized, limit=140)


def _render_frontmatter_list(key: str, values: list[str]) -> str:
    if not values:
        return f"{key}: []\n"
    return f"{key}:\n" + "".join(f"  - {value}\n" for value in values)


def _render_bullet_section(title: str, values: list[str]) -> str:
    body = "- None.\n" if not values else "".join(f"- {value}\n" for value in values)
    return f"## {title}\n\n{body}\n"


def _render_optional_bullet_section(title: str, values: list[str]) -> str:
    if not values:
        return ""
    return _render_bullet_section(title, values)


def _render_notes_section(analysis: SourceAnalysis) -> str:
    if not analysis.quality_flags:
        return "## Notes\n\n- None.\n"
    return "## Notes\n\n" + "".join(f"- {value}\n" for value in analysis.quality_flags)


def _render_outline_section(sections: list[SectionSummary]) -> str:
    if not sections:
        return "## Outline\n\n- None.\n\n"
    body = "".join(f"### {section.heading}\n\n- {section.summary}\n\n" for section in sections)
    return f"## Outline\n\n{body}"


def _section_summary_candidates(lines: list[str]) -> list[str]:
    candidates: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or _is_section_noise_line(line):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            normalized = sentence.strip().strip("-*").strip()
            if len(normalized) < 24:
                continue
            if _is_section_noise_line(normalized):
                continue
            candidates.append(normalized)

    return candidates


def _score_summary_candidate(value: str) -> tuple[int, int]:
    score = 0
    lowered = value.lower()

    if re.search(r"[.!?]$", value):
        score += 2
    if re.search(
        r"\b(is|are|helps|uses|supports|coordinates|improves|enables|combines|gives|provides|avoids)\b",
        lowered,
    ):
        score += 5
    if re.search(
        r"\b(agent|agents|workflow|workflows|retrieval|memory|search|document)\b",
        lowered,
    ):
        score += 2
    if " and " in lowered:
        score += 1
    if "`" in value:
        score -= 5
    if re.search(r"\b(qmd|curl|python|uv|pip|http://|https://)\b", lowered):
        score -= 5
    if "{" in value or "}" in value:
        score -= 6
    if re.search(r"\bfigure\b|\btable\b|\bappendix\b", lowered):
        score -= 4
    if re.match(r"^(user|assistant):", lowered):
        score -= 4
    return (score, len(value))


def _score_section_summary_candidate(value: str) -> tuple[int, int]:
    score = 0
    lowered = value.lower()

    if re.search(r"[.!?]$", value):
        score += 2
    if re.search(
        r"\b(is|are|helps|uses|supports|coordinates|improves|enables|combines)\b",
        lowered,
    ):
        score += 4
    if " and " in lowered:
        score += 1
    if "`" in value:
        score -= 4
    if re.search(r"\b(qmd|curl|python|uv|pip|http://|https://)\b", lowered):
        score -= 4
    if "{" in value or "}" in value:
        score -= 5
    if re.search(r"\bfigure\b|\btable\b|\bappendix\b", lowered):
        score -= 3
    return (score, len(value))


def _is_section_noise_line(value: str) -> bool:
    line = value.strip()
    lowered = line.lower()

    if not line:
        return True
    if line.startswith("```") or line.endswith("```"):
        return True
    if (
        re.search(r"`[^`]+`", line)
        and len(re.findall(r"`[^`]+`", line)) >= 1
        and len(line) < 120
        and re.search(r"\b(qmd|curl|python|uv|pip)\b", lowered)
    ):
        return True
    if "{" in line or "}" in line:
        return True
    if re.search(r"\bfigure\b|\btable\b", lowered):
        return True
    if re.search(r"\b(line:\d+|\w+://|localhost:\d+)\b", lowered):
        return True
    return bool(
        re.search(r"^[A-Za-z0-9_.-]+\s+[A-Za-z0-9_.-]+\s+[A-Za-z0-9_.-]+", line)
        and "," not in line
        and line.count(" ") <= 4
        and line.lower() == line
    )


def _is_summary_noise_line(value: str) -> bool:
    line = value.strip()
    lowered = line.lower()

    if _is_section_noise_line(line):
        return True
    if re.match(r"^(user|assistant):", lowered):
        return True
    if re.match(r"^(need|also support|also add)\b", lowered):
        return True
    return re.search(r"\b(skip to content|edit this page|table of contents)\b", lowered) is not None


def _build_aliases(*, title: str, source_title: str) -> list[str]:
    aliases: list[str] = []
    for candidate in (source_title, title):
        cleaned = candidate.strip()
        if cleaned and cleaned not in aliases:
            aliases.append(cleaned)
    return aliases


def _extract_tags(source_text: str) -> list[str]:
    counts: dict[str, int] = {}
    author_tokens = _extract_author_name_tokens(source_text)
    paragraph_parts = source_text.split("\n\n")
    first_paragraph = "\n\n".join(paragraph_parts[:2]) if len(paragraph_parts) >= 2 else source_text
    for match in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", source_text):
        token = match.lower()
        if _is_noise_key_term(token) or token in author_tokens:
            continue
        weight = 1
        if re.search(rf"^#.*\b{re.escape(match)}\b", source_text, flags=re.MULTILINE):
            weight += 2
        if re.search(rf"\b{re.escape(match)}\b", first_paragraph):
            weight += 2
        if _appears_in_title_line(match, source_text):
            weight += 4
        counts[token] = counts.get(token, 0) + weight
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:12]]


def _extract_entities(source_text: str) -> list[str]:
    entities: list[str] = []
    seen: set[str] = set()
    author_tokens = _extract_author_name_tokens(source_text)

    for heading in _extract_heading_entities(source_text):
        if _is_noise_entity(heading, source_text=source_text):
            continue
        if heading in seen:
            continue
        seen.add(heading)
        entities.append(heading)

    leading_title = _extract_leading_title_entity(source_text)
    if (
        leading_title
        and leading_title not in seen
        and not _is_noise_entity(leading_title, source_text=source_text)
    ):
        seen.add(leading_title)
        entities.append(leading_title)

    for pattern in (
        r"\b[A-Z]{2,}\d*\b",
        r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b",
        r"\b(?:[A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)+)\b",
    ):
        for match in re.finditer(pattern, source_text):
            entity = match.group(0).strip()
            if _is_noise_entity(entity, source_text=source_text):
                continue
            if entity.lower() in author_tokens:
                continue
            if entity in seen:
                continue
            seen.add(entity)
            entities.append(entity)
    return entities[:12]


def _extract_key_terms(source_text: str) -> list[str]:
    scored: dict[str, tuple[str, int]] = {}

    for entity in _extract_entities(source_text):
        normalized = entity.lower()
        if _is_noise_entity(entity, source_text=source_text):
            continue
        score = _score_key_term(entity, source_text, kind="entity")
        existing = scored.get(normalized)
        if existing is None or score > existing[1]:
            scored[normalized] = (entity, score)

    for tag in _extract_tags(source_text):
        normalized = tag.lower()
        if _is_noise_key_term(tag):
            continue
        score = _score_key_term(tag, source_text, kind="tag")
        existing = scored.get(normalized)
        if existing is None or score > existing[1]:
            scored[normalized] = (tag, score)

    ranked = sorted(scored.values(), key=lambda item: (-item[1], item[0].lower()))
    return [value for value, _ in ranked[:8]]


def _score_key_term(value: str, source_text: str, *, kind: str) -> int:
    score = 0
    lowered = value.lower()

    if kind == "entity":
        score += 6
    else:
        score += 2
    if " " in value:
        score += 4
    if _appears_in_title_line(value, source_text):
        score += 5
    if re.search(rf"^#.*\b{re.escape(value)}\b", source_text, flags=re.MULTILINE):
        score += 4
    if re.search(rf"\b{re.escape(value)}\b", source_text):
        score += min(4, len(re.findall(rf"\b{re.escape(value)}\b", source_text)))
    if re.search(
        r"\b(retrieval|reranking|normalization|search|memory|buffer|workflow|ingest)\b",
        lowered,
    ):
        score += 5
    if re.search(r"\b(retrieve|reading|read)\b", lowered):
        score += 2
    if re.search(r"\bbm25\b", lowered):
        score += 6
    if value.isupper() and len(value) <= 4:
        score -= 5
    if re.fullmatch(r"[A-Z]{2,}", value) and len(value) <= 5:
        score -= 3
    if kind == "tag" and re.search(r"\b(exposes|integrates|locate|over|passages)\b", lowered):
        score -= 4
    return score


def _is_noise_entity(value: str, *, source_text: str) -> bool:
    lowered = value.lower()

    if lowered in _GENERIC_ENTITY_TERMS:
        return True
    if re.fullmatch(r"[A-Z]{2,}", value) and len(value) <= 5:
        return True
    if "," in value:
        return True
    if lowered in _extract_author_name_tokens(source_text):
        return True
    return bool(_looks_like_person_name(value))


def _is_noise_key_term(value: str) -> bool:
    lowered = value.lower()
    if lowered in _STOP_TAGS or lowered in _STRUCTURAL_KEY_TERMS:
        return True
    return bool(re.fullmatch(r"[a-z]{1,3}", lowered))


def _extract_heading_entities(source_text: str) -> list[str]:
    entities: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading:
                entities.append(heading)
    return entities


def _extract_leading_title_entity(source_text: str) -> str | None:
    for raw_line in source_text.splitlines()[:5]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return None
        if len(re.findall(r"[A-Za-z]", line)) < 8:
            continue
        if len(line) > 120:
            continue
        if ":" in line:
            prefix = line.split(":", 1)[0].strip()
            if prefix and not _is_noise_entity(prefix, source_text=source_text):
                return prefix
        return line
    return None


def _appears_in_title_line(value: str, source_text: str) -> bool:
    value_pattern = re.escape(value)
    for raw_line in source_text.splitlines()[:5]:
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        if re.search(rf"\b{value_pattern}\b", line):
            return True
    return False


def _extract_author_name_tokens(source_text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_line in source_text.splitlines()[:8]:
        line = raw_line.strip()
        if not line or "," not in line:
            continue
        parts = [part.strip() for part in line.split(",")]
        name_like_parts = 0
        for part in parts:
            words = part.split()
            if len(words) < 2:
                continue
            if all(re.fullmatch(r"[A-Z][a-z]+", word) for word in words[:2]):
                name_like_parts += 1
                for word in words:
                    tokens.add(word.lower())
        if name_like_parts >= 2:
            return tokens
    return tokens


def _looks_like_person_name(value: str) -> bool:
    words = value.split()
    if len(words) not in {2, 3}:
        return False
    if any(not re.fullmatch(r"[A-Z][a-z]+", word) for word in words):
        return False
    return not any(word.lower() in _DOMAIN_ENTITY_WORDS for word in words)


def _normalize_session_lines(lines: list[str], *, session_id: str) -> str:
    grouped: list[tuple[str, list[str]]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = str(payload.get("role", "unknown")).strip().lower() or "unknown"
        text = _extract_session_content(payload.get("content"))
        if not text:
            continue
        if grouped and grouped[-1][0] == role:
            grouped[-1][1].append(text)
        else:
            grouped.append((role, [text]))

    if not grouped:
        return f"# Session {session_id}\n\nNo session content available.\n"

    lines_out = [f"# Session {session_id}", "", "## Summary Context", ""]
    for role, chunks in grouped[:2]:
        preview = _truncate_text(" ".join(chunks), limit=160)
        lines_out.append(f"- {role.title()}: {preview}")
    lines_out.extend(["", "## Conversation Flow", ""])
    for role, chunks in grouped:
        heading = "User Requests" if role == "user" else "Assistant Responses"
        lines_out.append(f"### {heading}")
        lines_out.append("")
        for chunk in chunks[:3]:
            lines_out.append(f"- {_truncate_text(chunk, limit=220)}")
        lines_out.append("")
    return "\n".join(lines_out).rstrip() + "\n"


def _extract_session_topics(source_text: str) -> list[str]:
    return _dedupe_preserve_order(
        [
            item
            for item in _extract_key_terms(source_text)
            if item.lower() not in _STRUCTURAL_KEY_TERMS and len(item) >= 4
        ][:6]
    )


def _extract_session_decisions(source_text: str) -> list[str]:
    decisions: list[str] = []
    for line in _extract_session_bullets(source_text):
        lowered = line.lower()
        if re.search(r"\b(we will|we should|agreed|focus on|decided|delay|defer)\b", lowered):
            decisions.append(_normalize_session_item(line))
    return _dedupe_preserve_order(decisions)[:5]


def _extract_session_open_questions(source_text: str) -> list[str]:
    questions: list[str] = []
    for line in _extract_session_bullets(source_text):
        if "?" in line or line.lower().startswith(("should ", "what ", "how ", "why ")):
            questions.append(_normalize_session_item(line))
    return _dedupe_preserve_order(questions)[:5]


def _extract_session_action_items(source_text: str) -> list[str]:
    actions: list[str] = []
    for line in _extract_session_bullets(source_text):
        lowered = line.lower()
        if re.search(r"\b(next step|add |support |implement |fix |improve |update )\b", lowered):
            actions.append(_normalize_session_item(line))
    return _dedupe_preserve_order(actions)[:5]


def _extract_session_bullets(source_text: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        candidate = line[2:].strip()
        if candidate:
            bullets.append(candidate)
    return bullets


def _normalize_session_item(value: str) -> str:
    cleaned = re.sub(r"^(User|Assistant):\s*", "", value).strip()
    cleaned = re.sub(r"^(we should|we will)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^the next step is to\s+", "", cleaned, flags=re.IGNORECASE)
    if not cleaned.endswith("?"):
        compact_match = re.search(
            r"\b(improve [^.?!]+|support [^.?!]+|add [^.?!]+)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
        if compact_match is not None:
            cleaned = compact_match.group(1)
    return cleaned.rstrip(".") + ("" if cleaned.endswith("?") else ".")


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(value)
    return output


def _extract_session_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        content_items = cast(list[object], content)
        for item in content_items:
            if isinstance(item, dict):
                item_dict = cast(dict[str, Any], item)
                if item_dict.get("type") != "text":
                    continue
                text = str(item_dict.get("text", "")).strip()
                if text:
                    parts.append(text)
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return " ".join(parts).strip()
    if isinstance(content, dict):
        content_dict = cast(dict[str, Any], content)
        text = str(content_dict.get("text", "")).strip()
        return text
    return ""


def _normalize_pdf_line(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line).strip()
    normalized = normalized.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return normalized


def _prepare_source_text_for_analysis(source_text: str, *, source_kind: str) -> str:
    if source_kind == "pdf":
        return _normalize_pdf_source_text(source_text)
    return source_text


def _normalize_pdf_source_text(source_text: str) -> str:
    lines = [_normalize_pdf_line(line) for line in source_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    lines = _merge_pdf_title_fragments(lines)
    lines = _trim_pdf_preamble(lines)
    filtered = [line for line in lines if not _should_drop_pdf_line(line)]
    return "\n".join(filtered)


def _merge_pdf_title_fragments(lines: list[str]) -> list[str]:
    title_start: int | None = None
    fragments: list[str] = []

    for index, line in enumerate(lines[:8]):
        if _is_pdf_author_line(line) or _parse_pdf_section_heading(line) is not None:
            break
        if line in _KNOWN_PDF_SECTION_HEADINGS:
            break
        if _is_pdf_title_fragment(line):
            if title_start is None:
                title_start = index
            fragments.append(line)
            continue
        if fragments:
            break

    if title_start is None or len(fragments) < 2:
        return lines

    merged = " ".join(fragments).strip()
    if not _is_pdf_title_candidate(merged):
        return lines
    return [*lines[:title_start], merged, *lines[title_start + len(fragments) :]]


def _trim_pdf_preamble(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines[:8]):
        if _is_pdf_title_candidate(line):
            return lines[index:]
    return lines


def _is_pdf_title_fragment(line: str) -> bool:
    if len(line) < 10 or len(line) > 120:
        return False
    if line.endswith("."):
        return False
    if _is_pdf_author_line(line):
        return False
    if _parse_pdf_section_heading(line) is not None or line in _KNOWN_PDF_SECTION_HEADINGS:
        return False
    if _is_pdf_table_like_line(line):
        return False
    return bool(re.search(r"[A-Za-z]", line)) and line[:1].isupper()


def _should_drop_pdf_line(line: str) -> bool:
    return _is_pdf_author_line(line) or _is_pdf_noise_line(line)


def _is_pdf_author_line(line: str) -> bool:
    cleaned = re.sub(r"[*†‡§0-9]", "", line).strip(" ,")
    if len(cleaned) < 10 or "." in cleaned:
        return False
    if re.search(r"\b(university|institute|school|laboratory|lab|department)\b", cleaned.lower()):
        return True
    names = re.findall(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+){1,2}\b", cleaned)
    return len(names) >= 2 and ("," in cleaned or " and " in cleaned.lower())


def _is_pdf_table_like_line(line: str) -> bool:
    lowered = line.lower()
    digit_count = sum(char.isdigit() for char in line)
    alpha_count = len(re.findall(r"[A-Za-z]", line))
    if digit_count >= 8 and digit_count >= alpha_count / 2:
        return True
    if line.count("Level") >= 2:
        return True
    return bool(
        re.search(r"\b(accuracy|precision|recall|f1|score|scores|val|test)\b", lowered)
        and digit_count >= 4
    )


def _is_pdf_title_candidate(line: str) -> bool:
    if len(line) < 20 or len(line) > 160:
        return False
    if not line[:1].isupper():
        return False
    if line.endswith("."):
        return False
    lower = line.lower()
    if any(token in lower for token in ("abstract", "introduction", "references", "appendix")):
        return False
    if re.match(r"^\d+(\.\d+)*\s+", line):
        return False
    if line.count("#") >= 2:
        return False
    return not len(re.findall(r"[A-Za-z]", line)) < 12


def _parse_pdf_section_heading(line: str) -> str | None:
    numbered_match = re.match(r"^(?:\d+(?:\.\d+)*)\s+(.+)$", line)
    if numbered_match:
        heading = numbered_match.group(1).strip(" .:-")
        if _is_pdf_heading_text(heading):
            return heading

    if line in _KNOWN_PDF_SECTION_HEADINGS:
        return line.strip(" .:-")
    return None


def _is_pdf_heading_text(line: str) -> bool:
    if len(line) < 4 or len(line) > 80:
        return False
    if line.endswith("."):
        return False
    if "," in line:
        return False
    if not line[:1].isupper():
        return False
    words = [word for word in re.split(r"\s+", line) if word]
    if not words:
        return False
    if len(words) > 5:
        return False
    title_case_words = sum(
        1
        for word in words
        if word[:1].isupper() or word.isupper() or re.match(r"^[A-Z][a-zA-Z-]+$", word)
    )
    return title_case_words >= max(1, len(words) - 1)


def _score_pdf_title_candidate(line: str, index: int) -> tuple[int, int, int]:
    score = 0
    if ":" in line:
        score += 4
    if index <= 2:
        score += 6
    elif index <= 5:
        score += 3
    if re.search(r"\b(without|using|for|towards)\b", line.lower()):
        score += 1
    return (score, -index, len(line))


def _is_pdf_noise_line(line: str) -> bool:
    if len(line) <= 2:
        return True
    if re.fullmatch(r"\d+", line):
        return True
    if _is_pdf_table_like_line(line):
        return True
    if "Figure " in line or "Table " in line:
        return True
    return bool(line.startswith("{") or line.endswith("}"))


_STOP_TAGS = {
    "about",
    "above",
    "after",
    "agent",
    "agents",
    "and",
    "document",
    "documents",
    "give",
    "gives",
    "have",
    "help",
    "headings",
    "inside",
    "inspect",
    "into",
    "line",
    "lines",
    "paper",
    "papers",
    "note",
    "pdf",
    "range",
    "read",
    "relevant",
    "reranking",
    "specific",
    "summary",
    "context",
    "that",
    "the",
    "their",
    "them",
    "this",
    "toc",
    "use",
    "with",
    "workflow",
    "workflows",
    "user",
    "users",
    "assistant",
    "session",
    "requests",
    "responses",
    "conversation",
}

_STRUCTURAL_KEY_TERMS = {
    "summary",
    "context",
    "session",
    "assistant",
    "user",
    "requests",
    "responses",
    "conversation",
    "overview",
    "installation",
}

_GENERIC_ENTITY_TERMS = {
    "ai",
    "cli",
    "http",
    "llm",
    "mcp",
    "pdf",
    "rag",
    "url",
    "llm agents",
}

_DOMAIN_ENTITY_WORDS = {
    "agent",
    "agents",
    "buffer",
    "cli",
    "document",
    "documents",
    "explorer",
    "interface",
    "learning",
    "memory",
    "memento",
    "mineru",
    "normalization",
    "retrieval",
    "search",
    "wiki",
    "workflow",
    "workflows",
}

_KNOWN_PDF_SECTION_HEADINGS = {
    "Abstract",
    "Introduction",
    "Background",
    "Method",
    "Methods",
    "Approach",
    "Experiments",
    "Evaluation",
    "Results",
    "Discussion",
    "Conclusion",
    "Conclusions",
    "Related Work",
}


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _default_parser_name(source_kind: str) -> str:
    if source_kind == "session":
        return "session"
    if source_kind == "pdf":
        return "pdf"
    return "markdown"


def _source_title_from_url(source: str) -> str:
    parsed = urlparse(source)
    last_segment = parsed.path.rstrip("/").split("/")[-1]
    return last_segment or parsed.netloc or "web-source"


def _convert_url_to_markdown(url: str) -> str:
    try:
        try:
            direct_markdown = _fetch_direct_markdown_url(url)
        except Exception:
            logger.exception("Failed direct markdown fetch for URL: {url}", url=url)
            direct_markdown = ""
        if direct_markdown:
            return _normalize_extracted_markdown(
                direct_markdown,
                fallback_title=_source_title_from_url(url),
            )
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            markdown = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                include_formatting=True,
                include_links=True,
                output_format="markdown",
                favor_precision=True,
            )
            if markdown:
                return _normalize_extracted_markdown(
                    markdown,
                    fallback_title=_source_title_from_url(url),
                )

            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                include_formatting=False,
                output_format="txt",
                favor_precision=True,
            )
            if text:
                return _normalize_plain_text_as_markdown(
                    text,
                    fallback_title=_source_title_from_url(url),
                )
    except Exception:
        logger.exception("Failed to convert URL: {url}", url=url)
    return ""


def _fetch_direct_markdown_url(url: str) -> str:
    raw_url = _github_blob_raw_url(url)
    if raw_url is None and not url.startswith("https://raw.githubusercontent.com/"):
        return ""
    target_url = raw_url or url
    with urlopen(target_url) as response:  # noqa: S310
        content_type = response.headers.get("Content-Type", "").lower()
        text = response.read().decode("utf-8", errors="replace")
    if "text/plain" not in content_type and "text/markdown" not in content_type:
        return ""
    return text


def _github_blob_raw_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "blob":
        return None
    owner, repo, _, branch, *rest = parts
    if not rest:
        return None
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{'/'.join(rest)}"


def _extract_pdf_content(path: Path) -> tuple[str, str, list[str]]:
    content = _normalize_pdf_with_pdfplumber(path)
    if content:
        return content, "pdfplumber", []
    fallback = _extract_pdf_with_pypdf(path)
    if fallback:
        return fallback, "pypdf", ["pdfplumber_low_text_fallback"]
    return "", "pypdf", ["pdfplumber_low_text_fallback"]


def _extract_pdf_with_pypdf(path: Path) -> str:
    try:
        reader = pypdf.PdfReader(path)
        pages_text: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        return "\n".join(pages_text)
    except Exception:
        logger.exception("Failed to convert PDF: {path}", path=path)
    return ""


def _normalize_pdf_with_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber

        lines: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                if text:
                    lines.append(text)
        return "\n".join(lines)
    except ImportError:
        return ""
    except Exception:
        logger.exception("Failed pdfplumber conversion for PDF: {path}", path=path)
    return ""


def _normalize_extracted_markdown(markdown: str, *, fallback_title: str) -> str:
    raw_lines = markdown.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    lines: list[str] = []
    previous_blank = True
    has_heading = False
    normalized_headings: set[str] = set()

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            if not previous_blank:
                lines.append("")
            previous_blank = True
            continue
        line = re.sub(r"\s+", " ", line)
        if _is_url_noise_line(line):
            continue
        if line.startswith("#"):
            line = re.sub(r"^(#+)\s*", r"\1 ", line)
            has_heading = True
            normalized_headings.add(_normalize_heading_text(line.lstrip("#").strip()))
        elif re.match(r"^[-*]\s+", line):
            line = re.sub(r"^[-*]\s+", "- ", line)
        elif re.match(r"^\d+\.\s+", line):
            pass
        lines.append(line)
        previous_blank = False

    lines = _filter_url_navigation_lines(lines, headings=normalized_headings)
    normalized_lines = lines
    if not has_heading and normalized_lines:
        normalized_lines = [f"# {fallback_title}", ""] + normalized_lines

    normalized = "\n".join(normalized_lines).strip()
    return normalized + "\n" if normalized else ""


def _normalize_plain_text_as_markdown(text: str, *, fallback_title: str) -> str:
    paragraphs: list[str] = []
    current: list[str] = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(re.sub(r"\s+", " ", line))

    if current:
        paragraphs.append(" ".join(current))

    if not paragraphs:
        return ""

    body = "\n\n".join(paragraphs)
    return f"# {fallback_title}\n\n{body}\n"


def _filter_url_navigation_lines(lines: list[str], *, headings: set[str]) -> list[str]:
    filtered: list[str] = []
    previous_blank = True

    for line in lines:
        if not line:
            if not previous_blank:
                filtered.append("")
            previous_blank = True
            continue
        if _is_anchor_toc_line(line, headings=headings):
            continue
        filtered.append(line)
        previous_blank = False

    while filtered and not filtered[-1]:
        filtered.pop()
    return filtered


def _is_anchor_toc_line(line: str, *, headings: set[str]) -> bool:
    bullet_anchor = re.match(r"^[-*]\s+\[([^\]]+)\]\(#([^)]+)\)$", line)
    numbered_anchor = re.match(r"^\d+\.\s+\[([^\]]+)\]\(#([^)]+)\)$", line)
    match = bullet_anchor or numbered_anchor
    if match is None:
        return False
    label = _normalize_heading_text(match.group(1))
    anchor = _normalize_heading_text(match.group(2).replace("-", " "))
    return label in headings or anchor in headings


def _is_url_noise_line(line: str) -> bool:
    lower = line.lower()
    if lower in {
        "skip to content",
        "table of contents",
        "on this page",
        "contents",
    }:
        return True
    if any(
        phrase in lower
        for phrase in (
            "you signed in with another tab or window",
            "you signed out in another tab or window",
            "reload to refresh your session",
            "edit this page",
            "view source",
        )
    ):
        return True
    if re.fullmatch(r"\[[^\]]+\]\(#start-of-content\)", line):
        return True
    return re.fullmatch(r"\[[^\]]+\]\(https?://[^)]+/(?:edit|raw|blob)/[^)]+\)", line) is not None


def _normalize_heading_text(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized
