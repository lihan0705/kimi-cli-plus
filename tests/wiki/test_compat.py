from kimi_cli.knowledge import (
    RawSourceKind as KnowledgeRawSourceKind,
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
