---
schema: memory-page/v1
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

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| entity.personal-assistant-oc.workspace | active | 0.85 | README.md | The repository is an OpenClaw personal assistant workspace. |
| entity.personal-assistant-oc.file-memory | active | 0.95 | README.md | The repository's baseline memory is file-only. |

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
