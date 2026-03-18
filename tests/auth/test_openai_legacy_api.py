from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from kimi_cli.config import Config, LLMModel, LLMProvider
from kimi_cli.web.app import create_app


@pytest.fixture
def mock_config():
    config = Config()
    config.providers["managed:openai-legacy:test-p"] = LLMProvider(
        type="openai_legacy",
        base_url="https://api.test.com/v1",
        api_key=SecretStr("sk-test"),
    )
    config.models["openai-legacy:test-p/model-1"] = LLMModel(
        provider="managed:openai-legacy:test-p",
        model="model-1",
        max_context_size=128000,
    )
    return config


@pytest.mark.asyncio
async def test_list_openai_legacy_providers(mock_config):
    app = create_app(restrict_sensitive_apis=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("kimi_cli.web.api.config.load_config", return_value=mock_config):
            response = await ac.get("/api/config/providers/openai-legacy")

    assert response.status_code == 200
    data = response.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["name"] == "test-p"
    assert data["providers"][0]["base_url"] == "https://api.test.com/v1"
    assert data["providers"][0]["has_api_key"] is True


@pytest.mark.asyncio
async def test_add_openai_legacy_provider():
    app = create_app(restrict_sensitive_apis=False)
    config = Config()

    async def mock_refresh(cfg):
        cfg.models["openai-legacy:new-p/m1"] = LLMModel(
            provider="managed:openai-legacy:new-p",
            model="m1",
            max_context_size=128000,
        )
        return True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("kimi_cli.web.api.config.load_config", return_value=config),
            patch("kimi_cli.web.api.config.save_config") as mock_save,
            patch("kimi_cli.auth.platforms.refresh_managed_models", side_effect=mock_refresh),
        ):
            payload = {"name": "new-p", "base_url": "https://new.api.com/v1", "api_key": "sk-new"}
            response = await ac.post("/api/config/providers/openai-legacy", json=payload)

    assert response.status_code == 200
    mock_save.assert_called_once()

    # Check if provider was added
    assert "managed:openai-legacy:new-p" in config.providers
    assert config.providers["managed:openai-legacy:new-p"].base_url == "https://new.api.com/v1"

    # Check if models were "refreshed" (via mock)
    assert "openai-legacy:new-p/m1" in config.models


@pytest.mark.asyncio
async def test_delete_openai_legacy_provider(mock_config):
    app = create_app(restrict_sensitive_apis=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("kimi_cli.web.api.config.load_config", return_value=mock_config),
            patch("kimi_cli.web.api.config.save_config") as mock_save,
        ):
            response = await ac.delete("/api/config/providers/openai-legacy/test-p")

    assert response.status_code == 200
    mock_save.assert_called_once()

    assert "managed:openai-legacy:test-p" not in mock_config.providers
    assert "openai-legacy:test-p/model-1" not in mock_config.models
