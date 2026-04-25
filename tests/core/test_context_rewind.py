from pathlib import Path

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.wire.types import TextPart


@pytest.mark.asyncio
async def test_rewind_to_truncates_context_and_appends_note(tmp_path: Path) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))
    await context.append_message(Message(role="assistant", content=[TextPart(text="answer")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="second")]))

    await context.rewind_to(1, "The user rewound to checkpoint 1.")

    assert [m.extract_text() for m in context.history] == [
        "first",
        "answer",
        "<system>The user rewound to checkpoint 1.</system>",
    ]
    assert context.n_checkpoints == 2


@pytest.mark.asyncio
async def test_has_checkpoint(tmp_path: Path) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)

    assert context.has_checkpoint(0) is True
    assert context.has_checkpoint(1) is False
