from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from typing import Optional

from kosong import generate
from kosong.chat_provider import ChatProvider
from kosong.message import Message

from kimi_cli.knowledge.models import (
    DocumentMetadata, 
    SourceType, 
    DocumentStatus,
    Category,
    TemporalType
)
from kimi_cli.knowledge.paths import generate_slug, get_document_dir
from kimi_cli.knowledge.store import KBStore
from kimi_cli.knowledge.log import LogManager

class IngestPipeline:
    def __init__(
        self, 
        root: Path, 
        chat_provider: ChatProvider,
        kb_store: KBStore,
        log_manager: LogManager
    ):
        self.root = root
        self.chat_provider = chat_provider
        self.kb_store = kb_store
        self.log_manager = log_manager
        # In production, this might need to be resolved differently, 
        # but following the requirement path for now.
        self.skill_path = Path("src/kimi_cli/skills/knowledge-ingest/SKILL.md")

    async def run(self, content: str, source_type: SourceType, original_source: str) -> DocumentMetadata:
        """Run the ingestion pipeline for the given content."""
        # 1. Load Skill
        if not self.skill_path.exists():
            # Fallback for tests or different execution context
            # This is a bit of a hack but helps if the test runs from a different dir
            alt_path = Path(__file__).parent.parent / "skills" / "knowledge-ingest" / "SKILL.md"
            if alt_path.exists():
                skill_content = alt_path.read_text()
            else:
                raise FileNotFoundError(f"Skill file not found at {self.skill_path}")
        else:
            skill_content = self.skill_path.read_text()

        # 2. Call LLM
        prompt = (
            f"Please classify and extract metadata for the following content.\n\n"
            f"Source Type: {source_type}\n"
            f"Original Source: {original_source}\n\n"
            f"Content:\n{content}"
        )
        
        result = await generate(
            self.chat_provider,
            system_prompt=skill_content,
            tools=[],
            history=[Message(role="user", content=prompt)]
        )
        
        # 3. Parse Result
        json_str = result.message.extract_text().strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
            
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {result.message.content}") from e

        # Ensure ID and source info
        data["id"] = uuid4()
        data["source_type"] = source_type
        data["original_source"] = original_source
        
        # Handle Confidence/Status
        confidence = data.get("confidence", 1.0)
        if confidence < 0.8:
            data["status"] = DocumentStatus.needs_review
        elif "status" not in data:
            data["status"] = DocumentStatus.classified

        try:
            metadata = DocumentMetadata.model_validate(data)
        except Exception as e:
            raise ValueError(f"Failed to validate metadata: {e}\nData: {data}") from e

        # 4. Apply Slug
        slug = generate_slug(metadata.title, metadata.id)

        # 5. Store
        # Determine the target path using paths.get_document_dir
        # If status is needs_review, we override the category to 'misc'
        effective_category = metadata.category
        effective_subcategory = metadata.subcategory
        
        if metadata.status == DocumentStatus.needs_review:
            # We treat 'misc' as a pseudo-category for routing to knowledge/misc/
            # This requires Category to have a value that maps to 'misc' or handling it here.
            # Based on models.py, we don't have a 'misc' Category, so we'll 
            # use a direct path construction or ensure paths.py can handle it.
            doc_dir = self.root / "knowledge" / "misc" / slug
        else:
            doc_dir = get_document_dir(
                self.root,
                slug,
                metadata.status,
                category=effective_category,
                subcategory=effective_subcategory
            )
        
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        # Save metadata.json and document.md
        (doc_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2))
        (doc_dir / "document.md").write_text(content)
        
        # Update KBStore
        self.kb_store.upsert_document(metadata, content)
        
        # Append to LogManager
        self.log_manager.append("ingest", metadata.title, metadata.id)
        
        return metadata
