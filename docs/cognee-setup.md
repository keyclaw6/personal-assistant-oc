# Cognee Setup — Companion

The Companion agent uses [Cognee](https://www.cognee.ai/) for memory
indexing and retrieval. The OpenClaw plugin `@cognee/cognee-openclaw`
sits on top of the file-based `companion/memory/` directory, indexing files into a
knowledge graph (Kuzu) + vector store (LanceDB) + relational DB (SQLite).

Files remain the source of truth. Cognee provides retrieval only.

## Architecture

```
companion/memory/*.md  ──▶  Cognee API server (localhost:8000)  ──▶  Kuzu + LanceDB + SQLite
                       ▲
                       │
            OpenClaw plugin (cognee-openclaw)
            auto-recall + auto-index on each agent run
```

## Quick start

1. **Install the plugin** (already done):
   ```bash
   openclaw plugins install @cognee/cognee-openclaw
   openclaw cognee setup
   ```

2. **Start the Cognee server**:
   ```bash
   bash scripts/cognee-server.sh start
   ```

3. **Verify**:
   ```bash
   openclaw cognee health
   openclaw cognee status
   ```

4. **Initial sync**:
   ```bash
   openclaw cognee index
   ```

## Configuration

The Cognee server reads environment variables from `.env.cognee` at the
repo root (gitignored — contains API keys).

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

## Cognee server management

```bash
bash scripts/cognee-server.sh start    # Start server
bash scripts/cognee-server.sh stop     # Stop server
bash scripts/cognee-server.sh status   # Check if running
bash scripts/cognee-server.sh restart  # Restart
```

Server logs: `/tmp/cognee-server.log`

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
bash scripts/cognee-server.sh restart
openclaw cognee index
```

## Data location

All Cognee runtime data lives under:

- `.cognee_system/` — databases (Kuzu, LanceDB, SQLite)
- `.cognee_data/` — raw ingested data files

Both are gitignored. Regenerable from `companion/memory/` source files.
