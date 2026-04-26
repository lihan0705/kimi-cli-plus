import json
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


@pytest.mark.asyncio
async def test_rewind_to_rejects_missing_checkpoint_without_mutating_history(
    tmp_path: Path,
) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))

    original_history = [m.extract_text() for m in context.history]

    with pytest.raises(ValueError, match="Checkpoint 1 does not exist"):
        await context.rewind_to(1, "The user rewound to checkpoint 1.")

    assert [m.extract_text() for m in context.history] == original_history
    assert context.has_checkpoint(0) is True
    assert context.has_checkpoint(1) is False


@pytest.mark.asyncio
async def test_rewind_to_rejects_negative_checkpoint_without_mutating_history(
    tmp_path: Path,
) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))

    original_history = [m.extract_text() for m in context.history]

    with pytest.raises(ValueError, match="Checkpoint -1 does not exist"):
        await context.rewind_to(-1, "The user rewound to checkpoint -1.")

    assert [m.extract_text() for m in context.history] == original_history
    assert context.has_checkpoint(0) is True
    assert context.has_checkpoint(-1) is False


@pytest.mark.asyncio
async def test_restore_round_trip_after_rewind(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="second")]))

    await context.rewind_to(1, "The user rewound to checkpoint 1.")

    restored = Context(context_file)
    assert await restored.restore() is True

    assert [m.extract_text() for m in restored.history] == [
        "first",
        "<system>The user rewound to checkpoint 1.</system>",
    ]
    assert restored.n_checkpoints == 2
    assert restored.has_checkpoint(0) is True
    assert restored.has_checkpoint(1) is True
    assert restored.has_checkpoint(2) is False


@pytest.mark.asyncio
async def test_restore_tracks_non_contiguous_checkpoint_records(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context_file.write_text(
        "\n".join(
            [
                json.dumps({"role": "_checkpoint", "id": 0}),
                json.dumps({"role": "_checkpoint", "id": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    context = Context(context_file)
    assert await context.restore() is True

    assert context.n_checkpoints == 3
    assert context.has_checkpoint(0) is True
    assert context.has_checkpoint(1) is False
    assert context.has_checkpoint(2) is True
