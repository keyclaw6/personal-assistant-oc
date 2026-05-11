---
schema: memory-page/v1
id: wiki.readme
type: guide
status: active
confidence: 0.8
freshness: stable
review_after: 2026-07-01
scope: runtime
owner: Kristian Bilstrup
agent: main
visibility: local
importance: high
updated_at: 2026-04-27
sources:
  - docs/comparison.md
source_refs:
  - docs/memory-lifecycle.md
  - docs/retrieval.md
tags:
  - memory
  - schema
  - retrieval
---

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
- `reports/`: generated health, stale, conflict, and low-confidence reports
- `_views/`: human-facing indexes and dashboards

## Claim Format

Use lightweight schema v1 frontmatter on durable pages:

```yaml
---
schema: memory-page/v1
id: profile.kristian
type: profile
status: active
confidence: 0.7
freshness: stable
review_after: 2026-07-01
scope: personal
owner: Kristian Bilstrup
agent: main
visibility: local
importance: high
updated_at: 2026-04-27
sources:
  - USER.md
source_refs:
  - docs/retrieval.md
related:
  - preferences.kristian
tags:
  - profile
---
```

Required fields are `schema`, `id`, `type`, `status`, `confidence`, `freshness`, `review_after`, and `sources`. Optional fields supported by the scripts are `scope`, `owner`, `agent`, `visibility`, `importance`, `updated_at`, `source_refs`, `related`, and `tags`.

Statuses:

- `active`: good enough to use
- `draft`: captured but not fully confirmed
- `contested`: conflicts with another memory
- `retired`: no longer current, kept for history

## Write Discipline

Raw observations land in `memory/`. Durable, reviewed knowledge lands here. If an update is uncertain, leave it in `memory/inbox/` or create a conflict note.

## Retrieval Sections

Use these headings when a page needs layered retrieval:

- `## L0`: one to three lines safe for startup or index context
- `## L1`: compact task-oriented summary for search and focused retrieval
- `## L2`: detailed evidence, rationale, and edge cases

Older `## Startup Summary` and `## Summary` headings remain valid. The compile script prefers L0, then L1, then the legacy summary headings.

## Claim Rows

Durable pages can include a `## Claims` table:

```markdown
| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| preference.memory.file-first | active | 0.90 | current setup request | Use files as the baseline memory store. |
```

The compile script emits these rows into `memory/_compiled/CLAIMS.jsonl` and the session index.
