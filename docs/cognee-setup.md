# Cognee Setup — Albert

The Albert agent uses [Cognee](https://www.cognee.ai/) for memory indexing and
retrieval. The active Hermes plugin is `cognee-memory`; it searches the
existing Cognee API first and falls back to direct file-memory search when the
vector store is unhealthy.

The old OpenClaw plugin `@cognee/cognee-openclaw` created the current datasets
and remains useful as migration reference.

Files remain the source of truth. Cognee provides retrieval only.

## Architecture

```
albert/memory/*.md  ──▶  Cognee API server (127.0.0.1:8001)  ──▶  Kuzu + LanceDB + SQLite
                       ▲
                       │
            Hermes plugin (cognee-memory)
            auto-recall with file fallback
```

## Quick start

1. **Link the Hermes plugin**:
   ```bash
   npm run hermes:migrate
   ```

2. **Install and start the Cognee user service**:
   ```bash
   npm run cognee -- install
   ```

3. **Verify**:
   ```bash
   npm run cognee -- status
   curl -fsS http://127.0.0.1:8001/health
   ```

4. **Legacy index maintenance**:
   ```bash
   openclaw cognee index
   ```

## Configuration

The Cognee server reads environment variables from the dotenvx-encrypted
`.env.cognee` at the repo root. The encrypted file is tracked; the shared
private key stays outside Git at `~/.config/dotenvx/.env.keys`. The server
script decrypts it only into the child process environment.

Key variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `LLM_PROVIDER` | `custom` | Routes through LiteLLM |
| `LLM_MODEL` | `openrouter/deepseek/deepseek-v4-flash` | Chat/reasoning model |
| `LLM_ENDPOINT` | `https://openrouter.ai/api/v1` | OpenRouter API |
| `LLM_API_KEY` | `sk-or-v1-...` | OpenRouter API key |
| `EMBEDDING_PROVIDER` | `custom` | Routes through LiteLLM |
| `EMBEDDING_MODEL` | `openrouter/qwen/qwen3-embedding-8b` | 4096-dim embeddings |
| `EMBEDDING_API_KEY` | `sk-or-v1-...` | OpenRouter API key |
| `EMBEDDING_DIMENSIONS` | `4096` | Qwen3 Embedding 8B native dim |
| `VECTOR_DB_PROVIDER` | `lancedb` | File-based vector store |
| `GRAPH_DATABASE_PROVIDER` | `kuzu` | File-based graph store |
| `DB_PROVIDER` | `sqlite` | File-based relational store |
| `SYSTEM_ROOT_DIRECTORY` | `<repo>/.cognee_system` | Cognee runtime data |
| `ENABLE_BACKEND_ACCESS_CONTROL` | `true` | Preserve per-user datasets and permissions |
| `REQUIRE_AUTHENTICATION` | `false` | Existing setting; access control still enforces authentication |

## Cognee server management

```bash
npm run cognee -- install  # Install, enable, and start the tracked user service
npm run cognee -- start    # Start the installed service
npm run cognee -- stop     # Stop the service
npm run cognee -- status   # Verify systemd plus Cognee identity/readiness
npm run cognee -- restart  # Restart the service
npm run cognee -- health   # Verify the endpoint is Cognee, not another app
```

The service is supervised by user systemd and survives login/reboot. Its tracked
unit is `systemd/user/cognee-server.service`; the installed copy is
`~/.config/systemd/user/cognee-server.service`. Cognee's upstream file handler
is disabled because exception tracebacks can include provider configuration.
The foreground service removes configured secrets and key fragments from both
output streams before copying them to the systemd journal. Journald owns
persistence, rotation, and size limits. The wrapper does not write a custom log
file:

```bash
journalctl --user -u cognee-server.service
```

For operational diagnostics, use `npm run cognee -- status`,
`npm run cognee -- health`, and the sanitized journal. Historical files under
`~/.cognee/logs/` predate this hardening and include a fragment of an
already-invalid provider credential; treat those files as sensitive history.
The earlier sanitized files under `~/.local/state/cognee/server.log*` are also
left untouched. New service runs write to neither location.

`run` is the foreground command used by systemd. It binds only to loopback,
defaults to port 8001, runs one Uvicorn worker, and refuses to start if that
port is already occupied. Port 8000 remains assigned to the GitHub MCP service.

## OpenClaw plugin commands

```bash
openclaw cognee health   # Check Cognee API connectivity
openclaw cognee status   # Show sync state (files indexed, dataset info)
openclaw cognee index    # Sync memory files to Cognee
openclaw cognee scopes   # Show memory scope routing
```

## Known issues

### Install bug (#24429)

The installer may register the config entry under `cognee-openclaw` instead
of the manifest id `cognee-openclaw`. After install, verify:

```bash
openclaw plugins list
```

The entry should show `cognee-openclaw` (the actual manifest id). The
plugin works correctly with this id.

### SQLite migration error on first start

The first server start may show a SQLite migration error followed by
"Migration completed successfully." This is a known race condition in the
alembic migration runner and is harmless — the database is created correctly.

## Embedding fallback

If OpenRouter embeddings fail, switch to fastembed (local, CPU, no extra
install):

```env
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384
```

Then restart the Cognee server and re-index:

```bash
npm run cognee -- restart
openclaw cognee index
```

## Data location

All Cognee runtime data lives under:

- `.cognee_system/` — databases (Kuzu, LanceDB, SQLite)
- `.cognee_data/` — raw ingested data files

Both are gitignored. Regenerable from `albert/memory/` source files.
