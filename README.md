# Kimi Code CLI

[![Version](https://img.shields.io/pypi/v/kimi-cli)](https://pypi.org/project/kimi-cli/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/lihan0705/kimi-cli-plus)

[Documentation](https://lihan0705.github.io/kimi-cli-plus/en/) | [文档](https://lihan0705.github.io/kimi-cli-plus/zh/)

Kimi Code CLI is an AI agent that runs in the terminal, helping you complete software development tasks and terminal operations. It can read and edit code, execute shell commands, and autonomously plan actions.

## Key Features

- **Shell Mode**: Toggle with `Ctrl-X` to run terminal commands directly.
  ![Shell Mode](./docs/media/shell-mode.gif)
- **IDE Integration**: Supports VS Code (via extension) and ACP-compatible editors (Zed, JetBrains).
  ![VS Code Integration](./docs/media/vscode.png)
- **MCP Support**: Full support for Model Context Protocol tools and servers.
- **Web UI**: Built-in local web interface for a rich interaction experience.

## Installation

### Prerequisites

- **Python 3.12+**
- **uv**: Python package manager. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 22+**: Required for the Web UI.

#### Installing Node.js 22+
We recommend using a version manager like `nvm` or `fnm`:

**Using nvm (Linux/macOS):**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
# Restart terminal, then:
nvm install 22
nvm use 22
```

**Using fnm (Fast Node Manager):**
```bash
curl -fsSL https://fnm.vercel.app/install | bash
# Restart terminal, then:
fnm install 22
```

### Build from Source

**Quick Install:**
```bash
curl -LsSf https://raw.githubusercontent.com/lihan0705/kimi-cli-plus/main/scripts/install.sh | bash
```

**Manual Setup:**
1. **Clone & Setup**:
   ```bash
   git clone https://github.com/lihan0705/kimi-cli-plus.git
   cd kimi-cli-plus
   ```

2. **One-click Install**:
   ```bash
   ./scripts/install.sh
   ```

## Usage

Run `kimi` to start. Use `/login` to configure your API provider:
1. Select **"OpenAI Legacy (Custom URL)"** for custom endpoints.
2. Enter your **API Base URL** and **API Key**.
![Setup Custom API](./docs/media/setlocalapi_1.png)

## Latest Improvements (2026-03-09)

- ✅ **Enhanced `/context` UI**: Switched to plain text for better TUI compatibility and fixed the `Task` tool attribute error.
- ✅ **Optimized vLLM Support**: Added `max_model_len` field support to correctly identify models (e.g., Qwen) from vLLM endpoints.
- ✅ **Fixed `edit` Tool**: Resolved Pydantic validation ambiguity by enforcing `list[Edit]` for more robust tool calls.
- ✅ **Web UI Security**: Reduced dependencies vulnerabilities and updated build tools.
- ✅ **Refined Documentation**: Simplified README with Node.js 22+ (nvm/fnm) instructions and a quick install command.

## Development

```sh
uv run kimi        # Run locally
make check         # Linting & Type checking
make test          # Run tests
make build-web     # Build Web UI
```
