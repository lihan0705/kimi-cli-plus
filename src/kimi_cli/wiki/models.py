from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class RawSourceKind(StrEnum):
    SESSION = "session"
    URL = "url"
    FILE = "file"
    NOTE = "note"


class WikiPageKind(StrEnum):
    ENTITY = "entity"
    CONCEPT = "concept"
    COMPARISON = "comparison"
    QUERY = "query"


class WikiSourceRef(BaseModel):
    kind: RawSourceKind
    source_id: str
    original_path: str = ""
