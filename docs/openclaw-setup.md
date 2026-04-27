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

## Google Workspace Skill

The primary Google Workspace integration is the ClawHub/OpenClaw `gog` skill installed in `skills/gog/`.

Verify the skill and binary:

```powershell
gog --version
openclaw skills info gog
```

Set up OAuth credentials outside this repository:

```powershell
gog auth credentials set C:\path\outside\repo\client_secret.json
gog auth add you@gmail.com --services gmail,calendar,drive,contacts,tasks,people,docs,sheets --readonly
gog auth list --json --no-input
```

Keep write scopes disabled until the read-only workflows are verified.

## Proactive Cron Jobs

The intended proactive jobs are:

```powershell
openclaw cron add --name morning-brief --agent main --cron "30 7 * * *" --tz Europe/Copenhagen --session isolated --no-deliver --timeout-seconds 600 --message "Execute the Morning Brief standing order from AGENTS.md. Check Google Workspace sources if available, local commitments, tasks, and memory. Deliver a short private phone-readable brief using the paired Android node Kristian's S22 via system.notify if no private chat channel is configured. If a source is unavailable, include it under Unavailable Sources."

openclaw cron add --name friday-belief-check --agent belief --cron "0 17 * * 5" --tz Europe/Copenhagen --session isolated --no-deliver --timeout-seconds 300 --message "Execute the Friday belief-work reminder from belief-system/AGENTS.md and HEARTBEAT.md. Check whether a qualifying belief session exists in the last 7 days. If none exists, send Kristian a short direct reminder using the paired Android node Kristian's S22 via system.notify if no private chat channel is configured. Do not modify belief files."
```

Use `openclaw cron list --json` to verify active jobs.

The Android notification path was verified with:

```powershell
openclaw nodes invoke --node "Kristian's S22" --command system.notify --params '{""title"":""OpenClaw setup"",""body"":""Automation delivery path verified.""}'
```
