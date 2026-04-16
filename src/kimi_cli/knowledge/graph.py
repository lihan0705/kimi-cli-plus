from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from .store import KBStore

from .models import DocumentStatus


def extract_links(content: str) -> list[str]:
    """
    Extract Wiki-style links from Markdown content.
    Supports [[Link Text]] and [[Link Text|Alias]].
    Returns a unique list of link targets.
    """
    # Regex for [[Target]] or [[Target|Label]]
    pattern = r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]"
    matches = re.findall(pattern, content)

    # Return unique list while preserving order
    seen: set[str] = set()
    unique_links: list[str] = []
    for match in matches:
        target = match.strip()
        if target and target not in seen:
            unique_links.append(target)
            seen.add(target)

    return unique_links


def resolve_link(store: KBStore, link_text: str) -> UUID | None:
    """
    Resolve a link target to a document UUID.
    Matches by title (case-insensitive) or slug (exact match).
    Prefers documents with status 'reviewed' or 'classified'.
    """
    with store._get_connection() as conn:  # pyright: ignore[reportPrivateUsage]
        # We need to match by title (case-insensitive) or slug (exact match)
        # Since 'slug' might not be in the DB yet, we'll try to match by title first.
        # But the requirement explicitly says 'slug (exact match)'.

        # Check if 'slug' column exists in documents table
        cursor = conn.execute("PRAGMA table_info(documents)")
        columns: list[str] = [str(row[1]) for row in cursor.fetchall()]
        has_slug = "slug" in columns

        query = "SELECT id, status FROM documents WHERE title = ? COLLATE NOCASE"
        params: list[str] = [link_text]

        if has_slug:
            query += " OR slug = ?"
            params.append(link_text)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            return None

        # Prioritize 'reviewed' or 'classified' status
        preferred_statuses = {DocumentStatus.reviewed, DocumentStatus.classified}

        best_match: UUID | None = None
        for row in rows:
            doc_id = UUID(str(row["id"]))
            status = DocumentStatus(str(row["status"]))

            if status in preferred_statuses:
                return doc_id

            if best_match is None:
                best_match = doc_id

        return best_match
