from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class DistilledPageResult:
    page_path: Path
    page_kind: WikiPageKind
    page_slug: str
    index_path: Path
    log_entry: WikiLogEntry
    source_identity: str


def distill_source_to_page(
    *,
    root: Path,
    source_text: str,
    source_title: str,
    page_kind: str | WikiPageKind,
    page_slug: str,
    source_identity: str | None = None,
) -> DistilledPageResult:
    ensure_wiki_dirs(root)
    normalized_kind = WikiPageKind(page_kind)
    resolved_source_identity = source_identity or _default_source_identity(
        source_title=source_title,
        source_text=source_text,
    )
    normalized_slug = _resolve_page_slug(page_slug, resolved_source_identity)
    page_path = root / WIKI_PAGE_DIRECTORIES[normalized_kind] / f"{normalized_slug}.md"

    page_path.write_text(
        _render_page(
            source_text=source_text,
            source_title=source_title,
            source_identity=resolved_source_identity,
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
        )

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise WikiSourceLoadError(f"File not found: {source}")

    try:
        if path.suffix.lower() == ".pdf":
            content = _convert_pdf_to_markdown(path)
        else:
            content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc
    except OSError as exc:
        raise WikiSourceLoadError(f"Failed to read file {source}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - converter-specific failures
        raise WikiSourceLoadError(f"Failed to extract content from file: {source}: {exc}") from exc

    if not content:
        raise WikiSourceLoadError(f"Failed to extract content from file: {source}")

    return SourceMaterial(
        source_kind="file",
        source_identity=str(path),
        source_text=content,
        source_title=path.stem,
    )


def _render_page(
    *,
    source_text: str,
    source_title: str,
    source_identity: str,
    page_kind: WikiPageKind,
    page_slug: str,
) -> str:
    summary_lines, outline_lines = _distill_source_text(source_text)
    outline_block = ""
    if outline_lines:
        outline_block = "## Outline\n\n" + "\n".join(f"- {line}" for line in outline_lines) + "\n\n"
    return (
        "---\n"
        f"source_title: {source_title}\n"
        f"source_identity: {source_identity}\n"
        f"page_kind: {page_kind.value}\n"
        f"page_slug: {page_slug}\n"
        "---\n\n"
        f"# {_display_title(source_text, page_slug)}\n\n"
        "## Summary\n\n"
        + "\n".join(f"- {line}" for line in summary_lines)
        + "\n\n"
        + outline_block
        + "\n"
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


def _display_title(source_text: str, page_slug: str) -> str:
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return page_slug.replace("-", " ").title()


def _distill_source_text(source_text: str) -> tuple[list[str], list[str]]:
    headings: list[str] = []
    paragraphs: list[str] = []
    current_paragraph: list[str] = []

    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            continue
        if line.startswith("#"):
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            heading = line.lstrip("#").strip()
            if heading:
                headings.append(heading)
            continue
        cleaned = line.lstrip("-*").strip()
        if cleaned and not cleaned.startswith("```"):
            current_paragraph.append(cleaned)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))

    summary_lines = _build_summary_lines(paragraphs)
    outline_lines = headings[:4]
    return summary_lines, outline_lines


def _build_summary_lines(paragraphs: list[str]) -> list[str]:
    sentences: list[str] = []
    for paragraph in paragraphs[:4]:
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            normalized = sentence.strip()
            if len(normalized) < 24:
                continue
            sentences.append(_truncate_text(normalized, limit=140))
            if len(sentences) == 3:
                return sentences
    if not sentences:
        return ["No source content provided."]
    return sentences
def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _source_title_from_url(source: str) -> str:
    parsed = urlparse(source)
    last_segment = parsed.path.rstrip("/").split("/")[-1]
    return last_segment or parsed.netloc or "web-source"


def _convert_url_to_markdown(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            result = trafilatura.extract(downloaded)
            return result or ""
    except Exception:
        logger.exception("Failed to convert URL: {url}", url=url)
    return ""


def _convert_pdf_to_markdown(path: Path) -> str:
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
