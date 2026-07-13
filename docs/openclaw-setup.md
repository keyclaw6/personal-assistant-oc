# Legacy OpenClaw Setup

Albert's active runtime is Hermes. This page is retained only as migration
reference for the previous OpenClaw setup.

## Use The Albert Folder As Workspace

```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc/albert"
openclaw gateway restart
```

## Authenticate The Model

The agent uses OpenRouter (DeepSeek V4 Flash). Configure the API key in the tracked dotenvx-encrypted `.env.cognee` with `dotenvx set`; never commit the private key. The OpenClaw runtime model config may differ from the Cognee LLM — that's intentional.

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

Memory is file-first. Write Markdown files under `albert/memory/` (or
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

## Context management

The Albert config assumes GPT-5.5 has a 400K window but effectively compacts
around 260K tokens because OpenAI reserves a large output budget. The repo
template therefore sets:

- `agents.defaults.compaction.reserveTokensFloor: 140000`
- `agents.defaults.compaction.memoryFlush.softThresholdTokens: 20000`

That means the memory flush should run before the effective 260K boundary, with
enough room to write durable notes. Session pruning is enabled to trim old tool
results without rewriting the transcript. Heartbeat is disabled; scheduled jobs
handle routine proactive work.

Do not proactively clear/reset context until `jobs/SESSION_CHECKPOINT.md` has
been run and durable memory has been written.
