---
id: concept.file-based-memory
type: concept
status: active
confidence: 0.85
freshness: quarterly
review_after: 2026-07-01
sources:
  - docs/comparison.md
---

# File-Based Memory

## Summary

File-based memory treats persistent assistant memory as structured text files. The assistant captures raw observations, promotes stable facts into durable pages, and compiles compact digests for cheap startup context.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| concept.file-memory.transparent | active | 0.90 | docs/comparison.md | File-based memory is transparent, auditable, and model-agnostic. |
| concept.file-memory.progressive | active | 0.85 | docs/retrieval.md | File-based memory should be retrieved progressively rather than loaded all at once. |

## Why It Fits This Assistant

- Transparent: humans can inspect and edit memory.
- Portable: works across models.
- Auditable: Git shows every memory change.
- Cheap: no vector database or separate memory service.
- Robust: conflicts and stale pages are visible.

## Retrieval Pattern

1. Read compact digest.
2. Search filenames/headings/tags.
3. Read relevant wiki pages.
4. Fall back to raw logs only when needed.
