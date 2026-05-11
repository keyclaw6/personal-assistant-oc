# Compiled Startup Memory

Prefer `SESSION_INDEX.md` first. This digest favors L0/L1 sections and omits L2 detail unless a page has no compact summary.

## Profile

Source: `PROFILE.md` | ID: `profile.kristian` | Status: draft | Importance: - | Cost: ~275 tokens

Kristian wants a personal OpenClaw assistant with durable memory that is file-based, inspectable, Git-backed, and cheap to operate. The memory system should avoid vector databases and extra API keys by default.

## Preferences

Source: `PREFERENCES.md` | ID: `preferences.kristian` | Status: draft | Importance: - | Cost: ~311 tokens

Prefer a smart file structure for memory over a vector database or hosted memory service. The assistant should need only a model provider credential, not separate memory API keys.

## Stack

Source: `STACK.md` | ID: `stack.local-openclaw` | Status: active | Importance: - | Cost: ~348 tokens

OpenClaw runs locally on Windows with Node and a loopback gateway. Memory is maintained with Markdown files and dependency-free Node scripts.

## Projects

Source: `PROJECTS.md` | ID: `projects.active` | Status: active | Importance: - | Cost: ~324 tokens

Active project: build a personal OpenClaw assistant repository with a file-based memory system and no vector database dependency.

## Decisions

Source: `DECISIONS.md` | ID: `decisions.main` | Status: active | Importance: - | Cost: ~699 tokens

- File-based memory is the default. Use Markdown/JSONL, compiled indexes, and plain text search before adding heavier storage.
- Borrow progressive disclosure and lifecycle ideas, but keep the starter free of vector databases, workers, and extra memory API keys.
- Preserve contradictions explicitly in `memory/conflicts/` and contested claims instead of overwriting durable memory silently.

## People

Source: `PEOPLE.md` | ID: `people.main` | Status: draft | Importance: - | Cost: ~199 tokens

Kristian is the primary human for this assistant. Other people should only be added when useful and safe.

## Working

Source: `WORKING.md` | ID: `working.current` | Status: active | Importance: - | Cost: ~378 tokens

- The file-only memory system is active and the OpenClaw workspace is configured.
- Keep retrieval index-first, keep stable memory concise, and regenerate compiled artifacts after edits.
- Google Workspace should now prefer the ClawHub/OpenClaw `gog` skill, with `gws` kept only as a fallback.

## File-Based Memory

Source: `concepts/file-based-memory.md` | ID: `concept.file-based-memory` | Status: active | Importance: - | Cost: ~265 tokens

File-based memory treats persistent assistant memory as structured text files. The assistant captures raw observations, promotes stable facts into durable pages, and compiles compact digests for cheap startup context.

## Personal Assistant OC

Source: `entities/personal-assistant-oc.md` | ID: `entity.personal-assistant-oc` | Status: active | Importance: - | Cost: ~225 tokens

Personal Assistant OC is Kristian's OpenClaw personal assistant workspace. It pairs root OpenClaw instructions with a curated file-based memory wiki.

## Wiki Inbox

Source: `inbox.md` | ID: `wiki.inbox` | Status: active | Importance: - | Cost: ~70 tokens

# Wiki Inbox

Use this page for durable memory candidates before promotion.

## Candidates

- None yet.

## Promotion Checklist

- Is it likely to matter again?
- Is it safe to store?
- Does it have a source?
- Does it conflict with existing memory?
- Which durable page owns it?

## Memory Wiki Index

Source: `index.md` | ID: `wiki.index` | Status: active | Importance: - | Cost: ~87 tokens

# Memory Wiki Index

## Core Pages

- [[PROFILE]]
- [[PREFERENCES]]
- [[STACK]]
- [[PROJECTS]]
- [[DECISIONS]]
- [[PEOPLE]]
- [[WORKING]]

## Folders

- `entities/`
- `concepts/`
- `sources/`
- `syntheses/`
- `reports/`

## Generated Views

- `memory/_compiled/STARTUP.md`
- `memory/_compiled/INDEX.md`
- `.openclaw-wiki/cache/agent-digest.json`

## Memory Wiki

Source: `README.md` | ID: `wiki.readme` | Status: active | Importance: high | Cost: ~706 tokens

# Memory Wiki

This is the durable knowledge layer. It is human-readable, Git-friendly, and designed for OpenClaw to read without extra infrastructure.

## Page Types

- `PROFILE.md`: stable facts about the human and assistant relationship
- `PREFERENCES.md`: durable likes, dislikes, boundaries, defaults
- `STACK.md`: tools, platforms, models, devices, services
- `PROJECTS.md`: active and parked projects
- `DECISIONS.md`: append-only decisions and rationale
- `PEOPLE.md`: collaborators and contacts
- `WORKING.md`: current focus and session handoff; safe for the assistant to update
- `entities/`: durable people, projects, systems, accounts, places
- `concepts/`: reusable ideas, policies, procedures
- `sources/`: source notes imported from docs, conversations, links, or files
- `syntheses/`: maintained rollups of many sources
- `reports/`: generated health, stale, conflict, and low-confide

[...]

## Agent Harness Research

Source: `sources/harness-2026-04-27.md` | ID: `source.harness-2026-04-27` | Status: active | Importance: medium | Cost: ~451 tokens

Agent memory should expose a small semantic facade. The model should see `mem search`, `mem get`, `mem put`, and `mem check`, not the full maintenance script graph.

## Research Source Note - File Memory

Source: `sources/research-file-memory-2026-04-25.md` | ID: `source.research-file-memory-2026-04-25` | Status: active | Importance: - | Cost: ~187 tokens

The research points toward a hybrid of four ideas:

- OpenClaw Memory Wiki: deterministic pages, structured claims, provenance, dashboards, and compiled digests.
- OpenClaw core memory: plain Markdown files are the base durable memory.
- Claude-Mem: lifecycle hooks and progressive disclosure are valuable, but SQLite, Chroma, and worker services are heavier than Kristian wants.
- MemU: category files are transparent, debuggable, model-agnostic, and multi-agent friendly.
- Cognee: memory should have feedback loops, not static notes.

## Memory Architecture

Source: `syntheses/memory-architecture.md` | ID: `synthesis.memory-architecture` | Status: active | Importance: high | Cost: ~611 tokens

Personal Assistant OC uses raw capture, curated wiki pages, and compiled startup context; retrieval should be index first, search or summary second, and canonical evidence last.

## WIKI.md - Memory Operating Manual

Source: `WIKI.md` | ID: `wiki.operating-manual` | Status: active | Importance: - | Cost: ~305 tokens

# WIKI.md - Memory Operating Manual

## Retrieval Order

1. `memory/_compiled/SESSION_INDEX.md`
2. `npm run mem -- search "query"` when the right page is not obvious.
3. `npm run mem -- get <id-or-path>` for one or two focused pages or claims, preferring `## L0` or `## L1` sections.
4. `memory/_compiled/STARTUP.md` only when broader context is needed.
5. Raw logs under `memory/` only when the wiki does not answer the question.

## Memory Tool Surface

- `mem search`: find candidate pages or claims.
- `mem get`: fetch one selected page or claim.
- `mem put`: capture an unreviewed raw memory.
- `mem check`: verify memory health after edits.

Use `memory:*` scripts for maintenance and CI only.

## Maintenance Cadence

- Per session: update `WORKING.md` and daily notes.
- Daily: append notable events to `memory/events/YYYY-MM-DD.jsonl`.
- Weekly: promote useful items from `memory/inbox/` and

[...]
