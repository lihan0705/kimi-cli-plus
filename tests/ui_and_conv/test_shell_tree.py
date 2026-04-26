from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.soul.timeline import TimelineNode
from kimi_cli.ui.shell import tree as shell_tree
from kimi_cli.ui.shell.slash import registry as shell_slash_registry
from kimi_cli.ui.shell.slash import shell_mode_registry
from kimi_cli.wire.types import TextPart


class FakeWorkspaceCheckpoints:
    def __init__(
        self,
        has_checkpoint: bool = False,
        events: list[str] | None = None,
        checkpoint_ids: set[int] | None = None,
    ) -> None:
        self.has_checkpoint = has_checkpoint
        self.checkpoint_ids = checkpoint_ids
        self.events = events
        self.restored: list[int] = []

    def get(self, checkpoint_id: int):
        if self.checkpoint_ids is not None:
            return object() if checkpoint_id in self.checkpoint_ids else None
        return object() if self.has_checkpoint else None

    def preview_restore(self, checkpoint_id: int):
        return SimpleNamespace(changed_files=["M app.py"])

    def restore(self, checkpoint_id: int) -> None:
        if self.events is not None:
            self.events.append("restore")
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


def test_tree_registered_in_shell_and_agent_modes() -> None:
    assert shell_slash_registry.find_command("tree") is not None
    assert shell_mode_registry.find_command("tree") is not None


@pytest.mark.asyncio
async def test_conversation_only_rewinds_context(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    app = _make_app(context, FakeWorkspaceCheckpoints())

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(
        shell_tree,
        "_select_checkpoint",
        AsyncMock(return_value=TimelineNode(checkpoint_id=1, title="second", message_index=1)),
    )
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="conversation"))

    await shell_tree.tree(app, "")

    assert [m.extract_text() for m in context.history] == [
        "first",
        "<system>The user rewound the conversation to checkpoint 1 with mode conversation-only. Continue from that point.</system>",
    ]


@pytest.mark.asyncio
async def test_restore_mode_restores_files_before_rewind(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    events: list[str] = []
    checkpoints = FakeWorkspaceCheckpoints(events=events, checkpoint_ids={3})
    app = _make_app(context, checkpoints)
    original_rewind_to = context.rewind_to

    async def rewind_to_with_event(checkpoint_id: int, note: str) -> None:
        events.append("rewind")
        await original_rewind_to(checkpoint_id, note)

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(
        shell_tree,
        "_select_checkpoint",
        AsyncMock(
            return_value=TimelineNode(
                checkpoint_id=1,
                title="second",
                message_index=1,
                restore_checkpoint_ids=(3,),
            )
        ),
    )
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="restore"))
    monkeypatch.setattr(shell_tree, "_confirm_restore", AsyncMock(return_value=True))
    monkeypatch.setattr(context, "rewind_to", rewind_to_with_event)

    await shell_tree.tree(app, "")

    assert events == ["restore", "rewind"]
    assert checkpoints.restored == [3]
    assert [m.extract_text() for m in context.history] == [
        "first",
        "<system>The user rewound the conversation to checkpoint 1 with mode conversation-and-files. Continue from that point.</system>",
    ]
