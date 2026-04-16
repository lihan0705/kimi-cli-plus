from kimi_cli.wiki.models import RawSourceKind, WikiPageKind, WikiSourceRef


def test_source_and_page_kinds_match_llm_wiki_design():
    assert RawSourceKind.SESSION == "session"
    assert RawSourceKind.URL == "url"
    assert WikiPageKind.CONCEPT == "concept"
    assert WikiPageKind.QUERY == "query"


def test_source_ref_keeps_legacy_origin():
    ref = WikiSourceRef(
        kind=RawSourceKind.SESSION,
        source_id="sess_123",
        original_path="/old/sessions/2026/04/foo.jsonl",
    )
    assert ref.source_id == "sess_123"
    assert ref.original_path.endswith("foo.jsonl")
