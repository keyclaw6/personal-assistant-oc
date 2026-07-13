# Domain: ai-releases

AI/LLM industry events: model releases and announcements, model sightings
(API strings, stealth checkpoints on arenas), benchmark positions, org events
(launches, acquisitions, departures). This is the highest-information-density
leaker ecosystem anywhere — and the most crowded: assume the market's crowd also
lives on X. The system's edge must come from measured leaker reliability, not
from being first.

## Polymarket market families seen in this domain

- "Will <lab> release <model> by <date>?" — release-timing
- "Will <model> be #1 on LMArena / <benchmark> by <date>?" — benchmark-position
- "Will OpenAI/Google/Anthropic announce X by Y?" — org-event
- Occasional one-offs (pricing, lawsuits, departures) — org-event

Resolution quirks to respect (matching precision!):
- "Release" often means general public availability — a waitlist, a stealth
  checkpoint, or an API-only drop may NOT resolve YES. Read criteria carefully.
- Date boundaries are exact (timezone of resolution source matters).
- Benchmark markets resolve on a specific leaderboard snapshot.

## Call classes

`release-timing`, `model-existence`, `feature-sighting`, `benchmark-position`,
`org-event`. Reuse these; add new ones sparingly.

## Source notes

- X is the primary leak surface; Reddit (r/LocalLLaMA, r/singularity, r/OpenAI)
  mirrors X leaks within minutes-to-hours and adds original string-hunting.
- Non-social tells worth adding later as pseudo-leakers (deterministic sources):
  OpenRouter new-slug appearances, LMArena stealth checkpoint names, app-store
  changelog diffs. Deferred — v0 is X + Reddit only.

## Sweep sources (community, not leakers — explorer fodder)

reddit:r/LocalLLaMA, reddit:r/singularity
