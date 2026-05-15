# MEMORY.md — Memory contract

Files are the source of truth. Cognee indexes and retrieves; it does not decide
what is true.

## Belief-change foundation

Kristian's belief-change frame is based on the Positive Drive principle from
The Freedom Model:

- People always do what currently seems best to them, given their understanding
  of the world, their perceived options, and their expected happiness/pain.
- "Most happiness" can include least pain, relief, safety, comfort, pleasure,
  meaning, or whatever seems preferable in that moment.
- Behavior follows perceived preference. If Kristian chooses pizza, chocolate,
  avoidance, honesty, or action, some belief currently makes that option seem
  best or most pleasurable overall.
- Changing behavior sustainably comes from changing understanding: what seems
  true, what seems pleasurable, what seems costly, and what seems like the best
  option.
- Kristian does not use willpower as the main tool for behavior change. He uses
  willpower, when needed, to examine and update beliefs/understanding.
- "I always do what I want" means: let current wants reveal the current belief
  system, then use the real consequences and reflection to recalibrate what is
  genuinely wanted in the future.

Albert should therefore treat unwanted or harmful behavior as information
about the current perceived-best option, not as moral failure or lack of
willpower. The useful question is: what understanding made this seem best, and
what would need to be understood differently for another option to honestly seem
better?

## Layout

```txt
memory/
├── profile/          stable/current user context and preferences
├── life/             commitments, journals, briefings, reviews
├── observations/     monthly working observations
├── patterns/         evidence-backed recurring patterns
├── beliefs/          belief understanding and integration logs
├── belief-sources/   structured imported belief candidates
├── sessions/         dated therapy/belief-chat/messenger summaries
└── conflicts.md      contested or corrected memory
```

Legacy `memory/shadow/` may exist for old files. New recurring self-development
work goes under `memory/patterns/`; use `shadow` as an optional tag, not as the
main storage ontology.

## What belongs where

- `profile/`: stable facts, current context, and preferences Kristian has
  confirmed.
- `life/commitments.md`: promises, follow-ups, waiting items, and deadlines.
  Google Tasks remains the source of truth for actionable to-dos; this file adds
  promise/waiting-for/context/task-ID metadata and should not duplicate the full
  task list.
- `life/journals/YYYY-MM-DD.md`: raw evening journals. Evidence, not analysis.
- `life/reflections/YYYY-MM-DD.md`: nightly local reviews.
- `life/dream-logs/YYYY-MM-DD.md`: operational logs for nightly reviews.
- `life/dream-staging/`: review proposals that need Kristian approval.
- `observations/YYYY-MM.md`: lightweight dated observations that are useful but
  not yet durable patterns.
- `patterns/<slug>.md`: recurring pattern files with evidence and
  counterevidence.
- `beliefs/<slug>.md`: understanding-first belief work and integration status.
- `beliefs/_index.md`: belief dashboard. Update it when a belief file is
  created, status/priority/current focus changes, or next review changes.
- `belief-sources/<slug>.md`: structured belief candidates from books/agents or
  other sources. Albert does not ingest raw books directly.
- `sessions/YYYY-MM-DD/<source>.summary.md`: therapy sessions, external
  belief-change chats, or Messenger summaries. Prefer summaries over raw
  transcripts unless Kristian explicitly wants raw storage.

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
- structured sources suggest beliefs to inspect; they do not confirm facts about
  Kristian

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
