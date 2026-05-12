# Proactive Assistant Programs

## Morning Brief

Schedule: every day at 07:30 Europe/Copenhagen.

Goal: give Kristian a short private phone-readable start-of-day brief.

Delivery: Messenger (primary). Fallback: Android `system.notify` to Kristian's S22. Final fallback: write to `companion/memory/life/briefings/YYYY-MM-DD.md` and surface on next heartbeat.

Required checks:

1. Calendar events today via `gog`.
2. Tasks/reminders due today, overdue, or stale via `gog tasks`.
3. Commitments due today, overdue, or waiting for reply (`companion/memory/life/commitments.md`).
4. New or unanswered Gmail messages via `gog --gmail-no-send`.
5. Active/testing beliefs with day count and last-touched (`companion/memory/beliefs/_index.md`).
6. Captured yesterday — auto-promoted items from `companion/memory/sessions/YYYY-MM-DD/clarification.md`.

Output shape:

```md
# Morning Brief — YYYY-MM-DD

## Schedule
- ...

## Commitments
- ...

## Beliefs in Progress
- ...

## Mail
- ...

## Captured Yesterday
- ...
```

If a source is unavailable, include a one-line note and continue with the remaining sources.

## Commitment Tracker

Commitments live in `companion/memory/life/commitments.md` as a rolling table.

Morning brief should show:

- overdue commitments
- due today
- waiting items older than their review date

## Gmail Event Handling

When Gmail webhooks are enabled, the event handler should:

1. Record the event source and message/thread id.
2. Classify urgency and likely required action.
3. Detect possible commitments.
4. Avoid replying automatically.
5. Surface only actionable items in the next brief unless urgency rules say to alert earlier.

## Auto-Capture

After each meaningful Messenger conversation (5+ minute pause defines end):

1. Write `companion/memory/sessions/YYYY-MM-DD/transcript.md` — raw conversation.
2. Write `companion/memory/sessions/YYYY-MM-DD/clarification.md` — deterministic fact-only summary.
3. Next morning brief includes a "captured yesterday" section.

Messenger message `forget: <fact>` deletes or edits the relevant file; Cognee re-syncs.
