from pathlib import Path
from typing import override
from urllib.parse import urlparse

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.knowledge import PDFConverter, SourceType, URLConverter
from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.utils.logging import logger
from kimi_cli.wiki import distill_source_to_page, ensure_wiki_dirs, get_wiki_root


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

            if source.startswith(("http://", "https://")):
                source_type = SourceType.URL
                content = URLConverter.convert_url_to_md(source)
                source_title = _source_title_from_url(source)
                if not content:
                    return builder.error(
                        f"Failed to extract content from URL: {source}",
                        brief="URL conversion failed",
                    )
            else:
                path = Path(source).expanduser().resolve()
                if not path.exists():
                    return builder.error(f"File not found: {source}", brief="File not found")

                source_type = SourceType.File
                source_title = path.stem
                if path.suffix.lower() == ".pdf":
                    content = PDFConverter.convert_pdf_to_md(path)
                else:
                    try:
                        content = path.read_text(encoding="utf-8")
                    except Exception as e:
                        return builder.error(
                            f"Failed to read file {source}: {e}",
                            brief="File read failed",
                        )

                if not content:
                    return builder.error(
                        f"Failed to extract content from file: {source}",
                        brief="File conversion failed",
                    )

            result = distill_source_to_page(
                root=root,
                source_text=content,
                source_title=source_title,
                page_kind="concept",
                page_slug=source_title,
            )

            msg = (
                f"Distilled {source_type.value} source into wiki page [[{result.page_slug}]]\n"
                f"Page path: {result.page_path}\n"
                f"Index updated: {result.index_path}\n"
                f"Log updated: {root / 'log.md'}"
            )
            return builder.ok(msg, brief="Wiki page written")

        except Exception as e:
            logger.exception("Failed to ingest content from {source}", source=source)
            return builder.error(f"Ingestion failed: {e}", brief="Ingestion error")


def _source_title_from_url(source: str) -> str:
    parsed = urlparse(source)
    last_segment = parsed.path.rstrip("/").split("/")[-1]
    return last_segment or parsed.netloc or "web-source"
