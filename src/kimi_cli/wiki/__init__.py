from __future__ import annotations

from .catalog import delete_pages, list_pages, read_page
from .ingest import DistilledPageResult as _DistilledPageResult
from .ingest import distill_source_to_page as _distill_source_to_page
from .layout import ensure_wiki_dirs, get_wiki_root
from .models import (
    WIKI_PAGE_DIRECTORIES as _WIKI_PAGE_DIRECTORIES,
)
from .models import (
    WIKI_PAGE_KINDS as _WIKI_PAGE_KINDS,
)
from .models import (
    RawSourceKind as _RawSourceKind,
)
from .models import (
    WikiPageKind as _WikiPageKind,
)
from .models import (
    WikiSourceRef as _WikiSourceRef,
)

RawSourceKind = _RawSourceKind
DistilledPageResult = _DistilledPageResult
WIKI_PAGE_DIRECTORIES = _WIKI_PAGE_DIRECTORIES
WIKI_PAGE_KINDS = _WIKI_PAGE_KINDS
WikiPageKind = _WikiPageKind
WikiSourceRef = _WikiSourceRef
distill_source_to_page = _distill_source_to_page

__all__ = ["delete_pages", "ensure_wiki_dirs", "get_wiki_root", "list_pages", "read_page"]
