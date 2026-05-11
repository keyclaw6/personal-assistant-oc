---
schema: memory-page/v1
id: synthesis.memory-architecture
type: synthesis
status: active
confidence: 0.85
freshness: monthly
review_after: 2026-05-25
scope: runtime
owner: Kristian Bilstrup
agent: main
visibility: local
importance: high
updated_at: 2026-04-27
sources:
  - memory-wiki/sources/research-file-memory-2026-04-25.md
  - memory-wiki/sources/harness-2026-04-27.md
  - docs/comparison.md
source_refs:
  - docs/retrieval.md
  - docs/memory-lifecycle.md
  - docs/agent-memory-interface.md
related:
  - concept.file-based-memory
  - preferences.kristian
tags:
  - memory
  - retrieval
  - architecture
---

# Memory Architecture

## L0

Personal Assistant OC uses raw capture, curated wiki pages, and compiled startup context; retrieval should be index first, search or summary second, and canonical evidence last.

## L1

Personal Assistant OC uses a three-lane memory system:

1. Raw capture: append-only events and daily notes.
2. Curated wiki: durable pages with evidence, confidence, and review dates.
3. Compiled context: generated startup digest and index.

The memory system stays dependency-free: Markdown and JSONL are the source of truth, Node scripts compile and lint them, and lexical search provides deterministic retrieval without embeddings or hosted storage.

The model-facing surface stays intentionally small: `mem search`, `mem get`, `mem put`, and `mem check`. Longer `memory:*` scripts are maintenance internals, not the normal OpenClaw recall interface.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| synthesis.memory.three-lane | active | 0.85 | docs/memory-lifecycle.md | The architecture separates raw capture, curated wiki, and compiled context. |
| synthesis.memory.index-first | active | 0.90 | docs/retrieval.md | The default retrieval path is index first, page second, raw logs last. |
| synthesis.memory.short-facade | active | 0.85 | docs/agent-memory-interface.md | OpenClaw agents should use the four-verb memory facade for normal memory work. |
| synthesis.memory.robust-personal | active | 0.80 | 2026-04-25 architecture review | The architecture is robust for personal assistant memory when maintenance checks are run after edits. |

## L2

### Why This Beats A Flat MEMORY.md

A single memory file eventually becomes hard to search, hard to review, and easy to corrupt. Splitting by lifecycle and domain keeps memory usable while remaining simple.

### Why This Avoids A Vector DB

Personal memory has many facts that are small, named, and audit-sensitive. For this workload, deterministic filenames, headings, tags, and compiled digests provide enough retrieval without an opaque semantic store.

### Robustness Boundary

This is robust for personal memory, project continuity, preferences, decisions, and lightweight knowledge. It is not meant to be a high-volume event warehouse or compliance archive. If memory grows enough that filenames, headings, and compiled indexes stop being easy to scan, add a local index before adding hosted memory infrastructure.
