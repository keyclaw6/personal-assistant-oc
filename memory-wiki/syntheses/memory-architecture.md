---
id: synthesis.memory-architecture
type: synthesis
status: active
confidence: 0.85
freshness: monthly
review_after: 2026-05-25
sources:
  - memory-wiki/sources/research-file-memory-2026-04-25.md
  - docs/comparison.md
---

# Memory Architecture

## Summary

Personal Assistant OC uses a three-lane memory system:

1. Raw capture: append-only events and daily notes.
2. Curated wiki: durable pages with evidence, confidence, and review dates.
3. Compiled context: generated startup digest and index.

## Why This Beats A Flat MEMORY.md

A single memory file eventually becomes hard to search, hard to review, and easy to corrupt. Splitting by lifecycle and domain keeps memory usable while remaining simple.

## Why This Avoids A Vector DB

Personal memory has many facts that are small, named, and audit-sensitive. For this workload, deterministic filenames, headings, tags, and compiled digests provide enough retrieval without an opaque semantic store.
