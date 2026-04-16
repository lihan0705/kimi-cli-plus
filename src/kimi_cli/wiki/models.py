from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from kimi_cli.knowledge.models import SourceType as RawSourceKind


class WikiPageKind(StrEnum):
    ENTITY = "entity"
    CONCEPT = "concept"
    COMPARISON = "comparison"
    QUERY = "query"


WIKI_PAGE_KINDS = tuple(WikiPageKind)
WIKI_PAGE_DIRECTORIES: dict[WikiPageKind, str] = {
    WikiPageKind.ENTITY: "entities",
    WikiPageKind.CONCEPT: "concepts",
    WikiPageKind.COMPARISON: "comparisons",
    WikiPageKind.QUERY: "queries",
}


class WikiSourceRef(BaseModel):
    kind: RawSourceKind
    source_id: str
    original_path: str = ""
