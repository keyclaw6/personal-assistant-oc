# Memory Update Policy

This policy keeps the system adaptive without letting agents rewrite the user's self-model too aggressively.

## Memory Locations

Durable memory may be stored in:

- `01_profile/*.md`
- `03_beliefs/**/belief.md`
- `04_sessions/<session-id>/**`
- `05_experiments/**`
- `06_reviews/**`
- `08_metrics/progress_ledger.csv`

## Marginal Update Rule

Normal sessions should make small, evidence-linked updates:

- Add a session ID.
- Add a new example.
- Update a score.
- Add a candidate belief.
- Move one belief status.
- Add or close one experiment.
- Add one pattern hypothesis with low confidence.

Avoid broad rewrites of profile, pattern, or belief files unless the user explicitly requests a redesign or a hardening pass.

## Evidence Rule

Every durable memory update should be traceable to one of:

- User direct statement.
- Session transcript.
- Deterministic clarification.
- Book/source note.
- Experiment result.
- Explicit user decision.

## Pattern Rule

Do not add established patterns from one session. Use:

- `low` for a single signal.
- `medium` for repeated signals across three or more sessions or two domains.
- `high` for repeated signals across time, contexts, and behavior.

## Profile Updates

Profile updates should use this format:

```text
Date:
Source:
Confidence:
Update:
Why it matters:
Revisit condition:
```

## System Memory Versus User Memory

Do not confuse system maintenance with user memory.

- User memory: beliefs, patterns, values, experiments, source insights.
- System memory: protocols, schemas, OpenClaw setup, heartbeat, hardening reports.

System memory changes require audit notes. User memory changes require session/source evidence.
