from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    Session = "session"
    SESSION = "session"
    URL = "url"
    File = "file"
    FILE = "file"
    Note = "note"
    NOTE = "note"


class DocumentStatus(StrEnum):
    raw = "raw"
    classified = "classified"
    needs_review = "needs_review"
    reviewed = "reviewed"


class Category(StrEnum):
    Concept = "concept"
    HowTo = "howto"
    Decision = "decision"
    Reference = "reference"
    Analysis = "analysis"
    Source = "source"
    Snippet = "snippet"
    Project = "project"


class TemporalType(StrEnum):
    Evergreen = "evergreen"
    TimeSensitive = "time_sensitive"


class DocumentMetadata(BaseModel):
    """Core metadata model for Knowledge Base documents."""

    id: UUID
    title: str
    slug: str = ""
    description: str
    tags: list[str] = Field(default_factory=list)
    category: Category
    subcategory: str
    status: DocumentStatus = DocumentStatus.raw
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    relevance_score: Annotated[int, Field(ge=1, le=10)]
    temporal_type: TemporalType
    key_claims: Annotated[list[str], Field(max_length=5)] = Field(default_factory=list)
    source_type: SourceType
    original_source: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SearchResult(BaseModel):
    """Result of a search query in the Knowledge Base."""

    metadata: DocumentMetadata
    snippet: str
