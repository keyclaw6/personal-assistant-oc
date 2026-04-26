---
id: projects.active
type: projects
status: active
confidence: 0.7
freshness: monthly
review_after: 2026-05-25
sources:
  - current setup request
---

# Projects

## Startup Summary

Active project: build a personal OpenClaw assistant repository with a file-based memory system and no vector database dependency.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| project.personal-assistant-oc.active | active | 0.90 | current setup request | The active project is the `personal-assistant-oc` OpenClaw workspace. |
| project.personal-assistant-oc.file-only | active | 0.95 | current setup request | The repository should work without a vector database or memory API service. |
| project.belief-system.integrated | active | 0.90 | 2026-04-26 consolidation | The belief tracking system is now included under `belief-system/` in this repository as the separate `belief` agent workspace. |

## Active

### Personal Assistant OC

- Goal: OpenClaw personal assistant workspace with durable file memory.
- Repository: `personal-assistant-oc`
- Status: active hardening and consolidation.
- Memory policy: files first, no vector DB by default.
- Included specialist workspace: `belief-system/` for the separate belief agent.

## Parked

- None yet.

## Done

- Reinstalled OpenClaw locally.
- Initialized OpenClaw workspace and gateway.
- Verified both `main` and `belief` agent turns through the local Gateway.
