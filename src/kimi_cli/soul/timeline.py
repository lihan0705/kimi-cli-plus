from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kosong.message import Message


@dataclass(frozen=True, slots=True)
class TimelineNode:
    checkpoint_id: int
    title: str
    message_index: int | None


def _is_checkpoint_user_message(message: Message) -> bool:
    if message.role != "user" or len(message.content) != 1:
        return False
    return message.extract_text().startswith("<system>CHECKPOINT ")


def _title_for_message(message: Message) -> str:
    text = " ".join(message.extract_text(" ").split())
    if not text:
        return "(empty user message)"
    return text if len(text) <= 80 else text[:77] + "..."


async def build_timeline(context_file: Path) -> list[TimelineNode]:
    records: list[tuple[str, int | None, Message | None]] = []
    if not context_file.exists():
        return []

    with context_file.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint":
                records.append(("_checkpoint", int(data["id"]), None))
            elif data.get("role", "").startswith("_"):
                continue
            else:
                records.append(("message", None, Message.model_validate(data)))

    nodes: list[TimelineNode] = []
    message_index = -1
    pending_checkpoint: int | None = None
    for kind, checkpoint_id, message in records:
        if kind == "_checkpoint":
            pending_checkpoint = checkpoint_id
            continue
        assert message is not None
        message_index += 1
        if pending_checkpoint is None:
            continue
        if message.role == "user" and not _is_checkpoint_user_message(message):
            nodes.append(
                TimelineNode(
                    checkpoint_id=pending_checkpoint,
                    title=_title_for_message(message),
                    message_index=message_index,
                )
            )
            pending_checkpoint = None

    if pending_checkpoint is not None:
        nodes.append(
            TimelineNode(
                checkpoint_id=pending_checkpoint,
                title="(checkpoint before next turn)",
                message_index=None,
            )
        )
    return nodes


async def checkpoint_exists(context_file: Path, checkpoint_id: int) -> bool:
    if checkpoint_id < 0 or not context_file.exists():
        return False
    with context_file.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint" and data.get("id") == checkpoint_id:
                return True
    return False
