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
