# OpenClaw Setup

## Use This Repo As Workspace

```powershell
openclaw config set agents.defaults.workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc"
openclaw config set agents.list[1].workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc\belief-system"
openclaw gateway restart
```

## Authenticate The Model

```powershell
openclaw models auth login --provider openai-codex
```

The verified model string is `openai-codex/gpt-5.5`. If you switch to `openai/gpt-5.5`, OpenClaw expects direct OpenAI API auth instead of Codex OAuth.

## Open Dashboard

```powershell
openclaw dashboard
```

## Optional Native Memory Wiki Plugin

This repo works without a native `openclaw wiki` command. If your OpenClaw build exposes one, enable the plugin and point it at `memory-wiki/`.

Either way, the local file scripts remain the baseline memory maintenance path.

## Daily Memory Commands

```powershell
npm run memory:capture -- --type observation --title "Short title" --summary "What changed" --source conversation
npm run memory:refresh
npm run check
```

The always-loaded memory entrypoint is `MEMORY.md`; it points the agent at `memory/_compiled/SESSION_INDEX.md` before any larger memory files.
