from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from rich.console import Console

from kimi_cli.soul.timeline import TimelineNode, build_timeline
from kimi_cli.ui.shell.slash import ensure_kimi_soul

if TYPE_CHECKING:
    from kimi_cli.ui.shell import Shell

console = Console()
TreeMode = Literal["conversation", "restore", "cancel"]


async def _select_checkpoint(nodes: list[TimelineNode], store: Any) -> int | None:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    if not nodes:
        return None

    choices = []
    prev_id: int | None = None

    for node in nodes:
        label = f"#{node.checkpoint_id} {node.title}"
        # Compare current node's snapshot with previous node's snapshot to see turn changes
        change_count = store.get_change_count(node.checkpoint_id, base_checkpoint_id=prev_id)

        if change_count is not None and change_count > 0:
            label += f" [dim][{change_count} file{'s' if change_count > 1 else ''} changed][/dim]"
        elif change_count == 0:
            label += " [dim][no file changes][/dim]"

        choices.append((str(node.checkpoint_id), label))
        prev_id = node.checkpoint_id

    selected = await ChoiceInput(
        message="Select a checkpoint to continue from:",
        options=choices,
        default=choices[-1][0],
    ).prompt_async()
    return int(selected) if selected else None


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
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    if changed_files:
        console.print("[yellow]Files that will be restored/changed:[/yellow]")
        for file in changed_files:
            console.print(f"  {file}")
    else:
        console.print("[blue]No file changes detected between current state and snapshot.[/blue]")

    choices = [("yes", "Yes, restore files"), ("no", "No, cancel restore")]
    selected = await ChoiceInput(
        message="Restore workspace files to this checkpoint?",
        options=choices,
        default="yes",
    ).prompt_async()

    return selected == "yes"


async def tree(app: Shell, args: str) -> None:
    soul = ensure_kimi_soul(app)
    if soul is None:
        return

    nodes = await build_timeline(soul.runtime.session.context_file)
    if not nodes:
        console.print("[yellow]No checkpoints available in this session.[/yellow]")
        return

    checkpoint_id = await _select_checkpoint(nodes, soul.runtime.workspace_checkpoints)
    if checkpoint_id is None:
        return

    store = soul.runtime.workspace_checkpoints
    has_workspace_checkpoint = store.get(checkpoint_id) is not None
    mode = await _select_mode(has_workspace_checkpoint)
    if mode == "cancel":
        return

    if mode == "restore":
        preview = store.preview_restore(checkpoint_id)
        if not await _confirm_restore(preview.changed_files):
            return
        store.restore(checkpoint_id)

    note = (
        f"The user rewound the conversation to checkpoint {checkpoint_id} "
        f"with mode {'conversation-only' if mode == 'conversation' else 'conversation-and-files'}. "
        "Continue from that point."
    )
    await soul.context.rewind_to(checkpoint_id, note)
    console.print(f"[green]Rewound to checkpoint {checkpoint_id}.[/green]")
