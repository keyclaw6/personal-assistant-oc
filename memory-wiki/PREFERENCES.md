---
id: preferences.kristian
type: preferences
status: draft
confidence: 0.7
freshness: stable
review_after: 2026-06-01
sources:
  - USER.md
  - current setup request
---

# Preferences

## Startup Summary

Prefer a smart file structure for memory over a vector database or hosted memory service. The assistant should need only a model provider credential, not separate memory API keys.

## Memory Preferences

- File-based memory by default.
- No vector database by default.
- No extra memory API keys by default.
- Human-readable Markdown preferred.
- Git history should make memory changes auditable.
- Conflicts should be surfaced, not silently overwritten.
- Memory should update continuously through events, daily notes, and curated promotion.

## Assistant Preferences To Confirm

- Tone and name.
- Proactivity level.
- Which external actions require explicit confirmation.
