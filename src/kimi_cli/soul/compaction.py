from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple, Protocol, runtime_checkable

import kosong
from kosong.chat_provider import TokenUsage
from kosong.message import Message
from kosong.tooling.empty import EmptyToolset

import kimi_cli.prompts as prompts
from kimi_cli.llm import LLM
from kimi_cli.soul.message import system
from kimi_cli.utils.logging import logger
from kimi_cli.wire.types import ContentPart, TextPart, ThinkPart


class CompactionResult(NamedTuple):
    messages: Sequence[Message]
    usage: TokenUsage | None
    summary: str | None = None

    @property
    def estimated_token_count(self) -> int:
        """Estimate the token count of the compacted messages."""
        if self.usage is not None and len(self.messages) > 0:
            summary_tokens = self.usage.output
            preserved_tokens = estimate_text_tokens(self.messages[1:])
            return summary_tokens + preserved_tokens

        return estimate_text_tokens(self.messages)


def estimate_text_tokens(messages: Sequence[Message]) -> int:
    """Estimate tokens from message text content using a character-based heuristic."""
    total_chars = 0
    for msg in messages:
        for part in msg.content:
            if isinstance(part, TextPart):
                total_chars += len(part.text)
    return total_chars // 4


def should_auto_compact(
    token_count: int,
    max_context_size: int,
    *,
    trigger_ratio: float,
    reserved_context_size: int,
) -> bool:
    """Determine whether auto-compaction should be triggered."""
    if max_context_size <= 0:
        return False
    return (
        token_count >= max_context_size * trigger_ratio
        or token_count + reserved_context_size >= max_context_size
    )


@runtime_checkable
class Compaction(Protocol):
    async def compact(
        self,
        messages: Sequence[Message],
        llm: LLM,
        *,
        custom_instruction: str = "",
        previous_summary: str | None = None,
    ) -> CompactionResult:
        """
        Compact a sequence of messages into a new sequence of messages.
        """
        ...


if TYPE_CHECKING:

    def type_check(simple: SimpleCompaction):
        _: Compaction = simple


class SimpleCompaction:
    """A compaction strategy that summarizes middle turns while protecting head and tail."""

    # Maximum characters for a single tool output before pruning during compaction input generation
    _PRUNE_THRESHOLD = 5000
    _PRUNED_PLACEHOLDER = "[Oversized tool output pruned during compaction to save space]"

    def __init__(self, max_preserved_messages: int = 4) -> None:
        # Increase default preserved messages to 4 for better short-term memory
        self.max_preserved_messages = max_preserved_messages

    async def compact(
        self,
        messages: Sequence[Message],
        llm: LLM,
        *,
        custom_instruction: str = "",
        previous_summary: str | None = None,
    ) -> CompactionResult:
        compact_message, to_preserve = self.prepare(
            messages, custom_instruction=custom_instruction, previous_summary=previous_summary
        )
        if compact_message is None:
            return CompactionResult(messages=to_preserve, usage=None, summary=previous_summary)

        logger.debug("Compacting context via LLM...")
        system_prompt = (
            "You are a helpful assistant that compacts conversation "
            "context into a structured summary."
        )
        result = await kosong.step(
            chat_provider=llm.chat_provider,
            system_prompt=system_prompt,
            toolset=EmptyToolset(),
            history=[compact_message],
        )
        if result.usage:
            logger.debug(
                "Compaction used {input} input tokens and {output} output tokens",
                input=result.usage.input,
                output=result.usage.output,
            )

        compacted_msg = result.message
        summary_text = compacted_msg.extract_text(" ").strip()

        content: list[ContentPart] = [
            system("Previous context has been compacted. Here is the structured summary:")
        ]
        compacted_msg = result.message

        # drop thinking parts if any
        content.extend(part for part in compacted_msg.content if not isinstance(part, ThinkPart))

        # Build initial message list
        compacted_messages: list[Message] = [Message(role="user", content=content)]
        compacted_messages.extend(to_preserve)

        # CRITICAL: Sanitize tool call/result pairs to ensure API compliance
        sanitized = self._sanitize_tool_pairs(compacted_messages)

        return CompactionResult(messages=sanitized, usage=result.usage, summary=summary_text)

    class PrepareResult(NamedTuple):
        compact_message: Message | None
        to_preserve: Sequence[Message]

    def prepare(
        self,
        messages: Sequence[Message],
        *,
        custom_instruction: str = "",
        previous_summary: str | None = None,
    ) -> PrepareResult:
        if not messages:
            return self.PrepareResult(compact_message=None, to_preserve=messages)

        history = list(messages)
        n = len(history)

        # 1. Protect head: System prompt
        head_end = 0
        if n > 0 and history[0].role == "system":
            head_end = 1

        # 2. Find tail boundary: protect last N user/assistant exchanges
        preserve_start_index = n
        n_preserved_key_turns = 0
        for index in range(n - 1, head_end - 1, -1):
            if history[index].role in {"user", "assistant"}:
                n_preserved_key_turns += 1
                if n_preserved_key_turns == self.max_preserved_messages:
                    preserve_start_index = index
                    break

        # Boundary Alignment: Walk backward to avoid splitting a tool call group
        preserve_start_index = self._align_boundary_backward(history, preserve_start_index)

        # Ensure we don't overlap with head
        preserve_start_index = max(preserve_start_index, head_end)

        to_compact = history[head_end:preserve_start_index]
        to_preserve = history[preserve_start_index:]

        if not to_compact:
            return self.PrepareResult(compact_message=None, to_preserve=history)

        # 3. Create input message for compaction with pruning
        compact_message = Message(role="user", content=[])

        # If we have a previous summary, include it as context for the update
        if previous_summary:
            summary_header = (
                "A previous compaction produced the summary below. "
                "New conversation turns have occurred since then and "
                "need to be incorporated.\n\n"
                f"PREVIOUS SUMMARY:\n{previous_summary}\n\n"
                "NEW TURNS TO INCORPORATE:\n"
            )
            compact_message.content.append(TextPart(text=summary_header))

        for i, msg in enumerate(to_compact):
            # Header for this message
            header = f"## Message {i + 1}\nRole: {msg.role}\n"
            if msg.tool_call_id:
                header += f"Tool Call ID: {msg.tool_call_id}\n"
            header += "Content:\n"
            compact_message.content.append(TextPart(text=header))

            # Pruning logic for tool results to save tokens in the compaction prompt
            if msg.role == "tool":
                content_text = msg.extract_text(" ")
                if len(content_text) > self._PRUNE_THRESHOLD:
                    pruned_text = (
                        f"{content_text[: self._PRUNE_THRESHOLD]}... {self._PRUNED_PLACEHOLDER}"
                    )
                    compact_message.content.append(TextPart(text=pruned_text))
                    continue

            # Regular content adding (excluding ThinkParts)
            compact_message.content.extend(
                part for part in msg.content if not isinstance(part, ThinkPart)
            )

            # Tool calls listing
            if msg.tool_calls:
                tc_list = "\nTool Calls generated by assistant:\n"
                for tc in msg.tool_calls:
                    tc_list += f"- {tc.function.name}({tc.function.arguments}) [ID: {tc.id}]\n"
                compact_message.content.append(TextPart(text=tc_list))

        prompt_text = "\n" + prompts.COMPACT
        if custom_instruction:
            prompt_text += (
                "\n\n**User's Custom Compaction Instruction:**\n"
                "The user has specifically requested the following focus during compaction. "
                "You MUST prioritize this instruction above the default compression priorities:\n"
                f"{custom_instruction}"
            )
        compact_message.content.append(TextPart(text=prompt_text))

        # Result: system message (if any) + compactable region summary prompt,
        # but to_preserve will be handled by caller
        return self.PrepareResult(compact_message=compact_message, to_preserve=to_preserve)

    def _align_boundary_backward(self, messages: list[Message], idx: int) -> int:
        """Move boundary backward to avoid splitting an assistant+tool group."""
        if idx <= 0 or idx >= len(messages):
            return idx

        # If current boundary starts with a tool result, we MUST move it back
        # to include its parent call. Or if the message before the boundary
        # is an assistant with tool calls, we should include it too.
        check = idx
        while check > 0 and messages[check].role == "tool":
            check -= 1

        # Now check is either 0 or points to a non-tool message
        if messages[check].role == "assistant" and messages[check].tool_calls:
            # Boundary was in the middle of a group or right after a call.
            # Pull back so the entire group stays together in the tail.
            return check

        return idx

    def _sanitize_tool_pairs(self, messages: list[Message]) -> list[Message]:
        """Remove orphaned tool results or add stubs for orphaned calls."""
        surviving_call_ids: set[str] = set()
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.id:
                        surviving_call_ids.add(tc.id)

        result_call_ids: set[str] = set()
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id:
                result_call_ids.add(msg.tool_call_id)

        # 1. Remove results that have no parent call in the current history
        orphaned_results = result_call_ids - surviving_call_ids
        if orphaned_results:
            logger.info("Compaction: removing {n} orphaned tool results", n=len(orphaned_results))
            messages = [
                m for m in messages if not (m.role == "tool" and m.tool_call_id in orphaned_results)
            ]

        # 2. Add stubs for calls that have no result in the current history
        # (This can happen if we cut after assistant but before tool)
        missing_results = surviving_call_ids - result_call_ids
        if missing_results:
            logger.info("Compaction: adding {n} stub tool results", n=len(missing_results))
            patched: list[Message] = []
            for msg in messages:
                patched.append(msg)
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.id in missing_results:
                            stub_content = [
                                system("Result from earlier conversation — see summary above.")
                            ]
                            patched.append(
                                Message(role="tool", content=stub_content, tool_call_id=tc.id)
                            )
            messages = patched

        return messages
