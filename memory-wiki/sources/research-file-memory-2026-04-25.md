---
schema: memory-page/v1
id: source.research-file-memory-2026-04-25
type: source
status: active
confidence: 0.8
freshness: stable
review_after: 2026-07-01
sources:
  - https://github.com/thedotmack/claude-mem
  - https://www.cognee.ai/blog/deep-dives/file-based-ai-memory
  - https://memu.pro/file-based-memory
  - https://docs.openclaw.ai/plugins/memory-wiki
---

# Research Source Note - File Memory

## Summary

The research points toward a hybrid of four ideas:

- OpenClaw Memory Wiki: deterministic pages, structured claims, provenance, dashboards, and compiled digests.
- OpenClaw core memory: plain Markdown files are the base durable memory.
- Claude-Mem: lifecycle hooks and progressive disclosure are valuable, but SQLite, Chroma, and worker services are heavier than Kristian wants.
- MemU: category files are transparent, debuggable, model-agnostic, and multi-agent friendly.
- Cognee: memory should have feedback loops, not static notes.

## Design Choice

Use files as the memory substrate, compile digest artifacts for startup context, and add reports for stale/conflicting/low-confidence memory.
