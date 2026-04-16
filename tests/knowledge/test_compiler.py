from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from kimi_cli.knowledge.compiler import compile_wiki_index
from kimi_cli.knowledge.models import (
    Category,
    DocumentMetadata,
    DocumentStatus,
    SourceType,
    TemporalType,
)


def create_document_on_disk(
    root: Path, metadata: DocumentMetadata, content: str, is_raw: bool = False
):
    if is_raw:
        doc_dir = root / "raw" / str(metadata.id)
    else:
        doc_dir = (
            root
            / "knowledge"
            / metadata.category.value
            / metadata.subcategory
            / f"doc_{str(metadata.id)[:8]}"
        )

    doc_dir.mkdir(parents=True, exist_ok=True)
    with open(doc_dir / "metadata.json", "w") as f:
        f.write(metadata.model_dump_json())
    with open(doc_dir / "document.md", "w") as f:
        f.write(content)
    return doc_dir


@pytest.fixture
def kb_root(tmp_path):
    root = tmp_path / "kb"
    root.mkdir()
    (root / "raw").mkdir()
    (root / "knowledge").mkdir()
    return root


def test_compile_wiki_index_empty(kb_root):
    compile_wiki_index(kb_root)
    index_path = kb_root / "index.md"
    assert index_path.exists()
    content = index_path.read_text()
    assert "# Knowledge Base Index" in content
    assert "No documents found." in content


def test_compile_wiki_index_basic(kb_root):
    # Create documents in different categories and subcategories
    doc1 = DocumentMetadata(
        id=uuid4(),
        title="Concept 1",
        description="Description 1",
        tags=["tag1", "tag2"],
        category=Category.Concept,
        subcategory="General",
        status=DocumentStatus.reviewed,
        confidence=1.0,
        relevance_score=10,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now() - timedelta(days=2),
    )
    create_document_on_disk(kb_root, doc1, "Content 1")

    doc2 = DocumentMetadata(
        id=uuid4(),
        title="HowTo 1",
        description="Description 2",
        tags=["tag3"],
        category=Category.HowTo,
        subcategory="Setup",
        status=DocumentStatus.reviewed,
        confidence=1.0,
        relevance_score=10,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now() - timedelta(days=1),
    )
    create_document_on_disk(kb_root, doc2, "Content 2")

    compile_wiki_index(kb_root)
    index_path = kb_root / "index.md"
    assert index_path.exists()
    content = index_path.read_text()

    assert "# Knowledge Base Index" in content
    assert "## Recently Added" in content
    assert f"- [{str(doc2.id)[:8]}] **HowTo 1**: Description 2 (Tags: tag3)" in content
    assert f"- [{str(doc1.id)[:8]}] **Concept 1**: Description 1 (Tags: tag1, tag2)" in content

    assert "## concept" in content.lower()
    assert "### General" in content
    assert f"- [{str(doc1.id)[:8]}] **Concept 1**: Description 1 (Tags: tag1, tag2)" in content

    assert "## howto" in content.lower()
    assert "### Setup" in content
    assert f"- [{str(doc2.id)[:8]}] **HowTo 1**: Description 2 (Tags: tag3)" in content


def test_compile_wiki_index_recently_added_limit(kb_root):
    # Create 6 documents
    docs = []
    for i in range(6):
        doc = DocumentMetadata(
            id=uuid4(),
            title=f"Doc {i}",
            description=f"Desc {i}",
            category=Category.Concept,
            subcategory="General",
            status=DocumentStatus.reviewed,
            confidence=1.0,
            relevance_score=10,
            temporal_type=TemporalType.Evergreen,
            source_type=SourceType.Note,
            original_source="manual",
            created_at=datetime.now() - timedelta(minutes=i),
        )
        create_document_on_disk(kb_root, doc, f"Content {i}")
        docs.append(doc)

    compile_wiki_index(kb_root)
    index_path = kb_root / "index.md"
    content = index_path.read_text()

    # Should only have Doc 0 to Doc 4 in Recently Added
    recently_added_section = content.split("## Recently Added")[1].split("##")[0]
    assert "Doc 0" in recently_added_section
    assert "Doc 4" in recently_added_section
    assert "Doc 5" not in recently_added_section
