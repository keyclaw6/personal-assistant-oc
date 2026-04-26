# Sub-Agent Orchestration

Use sub-agents to keep the main coaching context smaller and to parallelize bounded background work.

## Principle

The main `belief-coach` agent owns the user relationship, session continuity, final decisions, and durable memory updates. Sub-agents are temporary specialists.

## Good Sub-Agent Tasks

Use sub-agents for bounded work such as:

- Chapter ingestion.
- Source-to-belief extraction.
- Deterministic clarification from transcript.
- Pattern analysis across many completed sessions.
- Experiment design.
- Completion readiness review.
- Safety or integrity audit.
- Progress export drafting.
- System hardening audit.

## Do Not Delegate

Do not delegate:

- The live belief-change conversation.
- User-owned completion decisions.
- Final durable memory writes without main-agent review.
- Broad system redesign.
- Sensitive coaching moments where tone and continuity matter.

## Context Rule

OpenClaw sub-agents receive limited automatic context. Current OpenClaw docs state that sub-agent context injects `AGENTS.md` and `TOOLS.md`, but not `SOUL.md`, `HEARTBEAT.md`, or other root files.

Therefore every sub-agent task must explicitly say:

- Which files to read.
- Whether it may write files.
- Which files or folder it owns.
- What output format to return.
- Whether it must avoid protected files.

## Write Policy

Default sub-agent mode is read-only plus returned recommendation.

Sub-agents may write files only when the main agent gives them a narrow write scope, such as:

```text
Write only inside 02_sources/books/<book-slug>/chapters/003-title/
```

or:

```text
Write only 04_sessions/<session-id>/04_deterministic_clarification.json
```

Sub-agents must never rewrite:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `README.md`
- `HEARTBEAT.md`
- `skills/**/SKILL.md`
- `_system/protocols/**`
- `_system/schemas/**`
- `_system/openclaw/**`

unless the user explicitly asked for system hardening and the sub-agent is assigned that exact folder.

## Recommended OpenClaw Settings

Use conservative sub-agent limits:

```json5
subagents: {
  maxConcurrent: 3,
  maxChildrenPerAgent: 3,
  maxSpawnDepth: 1,
  runTimeoutSeconds: 900
}
```

Rationale:

- The main agent can spawn helpers.
- Helpers cannot spawn their own helpers.
- Context stays bounded.
- Runaway fan-out is avoided.

Enable `maxSpawnDepth: 2` only if you intentionally want an orchestrator pattern for large source-ingestion projects.

## Spawn Prompt Template

When spawning a sub-agent, use this shape:

```text
You are a bounded specialist in the Belief Change System.

Task:

Read these files:

Write permission:

Protected files:
Do not modify protected system files.

Output:

Return:
- Findings.
- Files read.
- Files changed, if any.
- Confidence.
- Remaining questions.
```

## Main-Agent Review

After a sub-agent finishes, the main agent should:

1. Read the returned result.
2. Review any changed files.
3. Integrate only what is supported.
4. Explain the user-facing result in normal language.

## Done Means

Sub-agents reduce context and workload without taking over the user's belief work or making unreviewed memory changes.
