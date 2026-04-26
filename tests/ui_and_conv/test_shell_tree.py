from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.ui.shell import tree as shell_tree
from kimi_cli.wire.types import TextPart


class FakeWorkspaceCheckpoints:
    def __init__(self, has_checkpoint: bool = False) -> None:
        self.has_checkpoint = has_checkpoint
        self.restored: list[int] = []

    def get(self, checkpoint_id: int):
        return object() if self.has_checkpoint else None

    def preview_restore(self, checkpoint_id: int):
        return SimpleNamespace(changed_files=["M app.py"])

    def restore(self, checkpoint_id: int) -> None:
        self.restored.append(checkpoint_id)


async def _make_context(tmp_path: Path) -> Context:
    context = Context(tmp_path / "context.jsonl")
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="second")]))
    return context


def _make_app(context: Context, checkpoints: FakeWorkspaceCheckpoints):
    app = Mock()
    app.soul.context = context
    app.soul.runtime.session.context_file = context.file_backend
    app.soul.runtime.workspace_checkpoints = checkpoints
    return app


@pytest.mark.asyncio
async def test_conversation_only_rewinds_context(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    app = _make_app(context, FakeWorkspaceCheckpoints())

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="conversation"))

    await shell_tree.tree(app, "")

    assert [m.extract_text() for m in context.history] == [
        "first",
        "<system>The user rewound the conversation to checkpoint 1 with mode conversation-only. Continue from that point.</system>",
    ]


@pytest.mark.asyncio
async def test_restore_mode_restores_files_before_rewind(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    checkpoints = FakeWorkspaceCheckpoints(has_checkpoint=True)
    app = _make_app(context, checkpoints)

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="restore"))
    monkeypatch.setattr(shell_tree, "_confirm_restore", AsyncMock(return_value=True))

    await shell_tree.tree(app, "")

    assert checkpoints.restored == [1]
