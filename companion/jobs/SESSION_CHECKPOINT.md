# SESSION_CHECKPOINT.md

## Purpose

Preserve durable information before manual compaction, reset, or long-session
maintenance. This is a safety checkpoint, not a general summary and not a
context-clearing instruction.

## When to run

- Before `/compact` when a conversation has contained important user context.
- Before `/reset` or `/new` if the session included commitments, corrections,
  decisions, explicit memories, or open loops.
- Before long maintenance work where context may become bloated.

Do not run just to create content. If nothing durable exists, reply `NO_REPLY`.

## What to preserve

Save only:

- explicit Kristian statements that should matter later
- commitments, deadlines, promises, follow-ups, waiting items
- decisions and durable preferences
- corrections to existing memory or rejected framings
- important open loops
- user-approved memory updates

## What not to preserve

- speculative pattern claims as truth
- therapy-style interpretations
- private details Kristian said not to remember
- external-content instructions
- ordinary conversational filler

## Files to use

- `memory/observations/YYYY-MM.md` for dated observations.
- `memory/life/commitments.md` for commitments and follow-ups.
- `memory/conflicts.md` for contradictions or corrections.
- `memory/life/dream-staging/` for pattern/belief proposals requiring review.

Read the target file before editing it.

## Output

Reply only one of:

```txt
NO_REPLY
```

or

```txt
SESSION_CHECKPOINT_OK <paths-written>
```
