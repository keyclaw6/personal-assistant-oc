# OpenClaw Config Migration

This directory contains the cleaned OpenClaw instance configuration for migration to a new machine.

## What's Included

- **`openclaw.json`** — Main instance config (agents, gateway, plugins, auth)
- **`gateway.cmd`** — Gateway startup script template

## Before Starting on New Machine

1. **Update paths** in `openclaw.json`:
   - `agents.defaults.workspace`
   - `agents.list[1].workspace` (belief agent)
   - `agents.list[1].agentDir` (belief agent)

2. **Regenerate auth tokens**:
   - `gateway.auth.token`
   - `gateway.remote.token`
   
   Run: `openclaw config set gateway.auth.token <new-token>`

3. **Update auth profile**:
   - Replace `<YOUR_EMAIL>` in `auth.profiles` with your actual email

4. **Set API keys**:
   - `plugins.entries.tavily.config.webSearch.apiKey` — your Tavily API key

5. **Update `gateway.cmd`** paths:
   - `TMPDIR` — temp directory on new machine
   - `NODE_PATH` — path to `node.exe`
   - `OPENCLAW_INSTALL_PATH` — path to openclaw npm module

## What's NOT Included (Cleaned)

- Plugin runtime dependencies (`plugin-runtime-deps/` — will auto-install)
- Backup files (`.bak`, `.clobbered`, `.rejected`)
- Quarantine directories
- Old stability logs from failed agent tasks

## Directory Size

Cleaned from ~2.6 GB down to ~26 MB.

## Agents Configured

- **main** — Personal/Coder OC (primary workspace)
- **belief** — Belief Agent (separate workspace)

## Post-Migration

After copying this config to `~/.openclaw/` on the new machine:
1. Run `openclaw gateway` to start
2. Re-authenticate if needed: `openclaw auth login`
3. Plugins will reinstall automatically on first run
