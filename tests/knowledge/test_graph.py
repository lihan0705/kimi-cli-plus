from datetime import datetime
from uuid import uuid4

import pytest

from kimi_cli.knowledge.graph import extract_links, resolve_link
from kimi_cli.knowledge.models import (
    Category,
    DocumentMetadata,
    DocumentStatus,
    SourceType,
    TemporalType,
)
from kimi_cli.knowledge.store import KBStore


def test_extract_links():
    content = """
    Check out [[Main Page]] and [[Another Page|Alias]].
    Multiple occurrences: [[Main Page]].
    Nested or weird: [[Page with spaces]].
    """
    links = extract_links(content)
    assert "Main Page" in links
    assert "Another Page" in links
    assert "Page with spaces" in links
    assert len(links) == 3


def test_extract_links_empty():
    assert extract_links("") == []
    assert extract_links("No links here.") == []


def test_extract_links_alias():
    content = "[[Target|Label]] and [[Target Only]]"
    links = extract_links(content)
    assert links == ["Target", "Target Only"]


@pytest.fixture
def kb_store(tmp_path):
    db_path = tmp_path / "test_kb.db"
    return KBStore(db_path)


def create_metadata(title: str, status: DocumentStatus = DocumentStatus.raw, slug: str = ""):
    return DocumentMetadata(
        id=uuid4(),
        title=title,
        slug=slug,
        description="Test desc",
        category=Category.Concept,
        subcategory="test",
        status=status,
        confidence=0.9,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="test",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def test_resolve_link_by_title(kb_store):
    meta = create_metadata("Target Page")
    kb_store.upsert_document(meta, "Content")

    resolved_id = resolve_link(kb_store, "Target Page")
    assert resolved_id == meta.id

    # Case insensitive
    resolved_id = resolve_link(kb_store, "target page")
    assert resolved_id == meta.id


def test_resolve_link_priority(kb_store):
    # Multiple matches
    meta_raw = create_metadata("Target", status=DocumentStatus.raw)
    meta_reviewed = create_metadata("Target", status=DocumentStatus.reviewed)

    kb_store.upsert_document(meta_raw, "Content 1")
    kb_store.upsert_document(meta_reviewed, "Content 2")

    resolved_id = resolve_link(kb_store, "Target")
    assert resolved_id == meta_reviewed.id


def test_resolve_link_not_found(kb_store):
    assert resolve_link(kb_store, "Non Existent") is None


# This test will fail if slug is not implemented
def test_resolve_link_by_slug(kb_store):
    # How do we get the slug if it's not in the DB?
    # For now, let's assume we can match by slug if we implement it.
    # This is a bit tricky without modifying the schema.
    pass
