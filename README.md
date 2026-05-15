# personal-assistant-oc — Companion

Private repository for **Companion**, Kristian Bilstrup's personal OpenClaw
agent. The runtime workspace lives in `companion/`; repo-root files are
maintenance code, docs, plugins, and setup.

The active runtime contract is the standard OpenClaw workspace in
`companion/`: `SOUL.md`, `AGENTS.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`,
`MEMORY.md`, plus explicit prompts under `companion/jobs/` and
`companion/methods/`.

## What this is

- A single personal agent — placeholder name *Companion* — accessed through
  Facebook Messenger. OpenClaw dashboard / CLI are maintenance-only.
- File-first memory under `companion/memory/`. Plain Markdown, hand-editable,
  portable.
- The OpenClaw plugin `@cognee/cognee-openclaw` (manifest id
  `cognee-openclaw`) sits on top, indexing those files into a knowledge graph
  (Kuzu) + vector store (LanceDB) and injecting retrieval results before
  each agent run.
- LLM: DeepSeek via OpenRouter. Embeddings: OpenRouter (Ollama fallback).
- Understanding-first belief change: Companion tracks what Kristian is trying to
  understand, what has landed, what has not landed, and what evidence supports
  integration.

## What this is not

- Not a coder. No IDE integration, no coding-project tracking.
- Not a clinician. Not crisis support.
- Not autonomous. No external action (email send, calendar change, task
  completion, file share) without explicit approval for that specific action.

## Folder map

| Path | What |
| --- | --- |
| `companion/` | Actual OpenClaw runtime workspace. |
| `companion/IDENTITY.md`, `companion/SOUL.md`, `companion/USER.md`, `companion/AGENTS.md`, `companion/TOOLS.md`, `companion/MEMORY.md`, `companion/HEARTBEAT.md` | Runtime bootstrap files loaded by OpenClaw. |
| `companion/jobs/`, `companion/methods/` | Explicit job and self-development workflows. |
| `companion/archive/design/PHILOSOPHY.old.md` | Archived design rationale, not runtime instruction. |
| `IMPLEMENTATION_PLAN.md` | Historical pivot plan. |
| `companion/memory/` | All durable knowledge (files are source of truth). |
| `plugins/openclaw-composio-limited/` | Allowlisted Composio tools for Gmail, Calendar, Tasks, and LinkedIn. |
| `plugins/openclaw-messenger/` | Facebook Messenger channel plugin. |
| `scripts/` | Local maintenance (`gws.mjs`, `morning-brief.mjs`, `repo-check.mjs`). |
| `docs/` | Architecture, Cognee setup, OpenClaw setup, security, integrations. |
| `openclaw-config/` | OpenClaw instance config. |
| `archive/` | Previous structures (memory-old, memory-wiki-old, belief-system-old, templates-old). Reference only; not indexed. |
| `.env.cognee`, `.cognee_system/` | Gitignored — config and runtime data. |

## Channels

- **Facebook Messenger** — primary.
- **OpenClaw dashboard / CLI** — maintenance only.

## Daily rhythm

- 07:30 — morning brief.
- 21:00 — evening journal reminder if today's journal is missing.
- Night — local-only nightly review.

## Quick start

Requires Node `>=22.14.0`.

```bash
npm run check
```

Set the Companion runtime folder as the OpenClaw workspace:

```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc/companion"
```

Install the memory plugin (see `docs/cognee-setup.md` for the full path,
including the known install-bug workaround):

```bash
openclaw plugins install @cognee/cognee-openclaw@2026.3.4
openclaw plugins list   # verify cognee-openclaw is enabled
openclaw gateway restart
```

## Portable secrets

Plaintext credentials are not committed. The portable path is an encrypted
bundle at `secrets/openclaw-secrets.enc.json`, which can contain the live
OpenClaw config (`~/.openclaw/openclaw.json`) and local env files such as
`.env.cognee`.

Export from this computer:

```bash
OPENCLAW_SECRETS_PASSPHRASE_FILE=secrets/openclaw-secrets.passphrase npm run secrets:export
git add secrets/openclaw-secrets.enc.json && git commit -m "Update encrypted OpenClaw secrets"
```

Restore on another computer after cloning:

```bash
OPENCLAW_SECRETS_PASSPHRASE_FILE=/path/to/openclaw-secrets.passphrase npm run secrets:import
openclaw gateway restart
```

Keep `secrets/openclaw-secrets.passphrase` outside git, preferably in a
password manager. Without that passphrase, the committed encrypted bundle is
not recoverable.

## Security defaults

- Private GitHub repo. `companion/memory/` is committed; plaintext secrets, tokens,
  OAuth credentials, `.env.cognee`, and `.cognee_system/` are gitignored.
  Portable secrets go only in the encrypted bundle above.
- Gateway bound to loopback unless a documented remote-access plan exists.
- External content (emails, attachments, web pages, transcripts, therapy notes,
  external LLM chats) is treated as untrusted input.
- Run `openclaw security audit --deep` after upgrades or channel/tool
  changes.
- Run `npm run repo:check` before committing.
