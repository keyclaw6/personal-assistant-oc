# THERAPY_SESSION_IMPORT.md

## Purpose

Import therapy sessions, therapist notes, or belief-change chats with another
language model so Companion can track what Kristian said, what landed, what did
not land, and which beliefs are changing.

This is high-value evidence because it contains Kristian's own words and
reactions. Treat it carefully.

## Storage

Prefer summaries over raw transcripts unless Kristian explicitly asks to store
raw text.

Write dated files under:

```txt
memory/sessions/YYYY-MM-DD/<source>.summary.md
```

Examples:

```txt
memory/sessions/2026-05-15/therapy.summary.md
memory/sessions/2026-05-15/belief-chat-claude.summary.md
```

If raw transcript storage is explicitly requested, use:

```txt
memory/sessions/YYYY-MM-DD/<source>.raw.md
```

and mark it `privacy: high`.

## Extract

Separate clearly:

- Kristian's own words
- therapist/other-agent interpretations
- what Kristian said landed
- what did not land
- beliefs named
- proposed new understandings
- patterns noticed
- contradictions or tensions
- open questions
- possible belief file updates
- privacy exclusions / things not to remember

## Summary shape

```md
# Session Import — YYYY-MM-DD — <source>

Source type: therapy | external-belief-chat | coaching | other
Privacy: normal | high
Imported:

## Kristian's words / positions

## What landed

## What did not land

## Beliefs named or updated

## Proposed new understandings

## Patterns or contradictions

## Open questions

## Proposed memory updates

## Do not remember / privacy exclusions
```

## Rules

- Do not treat another model's or therapist's interpretation as Kristian's
  confirmed belief.
- Do not store details Kristian says should not be remembered.
- Do not diagnose or pathologize.
- Do not auto-mark beliefs as integrated.
- Belief updates should preserve uncertainty and source.
- If updating a belief file, update `memory/beliefs/_index.md` in the same pass.

End with:

```txt
THERAPY_SESSION_IMPORT_OK <paths-written>
```
