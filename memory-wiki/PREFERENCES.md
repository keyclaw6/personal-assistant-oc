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

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| preference.memory.no-vector-db | active | 0.95 | current setup request | Use file-based memory without a vector database by default. |
| preference.memory.no-extra-api-keys | active | 0.90 | current setup request | Do not require a separate memory or embedding API key for baseline memory. |
| preference.memory.conflicts-visible | active | 0.85 | current setup request | Surface memory conflicts instead of silently overwriting them. |

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
