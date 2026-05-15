# OpenClaw Setup

## Use The Companion Folder As Workspace

```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc/companion"
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

Memory is file-first. Write Markdown files under `companion/memory/` (or
`memory/` from inside the configured OpenClaw workspace). The Cognee plugin
indexes them automatically.

```bash
openclaw cognee status    # check sync state
openclaw cognee index     # force re-sync
npm run check             # repo hygiene
```

## Composio integrations

The active Google/LinkedIn integration path is the local
`composio-limited` OpenClaw plugin.

Allowed tools:

```bash
composio_status
composio_gmail_personal
composio_gmail_work
composio_calendar
composio_tasks
composio_linkedin
```

GOG is not part of the active runtime.

## Proactive Cron Jobs

```bash
openclaw cron list --json
```

Expected:

- `morning-brief`: daily at 07:30 Europe/Copenhagen.
- `evening-journal-reminder`: daily at 21:00 Europe/Copenhagen.
- `nightly-review` / `nightly-dream-cycle`: nightly local review while Kristian sleeps.
