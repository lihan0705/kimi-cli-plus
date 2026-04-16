from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kimi_cli.knowledge.models import (
    Category,
    DocumentMetadata,
    DocumentStatus,
    SourceType,
    TemporalType,
)


def test_document_metadata_valid():
    """Test creating a valid DocumentMetadata object."""
    data = {
        "id": uuid4(),
        "title": "Test Title",
        "description": "Test Description",
        "tags": ["tag1", "tag2"],
        "category": Category.Concept,
        "subcategory": "General",
        "status": DocumentStatus.raw,
        "confidence": 0.8,
        "relevance_score": 7,
        "temporal_type": TemporalType.Evergreen,
        "key_claims": ["Claim 1", "Claim 2"],
        "source_type": SourceType.File,
        "original_source": "https://example.com",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    metadata = DocumentMetadata(**data)
    assert metadata.title == "Test Title"
    assert metadata.category == Category.Concept
    assert metadata.status == DocumentStatus.raw


def test_document_metadata_categories():
    """Ensure all 8 categories are handled."""
    categories = [
        Category.Concept,
        Category.HowTo,
        Category.Decision,
        Category.Reference,
        Category.Analysis,
        Category.Source,
        Category.Snippet,
        Category.Project,
    ]
    for cat in categories:
        data = {
            "id": uuid4(),
            "title": "Test Title",
            "description": "Test Description",
            "tags": [],
            "category": cat,
            "subcategory": "General",
            "status": DocumentStatus.raw,
            "confidence": 0.5,
            "relevance_score": 5,
            "temporal_type": TemporalType.Evergreen,
            "key_claims": [],
            "source_type": SourceType.File,
            "original_source": "source",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        metadata = DocumentMetadata(**data)
        assert metadata.category == cat


def test_document_metadata_statuses():
    """Ensure all 4 statuses are handled."""
    statuses = [
        DocumentStatus.raw,
        DocumentStatus.classified,
        DocumentStatus.needs_review,
        DocumentStatus.reviewed,
    ]
    for status in statuses:
        data = {
            "id": uuid4(),
            "title": "Test Title",
            "description": "Test Description",
            "tags": [],
            "category": Category.Concept,
            "subcategory": "General",
            "status": status,
            "confidence": 0.5,
            "relevance_score": 5,
            "temporal_type": TemporalType.Evergreen,
            "key_claims": [],
            "source_type": SourceType.File,
            "original_source": "source",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        metadata = DocumentMetadata(**data)
        assert metadata.status == status


def test_document_metadata_confidence_validation():
    """Test confidence validation (0.0 - 1.0)."""
    base_data = {
        "id": uuid4(),
        "title": "Test Title",
        "description": "Test Description",
        "tags": [],
        "category": Category.Concept,
        "subcategory": "General",
        "status": DocumentStatus.raw,
        "relevance_score": 5,
        "temporal_type": TemporalType.Evergreen,
        "key_claims": [],
        "source_type": SourceType.File,
        "original_source": "source",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Valid
    DocumentMetadata(confidence=0.0, **base_data)
    DocumentMetadata(confidence=1.0, **base_data)
    DocumentMetadata(confidence=0.5, **base_data)

    # Invalid
    with pytest.raises(ValidationError):
        DocumentMetadata(confidence=-0.1, **base_data)
    with pytest.raises(ValidationError):
        DocumentMetadata(confidence=1.1, **base_data)


def test_document_metadata_relevance_score_validation():
    """Test relevance_score validation (1 - 10)."""
    base_data = {
        "id": uuid4(),
        "title": "Test Title",
        "description": "Test Description",
        "tags": [],
        "category": Category.Concept,
        "subcategory": "General",
        "status": DocumentStatus.raw,
        "confidence": 0.5,
        "temporal_type": TemporalType.Evergreen,
        "key_claims": [],
        "source_type": SourceType.File,
        "original_source": "source",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Valid
    DocumentMetadata(relevance_score=1, **base_data)
    DocumentMetadata(relevance_score=10, **base_data)
    DocumentMetadata(relevance_score=5, **base_data)

    # Invalid
    with pytest.raises(ValidationError):
        DocumentMetadata(relevance_score=0, **base_data)
    with pytest.raises(ValidationError):
        DocumentMetadata(relevance_score=11, **base_data)


def test_document_metadata_defaults():
    """Test default values of DocumentMetadata."""
    data = {
        "id": uuid4(),
        "title": "Test Title",
        "description": "Test Description",
        "category": Category.Concept,
        "subcategory": "General",
        "confidence": 0.5,
        "relevance_score": 5,
        "temporal_type": TemporalType.Evergreen,
        "source_type": SourceType.File,
        "original_source": "source",
    }
    metadata = DocumentMetadata(**data)
    assert metadata.status == DocumentStatus.raw
    assert metadata.tags == []
    assert metadata.key_claims == []
    assert isinstance(metadata.created_at, datetime)
    assert isinstance(metadata.updated_at, datetime)


def test_document_metadata_key_claims_limit():
    """Test key_claims max 5 limit."""
    base_data = {
        "id": uuid4(),
        "title": "Test Title",
        "description": "Test Description",
        "tags": [],
        "category": Category.Concept,
        "subcategory": "General",
        "status": DocumentStatus.raw,
        "confidence": 0.5,
        "relevance_score": 5,
        "temporal_type": TemporalType.Evergreen,
        "source_type": SourceType.File,
        "original_source": "source",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Valid
    DocumentMetadata(key_claims=["1", "2", "3", "4", "5"], **base_data)

    # Invalid
    with pytest.raises(ValidationError):
        DocumentMetadata(key_claims=["1", "2", "3", "4", "5", "6"], **base_data)
