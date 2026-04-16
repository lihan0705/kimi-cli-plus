from __future__ import annotations

import os
from pathlib import Path


def get_wiki_root() -> Path:
    env_root = os.getenv("KIMI_WIKI_ROOT")
    return Path(env_root) if env_root else Path.home() / ".kimi" / "wiki"


def ensure_wiki_dirs(root: Path) -> None:
    for rel in [
        "raw/sessions",
        "raw/sources",
        "entities",
        "concepts",
        "comparisons",
        "queries",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)

    for filename, content in {
        "SCHEMA.md": "# Wiki Schema\n",
        "index.md": "# Wiki Index\n",
        "log.md": "# Wiki Log\n",
    }.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
