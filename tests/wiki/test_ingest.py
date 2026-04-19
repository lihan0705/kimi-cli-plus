from pathlib import Path
from unittest.mock import Mock

from kimi_cli.wiki.ingest import (
    analyze_source_text,
    distill_source_to_page,
    load_session_material,
    load_source_material,
)
from kimi_cli.wiki.layout import ensure_wiki_dirs


def test_distill_source_to_concept_page_writes_page_index_and_log(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    result = distill_source_to_page(
        root=root,
        source_text="# Raw Note\n\nRAG combines retrieval and generation.",
        source_title="rag-note",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
    )

    assert result.page_path.exists()
    page_text = result.page_path.read_text(encoding="utf-8")
    assert page_text.startswith("---\n")
    assert "source_title: rag-note\n" in page_text
    assert "source_identity: " in page_text
    assert "title: Raw Note\n" in page_text
    assert "aliases:\n" in page_text
    assert "source_kind: file\n" in page_text
    assert "parser: markdown\n" in page_text
    assert "quality_flags: []\n" in page_text
    assert f"page_slug: {result.page_slug}\n" in page_text
    assert result.page_slug.startswith("retrieval-augmented-generation--")
    assert "## Key Terms" in page_text
    assert "## Entities" in page_text
    assert "## Section Map" in page_text
    assert "## Outline" in page_text
    assert "## Notes" in page_text
    assert f"[[{result.page_slug}]]" in (root / "index.md").read_text(encoding="utf-8")
    assert "rag-note" in (root / "log.md").read_text(encoding="utf-8")


def test_distill_source_to_page_uses_source_identity_to_avoid_slug_collisions(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    first = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG helps with retrieval.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )
    second = distill_source_to_page(
        root=root,
        source_text="# Note\n\nAgents can use tools.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/b/index.md",
    )

    assert first.page_path != second.page_path
    assert first.page_path.exists()
    assert second.page_path.exists()
    index_text = (root / "index.md").read_text(encoding="utf-8")
    assert f"[[{first.page_slug}]]" in index_text
    assert f"[[{second.page_slug}]]" in index_text


def test_distill_source_to_page_updates_existing_page_for_same_source_identity(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)

    first = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG retrieves.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )
    second = distill_source_to_page(
        root=root,
        source_text="# Note\n\nRAG retrieves and generates grounded answers.",
        source_title="index",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="/notes/a/index.md",
    )

    assert first.page_path == second.page_path
    page_text = second.page_path.read_text(encoding="utf-8")
    assert "grounded answers" in page_text
    assert "source_identity: /notes/a/index.md" in page_text


def test_distill_source_to_page_writes_distilled_summary_not_full_source_dump(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source_text = (
        "# Raw Note\n\n"
        "RAG combines retrieval and generation to ground answers in relevant documents. "
        "It can improve factuality when the retriever is high quality.\n\n"
        "Systems usually need chunking, ranking, and citation handling.\n\n"
        "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE."
    )

    result = distill_source_to_page(
        root=root,
        source_text=source_text,
        source_title="rag-note",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="note://rag-note",
    )

    page_text = result.page_path.read_text(encoding="utf-8")
    assert "## Summary" in page_text
    assert "## Section Map" in page_text
    assert "## Source Excerpt" not in page_text
    assert "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE." not in page_text


def test_distill_source_to_page_builds_mixed_knowledge_page_structure(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source_text = (
        "# MinerU Document Explorer\n\n"
        "MinerU Document Explorer gives agents retrieve, read, and ingest workflows.\n\n"
        "## View document structure\n\n"
        "Use `qmd doc-toc papers/attention-is-all-you-need.pdf` to inspect headings.\n\n"
        "## Read a specific range\n\n"
        'Use `qmd doc-read papers/attention-is-all-you-need.pdf "line:45-120"` to inspect lines.\n\n'
        "## Search inside documents\n\n"
        "BM25 and reranking help locate relevant passages.\n"
    )

    result = distill_source_to_page(
        root=root,
        source_text=source_text,
        source_title="README-zh",
        page_kind="concept",
        page_slug="mineru-document-explorer",
        source_identity="https://example.com/mineru",
    )

    page_text = result.page_path.read_text(encoding="utf-8")
    assert "title: MinerU Document Explorer\n" in page_text
    assert "## Key Terms" in page_text
    assert "- MinerU Document Explorer" in page_text or "- MinerU" in page_text
    assert "- retrieve" in page_text or "- retrieval" in page_text
    assert "- BM25" in page_text
    assert "## Section Map" in page_text
    assert "- View document structure" in page_text
    assert "- Read a specific range" in page_text
    assert "- Search inside documents" in page_text
    assert "## Outline" in page_text
    assert "### View document structure" in page_text
    assert "### Read a specific range" in page_text


def test_load_session_material_normalizes_turns_into_mixed_page_source(tmp_path: Path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        '{"role":"user","content":"Need a plan for wiki search."}\n'
        '{"role":"assistant","content":"We can defer search and improve ingest first."}\n'
        '{"role":"user","content":"Also support session ingest."}\n',
        encoding="utf-8",
    )

    material = load_session_material(session, session_id="sess_123")

    assert material.source_kind == "session"
    assert material.source_title == "session-sess_123"
    assert "# Session sess_123" in material.source_text
    assert "## Conversation Flow" in material.source_text
    assert "### User Requests" in material.source_text
    assert "### Assistant Responses" in material.source_text


def test_analyze_source_text_recovers_pdf_title_and_sections() -> None:
    source_text = (
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        "Huichi Zhou, Yihang Chen, Siyuan Guo\n"
        "1 Introduction\n"
        "Memento enables low-cost continual adaptation for LLM agents.\n"
        "2 Unified Interface\n"
        "A unified interface coordinates tools, memory, and execution.\n"
        "3 Safety and Scaling\n"
        "The system improves scalable deployment with safer control points.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    assert analysis.title == "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs"
    assert analysis.sections
    assert analysis.sections[0].heading == "Introduction"
    assert "Unified Interface" in [section.heading for section in analysis.sections]
    assert "Safety and Scaling" in [section.heading for section in analysis.sections]


def test_pdf_analysis_ignores_lowercase_sentence_fragments_as_title_or_sections() -> None:
    source_text = (
        "equipped with a neural case-selection policy to guide action decisions\n"
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        "Huichi Zhou, Yihang Chen, Siyuan Guo\n"
        "Abstract\n"
        "Memento enables low-cost continual adaptation for LLM agents.\n"
        "1 Introduction\n"
        "The method uses an episodic memory to improve agent behavior.\n"
        "OpenAI DR\n"
        "Aworld\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    assert analysis.title == "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs"
    headings = [section.heading for section in analysis.sections]
    assert "Introduction" in headings
    assert "Abstract" in headings
    assert "Aworld" not in headings
    assert "OpenAI DR" not in headings


def test_load_source_material_normalizes_url_html_into_markdown(monkeypatch) -> None:
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest.trafilatura.fetch_url", Mock(return_value="<html></html>")
    )
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest.trafilatura.extract",
        Mock(
            return_value="# MinerU Document Explorer\n\n"
            "MinerU helps agents read and ingest documents.\n\n"
            "## Search\n\n"
            "- BM25 retrieval\n"
            "- Reranking\n"
        ),
    )

    material = load_source_material("https://example.com/docs/mineru")

    assert material.source_kind == "url"
    assert material.source_identity == "https://example.com/docs/mineru"
    assert material.source_title == "mineru"
    assert material.parser_name == "markdown"
    assert material.quality_flags == []
    assert material.source_text.startswith("# MinerU Document Explorer")
    assert "## Search" in material.source_text


def test_load_source_material_marks_pdf_parser_and_quality_flags(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest._extract_pdf_content",
        Mock(
            return_value=(
                "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\nAbstract\nBody text.\n",
                "pdfplumber",
                [],
            )
        ),
    )

    material = load_source_material(str(source))

    assert material.source_kind == "pdf"
    assert material.parser_name == "pdfplumber"
    assert material.quality_flags == []


def test_load_source_material_filters_noisy_github_like_markdown(monkeypatch) -> None:
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest.trafilatura.fetch_url", Mock(return_value="<html></html>")
    )
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest.trafilatura.extract",
        Mock(
            return_value=(
                "[Skip to content](#start-of-content)\n\n"
                "You signed in with another tab or window.\n\n"
                "# MinerU Document Explorer\n\n"
                "- [Overview](#overview)\n"
                "- [Installation](#installation)\n"
                "- [Usage](#usage)\n\n"
                "## Overview\n\n"
                "MinerU helps agents inspect, read, and ingest documents.\n\n"
                "[Edit this page](https://example.com/edit)\n\n"
                "## Installation\n\n"
                "Install with `uv tool install mineru`.\n"
            )
        ),
    )

    material = load_source_material("https://github.com/opendatalab/MinerU/blob/main/README.md")

    assert material.source_text.startswith("# MinerU Document Explorer")
    assert "Skip to content" not in material.source_text
    assert "You signed in with another tab or window." not in material.source_text
    assert "[Edit this page]" not in material.source_text
    assert "- [Overview](#overview)" not in material.source_text
    assert "## Overview" in material.source_text
    assert "## Installation" in material.source_text


def test_load_source_material_prefers_raw_markdown_for_github_blob_urls(monkeypatch) -> None:
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest._fetch_direct_markdown_url",
        lambda url: "# MinerU Document Explorer\n\n## Overview\n\nRaw markdown body.\n",
    )
    monkeypatch.setattr(
        "kimi_cli.wiki.ingest.trafilatura.fetch_url",
        Mock(side_effect=AssertionError("trafilatura should not be used for direct raw markdown")),
    )

    material = load_source_material(
        "https://github.com/opendatalab/MinerU-Document-Explorer/blob/main/README-zh.md"
    )

    assert material.source_kind == "url"
    assert material.source_text.startswith("# MinerU Document Explorer")
    assert "## Overview" in material.source_text


def test_distill_source_to_page_uses_url_markdown_structure_for_outline() -> None:
    source_text = (
        "# MinerU Document Explorer\n\n"
        "MinerU helps agents inspect, read, and ingest documents.\n\n"
        "## View document structure\n\n"
        "Use qmd doc-toc to inspect section headings.\n\n"
        "## Search documents\n\n"
        "BM25 retrieval and reranking locate relevant passages.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="mineru",
        page_slug="mineru--12345678",
        source_kind="url",
    )

    assert analysis.title == "MinerU Document Explorer"
    assert "View document structure" in [section.heading for section in analysis.sections]
    assert "Search documents" in [section.heading for section in analysis.sections]


def test_distill_source_to_page_ignores_url_navigation_noise_in_outline() -> None:
    source_text = (
        "# MinerU Document Explorer\n\n"
        "- [Overview](#overview)\n"
        "- [Installation](#installation)\n\n"
        "## Overview\n\n"
        "MinerU helps agents inspect, read, and ingest documents.\n\n"
        "## Installation\n\n"
        "Install with `uv tool install mineru`.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="mineru",
        page_slug="mineru--12345678",
        source_kind="url",
    )

    headings = [section.heading for section in analysis.sections]
    assert headings == ["Overview", "Installation"]


def test_markdown_section_summary_prefers_prose_over_commands() -> None:
    source_text = (
        "# MinerU Document Explorer\n\n"
        "## Search documents\n\n"
        '- `qmd doc-grep papers/attention-is-all-you-need.pdf "self-attention"`\n'
        '- `qmd doc-read papers/attention-is-all-you-need.pdf "line:45-120"`\n'
        "Search combines BM25 retrieval and reranking to locate relevant passages before reading.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="mineru",
        page_slug="mineru--12345678",
        source_kind="url",
    )

    section = next(
        section for section in analysis.sections if section.heading == "Search documents"
    )
    assert "BM25 retrieval and reranking" in section.summary
    assert "qmd doc-grep" not in section.summary


def test_pdf_section_summary_filters_structural_noise() -> None:
    source_text = (
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        "2 Unified Interface\n"
        'Tool Register {"type":"function","function":{"name":"","description":""}}\n'
        "A unified interface coordinates tools, memory, and execution across tasks.\n"
        "Replay Buffer Figure 3 shows how prior trajectories are reused.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    section = next(
        section for section in analysis.sections if section.heading == "Unified Interface"
    )
    assert "coordinates tools, memory, and execution" in section.summary
    assert 'Tool Register {"type"' not in section.summary


def test_session_section_summary_avoids_turn_by_turn_dump() -> None:
    source_text = (
        "# Session sess_123\n\n"
        "## Summary Context\n\n"
        "- User: Need a wiki ingest plan.\n"
        "- Assistant: Improve normalization first.\n\n"
        "## Conversation Flow\n\n"
        "### User Requests\n\n"
        "- Need a wiki ingest plan.\n"
        "- Also support session ingest.\n\n"
        "### Assistant Responses\n\n"
        "- Improve normalization first, then structure pages for search later.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="session-sess_123",
        page_slug="sess_123--12345678",
        source_kind="session",
    )

    section = next(
        section for section in analysis.sections if section.heading == "Assistant Responses"
    )
    assert "Improve normalization first" in section.summary
    assert section.summary != "No details extracted."


def test_page_summary_prefers_knowledge_sentences_over_commands() -> None:
    source_text = (
        "# MinerU Document Explorer\n\n"
        '- `qmd doc-grep papers/attention-is-all-you-need.pdf "self-attention"`\n'
        '- `qmd doc-read papers/attention-is-all-you-need.pdf "line:45-120"`\n\n'
        "MinerU gives agents retrieve, read, and ingest workflows for document understanding.\n\n"
        "BM25 retrieval and reranking help locate relevant passages before deep reading.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="mineru",
        page_slug="mineru--12345678",
        source_kind="url",
    )

    assert any("retrieve, read, and ingest workflows" in line for line in analysis.summary_lines)
    assert all("qmd doc-grep" not in line for line in analysis.summary_lines)


def test_page_summary_filters_pdf_structural_noise() -> None:
    source_text = (
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        'Tool Register {"type":"function","function":{"name":"","description":""}}\n'
        "Memento enables low-cost continual adaptation for LLM agents via memory-based updates.\n"
        "Replay Buffer Figure 3 shows how prior trajectories are reused.\n"
        "The method avoids expensive fine-tuning of the underlying model weights.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    assert any("memory-based updates" in line for line in analysis.summary_lines)
    assert all('Tool Register {"type"' not in line for line in analysis.summary_lines)
    assert all("Replay Buffer Figure 3" not in line for line in analysis.summary_lines)


def test_page_summary_filters_session_turn_noise() -> None:
    source_text = (
        "# Session sess_123\n\n"
        "## Summary Context\n\n"
        "- User: Need a wiki ingest plan.\n"
        "- Assistant: Improve normalization first.\n\n"
        "## Conversation Flow\n\n"
        "### User Requests\n\n"
        "- Need a wiki ingest plan.\n"
        "- Also support session ingest.\n\n"
        "### Assistant Responses\n\n"
        "- Improve normalization first, then structure pages for search later.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="session-sess_123",
        page_slug="sess_123--12345678",
        source_kind="session",
    )

    assert any("Improve normalization first" in line for line in analysis.summary_lines)
    assert all(not line.startswith("User:") for line in analysis.summary_lines)


def test_key_terms_prioritize_specific_concepts_over_generic_acronyms() -> None:
    source_text = (
        "# MinerU Document Explorer\n\n"
        "MinerU Document Explorer gives agents retrieve, read, and ingest workflows.\n\n"
        "BM25 retrieval and reranking help locate relevant passages.\n"
        "The project integrates with MCP over HTTP and exposes a CLI.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="mineru",
        page_slug="mineru--12345678",
        source_kind="url",
    )

    assert "MinerU Document Explorer" in analysis.key_terms
    assert "BM25" in analysis.key_terms
    assert "retrieval" in analysis.key_terms
    assert "CLI" not in analysis.key_terms
    assert "HTTP" not in analysis.key_terms


def test_key_terms_filter_session_structure_words() -> None:
    source_text = (
        "# Session sess_123\n\n"
        "## Summary Context\n\n"
        "- User: Need a wiki ingest plan.\n"
        "- Assistant: Improve normalization first.\n\n"
        "## Conversation Flow\n\n"
        "### User Requests\n\n"
        "- Need a wiki ingest plan.\n"
        "- Also support session ingest.\n\n"
        "### Assistant Responses\n\n"
        "- Improve normalization first, then structure pages for search later.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="session-sess_123",
        page_slug="sess_123--12345678",
        source_kind="session",
    )

    assert "normalization" in analysis.key_terms
    assert "search" in analysis.key_terms
    assert "session" not in analysis.key_terms
    assert "assistant" not in analysis.key_terms
    assert "summary" not in analysis.key_terms


def test_key_terms_filter_pdf_author_and_generic_terms() -> None:
    source_text = (
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        "Huichi Zhou, Yihang Chen, Siyuan Guo\n"
        "Memento enables low-cost continual adaptation for LLM agents via memory-based updates.\n"
        "The method uses a replay buffer and online reinforcement learning.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    assert (
        "Memento" in analysis.key_terms
        or "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs" in analysis.key_terms
    )
    assert "replay" in analysis.key_terms or "buffer" in analysis.key_terms
    assert "Huichi Zhou" not in analysis.key_terms
    assert "LLM" not in analysis.key_terms


def test_pdf_analysis_merges_split_title_fragments_and_filters_author_noise() -> None:
    source_text = (
        "equipped with a neural case-selection policy to guide action decisions.\n"
        "Memento: Fine-tuning LLM Agents without\n"
        "Fine-tuning LLMs\n"
        "Huichi Zhou, Yihang Chen, Siyuan Guo, Xue Yan\n"
        "Abstract\n"
        "Memento enables low-cost continual adaptation for LLM agents via memory-based updates.\n"
        "1 Introduction\n"
        "The method uses an episodic memory to improve agent behavior.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    assert analysis.title == "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs"
    assert any("memory-based updates" in line for line in analysis.summary_lines)
    assert all("Huichi Zhou" not in line for line in analysis.summary_lines)
    assert all(line != analysis.title for line in analysis.summary_lines)
    assert "Huichi Zhou" not in analysis.key_terms
    assert "Memento" in analysis.key_terms
    assert "Introduction" in [section.heading for section in analysis.sections]


def test_pdf_analysis_filters_table_like_noise_from_sections_and_summary() -> None:
    source_text = (
        "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs\n"
        "Abstract\n"
        "Memento enables low-cost continual adaptation for LLM agents via memory-based updates.\n"
        "Val-Level1Val-Level2Val-Level3Test-Level1Test-Level2Test-Level3\n"
        "0.0 0.2 0.4 0.6 0.8 1.0 Accuracy (%) 0.96 0.91 0.58 0.85 0.72 0.59\n"
        "2 Unified Interface\n"
        "Replay Buffer Figure 3 shows how prior trajectories are reused.\n"
        "A unified interface coordinates tools, memory, and execution across tasks.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="memento",
        page_slug="memento--2141dc4d",
        source_kind="pdf",
    )

    headings = [section.heading for section in analysis.sections]
    assert "Unified Interface" in headings
    assert "Val-Level1Val-Level2Val-Level3Test-Level1Test-Level2Test-Level3" not in headings
    assert all("Replay Buffer Figure 3" not in line for line in analysis.summary_lines)
    assert all("0.0 0.2 0.4" not in line for line in analysis.summary_lines)


def test_session_page_renders_decisions_questions_and_actions(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source_text = (
        "# Session sess_123\n\n"
        "## Summary Context\n\n"
        "- User: We should delay search and improve ingest first.\n"
        "- Assistant: Agreed, focus on wiki page quality now.\n\n"
        "## Conversation Flow\n\n"
        "### User Requests\n\n"
        "- We should delay search and improve ingest first.\n"
        "- Also support session ingest.\n"
        "- Should we add action items?\n\n"
        "### Assistant Responses\n\n"
        "- We will improve wiki page quality first.\n"
        "- The next step is to add decisions, open questions, and action items.\n"
    )

    result = distill_source_to_page(
        root=root,
        source_text=source_text,
        source_title="session-sess_123",
        page_kind="query",
        page_slug="sess_123",
        source_identity="session://sess_123",
        source_kind="session",
    )

    page_text = result.page_path.read_text(encoding="utf-8")
    assert "## Topics" in page_text
    assert "## Decisions" in page_text
    assert "## Open Questions" in page_text
    assert "## Action Items" in page_text
    assert "- improve ingest first" in page_text.lower()
    assert "- Also support session ingest." in page_text or "- support session ingest" in page_text


def test_session_analysis_extracts_structured_items() -> None:
    source_text = (
        "# Session sess_123\n\n"
        "## Summary Context\n\n"
        "- User: Search should come later.\n"
        "- Assistant: We will focus on ingest now.\n\n"
        "## Conversation Flow\n\n"
        "### User Requests\n\n"
        "- Search should come later.\n"
        "- Should we add an action items section?\n"
        "- Please support session ingest.\n\n"
        "### Assistant Responses\n\n"
        "- We will focus on ingest now.\n"
        "- The next step is to add action items and decisions.\n"
    )

    analysis = analyze_source_text(
        source_text=source_text,
        source_title="session-sess_123",
        page_slug="sess_123--12345678",
        source_kind="session",
    )

    assert analysis.session_topics
    assert any("ingest" in item.lower() for item in analysis.session_topics)
    assert any("focus on ingest" in item.lower() for item in analysis.session_decisions)
    assert any(
        "should we add an action items section" in item.lower()
        for item in analysis.session_open_questions
    )
    assert any("support session ingest" in item.lower() for item in analysis.session_action_items)
