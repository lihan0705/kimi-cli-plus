from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from unittest.mock import Mock

import pytest

from kimi_cli.ui.shell.slash import registry as shell_slash_registry
from kimi_cli.wiki.layout import ensure_wiki_dirs


def _write_page(root: Path, slug: str, title: str) -> None:
    (root / "concepts" / f"{slug}.md").write_text(
        "---\n"
        f"source_title: {title}\n"
        f"source_identity: note://{slug}\n"
        "page_kind: concept\n"
        f"page_slug: {slug}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Summary\n\n"
        "- Summary line.\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_wiki_list_subcommand_uses_filesystem_pages(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    shell = Mock()
    shell.soul = Mock()

    command = shell_slash_registry.find_command("wiki")
    assert command is not None
    ret = command.func(shell, "list")
    if isinstance(ret, Awaitable):
        await ret


@pytest.mark.asyncio
async def test_wiki_read_subcommand_uses_slug(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    shell = Mock()
    shell.soul = Mock()

    command = shell_slash_registry.find_command("wiki")
    assert command is not None
    ret = command.func(shell, "read alpha--aaaa1111")
    if isinstance(ret, Awaitable):
        await ret


@pytest.mark.asyncio
async def test_wiki_delete_subcommand_updates_artifacts(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    _write_page(root, "alpha--aaaa1111", "Alpha")
    monkeypatch.setenv("KIMI_WIKI_ROOT", str(root))

    shell = Mock()
    shell.soul = Mock()

    command = shell_slash_registry.find_command("wiki")
    assert command is not None
    ret = command.func(shell, "delete alpha--aaaa1111")
    if isinstance(ret, Awaitable):
        await ret

    assert not (root / "concepts" / "alpha--aaaa1111.md").exists()
    assert (root / "index.md").exists()
    assert (root / "RELATIONS.md").exists()
