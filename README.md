# Kimi Code Plus 🚀

<p align="center">
  <strong>The enhanced, multi-provider powered evolution of Kimi Code CLI.</strong><br>
  Built for developers who need maximum flexibility with a clean, monochrome aesthetic.
</p>

<p align="center">
  <a href="https://pypi.org/project/kimi-cli/"><img src="https://img.shields.io/pypi/v/kimi-cli?color=000000&labelColor=333333" alt="Version"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/en/"><img src="https://img.shields.io/badge/Docs-English-000000?labelColor=333333" alt="Docs EN"></a>
  <a href="https://lihan0705.github.io/kimi-cli-plus/zh/"><img src="https://img.shields.io/badge/文档-中文-000000?labelColor=333333" alt="Docs ZH"></a>
</p>

---

## ✨ The "Plus" Advantage

This version extends the original Kimi Code CLI with critical features for professional workflows:

### 🛠️ Multi-OpenAI Legacy Support
Stop overwriting your config. Manage multiple OpenAI-compatible endpoints (DeepSeek, GLM, Local LLMs) simultaneously with custom names.
- **CLI Power**: [Switch models globally](./docs/media/allURLmodel.png) with clear provider attribution.
- **Web Dashboard**: A dedicated [Management UI](./docs/media/simpleurlmanage.png) to add/delete endpoints on the fly.

### 🌐 Next-Gen Web Interface
A completely redesigned, monochrome web experience that feels like a professional IDE tool, not just a chat window.
- **Visual Model Selector**: [Browse and search](./docs/media/webmodelselect.png) models across all your configured providers.
- **Instant Sync**: Adding a provider in the web UI automatically refreshes and populates the model list.

### ⚡ Performance & Polish
- **Optimized vLLM Support**: Correct model identification for local vLLM/Ollama endpoints using `max_model_len`.
- **Surgical Code Editing**: Refined `edit` tool validation for more reliable autonomous programming.
- **Monochrome Aesthetic**: Deeply integrated shadcn/ui style for a distraction-free environment.

---

## 🚀 Capabilities

- **Shell Mode**: Toggle `Ctrl-X` to run terminal commands directly.
- **Autonomous Planning**: Let the agent handle complex multi-step engineering tasks.
- **IDE Integration**: Works seamlessly with **VS Code**, **Zed**, and **JetBrains**.
- **MCP Native**: Full support for the Model Context Protocol ecosystem.

---

## 📦 Quick Start

### Installation
```bash
curl -LsSf https://raw.githubusercontent.com/lihan0705/kimi-cli-plus/main/scripts/install.sh | bash
```
*Requires Python 3.12+ and Node.js 22+.*

### Configuration
Run `kimi` and use `/login` to set up your providers.
1. Select **"OpenAI Legacy (Custom URL)"**.
2. Name it (e.g., `deepseek`), add your URL and API Key.
3. Start coding.

---

## 🛠️ Development

```bash
uv run kimi         # Run locally
make build-web      # Build the enhanced UI
make test           # Run verification suite
```

<p align="center">
  <a href="https://github.com/lihan0705/kimi-cli-plus/issues">Report Issue</a> •
  <a href="https://github.com/lihan0705/kimi-cli-plus/blob/main/CONTRIBUTING.md">Contribute</a>
</p>
