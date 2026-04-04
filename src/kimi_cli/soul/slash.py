from __future__ import annotations

import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from kaos.path import KaosPath
from kosong.message import Message
from loguru import logger

import kimi_cli.prompts as prompts
from kimi_cli.soul import wire_send
from kimi_cli.soul.agent import load_agents_md
from kimi_cli.soul.context import Context
from kimi_cli.soul.message import system
from kimi_cli.utils.export import is_sensitive_file
from kimi_cli.utils.path import sanitize_cli_path, shorten_home
from kimi_cli.utils.slashcmd import SlashCommandRegistry
from kimi_cli.wire.types import StatusUpdate, TextPart

if TYPE_CHECKING:
    from kimi_cli.soul.kimisoul import KimiSoul

type SoulSlashCmdFunc = Callable[[KimiSoul, str], None | Awaitable[None]]
"""
A function that runs as a KimiSoul-level slash command.

Raises:
    Any exception that can be raised by `Soul.run`.
"""

registry = SlashCommandRegistry[SoulSlashCmdFunc]()


@registry.command
async def init(soul: KimiSoul, args: str):
    """Analyze the codebase and generate an `AGENTS.md` file"""
    from kimi_cli.soul.kimisoul import KimiSoul

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_context = Context(file_backend=Path(temp_dir) / "context.jsonl")
        tmp_soul = KimiSoul(soul.agent, context=tmp_context)
        await tmp_soul.run(prompts.INIT)

    agents_md = await load_agents_md(soul.runtime.builtin_args.KIMI_WORK_DIR)
    system_message = system(
        "The user just ran `/init` slash command. "
        "The system has analyzed the codebase and generated an `AGENTS.md` file. "
        f"Latest AGENTS.md file content:\n{agents_md}"
    )
    await soul.context.append_message(Message(role="user", content=[system_message]))


@registry.command
async def compact(soul: KimiSoul, args: str):
    """Compact the context (optionally with a custom focus, e.g. /compact keep db discussions)"""
    if soul.context.n_checkpoints == 0:
        wire_send(TextPart(text="The context is empty."))
        return

    logger.info("Running `/compact`")
    await soul.compact_context(custom_instruction=args.strip())
    wire_send(TextPart(text="The context has been compacted."))
    snap = soul.status
    wire_send(
        StatusUpdate(
            context_usage=snap.context_usage,
            context_tokens=snap.context_tokens,
            max_context_tokens=snap.max_context_tokens,
        )
    )


@registry.command(aliases=["reset"])
async def clear(soul: KimiSoul, args: str):
    """Clear the context"""
    logger.info("Running `/clear`")
    await soul.context.clear()
    wire_send(TextPart(text="The context has been cleared."))
    snap = soul.status
    wire_send(
        StatusUpdate(
            context_usage=snap.context_usage,
            context_tokens=snap.context_tokens,
            max_context_tokens=snap.max_context_tokens,
        )
    )


@registry.command
async def yolo(soul: KimiSoul, args: str):
    """Toggle YOLO mode (auto-approve all actions)"""
    if soul.runtime.approval.is_yolo():
        soul.runtime.approval.set_yolo(False)
        wire_send(TextPart(text="You only die once! Actions will require approval."))
    else:
        soul.runtime.approval.set_yolo(True)
        wire_send(TextPart(text="You only live once! All actions will be auto-approved."))


@registry.command(name="reload-skills")
async def reload_skills(soul: KimiSoul, args: str):
    """Reload all skills and plugins from their roots."""
    logger.info("Running `/reload-skills`")
    await soul.runtime.refresh_skills()
    soul.refresh_slash_commands()
    wire_send(TextPart(text=f"Reloaded {len(soul.runtime.skills)} skill(s)."))


@registry.command(name="add-dir")
async def add_dir(soul: KimiSoul, args: str):
    """Add a directory to the workspace. Usage: /add-dir <path>. Run without args to list added dirs"""  # noqa: E501
    from kaos.path import KaosPath

    from kimi_cli.utils.path import is_within_directory, list_directory

    args = sanitize_cli_path(args)
    if not args:
        if not soul.runtime.additional_dirs:
            wire_send(TextPart(text="No additional directories. Usage: /add-dir <path>"))
        else:
            lines = ["Additional directories:"]
            for d in soul.runtime.additional_dirs:
                lines.append(f"  - {d}")
            wire_send(TextPart(text="\n".join(lines)))
        return

    path = KaosPath(args).expanduser().canonical()

    if not await path.exists():
        wire_send(TextPart(text=f"Directory does not exist: {path}"))
        return
    if not await path.is_dir():
        wire_send(TextPart(text=f"Not a directory: {path}"))
        return

    # Check if already added (exact match)
    if path in soul.runtime.additional_dirs:
        wire_send(TextPart(text=f"Directory already in workspace: {path}"))
        return

    # Check if it's within the work_dir (already accessible)
    work_dir = soul.runtime.builtin_args.KIMI_WORK_DIR
    if is_within_directory(path, work_dir):
        wire_send(TextPart(text=f"Directory is already within the working directory: {path}"))
        return

    # Check if it's within an already-added additional directory (redundant)
    for existing in soul.runtime.additional_dirs:
        if is_within_directory(path, existing):
            wire_send(
                TextPart(
                    text=f"Directory is already within an added directory `{existing}`: {path}"
                )
            )
            return

    # Validate readability before committing any state changes
    try:
        ls_output = await list_directory(path)
    except OSError as e:
        wire_send(TextPart(text=f"Cannot read directory: {path} ({e})"))
        return

    # Add the directory (only after readability is confirmed)
    soul.runtime.additional_dirs.append(path)

    # Persist to session state
    soul.runtime.session.state.additional_dirs.append(str(path))
    soul.runtime.session.save_state()

    # Inject a system message to inform the LLM about the new directory
    system_message = system(
        f"The user has added an additional directory to the workspace: `{path}`\n\n"
        f"Directory listing:\n```\n{ls_output}\n```\n\n"
        "You can now read, write, search, and glob files in this directory "
        "as if it were part of the working directory."
    )
    await soul.context.append_message(Message(role="user", content=[system_message]))

    wire_send(TextPart(text=f"Added directory to workspace: {path}"))
    logger.info("Added additional directory: {path}", path=path)


@registry.command
async def export(soul: KimiSoul, args: str):
    """Export current session context to a markdown file"""
    from kimi_cli.utils.export import perform_export

    session = soul.runtime.session
    result = await perform_export(
        history=list(soul.context.history),
        session_id=session.id,
        work_dir=str(session.work_dir),
        token_count=soul.context.token_count,
        args=args,
        default_dir=Path(str(session.work_dir)),
    )
    if isinstance(result, str):
        wire_send(TextPart(text=result))
        return
    output, count = result
    display = shorten_home(KaosPath(str(output)))
    wire_send(TextPart(text=f"Exported {count} messages to {display}"))
    wire_send(
        TextPart(
            text="  Note: The exported file may contain sensitive information. "
            "Please be cautious when sharing it externally."
        )
    )


@registry.command(name="import")
async def import_context(soul: KimiSoul, args: str):
    """Import context from a file or session ID"""
    from kimi_cli.utils.export import perform_import

    target = sanitize_cli_path(args)
    if not target:
        wire_send(TextPart(text="Usage: /import <file_path or session_id>"))
        return

    session = soul.runtime.session
    raw_max_context_size = (
        soul.runtime.llm.max_context_size if soul.runtime.llm is not None else None
    )
    max_context_size = (
        raw_max_context_size
        if isinstance(raw_max_context_size, int) and raw_max_context_size > 0
        else None
    )
    result = await perform_import(
        target=target,
        current_session_id=session.id,
        work_dir=session.work_dir,
        context=soul.context,
        max_context_size=max_context_size,
    )
    if isinstance(result, str):
        wire_send(TextPart(text=result))
        return

    source_desc, content_len = result
    wire_send(TextPart(text=f"Imported context from {source_desc} ({content_len} chars)."))
    if source_desc.startswith("file") and is_sensitive_file(Path(target).name):
        wire_send(
            TextPart(
                text="Warning: This file may contain secrets (API keys, tokens, credentials). "
                "The content is now part of your session context."
            )
        )


@registry.command
async def context(soul: KimiSoul, args: str):
    """Show detailed context usage breakdown"""
    import json

    from kimi_cli.soul.toolset import MCPTool

    # 1. Gather stats
    total_tokens = soul.context.token_count
    max_tokens = soul.runtime.llm.max_context_size if soul.runtime.llm else 128000
    if max_tokens <= 0:
        max_tokens = 128000

    categories = {
        "System prompt": 0,
        "System tools": 0,
        "MCP tools": 0,
        "Messages": 0,
        "Tool use & results": 0,
    }

    # System Prompt
    categories["System prompt"] += len(str(soul.agent.system_prompt))

    # Tools
    for _tool_name, tool in soul.agent.toolset._tool_dict.items():  # type: ignore
        # Estimate tool definition size
        from typing import Any, cast

        tool_any: Any = cast(Any, tool)
        params: Any = {}
        if hasattr(tool_any, "parameters"):
            params = tool_any.parameters
        elif hasattr(tool_any, "base") and hasattr(tool_any.base, "parameters"):
            params = tool_any.base.parameters
        elif hasattr(tool_any, "params"):
            p: Any = tool_any.params
            from pydantic import BaseModel

            if isinstance(p, type) and issubclass(p, BaseModel):
                params = p.model_json_schema()
            else:
                params = cast(Any, p)

        description = getattr(tool_any, "description", "")
        try:
            params_str = json.dumps(params)
        except Exception:
            params_str = str(params)
        tool_size = len(str(description)) + len(params_str)

        if isinstance(tool, MCPTool):
            categories["MCP tools"] += tool_size
        else:
            categories["System tools"] += tool_size

    # Messages History
    for msg in soul.context.history:
        content_len = len(msg.extract_text())
        if msg.tool_calls:
            for tc in msg.tool_calls:
                content_len += len(tc.function.name) + len(tc.function.arguments or "")

        if msg.role == "system":
            categories["System prompt"] += content_len
        elif msg.role in ("user", "assistant"):
            if msg.tool_calls:
                categories["Tool use & results"] += content_len
            else:
                categories["Messages"] += content_len
        elif msg.role == "tool":
            categories["Tool use & results"] += content_len

    # Distribute total_tokens based on char counts
    total_chars = sum(categories.values())
    if total_chars > 0:
        token_breakdown = {k: int((v / total_chars) * total_tokens) for k, v in categories.items()}
    else:
        token_breakdown = {k: 0 for k in categories}

    # 2. Render UI
    lines: list[str] = []
    usage_pct = (total_tokens / max_tokens) * 100
    lines.append(f"Context Usage: {total_tokens}/{max_tokens} tokens ({usage_pct:.1f}%)")
    lines.append(f"Model: {soul.model_name}")
    lines.append("")

    for cat, tokens in token_breakdown.items():
        cat_pct = (tokens / max_tokens) * 100
        tokens_str = f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
        lines.append(f"- {cat}: {tokens_str} tokens ({cat_pct:.1f}%)")

    wire_send(TextPart(text="\n".join(lines)))
