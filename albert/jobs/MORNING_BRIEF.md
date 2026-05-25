# MORNING_BRIEF.md

## Purpose

Give Kristian a short, private, phone-readable start to the day.

## Inputs

- today's calendar via Composio Calendar
- due/overdue/stale Google Tasks via Composio Tasks
- unread/important Gmail headline counts via Composio Gmail
- `memory/life/commitments.md`
- `memory/profile/current-context.md`
- yesterday's journal/review when relevant
- active belief or pattern files only if they matter today or Kristian wants a
  nudge

## Output shape

```txt
Morning, Kristian.

- Calendar: only if something is on today's calendar.
- Mail: only if there is a real today-relevant item or deadline.
- Commitments: only if there is a real today-relevant commitment.
- Priority: one short suggestion, only if useful.
- Watch: one short evidence-backed risk/pattern, only if useful.
```

## Rules

- Keep it short. Aim for a few lines, not a mini-briefing.
- Do not dump email.
- Only include categories that actually have something useful today.
- Do not say that a category is empty or unavailable; just omit it.
- Do not include options, menus, or follow-up offers.
- Do not include a belief/pattern dashboard unless it is relevant today.
- Belief nudges should point to what still does not land or what needs review,
  not default to behavior experiments.
- If a source is unavailable, say so in one line and continue.
- Do not make external changes.
- Google Tasks is the source of truth for actionable to-dos. Use
  `memory/life/commitments.md` for promise/waiting-for/context only.
