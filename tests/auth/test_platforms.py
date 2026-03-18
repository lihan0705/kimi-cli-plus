"""Tests for OpenAI Legacy multi-URL helper functions."""

from kimi_cli.auth.platforms import (
    list_openai_legacy_providers,
    parse_openai_legacy_name,
    make_openai_legacy_provider_key,
)
from kimi_cli.config import Config, LLMProvider, LLMModel
from pydantic import SecretStr


def test_parse_openai_legacy_name_valid():
    """Test parsing a valid OpenAI Legacy provider key."""
    assert parse_openai_legacy_name("managed:openai-legacy:my-openai") == "my-openai"
    assert parse_openai_legacy_name("managed:openai-legacy:deepseek") == "deepseek"


def test_parse_openai_legacy_name_invalid():
    """Test parsing invalid provider keys."""
    assert parse_openai_legacy_name("managed:kimi-code") is None
    assert parse_openai_legacy_name("managed:openai-legacy") is None
    assert parse_openai_legacy_name("other:provider") is None


def test_make_openai_legacy_provider_key():
    """Test creating provider keys."""
    assert make_openai_legacy_provider_key("my-openai") == "managed:openai-legacy:my-openai"
    assert make_openai_legacy_provider_key("deepseek") == "managed:openai-legacy:deepseek"


def test_list_openai_legacy_providers_empty():
    """Test listing when no OpenAI Legacy providers exist."""
    config = Config()
    result = list_openai_legacy_providers(config)
    assert result == []


def test_list_openai_legacy_providers_multiple():
    """Test listing multiple OpenAI Legacy providers."""
    config = Config()
    config.providers["managed:openai-legacy:my-openai"] = LLMProvider(
        type="openai_legacy",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test"),
    )
    config.providers["managed:openai-legacy:deepseek"] = LLMProvider(
        type="openai_legacy",
        base_url="https://api.deepseek.com/v1",
        api_key=SecretStr("sk-test2"),
    )
    config.providers["managed:kimi-code"] = LLMProvider(
        type="kimi",
        base_url="https://api.kimi.com/v1",
        api_key=SecretStr("sk-test3"),
    )

    result = list_openai_legacy_providers(config)
    names = [name for name, _ in result]
    assert len(names) == 2
    assert "my-openai" in names
    assert "deepseek" in names


def test_get_platform_name_for_provider():
    """Test get_platform_name_for_provider with various provider keys."""
    from kimi_cli.auth.platforms import get_platform_name_for_provider

    # Standard platforms
    assert get_platform_name_for_provider("managed:kimi-code") == "Kimi Code"
    assert get_platform_name_for_provider("managed:openai-legacy") == "OpenAI Legacy (Custom URL)"

    # Named OpenAI Legacy
    assert get_platform_name_for_provider("managed:openai-legacy:my-openai") == "my-openai"
    assert get_platform_name_for_provider("managed:openai-legacy:deepseek") == "deepseek"

    # Unknown platform
    assert get_platform_name_for_provider("managed:unknown-platform") == "unknown-platform"

    # Non-managed
    assert get_platform_name_for_provider("other:provider") is None
