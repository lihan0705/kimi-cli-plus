from __future__ import annotations

from pathlib import Path
from typing import override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.knowledge import (
    KBStore,
    get_kb_root,
)
from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.utils.logging import logger


class Params(BaseModel):
    query: str = Field(description="The search query to find relevant documents in the Knowledge Base.")
    limit: int = Field(default=10, description="The maximum number of results to return.")


class WikiSearch(CallableTool2[Params]):
    name: str = "WikiSearch"
    description: str = load_desc(Path(__file__).parent / "search.md")
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        query = params.query
        limit = params.limit

        try:
            root = get_kb_root()
            db_path = root / "knowledge.db"
            if not db_path.exists():
                return builder.ok("Knowledge Base is empty.", brief="Empty Knowledge Base")

            kb_store = KBStore(db_path)
            results = kb_store.search(query, limit=limit)

            if not results:
                return builder.ok(f"No results found for query: '{query}'", brief="No results")

            output = []
            for res in results:
                meta = res.metadata
                snippet = res.snippet.replace("\n", " ")
                output.append(
                    f"### {meta.title}\n"
                    f"- **ID:** `{meta.id}`\n"
                    f"- **Category:** {meta.category}\n"
                    f"- **Snippet:** {snippet}\n"
                )

            msg = "\n".join(output)
            return builder.ok(msg, brief=f"Found {len(results)} results")

        except Exception as e:
            logger.exception("Failed to search Knowledge Base for {query}", query=query)
            return builder.error(f"Search failed: {e}", brief="Search error")
