from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import aiofiles
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


def _is_rewind_user_message(message: Message) -> bool:
    if message.role != "user" or len(message.content) != 1:
        return False
    return message.extract_text().startswith("<system>The user rewound")


def _title_for_message(message: Message) -> str:
    text = " ".join(message.extract_text(" ").split())
    if not text:
        return "(empty user message)"
    return text if len(text) <= 80 else text[:77] + "..."


async def build_timeline(context_file: Path) -> list[TimelineNode]:
    if not context_file.exists():
        return []

    nodes: list[TimelineNode] = []
    message_index = -1
    pending_checkpoints: list[int] = []

    async with aiofiles.open(context_file, encoding="utf-8") as f:
        async for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint":
                pending_checkpoints.append(int(data["id"]))
                continue
            if data.get("role", "").startswith("_"):
                continue

            message = Message.model_validate(data)
            message_index += 1
            if not pending_checkpoints:
                continue
            if message.role == "user" and _is_rewind_user_message(message):
                pending_checkpoints.clear()
                continue
            if message.role == "user" and not _is_checkpoint_user_message(message):
                title = _title_for_message(message)
                nodes.append(
                    TimelineNode(
                        checkpoint_id=max(pending_checkpoints),
                        title=title,
                        message_index=message_index,
                    )
                )
                pending_checkpoints.clear()
    return nodes


async def checkpoint_exists(context_file: Path, checkpoint_id: int) -> bool:
    if checkpoint_id < 0 or not context_file.exists():
        return False
    async with aiofiles.open(context_file, encoding="utf-8") as f:
        async for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint" and int(data["id"]) == checkpoint_id:
                return True
    return False
