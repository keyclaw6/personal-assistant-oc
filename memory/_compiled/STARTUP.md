# Compiled Startup Memory

Prefer `SESSION_INDEX.md` first. Use this file when a fuller startup digest is needed.

## Profile

Source: `PROFILE.md` | ID: `profile.kristian` | Cost: ~275 tokens

Kristian wants a personal OpenClaw assistant with durable memory that is file-based, inspectable, Git-backed, and cheap to operate. The memory system should avoid vector databases and extra API keys by default.

## Preferences

Source: `PREFERENCES.md` | ID: `preferences.kristian` | Cost: ~311 tokens

Prefer a smart file structure for memory over a vector database or hosted memory service. The assistant should need only a model provider credential, not separate memory API keys.

## Stack

Source: `STACK.md` | ID: `stack.local-openclaw` | Cost: ~293 tokens

OpenClaw runs locally on Windows with Node and a loopback gateway. Memory is maintained with Markdown files and dependency-free Node scripts.

## Projects

Source: `PROJECTS.md` | ID: `projects.active` | Cost: ~230 tokens

Active project: build a personal OpenClaw assistant repository with a file-based memory system and no vector database dependency.

## Decisions

Source: `DECISIONS.md` | ID: `decisions.main` | Cost: ~535 tokens

- File-based memory is the default. Use Markdown/JSONL, compiled indexes, and plain text search before adding heavier storage.
- Borrow progressive disclosure and lifecycle ideas, but keep the starter free of vector databases, workers, and extra memory API keys.
- Preserve contradictions explicitly in `memory/conflicts/` and contested claims instead of overwriting durable memory silently.

## People

Source: `PEOPLE.md` | ID: `people.main` | Cost: ~199 tokens

Kristian is the primary human for this assistant. Other people should only be added when useful and safe.

## Working

Source: `WORKING.md` | ID: `working.current` | Cost: ~317 tokens

- Current work: finish the polishing pass for the file-only memory system in Personal Assistant OC.
- Keep retrieval index-first, keep stable memory concise, and regenerate compiled artifacts after edits.
- Next practical test after model auth: start OpenClaw with this workspace and confirm the assistant reads `MEMORY.md`, then `SESSION_INDEX.md`, then only relevant pages.

## Personal Assistant OC

Source: `entities/personal-assistant-oc.md` | ID: `entity.personal-assistant-oc` | Cost: ~225 tokens

Personal Assistant OC is Kristian's OpenClaw personal assistant workspace. It pairs root OpenClaw instructions with a curated file-based memory wiki.

## File-Based Memory

Source: `concepts/file-based-memory.md` | ID: `concept.file-based-memory` | Cost: ~265 tokens

File-based memory treats persistent assistant memory as structured text files. The assistant captures raw observations, promotes stable facts into durable pages, and compiles compact digests for cheap startup context.

## Memory Architecture

Source: `syntheses/memory-architecture.md` | ID: `synthesis.memory-architecture` | Cost: ~280 tokens

Personal Assistant OC uses a three-lane memory system:

1. Raw capture: append-only events and daily notes.
2. Curated wiki: durable pages with evidence, confidence, and review dates.
3. Compiled context: generated startup digest and index.

## Research Source Note - File Memory

Source: `sources/research-file-memory-2026-04-25.md` | ID: `source.research-file-memory-2026-04-25` | Cost: ~187 tokens

The research points toward a hybrid of four ideas:

- OpenClaw Memory Wiki: deterministic pages, structured claims, provenance, dashboards, and compiled digests.
- OpenClaw core memory: plain Markdown files are the base durable memory.
- Claude-Mem: lifecycle hooks and progressive disclosure are valuable, but SQLite, Chroma, and worker services are heavier than Kristian wants.
- MemU: category files are transparent, debuggable, model-agnostic, and multi-agent friendly.
- Cognee: memory should have feedback loops, not static notes.
