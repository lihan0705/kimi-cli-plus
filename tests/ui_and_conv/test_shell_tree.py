from pathlib import Path
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
        change_counts: dict[int, int | None] | None = None,
        checkpoint_ids: set[int] | None = None,
    ) -> None:
        self.has_checkpoint = has_checkpoint
        self.events = events
        self.restored: list[int] = []
        self.change_counts = change_counts or {}
        self.checkpoint_ids = checkpoint_ids
        self.restore_checkpoint_id: int | None = None

    def get(self, checkpoint_id: int) -> str | None:
        if self.checkpoint_ids is not None:
            if checkpoint_id not in self.checkpoint_ids:
                return None
            return f"fake_hash_{checkpoint_id}"
        if self.has_checkpoint:
            return f"fake_hash_{checkpoint_id}"
        return None

    def get_change_count(self, checkpoint_id: int, base_checkpoint_id: int | None = None):
        return self.change_counts.get(checkpoint_id)

    def find_restore_checkpoint_id(self, checkpoint_id: int):
        if self.restore_checkpoint_id is not None:
            return self.restore_checkpoint_id
        if self.get(checkpoint_id) is not None:
            return checkpoint_id
        return None

    def preview_restore(self, checkpoint_id: int) -> list[str]:
        return ["M app.py"]

    def restore(self, checkpoint_id: int) -> None:
        if self.events is not None:
            self.events.append("restore")
        self.restored.append(checkpoint_id)

    def new_turn(self) -> None:
        pass


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


def test_checkpoint_label_is_short_plain_text() -> None:
    node = TimelineNode(
        checkpoint_id=20,
        title="显示下twosum.py 内容这个后面的显示简短点，而且为什么不是所有都显示了？",
        message_index=0,
    )
    store = FakeWorkspaceCheckpoints(has_checkpoint=True, change_counts={21: 0})

    label = shell_tree._format_checkpoint_label(node, store, 21)

    assert label == [
        ("", "#20 显示下twosum.py 内容这个后面的显示简... "),
        ("fg:#888888 italic", "[no files]"),
    ]
    assert all("[dim]" not in text for _style, text in label)


def test_checkpoint_label_omits_conversation_only_suffix() -> None:
    node = TimelineNode(checkpoint_id=1, title="hi", message_index=0)
    store = FakeWorkspaceCheckpoints(has_checkpoint=False)

    assert shell_tree._format_checkpoint_label(node, store, None) == [
        ("", "#1 hi "),
        ("fg:#888888 italic", "[no files]"),
    ]


def test_checkpoint_label_counts_changes_after_turn() -> None:
    nodes = [
        TimelineNode(checkpoint_id=14, title="这个写进在一个md file", message_index=0),
        TimelineNode(checkpoint_id=17, title="是的", message_index=1),
    ]
    store = FakeWorkspaceCheckpoints(checkpoint_ids={14, 17}, change_counts={17: 1})
    next_ids = shell_tree._next_workspace_checkpoint_ids(nodes, store)

    assert shell_tree._format_checkpoint_label(nodes[0], store, next_ids[14]) == [
        ("", "#14 这个写进在一个md file "),
        ("fg:#888888 italic", "[1 file]"),
    ]


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
    events: list[str] = []
    checkpoints = FakeWorkspaceCheckpoints(has_checkpoint=True, events=events)
    app = _make_app(context, checkpoints)
    original_rewind_to = context.rewind_to

    async def rewind_to_with_event(checkpoint_id: int, note: str) -> None:
        events.append("rewind")
        await original_rewind_to(checkpoint_id, note)

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="restore"))
    monkeypatch.setattr(shell_tree, "_confirm_restore", AsyncMock(return_value=True))
    monkeypatch.setattr(context, "rewind_to", rewind_to_with_event)

    await shell_tree.tree(app, "")

    assert events == ["restore", "rewind"]
    assert checkpoints.restored == [1]
    assert [m.extract_text() for m in context.history] == [
        "first",
        "<system>The user rewound the conversation to checkpoint 1 with mode conversation-and-files. Continue from that point.</system>",
    ]


@pytest.mark.asyncio
async def test_restore_mode_uses_next_workspace_checkpoint_for_conversation_only_target(
    tmp_path: Path, monkeypatch
) -> None:
    context = await _make_context(tmp_path)
    checkpoints = FakeWorkspaceCheckpoints(has_checkpoint=False)
    checkpoints.restore_checkpoint_id = 2
    app = _make_app(context, checkpoints)

    monkeypatch.setattr(shell_tree, "ensure_kimi_soul", lambda app: app.soul)
    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="restore"))
    monkeypatch.setattr(shell_tree, "_confirm_restore", AsyncMock(return_value=True))

    await shell_tree.tree(app, "")

    assert checkpoints.restored == [2]
