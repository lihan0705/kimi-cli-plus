from __future__ import annotations

from typing import Any

import pytest

import kimi_cli.ui.shell as shell_module
from kimi_cli.ui.shell import Shell
from kimi_cli.utils.slashcmd import SlashCommand, SlashCommandCall


class _DummySoul:
    def __init__(self) -> None:
        self.available_slash_commands = [
            SlashCommand(
                name="skill:llm-wiki",
                description="llm-wiki",
                func=lambda *_args: None,
                aliases=[],
            )
        ]


@pytest.mark.asyncio
async def test_skill_llm_wiki_without_args_prompts_and_injects_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shell = Shell(_DummySoul())  # type: ignore[arg-type]

    class _FakeChoiceInput:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def prompt_async(self) -> str:
            return "audit"

    monkeypatch.setattr(shell_module, "ChoiceInput", _FakeChoiceInput)

    call = SlashCommandCall(name="skill:llm-wiki", args="", raw_input="/skill:llm-wiki")
    normalized = await shell._maybe_prompt_llm_wiki_action(call)

    assert normalized == SlashCommandCall(
        name="llm-wiki:audit",
        args="",
        raw_input="/llm-wiki:audit",
    )
