# NIGHTLY_REVIEW.md

## Purpose

Make tomorrow easier by reviewing yesterday's local memory and writing a short,
evidence-led reflection. This is a local review/consolidation job, not a dream,
sensor sweep, or inner monologue.

## Inputs

Target date: yesterday in Europe/Copenhagen unless the cron prompt names a date.

Read local files only:

- `memory/life/journals/YYYY-MM-DD.md`
- `memory/sessions/YYYY-MM-DD/*.summary.md`, if present
- `memory/life/commitments.md`
- `memory/profile/current-context.md`
- active files under `memory/beliefs/`
- active files under `memory/patterns/`
- recently touched files under `memory/belief-sources/`
- recent files under `memory/life/reflections/`
- `memory/conflicts.md`

Do not call Gmail, Calendar, Tasks, LinkedIn, web search, or other external
services from this job.

## Outputs

Write:

- `memory/life/reflections/YYYY-MM-DD.md`
- `memory/life/dream-logs/YYYY-MM-DD.md` (legacy folder name; operational log)

If a recurring pattern deserves review, write a proposal under:

- `memory/life/dream-staging/YYYY-MM-DD-<slug>.md`

If overwriting an existing reflection/log, copy the old file to
`memory/life/dream-backups/` first.

## Reflection shape

```md
# Nightly Review — YYYY-MM-DD

<!-- review:date=YYYY-MM-DD review:source=local-files review:status=reviewable -->

## What happened

## Commitments detected

## Useful follow-up

## Possible pattern signals

## Belief understanding signals

## Suggested morning note

## Memory writes or proposals

## Uncertainties
```

## Rules

- Facts, hypotheses, and proposed actions must be separate.
- Never delete source material.
- Never auto-promote a recurring pattern into durable truth.
- Future-dated commitments and deadlines are protected.
- Weak pattern evidence becomes a question or staging proposal, not a claim.
- Belief updates should focus on what landed, what did not land, and what
  remains unresolved. Do not require an experiment.
- No clinical diagnosis, no pathologizing, no mystical language.

End by replying only:

```txt
NIGHTLY_REVIEW_OK <reflection-path> <dream-log-path>
```
