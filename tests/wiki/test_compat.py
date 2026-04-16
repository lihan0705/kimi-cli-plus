from kimi_cli.knowledge import (
    RawSourceKind as KnowledgeRawSourceKind,
)
from kimi_cli.knowledge import (
    SourceType as KnowledgeSourceType,
)
from kimi_cli.knowledge import (
    WikiPageKind as KnowledgeWikiPageKind,
)
from kimi_cli.knowledge import (
    WikiSourceRef as KnowledgeWikiSourceRef,
)
from kimi_cli.wiki import RawSourceKind, WikiPageKind, WikiSourceRef


def test_wiki_symbols_are_re_exported_through_knowledge():
    assert KnowledgeRawSourceKind is RawSourceKind
    assert KnowledgeWikiPageKind is WikiPageKind
    assert KnowledgeWikiSourceRef is WikiSourceRef


def test_source_type_compatibility_keeps_legacy_members():
    assert KnowledgeSourceType.Session == "session"
    assert KnowledgeSourceType.SESSION == "session"
    assert KnowledgeSourceType.File == "file"
    assert KnowledgeSourceType.Note == "note"
    assert KnowledgeSourceType.FILE == "file"
    assert KnowledgeSourceType.NOTE == "note"
