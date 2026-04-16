from __future__ import annotations

from pathlib import Path

from .models import WIKI_PAGE_DIRECTORIES, WikiPageKind


def rebuild_wiki_index(root: Path) -> Path:
    sections = ["# Wiki Index", ""]

    for page_kind in WikiPageKind:
        directory = root / WIKI_PAGE_DIRECTORIES[page_kind]
        pages = sorted(directory.glob("*.md"))
        sections.append(f"## {page_kind.value.title()}s")
        if pages:
            for page in pages:
                sections.append(f"- [[{page.stem}]]")
        else:
            sections.append("- (none)")
        sections.append("")

    index_path = root / "index.md"
    index_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return index_path
