# Kimi Code Plus 🚀

<p align="center">
  <strong>大道至简 — Simplicity is the ultimate sophistication.</strong><br>
  A high-precision AI engineering companion built for professional autonomy.
</p>

<p align="center">
  <a href="https://pypi.org/project/kimi-cli/"><img src="https://img.shields.io/pypi/v/kimi-cli?color=000000&labelColor=333333" alt="Version"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/en/"><img src="https://img.shields.io/badge/Docs-English-000000?labelColor=333333" alt="Docs EN"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/zh/"><img src="https://img.shields.io/badge/文档-中文-000000?labelColor=333333" alt="Docs ZH"></a>
</p>

## ✨ Preview

<p align="center">
  <img src="./docs/media/shell-mode.gif" width="48%" alt="Shell Mode">
  <img src="./docs/media/vscode.png" width="48%" alt="VS Code Integration">
</p>

---

## ☯️ The "Plus" Philosophy

Kimi Code Plus enhances the developer experience through thoughtful improvements that make AI assistance more intuitive and powerful.

| Improvement Type | Description & Links |
|------------------|-------------------|
| **🔄 Multi-LLM Provider Management** | • `/login` now supports switching between OpenAI Legacy providers<br>• Add, manage multiple URLs and API keys<br>• Auto-load all models from different endpoints<br>• Enhanced Web UI for provider management<br>• 📸 [Provider Management](./docs/media/allURLmodel.png) • [Web Dashboard](./docs/media/simpleurlmanage.png) |
| **👁️ Context Observation** | • New `/context` command to inspect current conversation context<br>• Real-time monitoring of token usage and memory state<br>• Debug and optimize agent interactions |
| **🎯 Enhanced Skill System** | • Added default skillset for common development tasks<br>• Ready-to-use behaviors for planning, research, and orchestration<br>• Improved autonomous multi-file coordination |
| **🌐 Web UI Enhancements** | • Updated interface reflects new provider management features<br>• Clean, monochrome design matching code aesthetics<br>• Responsive dashboard for endpoint configuration |

**Design Philosophy**: The Less is More

---

## 📦 Quick Start

### 1. Prerequisites
- **Python 3.12+**
- **uv**: Python package manager. [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 22+**: Required for the Web UI. We recommend `nvm` or `fnm`:
  ```bash
  # Using nvm (Linux/macOS)
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  nvm install 22
  ```

### 2. Installation
```bash
curl -LsSf https://raw.githubusercontent.com/lihan0705/kimi-cli-plus/main/scripts/install.sh | bash
```

### 3. Configuration
Run `kimi` and use `/login` to name your provider (e.g., `deepseek`), add your URL, and start coding.

---

## 🛠️ Development

```bash
uv run kimi         # Run locally
make build-web      # Build the enhanced UI
make check          # Quality check
```

<p align="center">
  <a href="https://github.com/lihan0705/kimi-cli-plus/issues">Report Issue</a> •
  <a href="https://github.com/lihan0705/kimi-cli-plus/blob/main/CONTRIBUTING.md">Contribute</a>
</p>
