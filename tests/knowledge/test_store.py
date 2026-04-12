import pytest
from pathlib import Path
from uuid import uuid4
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
def sample_metadata():
    doc_id = uuid4()
    return DocumentMetadata(
        id=doc_id,
        title="Test Document",
        description="A test document for knowledge base",
        tags=["test", "unit"],
        category=Category.Concept,
        subcategory="testing",
        status=DocumentStatus.raw,
        confidence=0.9,
        relevance_score=8,
        temporal_type=TemporalType.Evergreen,
        key_claims=["Claim 1", "Claim 2"],
        source_type=SourceType.Note,
        original_source="manual",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

def test_init_creates_tables(db_path):
    store = KBStore(db_path)
    assert db_path.exists()
    # Check if tables exist
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='content_fts'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='links'")
        assert cursor.fetchone() is not None

def test_upsert_document(store, sample_metadata):
    content = "This is the content of the test document."
    store.upsert_document(sample_metadata, content)
    
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].id == sample_metadata.id
    assert docs[0].title == sample_metadata.title

def test_upsert_updates_existing(store, sample_metadata):
    content1 = "Content version 1"
    store.upsert_document(sample_metadata, content1)
    
    sample_metadata.title = "Updated Title"
    content2 = "Content version 2"
    store.upsert_document(sample_metadata, content2)
    
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0].title == "Updated Title"

def test_delete_document(store, sample_metadata):
    content = "Content to be deleted"
    store.upsert_document(sample_metadata, content)
    assert len(store.list_documents()) == 1
    
    store.delete_document(sample_metadata.id)
    assert len(store.list_documents()) == 0

def test_search(store, sample_metadata):
    content = "The quick brown fox jumps over the lazy dog"
    store.upsert_document(sample_metadata, content)
    
    results = store.search("fox")
    assert len(results) == 1
    assert results[0].id == sample_metadata.id
    
    results = store.search("cat")
    assert len(results) == 0

def test_list_documents_filtering(store, sample_metadata):
    store.upsert_document(sample_metadata, "content 1")
    
    other_metadata = sample_metadata.model_copy(update={
        "id": uuid4(),
        "title": "Other Doc",
        "category": Category.HowTo,
        "status": DocumentStatus.classified
    })
    store.upsert_document(other_metadata, "content 2")
    
    assert len(store.list_documents()) == 2
    
    concept_docs = store.list_documents(category=Category.Concept)
    assert len(concept_docs) == 1
    assert concept_docs[0].id == sample_metadata.id
    
    howto_docs = store.list_documents(category=Category.HowTo)
    assert len(howto_docs) == 1
    assert howto_docs[0].id == other_metadata.id
    
    classified_docs = store.list_documents(status=DocumentStatus.classified)
    assert len(classified_docs) == 1
    assert classified_docs[0].id == other_metadata.id
