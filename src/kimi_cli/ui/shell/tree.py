from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from prompt_toolkit.shortcuts import button_dialog
from rich.console import Console

from kimi_cli.soul.timeline import TimelineNode, build_timeline
from kimi_cli.ui.shell.slash import ensure_kimi_soul

if TYPE_CHECKING:
    from kimi_cli.soul.workspace_checkpoint import WorkspaceCheckpointStore
    from kimi_cli.ui.shell import Shell

console = Console()
TreeMode = Literal["conversation", "restore", "cancel"]


async def _select_checkpoint(nodes: list[TimelineNode]) -> TimelineNode | None:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    if not nodes:
        return None
    choices = [
        (str(index), f"#{node.checkpoint_id} {node.title}") for index, node in enumerate(nodes)
    ]
    selected = await ChoiceInput(
        message="Select a checkpoint to continue from:",
        options=choices,
        default=choices[-1][0],
    ).prompt_async()
    return nodes[int(selected)] if selected else None


def _restore_checkpoint_id(store: WorkspaceCheckpointStore, node: TimelineNode) -> int | None:
    for checkpoint_id in (*node.restore_checkpoint_ids, node.checkpoint_id):
        if store.get(checkpoint_id) is not None:
            return checkpoint_id
    return None


async def _select_mode(has_workspace_checkpoint: bool) -> TreeMode:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    choices = [("conversation", "Conversation only")]
    if has_workspace_checkpoint:
        choices.append(("restore", "Conversation + restore files"))
    choices.append(("cancel", "Cancel"))
    selected = await ChoiceInput(
        message="How should Kimi continue?",
        options=choices,
        default="conversation",
    ).prompt_async()
    if selected in {"conversation", "restore", "cancel"}:
        return cast(TreeMode, selected)
    return "cancel"


async def _confirm_restore(changed_files: list[str]) -> bool:
    if changed_files:
        console.print("Files that may change:")
        for file in changed_files:
            console.print(f"  {file}")
    else:
        console.print("No file changes detected for restore.")
    result = await button_dialog(
        title="Restore files?",
        text="Restore workspace files from this checkpoint?",
        buttons=[("Yes", True), ("No", False)],
    ).run_async()
    return bool(result)


async def tree(app: Shell, args: str) -> None:
    soul = ensure_kimi_soul(app)
    if soul is None:
        return

    nodes = await build_timeline(soul.runtime.session.context_file)
    if not nodes:
        console.print("[yellow]No checkpoints available in this session.[/yellow]")
        return

    node = await _select_checkpoint(nodes)
    if node is None:
        return
    checkpoint_id = node.checkpoint_id

    store = soul.runtime.workspace_checkpoints
    restore_checkpoint_id = _restore_checkpoint_id(store, node)
    has_workspace_checkpoint = restore_checkpoint_id is not None
    mode = await _select_mode(has_workspace_checkpoint)
    if mode == "cancel":
        return

    if mode == "restore":
        assert restore_checkpoint_id is not None
        preview = store.preview_restore(restore_checkpoint_id)
        if not await _confirm_restore(preview.changed_files):
            return
        store.restore(restore_checkpoint_id)

    note = (
        f"The user rewound the conversation to checkpoint {checkpoint_id} "
        f"with mode {'conversation-only' if mode == 'conversation' else 'conversation-and-files'}. "
        "Continue from that point."
    )
    await soul.context.rewind_to(checkpoint_id, note)
    console.print(f"[green]Rewound to checkpoint {checkpoint_id}.[/green]")
