# Proactive Assistant Programs

## Morning Brief

Schedule: every day at 07:30 Europe/Copenhagen.

Goal: give Kristian a short private phone-readable start-of-day brief.

Delivery: prefer the paired Android node `Kristian's S22` via `system.notify` while no normal chat channel is configured. When a private channel is later bound, deliver there instead.

Required checks:

1. Calendar events today and tomorrow morning via `gog`.
2. Tasks/reminders due today, overdue, or stale via `gog tasks`.
3. Commitments due today, overdue, or waiting for reply.
4. New or unanswered Gmail messages via `gog --gmail-no-send`.
5. Drive files changed recently via `gog drive` only if relevant to today's work.
6. Open memory inbox or conflicts that need a decision.

Output shape:

```md
## Morning Brief

### Today
- ...

### Calendar
- ...

### Tasks
- ...

### Unanswered Mail
- ...

### Commitments
- ...

### Watch
- ...
```

If a source is unavailable, include a one-line `Unavailable` note and continue with the remaining sources.

## Commitment Tracker

Commitments live under `memory/commitments/`.

Lifecycle:

- `candidate`: extracted but uncertain.
- `active`: likely real and needs tracking.
- `waiting`: Kristian is waiting on someone else.
- `done`: completed.
- `dropped`: intentionally no longer tracked.
- `contested`: source conflict or uncertainty.

Morning brief should show:

- overdue active commitments
- due today
- waiting items older than their review date
- ambiguous candidate commitments that need Kristian's decision

## Gmail Event Handling

When Gmail webhooks are enabled, the event handler should:

1. Record the event source and message/thread id.
2. Classify urgency and likely required action.
3. Detect possible commitments.
4. Avoid replying automatically.
5. Surface only actionable items in the next brief unless urgency rules say to alert earlier.

Urgent examples:

- time-sensitive scheduling conflicts
- explicit same-day deadlines
- account/security alerts
- direct requests from important contacts

## Friday Belief Check

Schedule: every Friday, Europe/Copenhagen.

Agent: `belief`.

Goal: if no qualifying belief work happened during the last 7 days, send Kristian a short direct reminder that the belief work matters and suggest one session today.

Delivery: paired Android node notification unless a separate belief channel is configured.

A qualifying belief session requires a folder in `belief-system/04_sessions/` with `00_manifest.json` and at least one meaningful output file, such as:

- `03_interpretive_analysis.md`
- `04_deterministic_clarification.json`
- `06_next_actions.md`

Do not create or modify belief session files from the reminder job.
