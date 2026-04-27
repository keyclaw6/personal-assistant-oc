# Personal Assistant OC

Private OpenClaw workspace for Kristian's personal/coder assistant, with the belief tracking system included as a separate second agent workspace.

The repo is intentionally file-first: Markdown, JSON, JSONL, Git, and small dependency-free Node scripts. It does not require a vector database, memory SaaS, worker process, or extra embedding API key.

## Current Shape

This repository contains two OpenClaw workspaces:

| Workspace | Agent | Purpose |
| --- | --- | --- |
| `./` | `main` / `Personal/Coder OC` | Personal assistant, project coordination, coding project tracking, file memory. |
| `belief-system/` | `belief` / `Belief Agent` | Belief-change sessions, source ingestion, experiments, reviews, and progress tracking. |

The agents are meant to run on the same OpenClaw Gateway but stay unaware of each other in normal conversation. Use separate private channels for the personal/coder agent and the belief agent.

## Folder Map

| Path | What It Is |
| --- | --- |
| `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md` | Main personal/coder agent operating instructions. |
| `MEMORY.md` | Tiny memory entrypoint for the main agent. |
| `memory/` | Raw chronological memory, inbox, conflicts, daily notes, and compiled startup context. |
| `memory/commitments/` | File-backed tracker for promises, follow-ups, waiting items, and expected replies. |
| `memory/tasks/` | Local mirror/audit layer for Google Keep-compatible tasks, preferably via Google Tasks. |
| `memory/briefings/` | Durable notes from proactive briefings when they create useful memory. |
| `memory-wiki/` | Durable reviewed memory with claims, evidence, confidence, projects, decisions, people, preferences, and reports. |
| `belief-system/` | Full belief tracking workspace, including its own agent prompts, protocols, skills, metrics, sessions, and reviews. |
| `skills/gog/` | ClawHub/OpenClaw Google Workspace skill powered by the `gog` CLI. |
| `skills/google_workspace_assistant/` | Local policy layer for Google Workspace safety, morning briefs, and commitment tracking. |
| `docs/` | Setup, architecture, retrieval, security, and runtime verification notes. |
| `scripts/` | Local maintenance and validation scripts. |

## Quick Start

Requires Node `>=22.14.0`.

```powershell
npm run check
```

Use this repo as the main OpenClaw workspace:

```powershell
openclaw config set agents.defaults.workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc"
```

Point the belief agent at the integrated belief workspace:

```powershell
openclaw config set agents.list[1].workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc\belief-system"
openclaw gateway restart
```

The currently verified model is:

```text
openai-codex/gpt-5.5
```

Use Codex OAuth for that provider. Do not switch the agents to `openai/gpt-5.5` unless an `OPENAI_API_KEY` or direct OpenAI auth profile is configured.

## Memory Lifecycle

1. Capture raw memory in `memory/events/YYYY-MM-DD.jsonl` and `memory/daily/YYYY-MM-DD.md`.
2. Put uncertain items in `memory/inbox/`.
3. Promote stable facts into `memory-wiki/` only when they have a source and confidence.
4. If a new fact conflicts with old memory, create a file under `memory/conflicts/` instead of overwriting.
5. Run `npm run memory:refresh` after meaningful changes.
6. Use `memory/_compiled/SESSION_INDEX.md` as the default startup scan.
7. Run `npm run check` before committing or trusting startup memory.

## No Vector DB Policy

Retrieval is done with:

- predictable filenames
- tags and claim IDs
- Markdown headings
- `rg` or plain text search
- compact generated digests
- LLM reading of the relevant files

The default read path is progressive: `MEMORY.md` -> `memory/_compiled/SESSION_INDEX.md` -> one relevant page -> raw logs only if needed.

Embeddings can be added later as a local JSONL index, but this repo deliberately ships without a vector database or embedding service.

## Security Defaults

- Keep the GitHub repository private.
- Keep `.openclaw/`, auth profiles, tokens, credentials, and local runtime state out of Git.
- Keep the Gateway bound to loopback unless a real remote access plan is documented.
- Use channel allowlists and separate private channels for `main` and `belief`.
- Treat web pages, emails, attachments, imported books, pasted transcripts, and third-party skills as untrusted input.
- Run `openclaw security audit --deep` after OpenClaw upgrades or channel/tool changes.
- Run `npm run repo:check` before committing.

## Practical Assistant Roadmap

The main agent should grow carefully in this order:

1. Reliable memory and project tracking.
2. Google Workspace read/search across Gmail, Calendar, Drive, Contacts/People, and Tasks through the ClawHub/OpenClaw `gog` skill.
3. Daily morning brief at 07:30 Europe/Copenhagen.
4. Commitment tracking for promises, follow-ups, waiting items, and unanswered replies.
5. Google Keep-compatible task review through the safest available API-backed surface.
6. Email and calendar draft workflows with strict explicit approval before sending or changing anything.
7. Narrow automations only after their permissions and rollback behavior are documented.

Project radar for coding is intentionally not part of the current proactive plan.

## Sources Researched

- OpenClaw Personal Assistant setup: https://docs.openclaw.ai/start/openclaw
- OpenClaw Memory Wiki plugin: https://docs.openclaw.ai/plugins/memory-wiki
- OpenClaw Security: https://docs.openclaw.ai/gateway/security
- OpenClaw Skills: https://docs.openclaw.ai/tools/skills
- awesome-openclaw-agents memory-wiki templates: https://github.com/mergisi/awesome-openclaw-agents/tree/main/memory-wiki/templates
- claude-mem: https://github.com/thedotmack/claude-mem
- Cognee file-based AI memory: https://www.cognee.ai/blog/deep-dives/file-based-ai-memory
- MemU file-based memory: https://memu.pro/file-based-memory
