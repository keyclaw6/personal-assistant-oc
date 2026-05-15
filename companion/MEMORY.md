# MEMORY.md — Memory contract

Files are the source of truth. Cognee indexes and retrieves; it does not decide
what is true.

## Layout

```txt
memory/
├── profile/          stable/current user context and preferences
├── life/             commitments, journals, briefings, reviews
├── observations/     monthly working observations
├── patterns/         evidence-backed recurring patterns
├── beliefs/          active belief experiments and logs
├── sources/books/    book notes and possible applications
└── conflicts.md      contested or corrected memory
```

Legacy `memory/shadow/` may exist for old files. New recurring self-development
work goes under `memory/patterns/`; use `shadow` as an optional tag, not as the
main storage ontology.

## What belongs where

- `profile/`: stable facts, current context, and preferences Kristian has
  confirmed.
- `life/commitments.md`: promises, follow-ups, waiting items, and deadlines.
- `life/journals/YYYY-MM-DD.md`: raw evening journals. Evidence, not analysis.
- `life/reflections/YYYY-MM-DD.md`: nightly local reviews.
- `life/dream-logs/YYYY-MM-DD.md`: operational logs for nightly reviews.
- `life/dream-staging/`: review proposals that need Kristian approval.
- `observations/YYYY-MM.md`: lightweight dated observations that are useful but
  not yet durable patterns.
- `patterns/<slug>.md`: recurring pattern files with evidence and
  counterevidence.
- `beliefs/<slug>.md`: belief work tied to a concrete experiment.
- `sources/books/<slug>.md`: book ideas, source notes, and possible practices.

## Write rules

Write aggressively only for concrete facts:

- explicit Kristian statements
- commitments and decisions
- stable preferences
- corrections
- user-approved memory updates

Write conservatively for interpretations:

- pattern hypotheses require dated evidence
- belief/shadow readings are proposals unless Kristian confirms them
- weak signals become questions, not memory claims
- books suggest lenses; they do not confirm facts about Kristian

Before changing durable memory, read the relevant file first.

Before manual compaction/reset, use `jobs/SESSION_CHECKPOINT.md` if important
session context has not yet been written to files.

## Confidence and provenance

For extracted observations, include source/date/confidence when useful:

```md
<!-- type=commitment source=journal date=YYYY-MM-DD confidence=0.90 status=proposed -->
```

Confidence guide:

- `0.90+`: explicit statement or concrete commitment
- `0.70–0.89`: strong repeated evidence
- `0.40–0.69`: plausible hypothesis, needs checking
- below `0.40`: do not promote; ask a question instead

## Corrections, conflicts, forgetting

- Corrections override older memory.
- If two claims conflict, append a short note to `memory/conflicts.md` with
  pointers to both sources.
- `forget: <fact>` means remove/update the relevant memory when clear; ask one
  clarifying question if the target is ambiguous.

## Privacy

Never quote `<private>...</private>` blocks into compiled/shared artifacts.
Secrets, tokens, OAuth credentials, and runtime state stay out of git.
