from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from kosong import generate
from kosong.chat_provider import ChatProvider
from kosong.message import Message

from kimi_cli.knowledge.log import LogManager
from kimi_cli.knowledge.models import (
    DocumentMetadata,
    DocumentStatus,
    SourceType,
)
from kimi_cli.knowledge.paths import generate_slug, get_document_dir
from kimi_cli.knowledge.store import KBStore


class IngestPipeline:
    def __init__(
        self, root: Path, chat_provider: ChatProvider, kb_store: KBStore, log_manager: LogManager
    ):
        self.root = root
        self.chat_provider = chat_provider
        self.kb_store = kb_store
        self.log_manager = log_manager
        # In production, this might need to be resolved differently,
        # but following the requirement path for now.
        self.skill_path = Path("src/kimi_cli/skills/knowledge-ingest/SKILL.md")

    async def run(
        self, content: str, source_type: SourceType, original_source: str
    ) -> DocumentMetadata:
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
            history=[Message(role="user", content=prompt)],
        )

        # 3. Parse Result
        raw_response = result.message.extract_text().strip()

        # Extract JSON block
        json_str = ""
        if "```json" in raw_response:
            json_str = raw_response.split("```json")[1].split("```")[0].strip()

        # Extract Markdown block (the Wiki page)
        # We look for the second code block or the block starting with ---
        wiki_content = ""
        if "---" in raw_response:
            # Assume the block starting with --- is the Wiki page
            parts = raw_response.split("---")
            if len(parts) >= 3:
                wiki_content = "---" + "---".join(parts[1:])

        # Fallback if no explicit block but JSON exists
        if not wiki_content:
            # Fall back to the original content if the skill did not emit a wiki block.
            wiki_content = content

        try:
            if not json_str:
                # If LLM failed to provide a JSON block, try to find any JSON-like structure
                import re

                match = re.search(r"\{.*\}", raw_response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                else:
                    raise ValueError(f"No JSON block found in LLM response: {raw_response}")

            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {raw_response}") from e

        # Ensure ID and source info (Objective Facts)
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
        metadata.slug = slug

        # 5. Store
        # Determine the target path
        if metadata.status == DocumentStatus.needs_review:
            doc_dir = self.root / "knowledge" / "misc" / slug
        else:
            doc_dir = get_document_dir(
                self.root,
                slug,
                metadata.status,
                category=metadata.category,
                subcategory=metadata.subcategory,
            )

        doc_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata.json (System source of truth)
        (doc_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2))

        # Save document.md (The Wiki page with YAML)
        (doc_dir / "document.md").write_text(wiki_content.strip())

        # Update KBStore
        self.kb_store.upsert_document(metadata, wiki_content.strip())

        # Append to LogManager
        self.log_manager.append("ingest", metadata.title, metadata.id)

        return metadata
