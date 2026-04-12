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


class BacklinksParams(BaseModel):
    doc_id: str = Field(description="The UUID of the document to find backlinks for.")


class WikiBacklinks(CallableTool2[BacklinksParams]):
    name: str = "WikiBacklinks"
    description: str = "Find all documents linking TO a specific document by its ID."
    params: type[BacklinksParams] = BacklinksParams

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: BacklinksParams) -> ToolReturnValue:
        builder = ToolResultBuilder()
        try:
            doc_id = UUID(params.doc_id)
        except ValueError:
            return builder.error(f"Invalid UUID: {params.doc_id}", brief="Invalid ID")

        try:
            root = get_kb_root()
            db_path = root / "knowledge.db"
            if not db_path.exists():
                return builder.ok("Knowledge Base is empty.", brief="Empty Knowledge Base")

            kb_store = KBStore(db_path)
            backlinks = kb_store.get_backlinks(doc_id)

            if not backlinks:
                return builder.ok(
                    f"No backlinks found for document: {doc_id}",
                    brief="No backlinks",
                )

            output = ["### Backlinks (Documents linking to this one):"]
            for doc in backlinks:
                output.append(f"- **{doc.title}** (`{doc.id}`)")

            msg = "\n".join(output)
            return builder.ok(msg, brief=f"Found {len(backlinks)} backlinks")

        except Exception as e:
            logger.exception("Failed to fetch backlinks for {doc_id}", doc_id=params.doc_id)
            return builder.error(f"Failed to fetch backlinks: {e}", brief="Error")


class RelatedParams(BaseModel):
    doc_id: str = Field(description="The UUID of the document to find related documents for.")
    limit: int = Field(default=10, description="The maximum number of results to return.")


class WikiRelated(CallableTool2[RelatedParams]):
    name: str = "WikiRelated"
    description: str = "Find documents related to a target document by links or shared tags."
    params: type[RelatedParams] = RelatedParams

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: RelatedParams) -> ToolReturnValue:
        builder = ToolResultBuilder()
        try:
            doc_id = UUID(params.doc_id)
        except ValueError:
            return builder.error(f"Invalid UUID: {params.doc_id}", brief="Invalid ID")

        try:
            root = get_kb_root()
            db_path = root / "knowledge.db"
            if not db_path.exists():
                return builder.ok("Knowledge Base is empty.", brief="Empty Knowledge Base")

            kb_store = KBStore(db_path)
            related = kb_store.get_related_documents(doc_id, limit=params.limit)

            if not related:
                return builder.ok(
                    f"No related documents found for: {doc_id}",
                    brief="No related docs",
                )

            output = [f"### Related Documents for {doc_id}:"]
            for doc, score in related:
                output.append(f"- **{doc.title}** (`{doc.id}`) - Score: {score}")

            msg = "\n".join(output)
            return builder.ok(msg, brief=f"Found {len(related)} related documents")

        except Exception as e:
            logger.exception("Failed to fetch related documents for {doc_id}", doc_id=params.doc_id)
            return builder.error(f"Failed to fetch related documents: {e}", brief="Error")
