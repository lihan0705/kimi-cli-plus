# Multi OpenAI Legacy URL Support

**Date:** 2026-03-17
**Issue:** https://github.com/lihan0705/kimi-cli-plus/issues/7
**Status:** Design Approved

## Problem Statement

When using `/login` to configure OpenAI Legacy (Custom URL), users can only configure one URL at a time. If they run `/login` again with a different URL, the previous configuration gets overwritten. Users need to manage multiple OpenAI-compatible API endpoints (e.g., OpenAI, DeepSeek, local LLM servers) and switch between them easily.

## Goals

1. Support configuring multiple OpenAI Legacy URLs with custom names
2. Allow users to view, add, edit, and delete URL configurations
3. Display URL names in model selection UI to distinguish between different endpoints

## Non-Goals

- Automatic URL discovery or synchronization
- URL health checking
- Migrating existing single-URL configurations (will continue to work)

## Design

### 1. Configuration Structure

**Current issue:** Provider key is fixed as `managed:openai-legacy`, causing overwrites.

**Solution:** Include user-defined name in provider key:

```toml
# Before (single URL)
[providers."managed:openai-legacy"]
type = "openai_legacy"
base_url = "https://api.openai.com/v1"
api_key = "sk-xxx"

# After (multiple URLs)
[providers."managed:openai-legacy:my-openai"]
type = "openai_legacy"
base_url = "https://api.openai.com/v1"
api_key = "sk-xxx"

[providers."managed:openai-legacy:deepseek"]
type = "openai_legacy"
base_url = "https://api.deepseek.com/v1"
api_key = "sk-yyy"
```

**Provider key format:** `managed:openai-legacy:<user-name>`

**Model key format:** `managed:openai-legacy:<user-name>:<model-id>`

### 2. Login Flow

When user selects "OpenAI Legacy (Custom URL)" from `/login`:

```
┌─────────────────────────────────────────┐
│ OpenAI Legacy URL Management            │
│                                         │
│ Existing configurations:                │
│   1. my-openai (https://api.openai...)  │
│   2. deepseek (https://api.deepseek...) │
│                                         │
│ Actions:                                │
│   3. Add new URL                        │
│   4. Delete existing URL                │
└─────────────────────────────────────────┘
```

**Add new URL flow:**
1. Enter configuration name (e.g., "my-openai")
2. Enter base URL (e.g., "https://api.openai.com/v1")
3. Enter API key
4. Fetch available models from API
5. Select default model
6. Save configuration

**Delete URL flow:**
1. Select URL from list
2. Confirm deletion
3. Remove provider and all associated models from config

### 3. Model Selection UI

**Current display:** `gpt-4 (OpenAI Legacy)`

**New display:** `gpt-4 (my-openai)` where `my-openai` is the user-defined name

```
Select a model:
  gpt-4o (my-openai)
  gpt-4-turbo (my-openai)
  deepseek-chat (deepseek)
  deepseek-coder (deepseek)
  kimi-for-coding (kimi-code)
```

### 4. Implementation Details

#### File Changes

| File | Changes |
|------|---------|
| `src/kimi_cli/ui/shell/setup.py` | Add `_manage_openai_legacy_urls()`, modify `_setup_platform()` |
| `src/kimi_cli/ui/shell/slash.py` | Update model display format in `model` command |
| `src/kimi_cli/auth/platforms.py` | Add helper functions for listing/managing OpenAI Legacy providers |
| `tests/ui/shell/test_setup.py` | New test file for URL management |

#### Key Functions

```python
# In platforms.py
def list_openai_legacy_providers(config: Config) -> list[tuple[str, LLMProvider]]:
    """Return list of (name, provider) for all openai-legacy providers."""

def parse_openai_legacy_name(provider_key: str) -> str | None:
    """Extract user name from 'managed:openai-legacy:<name>'."""

# In setup.py
async def _manage_openai_legacy_urls(config: Config) -> _SetupResult | None:
    """Show URL list and handle add/delete actions."""

async def _add_openai_legacy_url() -> _SetupResult | None:
    """Prompt for new URL configuration."""

async def _delete_openai_legacy_url(config: Config) -> bool:
    """Delete selected URL configuration."""
```

### 5. Testing Strategy

```python
# tests/ui/shell/test_setup.py

async def test_add_first_openai_legacy_url():
    """First URL creates new provider with name."""

async def test_add_second_openai_legacy_url():
    """Second URL creates separate provider, first is preserved."""

async def test_delete_openai_legacy_url():
    """Delete removes provider and all associated models."""

async def test_model_selection_displays_url_name():
    """Model list shows URL name instead of generic 'OpenAI Legacy'."""

async def test_backwards_compatibility():
    """Existing 'managed:openai-legacy' configs continue to work."""
```

## Migration

No migration needed. Existing configurations using `managed:openai-legacy` key format will continue to work. When user adds a new URL, it will use the new `managed:openai-legacy:<name>` format.

## Open Questions

None - design approved by user.

## References

- GitHub Issue: https://github.com/lihan0705/kimi-cli-plus/issues/7
- Current implementation: `src/kimi_cli/ui/shell/setup.py`
