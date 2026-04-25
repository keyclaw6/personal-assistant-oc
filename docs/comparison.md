# File-Based Memory Comparison

This note compares the resources researched for Personal Assistant OC.

## Recommendation

Use OpenClaw Memory Wiki plus a stricter local file lifecycle:

- raw logs in `memory/`
- curated Markdown pages in `memory-wiki/`
- compiled startup digest in `memory/_compiled/`
- generated reports for stale, contested, low-confidence, and missing-metadata memory

Do not add a vector database by default.

## OpenClaw Memory Wiki

Best fit for this project. The current OpenClaw docs describe Memory Wiki as a durable knowledge vault with notes, claims, provenance, dashboards, stale/conflict reports, and an agent digest. It also keeps memory in Markdown files under `memory-wiki/`, which matches the desired no-extra-service constraint.

Strengths:

- native OpenClaw direction
- Markdown and JSON artifacts
- provenance and conflict-aware reporting
- Obsidian-friendly structure
- digest compilation for startup context

Limits:

- the installed CLI build may not expose a top-level `openclaw wiki` command yet
- still needs disciplined file layout and prompt rules

Decision:

- Use the structure now with local scripts.
- Keep `.openclaw-wiki/config.json` ready for native plugin use later.

## awesome-openclaw-agents Memory Wiki Template

The linked template is a good small starting point: profile, stack, projects, decisions, people, and working memory. It correctly separates stable human-maintained files from mutable working memory.

Strengths:

- simple
- OpenClaw-oriented
- low token overhead
- human-editable

Limits:

- too flat for long-term personal memory
- lacks explicit raw logs, inbox, conflict queue, metadata, and generated reports

Decision:

- Keep the six-page core.
- Add lifecycle folders, metadata, reports, and compile scripts.

## claude-mem

Claude-Mem is an advanced memory system for Claude Code. It emphasizes automatic capture through hooks, lifecycle management, progressive disclosure, memory routing, and background processing.

Strengths:

- strong lifecycle model
- automatic context capture
- progressive memory disclosure
- more mature automation pattern than a single `MEMORY.md`

Limits for this project:

- uses SQLite for metadata
- uses Chroma/vector search for semantic retrieval
- runs a worker process
- adds moving parts that Kristian explicitly wants to avoid

Decision:

- Borrow the lifecycle ideas: capture, promote, compile, review.
- Do not adopt the storage architecture.

## Cognee File-Based AI Memory

Cognee's file-memory article is useful mostly as a design frame: memory should become a feedback loop, not a passive archive. The best idea to carry over is continuous restructuring and uncertainty handling.

Strengths:

- emphasizes active memory evolution
- highlights the need to keep memory fresh
- treats file memory as an inspectable substrate

Limits:

- Cognee's broader product direction includes graph/vector-style memory
- less directly OpenClaw-specific

Decision:

- Use the feedback loop idea through reports, review dates, and promotion.
- Keep implementation file-only.

## MemU File-Based Memory

MemU's file-based memory model fits the desired simplicity: category files, transparent storage, model-agnostic behavior, easy debugging, and direct human editability.

Strengths:

- file-first and model-agnostic
- easy to debug
- friendly to multiple agents
- no mandatory vector database

Limits:

- category files alone can drift or duplicate facts
- needs conflict handling and review metadata for personal memory

Decision:

- Borrow category-based organization.
- Add claim metadata, conflict queue, and generated reports.

## Final Architecture

Use file memory with four layers:

1. Capture: JSONL events and daily notes.
2. Triage: inbox and conflict files.
3. Canon: memory-wiki pages with metadata.
4. Context: compiled startup digest and index.

This gives most of the practical benefit of memory systems while keeping the stack simple enough to understand and version-control.
