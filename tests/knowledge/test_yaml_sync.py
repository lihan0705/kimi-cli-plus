import pytest
import yaml
import json
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime
from kimi_cli.knowledge.models import DocumentMetadata, Category, DocumentStatus, SourceType, TemporalType
from kimi_cli.knowledge.store import KBStore
from kimi_cli.knowledge.paths import generate_slug

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_kb.db"

@pytest.fixture
def store(db_path):
    return KBStore(db_path)

@pytest.fixture
def kb_root(tmp_path):
    root = tmp_path / "kb"
    root.mkdir()
    (root / "raw").mkdir()
    (root / "knowledge").mkdir()
    # Create category dirs
    for cat in Category:
        (root / "knowledge" / cat.value).mkdir()
    return root

def create_doc_dir(root: Path, metadata: DocumentMetadata, content: str, yaml_frontmatter: str = None):
    slug = generate_slug(metadata.title, metadata.id)
    if metadata.status == DocumentStatus.raw:
        doc_dir = root / "raw" / slug
    else:
        doc_dir = root / "knowledge" / metadata.category.value
        if metadata.subcategory:
            doc_dir = doc_dir / metadata.subcategory
        doc_dir = doc_dir / slug
    
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    with open(doc_dir / "metadata.json", "w") as f:
        f.write(metadata.model_dump_json())
    
    with open(doc_dir / "document.md", "w") as f:
        if yaml_frontmatter:
            f.write(f"---\n{yaml_frontmatter}\n---\n\n")
        f.write(content)
    
    return doc_dir

def test_sync_metadata_basic(store, kb_root):
    doc_id = uuid4()
    meta = DocumentMetadata(
        id=doc_id,
        title="Original Title",
        description="Original Desc",
        category=Category.Concept,
        subcategory="general",
        status=DocumentStatus.classified,
        confidence=0.9,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    doc_dir = create_doc_dir(kb_root, meta, "Some content", yaml_frontmatter="title: New Title\nrelevance_score: 9\ntags: [tag1, tag2]")
    
    # Pre-sync: upsert to DB
    with open(doc_dir / "document.md", "r") as f:
        store.upsert_document(meta, f.read())
    
    # Sync
    new_dir = store.sync_metadata_from_md(doc_dir)
    
    assert new_dir == doc_dir
    assert (doc_dir / "metadata.json").exists()
    
    # Verify metadata.json
    with open(doc_dir / "metadata.json", "r") as f:
        updated_meta = DocumentMetadata.model_validate_json(f.read())
        assert updated_meta.title == "New Title"
        assert updated_meta.relevance_score == 9
        assert updated_meta.tags == ["tag1", "tag2"]
    
    # Verify DB
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].title == "New Title"
    assert docs[0].relevance_score == 9
    assert docs[0].tags == ["tag1", "tag2"]

def test_sync_metadata_category_change(store, kb_root):
    doc_id = uuid4()
    meta = DocumentMetadata(
        id=doc_id,
        title="Change Category",
        description="Desc",
        category=Category.Concept,
        subcategory="general",
        status=DocumentStatus.classified,
        confidence=0.9,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    doc_dir = create_doc_dir(kb_root, meta, "Some content", yaml_frontmatter="category: howto\nsubcategory: advanced")
    
    # Pre-sync: upsert to DB
    with open(doc_dir / "document.md", "r") as f:
        store.upsert_document(meta, f.read())
    
    # Sync
    new_dir = store.sync_metadata_from_md(doc_dir)
    
    assert new_dir != doc_dir
    assert not doc_dir.exists()
    assert new_dir.exists()
    assert "knowledge/howto/advanced" in str(new_dir)
    
    # Verify metadata.json in new location
    with open(new_dir / "metadata.json", "r") as f:
        updated_meta = DocumentMetadata.model_validate_json(f.read())
        assert updated_meta.category == Category.HowTo
        assert updated_meta.subcategory == "advanced"
    
    # Verify DB
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].category == Category.HowTo
    assert docs[0].subcategory == "advanced"

def test_sync_metadata_no_yaml(store, kb_root):
    doc_id = uuid4()
    meta = DocumentMetadata(
        id=doc_id,
        title="No YAML",
        description="Desc",
        category=Category.Concept,
        subcategory="general",
        status=DocumentStatus.classified,
        confidence=0.9,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    doc_dir = create_doc_dir(kb_root, meta, "Some content without YAML frontmatter")
    
    # Pre-sync: upsert to DB
    with open(doc_dir / "document.md", "r") as f:
        store.upsert_document(meta, f.read())
    
    # Sync
    new_dir = store.sync_metadata_from_md(doc_dir)
    
    assert new_dir == doc_dir
    
    # Verify metadata.json (should be unchanged)
    with open(doc_dir / "metadata.json", "r") as f:
        updated_meta = DocumentMetadata.model_validate_json(f.read())
        assert updated_meta.title == "No YAML"
    
    # Verify DB
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].title == "No YAML"

def test_sync_metadata_idempotent(store, kb_root):
    doc_id = uuid4()
    meta = DocumentMetadata(
        id=doc_id,
        title="Original",
        description="Desc",
        category=Category.Concept,
        subcategory="general",
        status=DocumentStatus.classified,
        confidence=0.9,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    doc_dir = create_doc_dir(kb_root, meta, "Content", yaml_frontmatter="title: Updated\ncategory: howto")
    
    # First sync
    new_dir = store.sync_metadata_from_md(doc_dir)
    assert "knowledge/howto" in str(new_dir)
    
    # Second sync on the same new_dir
    final_dir = store.sync_metadata_from_md(new_dir)
    assert final_dir == new_dir
    
    # Verify metadata.json
    with open(final_dir / "metadata.json", "r") as f:
        updated_meta = DocumentMetadata.model_validate_json(f.read())
        assert updated_meta.title == "Updated"
        assert updated_meta.category == Category.HowTo
