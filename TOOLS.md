# TOOLS.md — Tooling

## OpenClaw

- CLI: `openclaw`
- Dashboard: `openclaw dashboard`
- Local gateway: `http://127.0.0.1:18789/`
- Status: `openclaw status --json`
- Models status: `openclaw models status --json`
- Plugins list: `openclaw plugins list`
- Security audit: `openclaw security audit --deep`

## LLM and embeddings

- **Provider:** OpenRouter (single API key for everything possible).
- **Chat model:** DeepSeek high-reasoning variant via OpenRouter (slug
  confirmed at execution time).
- **Embeddings (primary):** OpenRouter embedding model.
- **Embeddings (fallback):** Ollama + `nomic-embed-text` local
  (`http://localhost:11434`).
- Config lives in `.env.cognee` at repo root (gitignored).

## Memory plugin

- `@cognee/cognee-openclaw` (manifest id `cognee-openclaw`).
- Indexes `MEMORY.md` and `memory/` into LanceDB (vectors) + Kuzu (graph) +
  SQLite (relational), under `.cognee_system/` (gitignored).
- Pre-run context injection is automatic. The agent does not call Cognee
  directly. Writing/editing/deleting files in `memory/` triggers re-sync.
- Setup notes: `docs/cognee-setup.md`.

## Messenger plugin

- Path: `plugins/openclaw-messenger/`.
- Primary user channel via Meta Graph API.
- Webhook smoke test:
  ```bash
  curl 'http://127.0.0.1:18789/messenger/webhook?hub.mode=subscribe&hub.verify_token=TEST&hub.challenge=abc123'
  ```
- Public exposure (deferred): Tailscale Funnel — see plugin README.

## Google Workspace (`gog`)

Primary CLI for Gmail, Calendar, Drive, Contacts/People, Tasks reads.

```bash
gog --help
gog auth status --json --no-input
gog schema --json --no-input
```

Safety flags:

- `--json --no-input` for scripted reads.
- `--gmail-no-send` for Gmail triage/draft.
- `--dry-run` before supported writes.
- `--enable-commands` / `--disable-commands` to narrow the surface.

Setup (credentials live outside the repo):

```bash
gog auth credentials set /path/outside/repo/client_secret.json
gog auth add you@gmail.com --services gmail,calendar,drive,contacts,tasks,people,docs,sheets --readonly
```

Fallback: `scripts/gws.mjs` (`npm run gws -- ...`).

## Scheduled jobs

```bash
openclaw cron list --json
```

Expected:

- `morning-brief` — daily 07:30 Europe/Copenhagen.

## Secrets

Do not commit: API keys, tokens, passwords, cookies, private SSH keys,
OpenClaw runtime config, `.env.cognee`, OAuth credentials, `.cognee_system/`.

## Search

Use `rg` for local search:

```bash
rg -n "keyword" memory/ MEMORY.md PHILOSOPHY.md
```
