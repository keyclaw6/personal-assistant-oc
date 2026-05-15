# OpenClaw Config Reference

Reference OpenClaw instance configuration for Albert. This is **not** the
live config — the live config lives at `~/.openclaw/openclaw.json` and is
managed via `openclaw config set`. This file documents the intended shape.

## What's Included

- **`openclaw.json`** — Reference instance config (agents, gateway, plugins)

## Setup on a New Machine

1. **Set workspace path**:
   ```bash
   openclaw config set agents.defaults.workspace "/path/to/personal-assistant-oc/albert"
   ```

2. **Regenerate auth tokens**:
   ```bash
   openclaw config set gateway.auth.token <new-token>
   openclaw config set gateway.remote.token <new-token>
   ```

3. **Set API keys**:
   - Tavily: `openclaw config set plugins.entries.tavily.config.webSearch.apiKey <key>`
   - OpenRouter: configure in `.env.cognee` (gitignored)

4. **Install plugins**:
   ```bash
   openclaw plugins install @cognee/cognee-openclaw
   openclaw cognee setup
   ```

5. **Start gateway**:
   ```bash
   openclaw gateway restart
   ```

## Agent

Single agent: **Albert**. No separate belief agent, no coder agent.

## Plugins

- **cognee-openclaw** — Memory indexing and retrieval (Cognee)
- **openclaw-messenger** — Facebook Messenger channel
- **openrouter** — LLM provider
- **tavily** — Web search

## What's NOT Included

- Plugin runtime dependencies (auto-install)
- Backup files (`.bak`, `.clobbered`, `.rejected`)
- `.env.cognee` (gitignored — contains API keys)
- `.cognee_system/` and `.cognee_data/` (gitignored — regenerable)
