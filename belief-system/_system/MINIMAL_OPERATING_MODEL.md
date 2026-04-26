# Minimal Operating Model

This file explains the smallest version of the system that still preserves the full function.

## Core Loop

1. User says what they want in natural language.
2. Load only relevant context.
3. Run the session or source pass.
4. Save a deterministic clarification.
5. Update belief status, experiments, and suggestion queue.
6. Review patterns periodically.

## Essential Files

For most normal work, the agent only needs:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `skills/belief_change_system/SKILL.md`
- `_system/protocols/14_capability_routing.md`
- `_system/protocols/17_context_loading_policy.md`
- The relevant protocol for the task.
- The relevant belief/source/session files.

## Do Not Load By Default

- Every session transcript.
- Every book folder.
- Every protocol.
- Every prompt.
- Every review.

Load broad context only for hardening, progress export, or major pattern analysis.

## Why The System Has Many Files

The files are not meant to all be in context at once. They are stable shelves:

- Protocols define how to do tasks.
- Prompts define role behavior.
- Templates define output shapes.
- Schemas define machine-readable records.
- Belief files store memory.
- Session folders store evidence.
- Reviews synthesize patterns.

## Best Default Use

Use the system with one clear request:

```text
I want to work on the belief: ...
```

or:

```text
Ingest chapter 3 of this book.
```

or:

```text
Create an external chat prompt for this belief.
```

The agent should route the request instead of loading everything.

## Sub-Agents

The main agent may use sub-agents for bounded tasks such as chapter ingestion, pattern analysis, deterministic clarification, audits, or experiment design.

The main agent should not delegate the live belief-change conversation itself.
