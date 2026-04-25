---
id: wiki.operating-manual
type: guide
status: active
confidence: 0.8
freshness: stable
review_after: 2026-07-01
sources:
  - docs/memory-lifecycle.md
---

# WIKI.md - Memory Operating Manual

## Retrieval Order

1. `MEMORY.md`
2. `memory/_compiled/SESSION_INDEX.md`
3. `memory-wiki/WORKING.md` when current focus matters
4. Direct wiki page by filename or `rg`
5. `memory/_compiled/STARTUP.md` when broader context is needed
6. Raw logs under `memory/`

## Maintenance Cadence

- Per session: update `WORKING.md` and daily notes.
- Daily: append notable events to `memory/events/YYYY-MM-DD.jsonl`.
- Weekly: promote useful items from `memory/inbox/` and daily notes.
- Monthly: review projects, people, preferences, and stale reports.
- Quarterly: review profile, stack, decisions, and assistant behavior.

## No Vector DB

This wiki relies on clear file boundaries, deterministic names, tags, and compact compiled digests. Use text search before considering embeddings.
