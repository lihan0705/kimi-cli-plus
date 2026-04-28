from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal, cast

from rich.console import Console

from kimi_cli.soul.timeline import TimelineNode, build_timeline
from kimi_cli.ui.shell.slash import ensure_kimi_soul

if TYPE_CHECKING:
    from kimi_cli.ui.shell import Shell

console = Console()
TreeMode = Literal["conversation", "restore", "cancel"]
MAX_TITLE_LEN = 24
ChoiceLabel = list[tuple[str, str]]


def _short_title(title: str) -> str:
    text = " ".join(title.split())
    if len(text) <= MAX_TITLE_LEN:
        return text
    return text[: MAX_TITLE_LEN - 1] + "..."


def _format_checkpoint_label(
    node: TimelineNode,
    store: Any,
    next_workspace_checkpoint_id: int | None,
) -> ChoiceLabel:
    label = f"#{node.checkpoint_id} {_short_title(node.title)}"
    commit_hash = store.get(node.checkpoint_id)
    has_own_snapshot = commit_hash is not None

    if not has_own_snapshot:
        # Only conversation checkpoint, no workspace snapshot for this turn
        return [("", f"{label} "), ("fg:#888888 italic", "[no file changes]")]

    if next_workspace_checkpoint_id is None:
        # Last workspace checkpoint — compare against current worktree
        change_count = len(store.preview_restore(node.checkpoint_id))
    else:
        # Files changed between this snapshot and the next one
        change_count = store.get_change_count(
            next_workspace_checkpoint_id, base_checkpoint_id=node.checkpoint_id
        )

    if change_count is None:
        return [("", f"{label} "), ("fg:#888888 italic", "[files unknown]")]
    if change_count == 0:
        return [("", f"{label} "), ("fg:#888888 italic", "[no file changes]")]
    suffix = f"[{change_count} file{'s' if change_count > 1 else ''} changed]"
    return [("", f"{label} "), ("fg:#888888 italic", suffix)]


def _next_workspace_checkpoint_ids(nodes: list[TimelineNode], store: Any) -> dict[int, int | None]:
    """For each checkpoint, find the next workspace checkpoint that follows it.

    Returns a dict mapping checkpoint_id -> next_workspace_checkpoint_id (or None).
    This allows checkpoints without their own workspace snapshot to still show
    file change counts from the nearest following workspace checkpoint.
    """
    next_ids: dict[int, int | None] = {}
    next_workspace_id: int | None = None
    for node in reversed(nodes):
        next_ids[node.checkpoint_id] = next_workspace_id
        if store.get(node.checkpoint_id) is not None:
            next_workspace_id = node.checkpoint_id
    return next_ids


def _get_user_message_at_checkpoint(context: Any, checkpoint_id: int) -> str | None:
    """Get the original user message text at the given checkpoint."""
    # Prefer file-backed checkpoint markers, which exist even when
    # add_user_message=False was used during checkpoint creation.
    context_path = getattr(context, "file_backend", None)
    if context_path is not None:
        found_checkpoint = False
        try:
            with open(context_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        loaded = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(loaded, dict):
                        continue
                    record = cast(dict[str, Any], loaded)
                    if record.get("role") == "_checkpoint" and record.get("id") == checkpoint_id:
                        found_checkpoint = True
                        continue
                    if not found_checkpoint or record.get("role") != "user":
                        continue
                    msg_text = record.get("content", "")
                    if isinstance(msg_text, list):
                        text_parts: list[str] = []
                        for part in cast(list[Any], msg_text):
                            if not isinstance(part, dict):
                                continue
                            part_dict = cast(dict[str, Any], part)
                            if part_dict.get("type") == "text":
                                maybe_text = part_dict.get("text")
                                if isinstance(maybe_text, str):
                                    text_parts.append(maybe_text)
                        msg_text = " ".join(text_parts)
                    if isinstance(msg_text, str):
                        text = msg_text.strip()
                        if text and not text.startswith("<system>"):
                            return text
        except OSError:
            pass

    # Fallback to in-memory history scan for legacy sessions.
    found_checkpoint = False
    for msg in context.history:
        if msg.role != "user":
            continue
        text = msg.extract_text().strip()
        if text == f"<system>CHECKPOINT {checkpoint_id}</system>":
            found_checkpoint = True
            continue
        if found_checkpoint and not text.startswith("<system>"):
            return text
    return None


async def _select_checkpoint(nodes: list[TimelineNode], store: Any) -> int | None:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    if not nodes:
        return None

    choices: list[tuple[str, Any]] = []
    next_workspace_ids = _next_workspace_checkpoint_ids(nodes, store)

    for node in nodes:
        label = _format_checkpoint_label(node, store, next_workspace_ids.get(node.checkpoint_id))
        choices.append((str(node.checkpoint_id), label))

    selected = cast(
        str | None,
        await ChoiceInput(
            message="Select a checkpoint to continue from:",
            options=choices,
            default=choices[-1][0],
        ).prompt_async(),
    )
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

    store = soul.runtime.workspace_checkpoints
    checkpoint_id = await _select_checkpoint(nodes, store)
    if checkpoint_id is None:
        return

    original_message = _get_user_message_at_checkpoint(soul.context, checkpoint_id)

    restore_checkpoint_id = store.find_restore_checkpoint_id(checkpoint_id)
    has_workspace_checkpoint = restore_checkpoint_id is not None
    mode = await _select_mode(has_workspace_checkpoint)
    if mode == "cancel":
        return

    if mode == "restore":
        assert restore_checkpoint_id is not None
        changed_files = store.preview_restore(restore_checkpoint_id)
        if not await _confirm_restore(changed_files):
            return
        store.restore(restore_checkpoint_id)

    note = (
        f"The user rewound the conversation to checkpoint {checkpoint_id} "
        f"with mode {'conversation-only' if mode == 'conversation' else 'conversation-and-files'}. "
        "Continue from that point."
    )
    await soul.context.rewind_to(checkpoint_id, note)
    if original_message is not None:
        app.set_pending_prefill(original_message)
    console.print(f"[green]Rewound to checkpoint {checkpoint_id}.[/green]")
