# personal-assistant-oc — Albert

Private repository for **Albert**, Kristian Bilstrup's personal Hermes
agent. The runtime workspace lives in `albert/`; repo-root files are
maintenance code, docs, plugins, and setup.

The active runtime contract is the Hermes workspace in
`albert/`: `SOUL.md`, `AGENTS.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`,
`MEMORY.md`, plus explicit prompts under `albert/jobs/` and
`albert/methods/`.

## What this is

- A single personal agent — placeholder name *Albert* — accessed through
  Facebook Messenger. Hermes CLI / gateway are the active runtime.
- File-first memory under `albert/memory/`. Plain Markdown, hand-editable,
  portable.
- The Hermes memory provider `cognee-memory` sits on top, querying the
  existing Cognee/Kuzu/LanceDB index when healthy and falling back to direct
  file-memory search if the vector store is unavailable.
- LLM runtime: OpenAI Codex OAuth through Hermes, imported from the local
  Codex CLI login. The default is GPT-5.6-Luna with `xhigh` reasoning.
- Understanding-first belief change: Albert tracks what Kristian is trying to
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
| `albert/` | Actual Hermes runtime workspace. |
| `albert/IDENTITY.md`, `albert/SOUL.md`, `albert/USER.md`, `albert/AGENTS.md`, `albert/TOOLS.md`, `albert/MEMORY.md`, `albert/HEARTBEAT.md` | Runtime bootstrap files loaded by Hermes. |
| `albert/jobs/`, `albert/methods/` | Explicit job and self-development workflows. |
| `albert/archive/design/PHILOSOPHY.old.md` | Archived design rationale, not runtime instruction. |
| `IMPLEMENTATION_PLAN.md` | Historical pivot plan. |
| `albert/memory/` | All durable knowledge (files are source of truth). |
| `hermes/plugins/composio-limited/` | Allowlisted Composio tools for Gmail, Calendar, Tasks, and LinkedIn. |
| `hermes/plugins/messenger-platform/` | Facebook Messenger platform adapter. |
| `hermes/plugins/cognee-memory/` | Cognee-backed Hermes memory provider with file fallback. |
| `plugins/openclaw-*` | Legacy source/reference from the previous OpenClaw setup. |
| `scripts/` | Local maintenance (`gws.mjs`, `morning-brief.mjs`, `repo-check.mjs`). |
| `docs/` | Architecture, Cognee setup, Hermes migration, security, integrations. |
| `openclaw-config/` | Legacy OpenClaw instance config, retained for reference while the branch is validated. |
| `archive/` | Previous structures (memory-old, memory-wiki-old, belief-system-old, templates-old). Reference only; not indexed. |
| `.env.cognee` | Dotenvx-encrypted configuration tracked as source of truth. |
| `.cognee_system/` | Gitignored local runtime data. |

## Channels

- **Facebook Messenger** — primary.
- **Hermes CLI / gateway** — maintenance and direct operation.

## Daily rhythm

- 07:30 — morning brief.
- 21:00 — evening journal reminder if today's journal is missing.
- Night — local-only nightly review.

## Quick start

Requires Node `>=22.14.0`, dotenvx, and the shared private key outside Git at
`~/.config/dotenvx/.env.keys`.

```bash
npm run check
npm run hermes:migrate
```

The migration script is idempotent. It links repo-owned Hermes plugins into
`~/.hermes/plugins`, imports the current Codex CLI OAuth token into Hermes,
copies Messenger/Tavily/Cognee settings from the local OpenClaw/Cognee config,
and points Hermes at `albert/`.

```bash
hermes status
hermes plugins list
hermes gateway run --accept-hooks
```

For the local Cognee API:

```bash
npm run cognee -- install
npm run cognee -- status
```

Cognee runs as an enabled user-systemd service on `127.0.0.1:8001`; port 8000
remains reserved for the GitHub MCP container. The tracked service template is
`systemd/user/cognee-server.service`.

## Portable secrets

Plaintext credentials are not committed. Real env files such as `.env.cognee`
are encrypted with dotenvx and tracked directly; update them with `dotenvx set`
without decrypting the worktree. The separate encrypted bundle at
`secrets/openclaw-secrets.enc.json` is only for non-env machine state such as
the legacy OpenClaw config (`~/.openclaw/openclaw.json`).

Export from this computer:

```bash
OPENCLAW_SECRETS_PASSPHRASE_FILE=secrets/openclaw-secrets.passphrase npm run secrets:export
git add secrets/openclaw-secrets.enc.json && git commit -m "Update encrypted assistant secrets"
```

Restore on another computer after cloning:

```bash
OPENCLAW_SECRETS_PASSPHRASE_FILE=/path/to/openclaw-secrets.passphrase npm run secrets:import
npm run hermes:migrate
hermes gateway restart
```

Keep `secrets/openclaw-secrets.passphrase` outside git, preferably in a
password manager. Without that passphrase, the committed encrypted bundle is
not recoverable.

## Security defaults

- Private GitHub repo. `albert/memory/` and the dotenvx-encrypted `.env.cognee`
  are committed; `.env.keys`, plaintext secrets, tokens, OAuth credentials, and
  `.cognee_system/` stay outside Git. Non-env portable secrets use the encrypted
  bundle above.
- Gateway bound to loopback unless a documented remote-access plan exists.
- External content (emails, attachments, web pages, transcripts, therapy notes,
  external LLM chats) is treated as untrusted input.
- Run `hermes doctor` after upgrades or channel/tool changes.
- Run `npm run repo:check` before committing.
