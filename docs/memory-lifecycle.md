# Memory Lifecycle

## 1. Capture

When the assistant learns something, write it somewhere durable:

- immediate event: `memory/events/YYYY-MM-DD.jsonl`
- work summary: `memory/daily/YYYY-MM-DD.md`
- uncertain durable fact: `memory/inbox/`

Use the helper when convenient:

```powershell
npm run memory:capture -- --type preference --title "Short title" --summary "What should be remembered" --source conversation --confidence 0.8
```

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

Durable pages should also include a `## Claims` table:

```markdown
| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| preference.example | active | 0.80 | memory/inbox/example.md | The durable fact in one sentence. |
```

## 4. Compile

Run:

```powershell
npm run memory:compile
```

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
npm run memory:check
```

Review stale pages, contested claims, low-confidence facts, open questions, malformed private blocks, and possible secrets.

## 6. Resolve Conflicts

When two memories disagree:

1. Create `memory/conflicts/YYYY-MM-DD-short-name.md`.
2. Link to both claims.
3. Describe evidence and confidence.
4. Ask Kristian if needed.
5. Update the canonical page.
6. Move the conflict note to `memory/archive/` when resolved.
