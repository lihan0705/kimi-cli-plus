from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts.choice_input import ChoiceInput
from pydantic import SecretStr

from kimi_cli.auth.platforms import (
    PLATFORMS,
    ModelInfo,
    Platform,
    get_platform_by_name,
    list_models,
    managed_model_key,
    managed_provider_key,
    parse_openai_legacy_name,
    make_openai_legacy_provider_key,
    list_openai_legacy_providers,
)
from kimi_cli.config import (
    LLMModel,
    LLMProvider,
    MoonshotFetchConfig,
    MoonshotSearchConfig,
    load_config,
    save_config,
)
from kimi_cli.ui.shell.console import console
from kimi_cli.ui.shell.slash import registry

if TYPE_CHECKING:
    from kimi_cli.ui.shell import Shell


async def select_platform() -> Platform | None:
    platform_name = await _prompt_choice(
        header="Select a platform (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=[platform.name for platform in PLATFORMS],
    )
    if not platform_name:
        console.print("[red]No platform selected[/red]")
        return None

    platform = get_platform_by_name(platform_name)
    if platform is None:
        console.print("[red]Unknown platform[/red]")
        return None
    return platform


async def setup_platform(platform: Platform) -> bool:
    # Check if this is the OpenAI Legacy platform that needs multi-URL management
    if platform.id == "openai-legacy" and not platform.base_url:
        return await setup_openai_legacy()
    
    result = await _setup_platform(platform)
    if not result:
        # error message already printed
        return False

    _apply_setup_result(result)
    console.print("[green]✓[/green] Kimi Code CLI has been setup! Reloading...")
    return True


class _SetupResult(NamedTuple):
    platform: Platform
    api_key: SecretStr
    selected_model: ModelInfo
    models: list[ModelInfo]
    thinking: bool


async def _setup_platform(platform: Platform) -> _SetupResult | None:
    # prompt for URL if needed
    if not platform.base_url:
        base_url = await _prompt_text("Enter the API base URL (e.g., https://api.openai.com/v1)")
        if not base_url:
            return None
        platform = platform._replace(base_url=base_url)

    # enter the API key
    api_key = await _prompt_text("Enter your API key", is_password=True)
    if not api_key:
        return None

    # list models
    try:
        models = await list_models(platform, api_key)
    except Exception as e:
        logger.error("Failed to get models: {error}", error=e)
        console.print(f"[red]Failed to get models: {e}[/red]")
        return None

    # select the model
    if not models:
        console.print("[red]No models available for the selected platform[/red]")
        return None

    model_map = {model.id: model for model in models}
    model_id = await _prompt_choice(
        header="Select a model (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=list(model_map),
    )
    if not model_id:
        console.print("[red]No model selected[/red]")
        return None

    selected_model = model_map[model_id]

    # Determine thinking mode based on model capabilities
    capabilities = selected_model.capabilities
    thinking: bool

    if "always_thinking" in capabilities:
        thinking = True
    elif "thinking" in capabilities:
        thinking_selection = await _prompt_choice(
            header="Enable thinking mode? (↑↓ navigate, Enter select, Ctrl+C cancel):",
            choices=["off", "on"],
        )
        if not thinking_selection:
            return None
        thinking = thinking_selection == "on"
    else:
        thinking = False

    return _SetupResult(
        platform=platform,
        api_key=SecretStr(api_key),
        selected_model=selected_model,
        models=models,
        thinking=thinking,
    )


def _apply_setup_result(result: _SetupResult) -> None:
    config = load_config()
    provider_key = managed_provider_key(result.platform.id)
    model_key = managed_model_key(result.platform.id, result.selected_model.id)
    config.providers[provider_key] = LLMProvider(
        type=result.platform.provider_type,  # type: ignore
        base_url=result.platform.base_url,
        api_key=result.api_key,
    )
    for key, model in list(config.models.items()):
        if model.provider == provider_key:
            del config.models[key]
    for model_info in result.models:
        capabilities = model_info.capabilities or None
        max_context_size = model_info.context_length if model_info.context_length > 0 else 128000
        config.models[managed_model_key(result.platform.id, model_info.id)] = LLMModel(
            provider=provider_key,
            model=model_info.id,
            max_context_size=max_context_size,
            capabilities=capabilities,
        )
    config.default_model = model_key
    config.default_thinking = result.thinking

    if result.platform.search_url:
        config.services.moonshot_search = MoonshotSearchConfig(
            base_url=result.platform.search_url,
            api_key=result.api_key,
        )

    if result.platform.fetch_url:
        config.services.moonshot_fetch = MoonshotFetchConfig(
            base_url=result.platform.fetch_url,
            api_key=result.api_key,
        )

    save_config(config)


async def _prompt_choice(*, header: str, choices: list[str]) -> str | None:
    if not choices:
        return None

    try:
        return await ChoiceInput(
            message=header,
            options=[(choice, choice) for choice in choices],
            default=choices[0],
        ).prompt_async()
    except (EOFError, KeyboardInterrupt):
        return None


async def _prompt_text(prompt: str, *, is_password: bool = False) -> str | None:
    session = PromptSession[str]()
    try:
        return str(
            await session.prompt_async(
                f" {prompt}: ",
                is_password=is_password,
            )
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return None


async def setup_openai_legacy() -> bool:
    """Setup multiple OpenAI Legacy URLs with custom names."""
    console.print("[bold]OpenAI Legacy URL Management[/bold]")
    console.print("Choose an action:")
    
    action = await _prompt_choice(
        header="Action (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=["Add new URL", "Edit existing URL", "Delete URL", "List all URLs", "Back to platform selection"]
    )
    
    if not action or action == "Back to platform selection":
        return False
        
    elif action == "Add new URL":
        return await _add_openai_legacy_url()
    elif action == "Edit existing URL":
        return await _edit_openai_legacy_url()
    elif action == "Delete URL":
        return await _delete_openai_legacy_url()
    elif action == "List all URLs":
        await _list_openai_legacy_urls()
        return False
    
    return False


async def _add_openai_legacy_url() -> bool:
    """Add a new OpenAI Legacy URL with custom name."""
    name = await _prompt_text("Enter a custom name for this OpenAI Legacy URL (e.g., 'my-openai', 'deepseek')")
    if not name:
        return False
        
    # Validate name format
    if " " in name or ":" in name or "/" in name:
        console.print("[red]Name cannot contain spaces, colons, or slashes[/red]")
        return False
        
    base_url = await _prompt_text("Enter the API base URL (e.g., https://api.openai.com/v1)")
    if not base_url:
        return False
        
    api_key = await _prompt_text("Enter your API key", is_password=True)
    if not api_key:
        return False
        
    # Setup the platform with the custom name
    platform = Platform(
        id="openai-legacy",
        name=f"OpenAI Legacy ({name})",
        base_url=base_url,
        provider_type="openai_legacy",
    )
    
    try:
        models = await list_models(platform, api_key)
    except Exception as e:
        logger.error("Failed to get models: {error}", error=e)
        console.print(f"[red]Failed to get models: {e}[/red]")
        return False
        
    if not models:
        console.print("[red]No models available for this URL[/red]")
        return False
        
    model_map = {model.id: model for model in models}
    model_id = await _prompt_choice(
        header="Select a default model (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=list(model_map),
    )
    if not model_id:
        return False
        
    selected_model = model_map[model_id]
    
    # Save configuration
    config = load_config()
    provider_key = make_openai_legacy_provider_key(name)
    model_key = managed_model_key("openai-legacy", selected_model.id)
    
    config.providers[provider_key] = LLMProvider(
        type="openai_legacy",
        base_url=base_url,
        api_key=SecretStr(api_key),
    )
    
    # Add all models
    for model_info in models:
        capabilities = model_info.capabilities or None
        max_context_size = model_info.context_length if model_info.context_length > 0 else 128000
        config.models[managed_model_key("openai-legacy", model_info.id)] = LLMModel(
            provider=provider_key,
            model=model_info.id,
            max_context_size=max_context_size,
            capabilities=capabilities,
        )
    
    if not config.default_model:
        config.default_model = model_key
        
    save_config(config)
    console.print(f"[green]✓[/green] Added OpenAI Legacy URL '{name}' with {len(models)} models")
    return True


async def _list_openai_legacy_urls() -> None:
    """List all configured OpenAI Legacy URLs."""
    config = load_config()
    providers = list_openai_legacy_providers(config)
    
    if not providers:
        console.print("[yellow]No OpenAI Legacy URLs configured[/yellow]")
        return
        
    console.print(f"\n[bold]Configured OpenAI Legacy URLs ({len(providers)})[/bold]")
    for name, provider in providers:
        console.print(f"  • [cyan]{name}[/cyan]: {provider.base_url}")
        model_count = sum(1 for m in config.models.values() if m.provider == make_openai_legacy_provider_key(name))
        console.print(f"    Models: {model_count}")


async def _edit_openai_legacy_url() -> bool:
    """Edit an existing OpenAI Legacy URL."""
    config = load_config()
    providers = list_openai_legacy_providers(config)
    
    if not providers:
        console.print("[yellow]No OpenAI Legacy URLs configured to edit[/yellow]")
        return False
        
    choices = [name for name, _ in providers]
    choices.append("Cancel")
    
    name = await _prompt_choice(
        header="Select URL to edit (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=choices
    )
    
    if not name or name == "Cancel":
        return False
        
    # For now, we'll just show a message that editing requires deletion and re-addition
    console.print("[yellow]Editing requires deleting and re-adding the URL[/yellow]")
    console.print("Use 'Delete URL' then 'Add new URL' to change settings")
    return False


async def _delete_openai_legacy_url() -> bool:
    """Delete an OpenAI Legacy URL."""
    config = load_config()
    providers = list_openai_legacy_providers(config)
    
    if not providers:
        console.print("[yellow]No OpenAI Legacy URLs configured to delete[/yellow]")
        return False
        
    choices = [name for name, _ in providers]
    choices.append("Cancel")
    
    name = await _prompt_choice(
        header="Select URL to delete (↑↓ navigate, Enter select, Ctrl+C cancel):",
        choices=choices
    )
    
    if not name or name == "Cancel":
        return False
        
    provider_key = make_openai_legacy_provider_key(name)
    if provider_key not in config.providers:
        console.print("[red]Provider not found[/red]")
        return False
        
    # Delete provider and all associated models
    del config.providers[provider_key]
    models_to_delete = [key for key, model in config.models.items() if model.provider == provider_key]
    for key in models_to_delete:
        del config.models[key]
        
    # If this was the default model, clear it
    if config.default_model in models_to_delete:
        config.default_model = next(iter(config.models.keys()), "")
        
    save_config(config)
    console.print(f"[green]✓[/green] Deleted OpenAI Legacy URL '{name}' and {len(models_to_delete)} models")
    return True


@registry.command
def reload(app: Shell, args: str):
    """Reload configuration"""
    from kimi_cli.cli import Reload

    raise Reload
