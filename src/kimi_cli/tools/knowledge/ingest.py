from __future__ import annotations

from pathlib import Path
from typing import override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.knowledge import (
    KBStore,
    LogManager,
    SourceType,
    URLConverter,
    PDFConverter,
    ensure_kb_dirs,
    get_kb_root,
)
from kimi_cli.knowledge.ingest import IngestPipeline
from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.utils.logging import logger


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
            root = get_kb_root()
            ensure_kb_dirs(root)

            # 1. Determine source type and content
            if source.startswith(("http://", "https://")):
                source_type = SourceType.URL
                content = URLConverter.convert_url_to_md(source)
                if not content:
                    return builder.error(f"Failed to extract content from URL: {source}", brief="URL conversion failed")
            else:
                path = Path(source).expanduser().resolve()
                if not path.exists():
                    return builder.error(f"File not found: {source}", brief="File not found")

                source_type = SourceType.File
                if path.suffix.lower() == ".pdf":
                    content = PDFConverter.convert_pdf_to_md(path)
                else:
                    # Assume text/markdown for other files
                    try:
                        content = path.read_text(encoding="utf-8")
                    except Exception as e:
                        return builder.error(f"Failed to read file {source}: {e}", brief="File read failed")

                if not content:
                    return builder.error(f"Failed to extract content from file: {source}", brief="File conversion failed")

            # 2. Initialize Pipeline
            db_path = root / "knowledge.db"
            kb_store = KBStore(db_path)
            log_manager = LogManager(root)

            if not self._runtime.llm:
                return builder.error("No LLM configured for ingestion.", brief="LLM not configured")

            pipeline = IngestPipeline(
                root=root,
                chat_provider=self._runtime.llm.chat_provider,
                kb_store=kb_store,
                log_manager=log_manager
            )

            # 3. Run Pipeline
            metadata = await pipeline.run(content, source_type, source)

            msg = (
                f"Successfully ingested document: {metadata.title} (ID: {metadata.id})\n"
                f"Category: {metadata.category}\n"
                f"Status: {metadata.status}"
            )
            return builder.ok(msg, brief="Ingestion successful")

        except Exception as e:
            logger.exception("Failed to ingest content from {source}", source=source)
            return builder.error(f"Ingestion failed: {e}", brief="Ingestion error")
