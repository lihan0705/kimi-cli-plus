"""Integration tests for OpenAI Legacy multi-URL support."""

import tempfile
from pathlib import Path

from pydantic import SecretStr

from kimi_cli.auth.platforms import (
    list_openai_legacy_providers,
    make_openai_legacy_provider_key,
    parse_openai_legacy_name,
)
from kimi_cli.config import Config, LLMModel, LLMProvider


def test_parse_openai_legacy_name():
    """Test parsing OpenAI Legacy provider names."""
    assert parse_openai_legacy_name("managed:openai-legacy:my-openai") == "my-openai"
    assert parse_openai_legacy_name("managed:openai-legacy:deepseek") == "deepseek"
    assert parse_openai_legacy_name("managed:kimi-code") is None
    assert parse_openai_legacy_name("managed:openai-legacy:") is None
    assert parse_openai_legacy_name("other:provider") is None


def test_make_openai_legacy_provider_key():
    """Test creating OpenAI Legacy provider keys."""
    assert make_openai_legacy_provider_key("my-openai") == "managed:openai-legacy:my-openai"
    assert make_openai_legacy_provider_key("deepseek") == "managed:openai-legacy:deepseek"


def test_list_openai_legacy_providers():
    """Test listing OpenAI Legacy providers from config."""
    config = Config()

    # Add some test providers
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

    providers = list_openai_legacy_providers(config)

    assert len(providers) == 2
    names = [name for name, _ in providers]
    assert "my-openai" in names
    assert "deepseek" in names

    # Check provider configurations
    for name, provider in providers:
        if name == "my-openai":
            assert provider.base_url == "https://api.openai.com/v1"
        elif name == "deepseek":
            assert provider.base_url == "https://api.deepseek.com/v1"


def test_full_integration_flow(tmp_path: Path):
    """Test full integration flow with temporary config."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_file = tmp_path / "config.toml"

        # Create initial config
        config = Config()
        config.source_file = config_file

        # Simulate adding an OpenAI Legacy provider
        name = "test-openai"
        provider_key = make_openai_legacy_provider_key(name)
        base_url = "https://api.test-openai.com/v1"
        api_key = "sk-test123"

        config.providers[provider_key] = LLMProvider(
            type="openai_legacy",
            base_url=base_url,
            api_key=SecretStr(api_key),
        )

        # Add some models
        model_key = "openai-legacy/test-model"
        config.models[model_key] = LLMModel(
            provider=provider_key,
            model="test-model",
            max_context_size=128000,
        )

        # Save and reload
        from kimi_cli.config import save_config

        save_config(config, config_file)

        # Load and verify
        from kimi_cli.config import load_config

        loaded_config = load_config(config_file)

        assert provider_key in loaded_config.providers
        assert loaded_config.providers[provider_key].base_url == base_url
        assert make_openai_legacy_provider_key("test-openai") in loaded_config.providers

        # Test listing
        providers = list_openai_legacy_providers(loaded_config)
        assert len(providers) == 1
        assert providers[0][0] == "test-openai"
        assert providers[0][1].base_url == base_url
