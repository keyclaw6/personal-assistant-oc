# Personal Assistant OC

Private OpenClaw personal assistant workspace with a file-based memory system. It is designed to need only your model provider login. No vector database, no memory SaaS key, and no hidden memory store.

## What This Is

This repository combines the normal OpenClaw workspace boilerplate with a curated memory-wiki structure:

- Root files (`AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md`) define behavior and startup rules.
- `memory/` stores raw chronological memory: events, daily notes, inbox items, conflicts, and compiled startup context.
- `memory-wiki/` stores durable reviewed memory: profile, projects, tools, decisions, people, preferences, entities, concepts, sources, syntheses, and reports.
- `scripts/` contains dependency-free Node scripts to compile a compact startup digest and report stale or conflicting memory.

## Why File-Based

The design intentionally keeps memory inspectable and version-controlled. OpenClaw's own memory docs say the model remembers what is written to disk, and the bundled Memory Wiki plugin turns durable memory into a compiled knowledge vault with provenance, claims, dashboards, and digests. MemU's file-memory pattern argues for category files that are readable, structured, model-agnostic, and easy to debug. Claude-Mem shows the value of automatic lifecycle capture and progressive disclosure, but its default architecture uses SQLite, a worker service, and Chroma vector search, so this repo borrows the lifecycle idea rather than the storage stack. Cognee's writing is useful for the feedback-loop idea: memory should continuously update, restructure, and surface uncertainty instead of becoming a static pile of notes.

## Quick Start

```powershell
npm run memory:compile
npm run memory:report
```

To use this repo as the active OpenClaw workspace:

```powershell
openclaw config set agents.defaults.workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc"
openclaw gateway restart
```

Then authenticate a model provider:

```powershell
openclaw models auth login --provider openai
openclaw dashboard
```

## Memory Lifecycle

1. Capture raw memory in `memory/events/YYYY-MM-DD.jsonl` and `memory/daily/YYYY-MM-DD.md`.
2. Put uncertain items in `memory/inbox/`.
3. Promote stable facts into `memory-wiki/` only when they have a source and confidence.
4. If a new fact conflicts with old memory, create a file under `memory/conflicts/` instead of overwriting.
5. Run `npm run memory:compile` after meaningful changes so `memory/_compiled/STARTUP.md` stays small and useful.
6. Run `npm run memory:report` to refresh stale/conflict/low-confidence reports.

## No Vector DB Policy

Retrieval is done with:

- predictable filenames
- tags and claim IDs
- Markdown headings
- `rg`/plain text search
- compact generated digests
- LLM reading of the relevant files

Embeddings can be added later as a local JSONL index, but this repo deliberately ships without a vector database or embedding service.

## Sources Researched

- OpenClaw Memory Overview: https://docs.openclaw.ai/concepts/memory
- OpenClaw Memory Wiki plugin: https://docs.openclaw.ai/plugins/memory-wiki
- awesome-openclaw-agents memory-wiki templates: https://github.com/mergisi/awesome-openclaw-agents/tree/main/memory-wiki/templates
- claude-mem: https://github.com/thedotmack/claude-mem
- Cognee file-based AI memory: https://www.cognee.ai/blog/deep-dives/file-based-ai-memory
- MemU file-based memory: https://memu.pro/file-based-memory
