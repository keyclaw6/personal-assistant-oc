---
id: wiki.readme
type: guide
status: active
confidence: 0.8
freshness: stable
review_after: 2026-07-01
sources:
  - docs/comparison.md
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

Use lightweight frontmatter on durable pages:

```yaml
---
id: profile.kristian
type: profile
status: active
confidence: 0.7
freshness: stable
review_after: 2026-07-01
sources:
  - USER.md
---
```

Statuses:

- `active`: good enough to use
- `draft`: captured but not fully confirmed
- `contested`: conflicts with another memory
- `retired`: no longer current, kept for history

## Write Discipline

Raw observations land in `memory/`. Durable, reviewed knowledge lands here. If an update is uncertain, leave it in `memory/inbox/` or create a conflict note.

## Claim Rows

Durable pages can include a `## Claims` table:

```markdown
| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| preference.memory.file-first | active | 0.90 | current setup request | Use files as the baseline memory store. |
```

The compile script emits these rows into `memory/_compiled/CLAIMS.jsonl` and the session index.
