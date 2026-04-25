# Compiled Startup Memory

Generated: 2026-04-25T06:50:09.329Z

This file is generated. Edit durable memory in `memory-wiki/`, then rerun `npm run memory:compile`.

## Profile

Source: `PROFILE.md`

Kristian wants a personal OpenClaw assistant with durable memory that is file-based, inspectable, Git-backed, and cheap to operate. The memory system should avoid vector databases and extra API keys by default.

## Preferences

Source: `PREFERENCES.md`

Prefer a smart file structure for memory over a vector database or hosted memory service. The assistant should need only a model provider credential, not separate memory API keys.

## Stack

Source: `STACK.md`

OpenClaw runs locally on Windows with Node and a loopback gateway. Memory is maintained with Markdown files and dependency-free Node scripts.

## Projects

Source: `PROJECTS.md`

Active project: build a personal OpenClaw assistant repository with a file-based memory system and no vector database dependency.

## Decisions

Source: `DECISIONS.md`

# Decisions

Append only. If a decision changes, add a new entry that supersedes the old one.

## 2026-04-25 - Use File-Based Memory By Default

- Decision: Personal Assistant OC will use Markdown/JSONL files as the primary memory store.
- Rationale: Kristian wants memory without a separate vector database or memory API key.
- Consequence: Retrieval depends on file structure, compiled digests, plain text search, and good maintenance discipline.
- Status: active.

## 2026-04-25 - Borrow Lifecycle Ideas, Not Heavy Storage

- Decision: Borrow lifecycle capture and progressive disclosure from systems like claude-mem, but do not adopt SQLite, Chroma, worker services, or extra dependencies for this starter.
- Rationale: The desired system should run with only OpenClaw, Node, Git, and a model provider.
- Status: active.

## 2026-04-25 - Preserve Conflicts Explicitly

- Decision: Contradictory memories become conflict notes until resolved.
- Rationale: Silent overwrites make personal memory untrustworthy.
- Status: active.

## People

Source: `PEOPLE.md`

Kristian is the primary human for this assistant. Other people should only be added when useful and safe.

## Working

Source: `WORKING.md`

# Working

## Current Focus

Build and publish `personal-assistant-oc`, a private OpenClaw workspace repository with file-based memory.

## Next Actions

- Compile startup memory.
- Run memory health report.
- Create the GitHub repository.
- Push the initial commit.
- After model auth is configured, test the assistant through OpenClaw.

## Handoff Notes

- The memory system intentionally avoids vector DBs.
- Use `npm run memory:compile` after editing durable pages.
- Use `npm run memory:report` after resolving or adding conflicts.

## Personal Assistant OC

Source: `entities/personal-assistant-oc.md`

# Personal Assistant OC

## Summary

Personal Assistant OC is Kristian's OpenClaw personal assistant workspace. It pairs root OpenClaw instructions with a curated file-based memory wiki.

## Responsibilities

- Preserve personal context across sessions.
- Keep memory readable and reviewable.
- Avoid extra memory infrastructure by default.
- Surface stale, contested, or low-confidence facts.

## Links

- Core memory: `memory-wiki/`
- Raw memory: `memory/`
- Compile script: `scripts/compile-memory.mjs`
- Report script: `scripts/memory-report.mjs`

## File-Based Memory

Source: `concepts/file-based-memory.md`

# File-Based Memory

## Summary

File-based memory treats persistent assistant memory as structured text files. The assistant captures raw observations, promotes stable facts into durable pages, and compiles compact digests for cheap startup context.

## Why It Fits This Assistant

- Transparent: humans can inspect and edit memory.
- Portable: works across models.
- Auditable: Git shows every memory change.
- Cheap: no vector database or separate memory service.
- Robust: conflicts and stale pages are visible.

## Retrieval Pattern

1. Read compact digest.
2. Search filenames/headings/tags.
3. Read relevant wiki pages.
4. Fall back to raw logs only when needed.

## Memory Architecture

Source: `syntheses/memory-architecture.md`

# Memory Architecture

## Summary

Personal Assistant OC uses a three-lane memory system:

1. Raw capture: append-only events and daily notes.
2. Curated wiki: durable pages with evidence, confidence, and review dates.
3. Compiled context: generated startup digest and index.

## Why This Beats A Flat MEMORY.md

A single memory file eventually becomes hard to search, hard to review, and easy to corrupt. Splitting by lifecycle and domain keeps memory usable while remaining simple.

## Why This Avoids A Vector DB

Personal memory has many facts that are small, named, and audit-sensitive. For this workload, deterministic filenames, headings, tags, and compiled digests provide enough retrieval without an opaque semantic store.

## Research Source Note - File Memory

Source: `sources/research-file-memory-2026-04-25.md`

# Research Source Note - File Memory

## Summary

The research points toward a hybrid of four ideas:

- OpenClaw Memory Wiki: deterministic pages, structured claims, provenance, dashboards, and compiled digests.
- OpenClaw core memory: plain Markdown files are the base durable memory.
- Claude-Mem: lifecycle hooks and progressive disclosure are valuable, but SQLite, Chroma, and worker services are heavier than Kristian wants.
- MemU: category files are transparent, debuggable, model-agnostic, and multi-agent friendly.
- Cognee: memory should have feedback loops, not static notes.

## Design Choice

Use files as the memory substrate, compile digest artifacts for startup context, and add reports for stale/conflicting/low-confidence memory.
