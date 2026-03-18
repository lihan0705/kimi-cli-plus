# Multi OpenAI Legacy URL Support (Web)

**ID:** `multi-openai-legacy-url-web`
**Status:** Completed
**Track Directory:** `conductor/tracks/multi-openai-legacy-url-web`

## Overview

Extend the web UI to support multiple OpenAI legacy URLs. This includes displaying user-defined names for OpenAI legacy providers in the model selection UI.

## Specification

1.  **Backend:**
    -   Update `get_platform_name_for_provider` in `src/kimi_cli/auth/platforms.py` to extract and return the custom name for `managed:openai-legacy:<name>` providers.
    -   Update `_build_global_config` in `src/kimi_cli/web/api/config.py` to use the friendly provider name instead of the raw provider key.

2.  **Frontend:**
    -   Ensure the model selection UI in `web/src/features/chat/global-config-controls.tsx` displays the friendly provider name correctly.

## Tasks

- [x] Update `src/kimi_cli/auth/platforms.py` <!-- id: 0 -->
- [x] Update `src/kimi_cli/web/api/config.py` <!-- id: 1 -->
- [x] Verify web UI display <!-- id: 2 -->
