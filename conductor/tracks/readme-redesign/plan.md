# Kimi Code CLI

<p align="center">
  <strong>An autonomous AI engineer in your terminal.</strong><br>
  Built for developers who value speed, precision, and a clean, monochrome aesthetic.
</p>

<p align="center">
  <a href="https://pypi.org/project/kimi-cli/"><img src="https://img.shields.io/pypi/v/kimi-cli?color=000000&labelColor=333333" alt="Version"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/en/"><img src="https://img.shields.io/badge/Docs-English-000000?labelColor=333333" alt="Docs EN"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/zh/"><img src="https://img.shields.io/badge/文档-中文-000000?labelColor=333333" alt="Docs ZH"></a>
</p>

---

Kimi Code CLI is a high-performance AI agent that seamlessly integrates with your terminal and development environment. It plans autonomously, executes shell commands, and handles complex code editing tasks with ease.

## Key Capabilities

### ⚡ Interactive Terminal
Toggle **Shell Mode** with `Ctrl-X` to execute system commands directly without leaving the agent.
<p align="center">
  <img src="./docs/media/shell-mode.gif" width="800" alt="Shell Mode">
</p>

### 🌐 Rich Web Interface
Manage sessions and configuration through a clean, modern local web UI.
<p align="center">
  <img src="./docs/media/webmodelselect.png" width="800" alt="Web UI">
</p>

### 🛠 Flexible Provider Management
Easily manage multiple OpenAI-compatible API endpoints with custom names and configurations.
<p align="center">
  <img src="./docs/media/simpleurlmanage.png" width="800" alt="URL Management">
</p>

### 🔌 IDE & Protocol Support
Deep integration with **VS Code**, **Zed**, **JetBrains**, and full **Model Context Protocol (MCP)** support.
<p align="center">
  <img src="./docs/media/vscode.png" width="800" alt="VS Code Integration">
</p>

---

## Quick Start

### 1. Installation

Install via the one-click script:
```bash
curl -LsSf https://raw.githubusercontent.com/lihan0705/kimi-cli-plus/main/scripts/install.sh | bash
```

*Requires Python 3.12+ and Node.js 22+ (for Web UI).*

### 2. Configuration

Run `kimi` and use `/login` to set up your primary model. For custom OpenAI-compatible providers:
1. Choose **"OpenAI Legacy (Custom URL)"**.
2. Define a **Configuration Name** (e.g., "deepseek").
3. Provide your **API Base URL** and **API Key**.

### 3. Usage

```bash
kimi                # Start interactive session
kimi --web          # Launch with Web UI
kimi --model gpt-4  # Force specific model
```

---

## Development

```bash
uv run kimi         # Local run
make check          # Quality check (lint/types)
make test           # Run suite
make build-web      # Rebuild Web UI
```

<p align="center">
  <a href="https://github.com/lihan0705/kimi-cli-plus/issues/new/choose">Report Bug</a> •
  <a href="https://github.com/lihan0705/kimi-cli-plus/blob/main/CONTRIBUTING.md">Contributing</a>
</p>
