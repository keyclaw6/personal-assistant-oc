# Memory Lifecycle

## 1. Capture

When the assistant learns something, write it somewhere durable:

- immediate event: `memory/events/YYYY-MM-DD.jsonl`
- work summary: `memory/daily/YYYY-MM-DD.md`
- uncertain durable fact: `memory/inbox/`

Use the helper when convenient:

```powershell
npm run mem -- put --type preference --title "Short title" --summary "What should be remembered" --source conversation --confidence 0.8
```

## 2. Triage

During heartbeat or session close:

- delete noise
- archive one-off context
- promote durable facts
- create conflicts for contradictions

## 3. Promote

Promotion means moving a fact into `memory-wiki/` with:

- `schema` (`memory-page/v1`)
- `id`
- `type`
- `status`
- `confidence`
- `freshness`
- `review_after`
- `sources`

Schema v1 also supports optional metadata:

- `scope`: domain or project boundary, such as `personal`, `project`, or `runtime`
- `owner`: accountable human or maintainer
- `agent`: assistant or agent workspace that owns the page
- `visibility`: `private`, `local`, or `shareable`
- `importance`: `low`, `medium`, `high`, or `critical`
- `updated_at`: ISO date or timestamp for the last meaningful content update
- `source_refs`: additional source paths or stable external references
- `related`: page IDs, claim IDs, or paths that should be considered nearby
- `tags`: search keywords

Example:

```yaml
---
schema: memory-page/v1
id: preferences.example
type: preferences
status: active
confidence: 0.8
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
  - preference.memory.no-vector-db
tags:
  - retrieval
  - memory
---
```

Durable pages should also include a `## Claims` table:

```markdown
| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| preference.example | active | 0.80 | memory/inbox/example.md | The durable fact in one sentence. |
```

## 4. Compile

For normal use, run:

```powershell
npm run mem -- refresh
```

Use `npm run memory:compile` only when you need to regenerate compiled context without reports.

This generates:

- `memory/_compiled/SESSION_INDEX.md`
- `memory/_compiled/STARTUP.md`
- `memory/_compiled/INDEX.md`
- `memory/_compiled/CLAIMS.jsonl`
- `memory-wiki/.openclaw-wiki/cache/agent-digest.json`
- `memory-wiki/.openclaw-wiki/cache/claims.jsonl`

## 5. Review

Run:

```powershell
npm run memory:report
npm run memory:maintain
npm run mem -- check
npm run memory:smoke
```

Review stale pages, contested claims, low-confidence facts, open questions, malformed private blocks, possible secrets, and capture/privacy smoke-test failures.

## 6. Resolve Conflicts

When two memories disagree:

1. Create `memory/conflicts/YYYY-MM-DD-short-name.md`.
2. Link to both claims.
3. Describe evidence and confidence.
4. Ask Kristian if needed.
5. Update the canonical page.
6. Move the conflict note to `memory/archive/` when resolved.
