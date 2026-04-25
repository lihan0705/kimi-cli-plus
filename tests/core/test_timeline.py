from pathlib import Path

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.soul.timeline import TimelineNode, build_timeline, checkpoint_exists
from kimi_cli.wire.types import TextPart


@pytest.mark.asyncio
async def test_build_timeline_maps_checkpoint_to_following_user_turn(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="build auth")]))
    await context.append_message(Message(role="assistant", content=[TextPart(text="done")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="fix auth tests")]))

    nodes = await build_timeline(context_file)

    assert nodes == [
        TimelineNode(checkpoint_id=0, title="build auth", message_index=0),
        TimelineNode(checkpoint_id=1, title="fix auth tests", message_index=2),
    ]


@pytest.mark.asyncio
async def test_build_timeline_ignores_synthetic_checkpoint_user_messages(
    tmp_path: Path,
) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=True)
    await context.append_message(Message(role="user", content=[TextPart(text="real request")]))

    nodes = await build_timeline(context_file)

    assert nodes == [TimelineNode(checkpoint_id=0, title="real request", message_index=1)]


@pytest.mark.asyncio
async def test_checkpoint_exists_reads_raw_checkpoint_records(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=False)

    assert await checkpoint_exists(context_file, 0) is True
    assert await checkpoint_exists(context_file, 1) is False
