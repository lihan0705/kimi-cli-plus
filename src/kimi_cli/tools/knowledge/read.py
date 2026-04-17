from typing import override

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.agent import Runtime
from kimi_cli.tools.utils import ToolResultBuilder
from kimi_cli.utils.logging import logger
from kimi_cli.wiki import ensure_wiki_dirs, get_wiki_root, read_page


class Params(BaseModel):
    slug: str = Field(description="The wiki page slug to read.")


class WikiRead(CallableTool2[Params]):
    name: str = "WikiRead"
    description: str = "Read the full content of a wiki page by slug."
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()
        try:
            root = get_wiki_root()
            ensure_wiki_dirs(root)
            page = read_page(root, params.slug)
            return builder.ok(page.content, brief=f"Read {page.slug}")
        except FileNotFoundError:
            return builder.error(f"Wiki page not found: {params.slug}", brief="Not found")
        except Exception as e:
            logger.exception("Failed to read wiki page {slug}", slug=params.slug)
            return builder.error(f"Read failed: {e}", brief="Read error")
