import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from kimi_cli.knowledge.models import DocumentMetadata, SourceType, DocumentStatus, Category, TemporalType
from kimi_cli.knowledge.ingest import IngestPipeline

@pytest.fixture
def kb_root(tmp_path):
    root = tmp_path / "kb"
    root.mkdir(parents=True, exist_ok=True)
    return root

@pytest.fixture
def mock_chat_provider():
    return AsyncMock()

@pytest.fixture
def mock_kb_store():
    return MagicMock()

@pytest.fixture
def mock_log_manager():
    return MagicMock()

class MockMessage:
    def __init__(self, content):
        self.content = content
    def extract_text(self):
        return self.content

class MockGenerateResult:
    def __init__(self, content):
        self.message = MockMessage(content)
        self.usage = None

@pytest.mark.asyncio
async def test_ingest_pipeline_success(kb_root, mock_chat_provider, mock_kb_store, mock_log_manager):
    # Mock LLM response with both JSON and Markdown blocks
    json_part = """{
      "title": "Test Title",
      "description": "A test document description",
      "category": "concept",
      "subcategory": "testing",
      "tags": ["test"],
      "confidence": 0.95,
      "relevance_score": 8,
      "temporal_type": "evergreen",
      "key_claims": ["claim 1", "claim 2"]
    }"""
    
    markdown_part = """---
title: Test Title
category: concept
subcategory: testing
tags: [test]
relevance_score: 8
key_claims:
  - claim 1
  - claim 2
---

# Test Title

Some raw content"""

    full_response = f"Here is the result:\n\n```json\n{json_part}\n```\n\n```markdown\n{markdown_part}\n```"
    
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult(full_response)

        pipeline = IngestPipeline(
            root=kb_root,
            chat_provider=mock_chat_provider,
            kb_store=mock_kb_store,
            log_manager=mock_log_manager
        )
        
        skill_file = kb_root / "test_skill.md"
        skill_file.write_text("Skill content")
        pipeline.skill_path = skill_file

        metadata = await pipeline.run("Some raw content", SourceType.URL, "https://example.com")

        assert metadata.title == "Test Title"
        assert metadata.category == Category.Concept
        
        # Verify files created
        slug = f"{metadata.created_at.strftime('%Y%m%d')}_test-title_{str(metadata.id)[:8]}"
        doc_dir = kb_root / "knowledge" / "concept" / "testing" / slug
        assert doc_dir.exists()
        assert (doc_dir / "metadata.json").exists()
        
        # Verify document.md contains YAML
        doc_content = (doc_dir / "document.md").read_text()
        assert "---" in doc_content
        assert "title: Test Title" in doc_content
        
        mock_kb_store.upsert_document.assert_called_once()

@pytest.mark.asyncio
async def test_ingest_pipeline_needs_review(kb_root, mock_chat_provider, mock_kb_store, mock_log_manager):
    # Mock LLM response with low confidence
    json_part = """{
      "title": "Uncertain Title",
      "description": "An uncertain document description",
      "category": "concept",
      "subcategory": "testing",
      "confidence": 0.5,
      "relevance_score": 5,
      "temporal_type": "evergreen",
      "key_claims": ["claim 1"]
    }"""
    
    full_response = f"```json\n{json_part}\n```\n\n--- \ntitle: Uncertain Title\n---"
    
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult(full_response)

        pipeline = IngestPipeline(
            root=kb_root,
            chat_provider=mock_chat_provider,
            kb_store=mock_kb_store,
            log_manager=mock_log_manager
        )
        skill_file = kb_root / "test_skill.md"
        skill_file.write_text("Skill")
        pipeline.skill_path = skill_file

        metadata = await pipeline.run("content", SourceType.URL, "https://example.com")

        assert metadata.status == DocumentStatus.needs_review

        # Check storage
        slug = f"{metadata.created_at.strftime('%Y%m%d')}_uncertain-title_{str(metadata.id)[:8]}"
        doc_dir = kb_root / "knowledge" / "misc" / slug
        assert doc_dir.exists()

@pytest.mark.asyncio
async def test_ingest_pipeline_parsing_error(kb_root, mock_chat_provider, mock_kb_store, mock_log_manager):
    # Mock LLM response with invalid content
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult("No JSON and no YAML here")

        pipeline = IngestPipeline(
            root=kb_root,
            chat_provider=mock_chat_provider,
            kb_store=mock_kb_store,
            log_manager=mock_log_manager
        )
        skill_file = kb_root / "test_skill.md"
        skill_file.write_text("Skill")
        pipeline.skill_path = skill_file

        with pytest.raises(ValueError, match="No JSON block found"):
            await pipeline.run("content", SourceType.URL, "https://example.com")
