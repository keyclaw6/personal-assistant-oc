# OpenClaw Setup

## Use This Repo As Workspace

```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc"
openclaw gateway restart
```

## Authenticate The Model

The agent uses OpenRouter (DeepSeek V4 Flash). Configure the API key in `.env.cognee` (gitignored). The OpenClaw runtime model config may differ from the Cognee LLM — that's intentional.

## Open Dashboard

```bash
openclaw dashboard
```

## Cognee Memory Plugin

See `docs/cognee-setup.md` for full setup. Quick version:

```bash
openclaw plugins install @cognee/cognee-openclaw
openclaw cognee setup
bash scripts/cognee-server.sh start
openclaw cognee health
openclaw cognee index
```

## Daily Memory Commands

Memory is file-first. Write Markdown files under `memory/`. The Cognee plugin indexes them automatically.

```bash
openclaw cognee status    # check sync state
openclaw cognee index     # force re-sync
npm run check             # repo hygiene
```

## Google Workspace Skill

The primary Google Workspace integration is the ClawHub/OpenClaw `gog` skill installed in `skills/gog/`.

Verify the skill and binary:

```bash
gog --version
openclaw skills info gog
```

Set up OAuth credentials outside this repository:

```bash
gog auth credentials set /path/outside/repo/client_secret.json
gog auth add you@gmail.com --services gmail,calendar,drive,contacts,tasks,people,docs,sheets --readonly
gog auth list --json --no-input
```

## Proactive Cron Jobs

```bash
openclaw cron list --json
```

Expected:

- `morning-brief`: daily at 07:30 Europe/Copenhagen.
