import json
import pytest
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime
from kimi_cli.knowledge.models import DocumentMetadata, Category, DocumentStatus, SourceType, TemporalType
from kimi_cli.knowledge.store import KBStore

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
    return root

def create_document_on_disk(root: Path, metadata: DocumentMetadata, content: str, is_raw: bool = False):
    if is_raw:
        doc_dir = root / "raw" / str(metadata.id)
    else:
        # knowledge/{category}/{subcategory}/{slug}/
        category_dir = root / "knowledge" / metadata.category.value
        subcategory_dir = category_dir / metadata.subcategory
        slug = metadata.title.lower().replace(" ", "-")
        doc_dir = subcategory_dir / slug
    
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    with open(doc_dir / "metadata.json", "w") as f:
        # Use model_dump(mode='json') for proper datetime/uuid serialization
        f.write(metadata.model_dump_json())
        
    with open(doc_dir / "document.md", "w") as f:
        f.write(content)
    
    return doc_dir

def test_sync_from_disk_basic(store, kb_root):
    # Create a couple of documents on disk
    doc1_id = uuid4()
    meta1 = DocumentMetadata(
        id=doc1_id,
        title="Doc 1",
        description="Desc 1",
        category=Category.Concept,
        subcategory="sub1",
        status=DocumentStatus.raw,
        confidence=0.9,
        relevance_score=8,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    create_document_on_disk(kb_root, meta1, "Content 1", is_raw=True)
    
    doc2_id = uuid4()
    meta2 = DocumentMetadata(
        id=doc2_id,
        title="Doc 2",
        description="Desc 2",
        category=Category.HowTo,
        subcategory="sub2",
        status=DocumentStatus.classified,
        confidence=0.8,
        relevance_score=7,
        temporal_type=TemporalType.TimeSensitive,
        source_type=SourceType.URL,
        original_source="http://example.com",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    create_document_on_disk(kb_root, meta2, "Content 2", is_raw=False)
    
    # Sync
    store.sync_from_disk(kb_root)
    
    # Verify
    docs = store.list_documents()
    assert len(docs) == 2
    
    doc_ids = {d.id for d in docs}
    assert doc1_id in doc_ids
    assert doc2_id in doc_ids
    
    # Verify content in FTS
    results = store.search("Content 1")
    assert len(results) == 1
    assert results[0].id == doc1_id

def test_sync_from_disk_cleanup(store, kb_root):
    # Add a document to the store that is NOT on disk
    old_id = uuid4()
    old_meta = DocumentMetadata(
        id=old_id,
        title="Old Doc",
        description="Old Desc",
        category=Category.Concept,
        subcategory="old",
        status=DocumentStatus.raw,
        confidence=0.5,
        relevance_score=5,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    store.upsert_document(old_meta, "Old content")
    
    # Verify it exists
    assert len(store.list_documents()) == 1
    
    # Sync with an empty root
    store.sync_from_disk(kb_root)
    
    # Verify it was removed
    assert len(store.list_documents()) == 0

def test_sync_from_disk_nested_structure(store, kb_root):
    # Test deeply nested structure
    doc_id = uuid4()
    meta = DocumentMetadata(
        id=doc_id,
        title="Deep Doc",
        description="Deep Desc",
        category=Category.Reference,
        subcategory="deep/nested/sub",
        status=DocumentStatus.reviewed,
        confidence=1.0,
        relevance_score=10,
        temporal_type=TemporalType.Evergreen,
        source_type=SourceType.File,
        original_source="deep.txt",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    create_document_on_disk(kb_root, meta, "Deep content")
    
    store.sync_from_disk(kb_root)
    
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].id == doc_id
    assert docs[0].subcategory == "deep/nested/sub"
