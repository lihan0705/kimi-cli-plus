from __future__ import annotations

import os
from pathlib import Path

from .models import WIKI_PAGE_DIRECTORIES


def get_wiki_root() -> Path:
    env_root = os.getenv("KIMI_WIKI_ROOT")
    return Path(env_root).expanduser() if env_root else Path.home() / ".kimi" / "wiki"


def ensure_wiki_dirs(root: Path) -> None:
    for rel in ["raw/sessions", "raw/sources"]:
        (root / rel).mkdir(parents=True, exist_ok=True)

    for directory in WIKI_PAGE_DIRECTORIES.values():
        (root / directory).mkdir(parents=True, exist_ok=True)

    for filename, content in {
        "SCHEMA.md": "# Wiki Schema\n",
        "index.md": "# Wiki Index\n",
        "log.md": "# Wiki Log\n",
    }.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
