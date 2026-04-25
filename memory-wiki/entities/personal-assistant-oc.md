---
id: entity.personal-assistant-oc
type: entity
status: active
confidence: 0.8
freshness: monthly
review_after: 2026-05-25
sources:
  - README.md
---

# Personal Assistant OC

## Summary

Personal Assistant OC is Kristian's OpenClaw personal assistant workspace. It pairs root OpenClaw instructions with a curated file-based memory wiki.

## Responsibilities

- Preserve personal context across sessions.
- Keep memory readable and reviewable.
- Avoid extra memory infrastructure by default.
- Surface stale, contested, or low-confidence facts.

## Links

- Core memory: `memory-wiki/`
- Raw memory: `memory/`
- Compile script: `scripts/compile-memory.mjs`
- Report script: `scripts/memory-report.mjs`
