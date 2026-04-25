# OpenClaw Setup

## Use This Repo As Workspace

```powershell
openclaw config set agents.defaults.workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc"
openclaw gateway restart
```

## Authenticate A Model

```powershell
openclaw models auth login --provider openai
```

## Open Dashboard

```powershell
openclaw dashboard
```

## Optional Native Memory Wiki Plugin

OpenClaw 2026.4.23 ships a disabled `memory-wiki` plugin, but this local CLI did not expose a top-level `openclaw wiki` command during setup. This repo therefore works without that command.

When the native command is available, enable the plugin and point it at `memory-wiki/`.

## Daily Memory Commands

```powershell
npm run memory:capture -- --type observation --title "Short title" --summary "What changed" --source conversation
npm run memory:compile
npm run memory:check
```

The always-loaded memory entrypoint is `MEMORY.md`; it points the agent at `memory/_compiled/SESSION_INDEX.md` before any larger memory files.
