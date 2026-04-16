from pathlib import Path
from typing import override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.utils.logging import logger
from kimi_cli.wiki import ensure_wiki_dirs, get_wiki_root
from kimi_cli.wiki.ingest import WikiSourceLoadError, distill_source_to_page, load_source_material


class Params(BaseModel):
    source: str = Field(description="The URL or local file path to ingest into the Knowledge Base.")


class WikiIngest(CallableTool2[Params]):
    name: str = "WikiIngest"
    description: str = load_desc(Path(__file__).parent / "ingest.md")
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        source = params.source

        try:
            root = get_wiki_root()
            ensure_wiki_dirs(root)
            material = load_source_material(source)
        except WikiSourceLoadError as exc:
            brief = (
                "File read failed" if "read file" in str(exc).lower() else "Ingest source failed"
            )
            return builder.error(str(exc), brief=brief)
        except Exception as e:
            logger.exception("Failed to ingest content from {source}", source=source)
            return builder.error(f"Ingestion failed: {e}", brief="Ingestion error")

        try:
            result = distill_source_to_page(
                root=root,
                source_text=material.source_text,
                source_title=material.source_title,
                page_kind="concept",
                page_slug=material.source_title,
                source_identity=material.source_identity,
            )

            msg = (
                f"Distilled {material.source_kind} source into wiki page [[{result.page_slug}]]\n"
                f"Page path: {result.page_path}\n"
                f"Index updated: {result.index_path}\n"
                f"Log updated: {root / 'log.md'}"
            )
            return builder.ok(msg, brief="Wiki page written")

        except Exception as e:
            logger.exception("Failed to ingest content from {source}", source=source)
            return builder.error(f"Ingestion failed: {e}", brief="Ingestion error")
