from __future__ import annotations

from typing import override
from uuid import UUID

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.knowledge import (
    KBStore,
    get_kb_root,
)
from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder
from kimi_cli.utils.logging import logger


class Params(BaseModel):
    id: str = Field(description="The UUID of the document to read.")


class WikiRead(CallableTool2[Params]):
    name: str = "WikiRead"
    description: str = "Read the full content of a Knowledge Base document by its ID."
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        try:
            doc_id = UUID(params.id)
        except ValueError:
            return builder.error(f"Invalid UUID: {params.id}", brief="Invalid ID")

        try:
            root = get_kb_root()
            db_path = root / "knowledge.db"
            if not db_path.exists():
                return builder.error("Knowledge Base is empty.", brief="Empty KB")

            kb_store = KBStore(db_path)
            result = kb_store.get_document(doc_id)

            if not result:
                return builder.error(f"Document not found: {doc_id}", brief="Not found")

            meta, content = result
            msg = (
                f"# {meta.title}\n"
                f"- **ID:** `{meta.id}`\n"
                f"- **Category:** {meta.category}\n"
                f"- **Tags:** {', '.join(meta.tags)}\n"
                f"- **Source:** {meta.original_source}\n"
                f"\n---\n\n"
                f"{content}"
            )
            return builder.ok(msg, brief=f"Read {meta.title}")

        except Exception as e:
            logger.exception("Failed to read document {doc_id}", doc_id=params.id)
            return builder.error(f"Read failed: {e}", brief="Read error")
