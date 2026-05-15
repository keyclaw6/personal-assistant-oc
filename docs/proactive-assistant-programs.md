# Proactive Assistant Programs

## Morning Brief

Schedule: every day at 07:30 Europe/Copenhagen.

Goal: give Kristian a short private phone-readable start-of-day brief.

Delivery: Messenger (primary). File fallback writes to
`companion/memory/life/briefings/YYYY-MM-DD.md`. Android notification fallback
is future/optional unless explicitly wired.

Required checks:

1. Calendar events today via Composio Calendar.
2. Tasks/reminders due today, overdue, or stale via Composio Google Tasks.
3. Commitments due today, overdue, or waiting for reply (`companion/memory/life/commitments.md`).
4. New or unanswered Gmail messages via Composio Gmail tools.
5. Active beliefs or patterns only when relevant today.
6. Yesterday's journal/nightly review if it produced a useful morning note.

Output shape follows `companion/jobs/MORNING_BRIEF.md`:

```txt
Morning, Kristian.

Today:
- Calendar:
- Must-not-miss:
- Commitments:
- Suggested priority:

Watch:
- One evidence-backed risk/pattern, only if useful.

Optional:
- Want me to summarize mail?
```

If a source is unavailable, include a one-line note and continue with the remaining sources.

## Commitment Tracker

Commitments live in `companion/memory/life/commitments.md` as a rolling table.

Morning brief should show:

- overdue commitments
- due today
- waiting items older than their review date

## Gmail Event Handling (future/optional)

No Gmail webhook handler is part of the active runtime yet. If enabled later, it
should:

1. Record the event source and message/thread id.
2. Classify urgency and likely required action.
3. Detect possible commitments.
4. Avoid replying automatically.
5. Surface only actionable items in the next brief unless urgency rules say to alert earlier.

## Session Capture (explicit workflow only)

When a capture workflow is explicitly run after a meaningful Messenger
conversation:

1. Write `companion/memory/sessions/YYYY-MM-DD/transcript.md` — raw conversation.
2. Write `companion/memory/sessions/YYYY-MM-DD/clarification.md` — deterministic fact-only summary.
3. Next morning brief may include the concrete captures.

Messenger message `forget: <fact>` asks Companion to delete or edit the relevant
file when the target is clear; Cognee re-syncs.

## Session Checkpoint

Run before manual compaction/reset, and optionally before long maintenance
sessions. This is not proactive clearing; it is a safety step that writes
durable state before context may be summarized or replaced.

Instructions live in `companion/jobs/SESSION_CHECKPOINT.md`.

Allowed writes:

- `companion/memory/observations/YYYY-MM.md`
- `companion/memory/life/commitments.md`
- `companion/memory/conflicts.md`
- `companion/memory/life/dream-staging/` for review proposals

The checkpoint should reply `NO_REPLY` when nothing durable should be saved.

## Evening Journal

Schedule: every day at 21:00 Europe/Copenhagen.

Goal: if no journal exists for today, send Kristian a short Messenger reminder
asking whether he wants to journal.

Journal file:

```txt
companion/memory/life/journals/YYYY-MM-DD.md
```

Prompt shape:

1. What actually happened today?
2. What mattered, emotionally or practically?
3. What did you avoid, postpone, or keep circling?
4. Any commitments, replies, promises, or decisions?
5. What does tomorrow need from you?
6. Anything from today that should not be remembered?

If Kristian says `skip journal`, write a skipped marker for the date and do not
nag again that evening.

## Nightly Review

Schedule: nightly while Kristian sleeps.

Goal: make life easier tomorrow by reviewing yesterday's local memory and
journal material.

Allowed:

- read local memory files
- write `companion/memory/life/reflections/YYYY-MM-DD.md`
- write `companion/memory/life/dream-logs/YYYY-MM-DD.md`
- write review proposals under `companion/memory/life/dream-staging/`

Not allowed in this job:

- sensor sweeps
- ambient actions
- external service changes
- emergency surfacing
- inner monologue artifacts
- auto-promoting belief/pattern conclusions into truth
