import asyncio
import json
from typing import Any

import httpx
import pytest

from kosong.chat_provider import APIConnectionError, openai_common
from kosong.contrib.chat_provider.openai_legacy import OpenAILegacy
from kosong.contrib.chat_provider.openai_responses import OpenAIResponses
from kosong.message import Message, ToolCall


def test_create_openai_client_does_not_inject_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(openai_common, "AsyncOpenAI", FakeAsyncOpenAI)

    openai_common.create_openai_client(
        api_key="test-key",
        base_url="https://example.com/v1",
        client_kwargs={"timeout": 3},
    )

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.com/v1"
    assert captured["timeout"] == 3
    assert "max_retries" not in captured


@pytest.mark.asyncio
async def test_retry_recovery_does_not_close_shared_http_client() -> None:
    http_client = httpx.AsyncClient()
    provider = OpenAILegacy(
        model="gpt-4.1",
        api_key="test-key",
        http_client=http_client,
    )

    provider.on_retryable_error(APIConnectionError("Connection error."))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert provider.client._client is http_client  # pyright: ignore[reportPrivateUsage]
    assert http_client.is_closed is False
    await http_client.aclose()


def test_openai_legacy_normalizes_malformed_tool_call_arguments() -> None:
    provider = OpenAILegacy(model="gpt-4.1", api_key="test-key", stream=False)
    message = Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(
                id="call_1",
                function=ToolCall.FunctionBody(
                    name="shell",
                    arguments='{"command":"curl -k ... 2>&1"{}}',
                ),
            )
        ],
    )

    converted = provider._convert_message(message)
    tool_calls = converted["tool_calls"]
    assert isinstance(tool_calls, list)
    args = tool_calls[0]["function"]["arguments"]
    assert json.loads(args) == {"command": "curl -k ... 2>&1"}


def test_openai_responses_normalizes_malformed_tool_call_arguments() -> None:
    provider = OpenAIResponses(model="gpt-4.1", api_key="test-key", stream=False)
    message = Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(
                id="call_1",
                function=ToolCall.FunctionBody(
                    name="shell",
                    arguments='{"command":"curl -k ... 2>&1"{}}',
                ),
            )
        ],
    )

    converted = provider._convert_message(message)
    function_call = next(item for item in converted if item["type"] == "function_call")
    assert json.loads(function_call["arguments"]) == {"command": "curl -k ... 2>&1"}
