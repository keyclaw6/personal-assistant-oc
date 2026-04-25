# Memory Lifecycle

## 1. Capture

When the assistant learns something, write it somewhere durable:

- immediate event: `memory/events/YYYY-MM-DD.jsonl`
- work summary: `memory/daily/YYYY-MM-DD.md`
- uncertain durable fact: `memory/inbox/`

## 2. Triage

During heartbeat or session close:

- delete noise
- archive one-off context
- promote durable facts
- create conflicts for contradictions

## 3. Promote

Promotion means moving a fact into `memory-wiki/` with:

- `id`
- `type`
- `status`
- `confidence`
- `freshness`
- `review_after`
- `sources`

## 4. Compile

Run:

```powershell
npm run memory:compile
```

This generates:

- `memory/_compiled/STARTUP.md`
- `memory/_compiled/INDEX.md`
- `memory-wiki/.openclaw-wiki/cache/agent-digest.json`

## 5. Review

Run:

```powershell
npm run memory:report
```

Review stale pages, contested claims, low-confidence facts, and open questions.

## 6. Resolve Conflicts

When two memories disagree:

1. Create `memory/conflicts/YYYY-MM-DD-short-name.md`.
2. Link to both claims.
3. Describe evidence and confidence.
4. Ask Kristian if needed.
5. Update the canonical page.
6. Move the conflict note to `memory/archive/` when resolved.
