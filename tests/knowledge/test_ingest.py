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
    # Mock LLM response
    json_content = """```json
    {
      "title": "Test Title",
      "description": "Test Summary",
      "tags": ["test"],
      "category": "concept",
      "subcategory": "testing",
      "status": "classified",
      "confidence": 0.95,
      "relevance_score": 8,
      "temporal_type": "evergreen",
      "key_claims": ["claim 1", "claim 2"],
      "source_type": "url",
      "original_source": "https://example.com"
    }
    ```"""
    
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult(json_content)

        pipeline = IngestPipeline(
            root=kb_root,
            chat_provider=mock_chat_provider,
            kb_store=mock_kb_store,
            log_manager=mock_log_manager
        )
        
        # Mock skill path
        skill_file = kb_root / "test_skill.md"
        skill_file.write_text("Skill content")
        pipeline.skill_path = skill_file

        metadata = await pipeline.run("Some raw content", SourceType.URL, "https://example.com")

        assert metadata.title == "Test Title"
        assert metadata.category == Category.Concept
        assert metadata.status == DocumentStatus.classified
        
        # Verify files created
        # Check date in slug
        slug = f"{metadata.created_at.strftime('%Y%m%d')}_test-title_{str(metadata.id)[:8]}"
        doc_dir = kb_root / "knowledge" / "concept" / "testing" / slug
        assert doc_dir.exists()
        assert (doc_dir / "metadata.json").exists()
        assert (doc_dir / "document.md").exists()
        
        # Verify storage and log called
        mock_kb_store.upsert_document.assert_called_once()
        mock_log_manager.append.assert_called_once()

@pytest.mark.asyncio
async def test_ingest_pipeline_needs_review(kb_root, mock_chat_provider, mock_kb_store, mock_log_manager):
    # Mock LLM response with low confidence
    json_content = """```json
    {
      "title": "Uncertain Title",
      "description": "Test Summary",
      "tags": ["test"],
      "category": "concept",
      "subcategory": "testing",
      "status": "needs_review",
      "confidence": 0.5,
      "relevance_score": 5,
      "temporal_type": "evergreen",
      "key_claims": ["claim 1"],
      "source_type": "url",
      "original_source": "https://example.com"
    }
    ```"""
    
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult(json_content)

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
        # documents with status needs_review go to knowledge/misc/
        doc_dir = kb_root / "knowledge" / "misc" / slug
        assert doc_dir.exists()

@pytest.mark.asyncio
async def test_ingest_pipeline_parsing_error(kb_root, mock_chat_provider, mock_kb_store, mock_log_manager):
    # Mock LLM response with invalid JSON
    with patch("kimi_cli.knowledge.ingest.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult("Invalid response from LLM")

        pipeline = IngestPipeline(
            root=kb_root,
            chat_provider=mock_chat_provider,
            kb_store=mock_kb_store,
            log_manager=mock_log_manager
        )
        skill_file = kb_root / "test_skill.md"
        skill_file.write_text("Skill")
        pipeline.skill_path = skill_file

        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            await pipeline.run("content", SourceType.URL, "https://example.com")
