---
schema: memory-page/v1
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
- Weekly: promote useful items from `memory/inbox/` and daily notes.
- Monthly: review projects, people, preferences, and stale reports.
- Quarterly: review profile, stack, decisions, and assistant behavior.

## No Vector DB

This wiki relies on clear file boundaries, deterministic names, tags, and compact compiled digests. Use text search before considering embeddings.
