# personal-assistant-oc — Companion

Private OpenClaw workspace for **Companion**, Kristian Bilstrup's personal
agent. One agent, three intertwined responsibilities: life ops, belief
change, and shadow / self-knowledge work.

**Read [`PHILOSOPHY.md`](./PHILOSOPHY.md) first.** It is the stable center
of this project. Every architectural decision below traces back to it.

## What this is

- A single personal agent — placeholder name *Companion* — accessed through
  Facebook Messenger. OpenClaw dashboard / CLI are maintenance-only.
- File-first memory under `memory/`. Plain Markdown, hand-editable, portable.
- The OpenClaw plugin `@cognee/cognee-openclaw` (manifest id
  `cognee-openclaw`) sits on top, indexing those files into a knowledge graph
  (Kuzu) + vector store (LanceDB) and injecting retrieval results before
  each agent run.
- LLM: DeepSeek via OpenRouter. Embeddings: OpenRouter (Ollama fallback).
- Active-interlocutor posture: not a mirror, not an oracle. See
  `PHILOSOPHY.md` and `SOUL.md`.

## What this is not

- Not a coder. No IDE integration, no coding-project tracking.
- Not a clinician. Not crisis support.
- Not autonomous. No external action (email send, calendar change, task
  completion, file share) without explicit approval for that specific action.

## Folder map

| Path | What |
| --- | --- |
| `PHILOSOPHY.md` | Root statement of intent. Read first. |
| `IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `TOOLS.md`, `MEMORY.md`, `HEARTBEAT.md` | Operating rules. |
| `IMPLEMENTATION_PLAN.md` | The pivot plan. |
| `memory/` | All durable knowledge (files are source of truth). |
| `plugins/openclaw-messenger/` | Facebook Messenger channel plugin. |
| `scripts/` | Local maintenance (`gws.mjs`, `morning-brief.mjs`, `repo-check.mjs`). |
| `skills/` | `gog`, `google_workspace_assistant`. |
| `docs/` | Architecture, Cognee setup, OpenClaw setup, security, integrations. |
| `openclaw-config/` | OpenClaw instance config. |
| `archive/` | Previous structures (memory-old, memory-wiki-old, belief-system-old, templates-old). Reference only; not indexed. |
| `.env.cognee`, `.cognee_system/` | Gitignored — config and runtime data. |

## Channels

- **Facebook Messenger** — primary.
- **OpenClaw dashboard / CLI** — maintenance only.

## Daily rhythm

A morning brief at 07:30 Europe/Copenhagen lands in Messenger: schedule,
priorities, commitments, beliefs in progress, captured-yesterday
acknowledgments, mail headline.

## Quick start

Requires Node `>=22.14.0`.

```bash
npm run check
```

Set this repo as the OpenClaw workspace:

```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc"
```

Install the memory plugin (see `docs/cognee-setup.md` for the full path,
including the known install-bug workaround):

```bash
openclaw plugins install @cognee/cognee-openclaw@2026.3.4
openclaw plugins list   # verify cognee-openclaw is enabled
openclaw gateway restart
```

## Security defaults

- Private GitHub repo. `memory/` is committed; secrets, tokens, OAuth
  credentials, `.env.cognee`, and `.cognee_system/` are gitignored.
- Gateway bound to loopback unless a documented remote-access plan exists.
- External content (emails, attachments, web pages, transcripts, books) is
  treated as untrusted input.
- Run `openclaw security audit --deep` after upgrades or channel/tool
  changes.
- Run `npm run repo:check` before committing.
