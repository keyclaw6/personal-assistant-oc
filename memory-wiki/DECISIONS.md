---
id: decisions.main
type: decisions
status: active
confidence: 0.8
freshness: stable
review_after: 2026-07-01
sources:
  - current setup request
---

# Decisions

Append only. If a decision changes, add a new entry that supersedes the old one.

## Startup Summary

- File-based memory is the default. Use Markdown/JSONL, compiled indexes, and plain text search before adding heavier storage.
- Borrow progressive disclosure and lifecycle ideas, but keep the starter free of vector databases, workers, and extra memory API keys.
- Preserve contradictions explicitly in `memory/conflicts/` and contested claims instead of overwriting durable memory silently.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| decision.file-memory-default | active | 0.95 | 2026-04-25 decision | Personal Assistant OC uses Markdown and JSONL files as the primary memory store. |
| decision.progressive-disclosure | active | 0.85 | docs/comparison.md | The assistant should scan an index first and fetch details on demand. |
| decision.no-heavy-storage | active | 0.90 | docs/comparison.md | The starter borrows lifecycle ideas from heavier systems without adopting SQLite, Chroma, or workers. |
| decision.conflicts-explicit | active | 0.90 | 2026-04-25 decision | Contradictory memories become conflict notes until resolved. |
| decision.two-agent-single-repo | active | 0.90 | 2026-04-26 consolidation | Keep `main` and `belief` as separate OpenClaw agents while storing both workspaces in this private repository. |

## 2026-04-25 - Use File-Based Memory By Default

- Decision: Personal Assistant OC will use Markdown/JSONL files as the primary memory store.
- Rationale: Kristian wants memory without a separate vector database or memory API key.
- Consequence: Retrieval depends on file structure, compiled digests, plain text search, and good maintenance discipline.
- Status: active.

## 2026-04-25 - Borrow Lifecycle Ideas, Not Heavy Storage

- Decision: Borrow lifecycle capture and progressive disclosure from systems like claude-mem, but do not adopt SQLite, Chroma, worker services, or extra dependencies for this starter.
- Rationale: The desired system should run with only OpenClaw, Node, Git, and a model provider.
- Status: active.

## 2026-04-25 - Preserve Conflicts Explicitly

- Decision: Contradictory memories become conflict notes until resolved.
- Rationale: Silent overwrites make personal memory untrustworthy.
- Status: active.

## 2026-04-26 - Store Both Agent Workspaces In One Private Repo

- Decision: Keep `main` and `belief` as separate OpenClaw agents, but store the belief tracking workspace under `belief-system/` in this repository.
- Rationale: Kristian wants one GitHub source of truth while preserving separate channels and memory boundaries.
- Consequence: Root instructions are for the personal/coder assistant; `belief-system/AGENTS.md` governs belief work.
- Status: active.
