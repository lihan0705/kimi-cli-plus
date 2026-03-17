from __future__ import annotations

import json
from typing import Any

from inline_snapshot import snapshot

from tests_e2e.wire_helpers import (
    collect_until_response,
    make_home_dir,
    make_work_dir,
    normalize_response,
    send_initialize,
    start_wire,
    summarize_messages,
    write_scripted_config,
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def test_initialize_handshake(tmp_path) -> None:
    config_path = write_scripted_config(tmp_path, ["text: hello"])
    work_dir = make_work_dir(tmp_path)
    home_dir = make_home_dir(tmp_path)

    wire = start_wire(
        config_path=config_path,
        config_text=None,
        work_dir=work_dir,
        home_dir=home_dir,
        yolo=True,
    )
    try:
        resp = send_initialize(wire)
        result = _as_dict(resp.get("result"))
        assert result.get("protocol_version") == "1.3"
        assert "slash_commands" in result
        assert normalize_response(resp) == snapshot(
            {
                "result": {
                    "protocol_version": "1.3",
                    "server": {"name": "Kimi Code CLI", "version": "<VERSION>"},
                    "slash_commands": [
                        {
                            "name": "init",
                            "description": "Analyze the codebase and generate an `AGENTS.md` file",
                            "aliases": [],
                        },
                        {
                            "name": "compact",
                            "description": "Compact the context (optionally with a custom focus, e.g. /compact keep db discussions)",
                            "aliases": [],
                        },
                        {"name": "clear", "description": "Clear the context", "aliases": ["reset"]},
                        {
                            "name": "yolo",
                            "description": "Toggle YOLO mode (auto-approve all actions)",
                            "aliases": [],
                        },
                        {
                            "name": "add-dir",
                            "description": "Add a directory to the workspace. Usage: /add-dir <path>. Run without args to list added dirs",
                            "aliases": [],
                        },
                        {
                            "name": "export",
                            "description": "Export current session context to a markdown file",
                            "aliases": [],
                        },
                        {
                            "name": "import",
                            "description": "Import context from a file or session ID",
                            "aliases": [],
                        },
                        {
                            "name": "context",
                            "description": "Show detailed context usage breakdown",
                            "aliases": [],
                        },
                        {
                            "name": "skill:academic-researcher",
                            "description": """\
Academic research assistant for literature reviews, paper analysis, and scholarly writing.
Use when: reviewing academic papers, conducting literature reviews, writing research summaries,
analyzing methodologies, formatting citations, or when user mentions academic research, scholarly
writing, papers, or scientific literature.
""",
                            "aliases": [],
                        }, {
    "name": "skill:algorithmic-art",
    "description": "Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields, or particle systems. Create original algorithmic art rather than copying existing artists' work to avoid copyright violations.",
    "aliases": [],
}, {
    "name": "skill:artifacts-builder",
    "description": "Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.",
    "aliases": [],
}, {
    "name": "skill:brand-guidelines",
    "description": "Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatting, or company design standards apply.",
    "aliases": [],
}, {
    "name": "skill:canvas-design",
    "description": "Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.",
    "aliases": [],
}, {
    "name": "skill:internal-comms",
    "description": "A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal communications (status reports, leadership updates, 3P updates, company newsletters, FAQs, incident reports, project updates, etc.).",
    "aliases": [],
}, {
    "name": "skill:kimi-cli-help",
    "description": "Answer Kimi Code CLI usage, configuration, and troubleshooting questions. Use when user asks about Kimi Code CLI installation, setup, configuration, slash commands, keyboard shortcuts, MCP integration, providers, environment variables, how something works internally, or any questions about Kimi Code CLI itself.",
    "aliases": [],
}, {
    "name": "skill:mcp-builder",
    "description": "Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).",
    "aliases": [],
}, {
    "name": "skill:skill-creator",
    "description": "Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations.",
    "aliases": [],
}, {
    "name": "skill:slack-gif-creator",
    "description": 'Toolkit for creating animated GIFs optimized for Slack, with validators for size constraints and composable animation primitives. This skill applies when users request animated GIFs or emoji animations for Slack from descriptions like "make me a GIF for Slack of X doing Y".',
    "aliases": [],
}, {
    "name": "skill:template-skill",
    "description": "Replace with description of the skill and when Claude should use it.",
    "aliases": [],
}, {
    "name": "skill:theme-factory",
    "description": "Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.",
    "aliases": [],
}, {
    "name": "skill:webapp-testing",
    "description": "Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.",
    "aliases": [],
}],
                    "capabilities": {"supports_question": True},
                }
            }
        )
    finally:
        wire.close()


def test_initialize_external_tool_conflict(tmp_path) -> None:
    config_path = write_scripted_config(tmp_path, ["text: hello"])
    work_dir = make_work_dir(tmp_path)
    home_dir = make_home_dir(tmp_path)
    external_tools = [
        {
            "name": "Shell",
            "description": "Conflicts with built-in",
            "parameters": {"type": "object", "properties": {}},
        }
    ]

    wire = start_wire(
        config_path=config_path,
        config_text=None,
        work_dir=work_dir,
        home_dir=home_dir,
        yolo=True,
    )
    try:
        resp = send_initialize(wire, external_tools=external_tools)
        result = _as_dict(resp.get("result"))
        external_tools_result = _as_dict(result.get("external_tools"))
        rejected = external_tools_result.get("rejected")
        assert isinstance(rejected, list)
        assert any(isinstance(item, dict) and item.get("name") == "Shell" for item in rejected)
        assert normalize_response(resp) == snapshot(
            {
                "result": {
                    "protocol_version": "1.3",
                    "server": {"name": "Kimi Code CLI", "version": "<VERSION>"},
                    "slash_commands": [
                        {
                            "name": "init",
                            "description": "Analyze the codebase and generate an `AGENTS.md` file",
                            "aliases": [],
                        },
                        {
                            "name": "compact",
                            "description": "Compact the context (optionally with a custom focus, e.g. /compact keep db discussions)",
                            "aliases": [],
                        },
                        {"name": "clear", "description": "Clear the context", "aliases": ["reset"]},
                        {
                            "name": "yolo",
                            "description": "Toggle YOLO mode (auto-approve all actions)",
                            "aliases": [],
                        },
                        {
                            "name": "add-dir",
                            "description": "Add a directory to the workspace. Usage: /add-dir <path>. Run without args to list added dirs",
                            "aliases": [],
                        },
                        {
                            "name": "export",
                            "description": "Export current session context to a markdown file",
                            "aliases": [],
                        },
                        {
                            "name": "import",
                            "description": "Import context from a file or session ID",
                            "aliases": [],
                        },
                        {
                            "name": "context",
                            "description": "Show detailed context usage breakdown",
                            "aliases": [],
                        },
                        {
                            "name": "skill:academic-researcher",
                            "description": """\
Academic research assistant for literature reviews, paper analysis, and scholarly writing.
Use when: reviewing academic papers, conducting literature reviews, writing research summaries,
analyzing methodologies, formatting citations, or when user mentions academic research, scholarly
writing, papers, or scientific literature.
""",
                            "aliases": [],
                        }, {
    "name": "skill:algorithmic-art",
    "description": "Creating algorithmic art using p5.js with seeded randomness and interactive parameter exploration. Use this when users request creating art using code, generative art, algorithmic art, flow fields, or particle systems. Create original algorithmic art rather than copying existing artists' work to avoid copyright violations.",
    "aliases": [],
}, {
    "name": "skill:artifacts-builder",
    "description": "Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.",
    "aliases": [],
}, {
    "name": "skill:brand-guidelines",
    "description": "Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidelines, visual formatting, or company design standards apply.",
    "aliases": [],
}, {
    "name": "skill:canvas-design",
    "description": "Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.",
    "aliases": [],
}, {
    "name": "skill:internal-comms",
    "description": "A set of resources to help me write all kinds of internal communications, using the formats that my company likes to use. Claude should use this skill whenever asked to write some sort of internal communications (status reports, leadership updates, 3P updates, company newsletters, FAQs, incident reports, project updates, etc.).",
    "aliases": [],
}, {
    "name": "skill:kimi-cli-help",
    "description": "Answer Kimi Code CLI usage, configuration, and troubleshooting questions. Use when user asks about Kimi Code CLI installation, setup, configuration, slash commands, keyboard shortcuts, MCP integration, providers, environment variables, how something works internally, or any questions about Kimi Code CLI itself.",
    "aliases": [],
}, {
    "name": "skill:mcp-builder",
    "description": "Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).",
    "aliases": [],
}, {
    "name": "skill:skill-creator",
    "description": "Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations.",
    "aliases": [],
}, {
    "name": "skill:slack-gif-creator",
    "description": 'Toolkit for creating animated GIFs optimized for Slack, with validators for size constraints and composable animation primitives. This skill applies when users request animated GIFs or emoji animations for Slack from descriptions like "make me a GIF for Slack of X doing Y".',
    "aliases": [],
}, {
    "name": "skill:template-skill",
    "description": "Replace with description of the skill and when Claude should use it.",
    "aliases": [],
}, {
    "name": "skill:theme-factory",
    "description": "Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.",
    "aliases": [],
}, {
    "name": "skill:webapp-testing",
    "description": "Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.",
    "aliases": [],
}],
                    "external_tools": {
                        "accepted": [],
                        "rejected": [{"name": "Shell", "reason": "conflicts with builtin tool"}],
                    },
                    "capabilities": {"supports_question": True},
                }
            }
        )
    finally:
        wire.close()


def test_external_tool_call(tmp_path) -> None:
    tool_args = json.dumps({"path": "README.md"})
    tool_call = json.dumps({"id": "tc-1", "name": "ext_tool", "arguments": tool_args})
    scripts = [
        "\n".join(
            [
                "text: calling external tool",
                f"tool_call: {tool_call}",
            ]
        ),
        "text: done",
    ]
    config_path = write_scripted_config(tmp_path, scripts)
    work_dir = make_work_dir(tmp_path)
    home_dir = make_home_dir(tmp_path)
    external_tools = [
        {
            "name": "ext_tool",
            "description": "External tool",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]

    wire = start_wire(
        config_path=config_path,
        config_text=None,
        work_dir=work_dir,
        home_dir=home_dir,
        yolo=True,
    )
    try:
        send_initialize(wire, external_tools=external_tools)
        wire.send_json(
            {
                "jsonrpc": "2.0",
                "id": "prompt-1",
                "method": "prompt",
                "params": {"user_input": "run external tool"},
            }
        )

        def handle_request(msg: dict[str, Any]) -> dict[str, Any]:
            params = msg.get("params")
            payload = params.get("payload") if isinstance(params, dict) else None
            tool_call_id = payload.get("id") if isinstance(payload, dict) else None
            assert isinstance(tool_call_id, str)
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {
                    "tool_call_id": tool_call_id,
                    "return_value": {
                        "is_error": False,
                        "output": "Opened",
                        "message": "Opened README.md",
                        "display": [],
                    },
                },
            }

        resp, messages = collect_until_response(wire, "prompt-1", request_handler=handle_request)
        assert resp.get("result", {}).get("status") == "finished"
        assert summarize_messages(messages) == snapshot(
            [
                {
                    "method": "event",
                    "type": "TurnBegin",
                    "payload": {"user_input": "run external tool"},
                },
                {"method": "event", "type": "StepBegin", "payload": {"n": 1}},
                {
                    "method": "event",
                    "type": "ContentPart",
                    "payload": {"type": "text", "text": "calling external tool"},
                },
                {
                    "method": "event",
                    "type": "ToolCall",
                    "payload": {
                        "type": "function",
                        "id": "tc-1",
                        "function": {"name": "ext_tool", "arguments": '{"path": "README.md"}'},
                        "extras": None,
                    },
                },
                {
                    "method": "event",
                    "type": "StatusUpdate",
                    "payload": {
                        "context_usage": None,
                        "context_tokens": None,
                        "max_context_tokens": None,
                        "token_usage": None,
                        "message_id": None,
                    },
                },
                {
                    "method": "request",
                    "type": "ToolCallRequest",
                    "payload": {
                        "id": "tc-1",
                        "name": "ext_tool",
                        "arguments": '{"path": "README.md"}',
                    },
                },
                {
                    "method": "event",
                    "type": "ToolResult",
                    "payload": {
                        "tool_call_id": "tc-1",
                        "return_value": {
                            "is_error": False,
                            "output": "Opened",
                            "message": "Opened README.md",
                            "display": [],
                            "extras": None,
                        },
                    },
                },
                {"method": "event", "type": "StepBegin", "payload": {"n": 2}},
                {
                    "method": "event",
                    "type": "ContentPart",
                    "payload": {"type": "text", "text": "done"},
                },
                {
                    "method": "event",
                    "type": "StatusUpdate",
                    "payload": {
                        "context_usage": None,
                        "context_tokens": None,
                        "max_context_tokens": None,
                        "token_usage": None,
                        "message_id": None,
                    },
                },
                {"method": "event", "type": "TurnEnd", "payload": {}},
            ]
        )
    finally:
        wire.close()


def test_prompt_without_initialize(tmp_path) -> None:
    config_path = write_scripted_config(tmp_path, ["text: hello without init"])
    work_dir = make_work_dir(tmp_path)
    home_dir = make_home_dir(tmp_path)

    wire = start_wire(
        config_path=config_path,
        config_text=None,
        work_dir=work_dir,
        home_dir=home_dir,
        yolo=True,
    )
    try:
        wire.send_json(
            {
                "jsonrpc": "2.0",
                "id": "prompt-1",
                "method": "prompt",
                "params": {"user_input": "hi"},
            }
        )
        resp, messages = collect_until_response(wire, "prompt-1")
        assert resp.get("result", {}).get("status") == "finished"
        assert summarize_messages(messages) == snapshot(
            [
                {"method": "event", "type": "TurnBegin", "payload": {"user_input": "hi"}},
                {"method": "event", "type": "StepBegin", "payload": {"n": 1}},
                {
                    "method": "event",
                    "type": "ContentPart",
                    "payload": {"type": "text", "text": "hello without init"},
                },
                {
                    "method": "event",
                    "type": "StatusUpdate",
                    "payload": {
                        "context_usage": None,
                        "context_tokens": None,
                        "max_context_tokens": None,
                        "token_usage": None,
                        "message_id": None,
                    },
                },
                {"method": "event", "type": "TurnEnd", "payload": {}},
            ]
        )
    finally:
        wire.close()
