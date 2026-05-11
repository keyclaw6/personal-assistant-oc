---
name: belief_change_system
description: Work with the user's structured belief-change workspace, including belief sessions, book ingestion, session closing, pattern analysis, experiments, and completion marks.
metadata: {"openclaw":{"always":true}}
---

# Belief Change System Skill

Use this skill whenever the user wants to:

- Work on a belief.
- Ingest a book or source for belief change.
- End a belief session.
- Review patterns across sessions.
- Create or evaluate experiments.
- Mark a belief complete.
- Ask what belief to work on next.
- Run a weekly, monthly, or hardening review.
- Generate a progress report or export.
- Export a focused external-chat prompt.
- Import an external-chat transcript.

## Capability Routing

- Natural language interface: use `_system/protocols/20_natural_language_interface.md` before asking the user for internal commands.
- Belief session: use `09_prompts/belief_coach_agent.md` and `_system/protocols/02_session_protocol.md`.
- Book/source ingestion: use `09_prompts/source_librarian_agent.md` and `_system/protocols/03_book_ingestion_protocol.md`.
- Chapter/section ingestion: use `_system/protocols/18_chapter_ingestion_protocol.md`.
- Session clarification: use `09_prompts/deterministic_clarifier_agent.md` and `_system/protocols/09_deterministic_clarification_protocol.md`.
- Pattern review: use `09_prompts/pattern_analyst_agent.md` and `_system/protocols/04_pattern_analysis_protocol.md`.
- Experiment design: use `09_prompts/experiment_designer_agent.md`.
- Completion review: use `09_prompts/completion_reviewer_agent.md` and `_system/protocols/05_completion_protocol.md`.
- Safety or integrity audit: use `09_prompts/auditor_agent.md`.
- Next-belief suggestion: use `_system/protocols/08_suggestion_ranking_protocol.md`.
- Reframing material: use `_system/protocols/10_reframing_material_protocol.md`.
- Hardening: use `_system/protocols/12_system_hardening_protocol.md`.
- Progress export: use `_system/protocols/16_progress_export_protocol.md`.
- External chat export/import: use `_system/protocols/19_external_chat_workflow.md`.
- Sub-agent orchestration: use `_system/protocols/21_subagent_orchestration.md` for bounded background work.

## Workspace Files

Read the root files first:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `README.md`

Then use:

- `_system/protocols`
- `_system/templates`
- `_system/schemas`
- `09_prompts`
- `01_profile`
- `03_beliefs`
- `04_sessions`
- `05_experiments`
- `06_reviews`
- `08_metrics`

## Protected System Files

Do not modify root instructions, protocols, schemas, OpenClaw config examples, or this skill during normal belief sessions. Modify them only when the user asks for setup, maintenance, or hardening.

## Session Rule

If the user naturally indicates the session is done, run `_system/protocols/02_session_protocol.md` and write the required session files. Do not require exact wording.

## Book Rule

If the user gives a book, run `_system/protocols/03_book_ingestion_protocol.md`. Extract belief candidates and daily-life implications, not only a summary.

Add major source-derived beliefs to the source folder and suggestion queue. Create candidate belief files for the strongest or user-requested candidates while marking source-only candidates as unadopted until the user chooses them.

## Completion Rule

Only create a completion mark when the user explicitly chooses completion. Use `_system/protocols/05_completion_protocol.md`.

## Pattern Rule

Use deterministic clarifications as primary evidence. Do not infer long-term patterns from one session.

## Memory Rule

Save memory in files, not in assumptions. Durable memory belongs in profile files, belief files, session folders, experiment files, review reports, and the progress ledger. Memory updates should be small, explicit, and traceable to a session, source, or review.

For details, use `_system/protocols/13_memory_update_policy.md`.

## Context Rule

Do not load the entire workspace by default. Use `_system/protocols/17_context_loading_policy.md` and load only the files needed for the task.

## Sub-Agent Rule

Sub-agents are allowed for bounded specialist work. The main agent owns the user conversation and reviews all durable memory updates. Use `_system/protocols/21_subagent_orchestration.md`.

## Heartbeat Rule

If the run is an OpenClaw heartbeat, read `HEARTBEAT.md` and follow it exactly. If no reminder is due, return `HEARTBEAT_OK`.

## Safety Rule

This is a self-improvement system, not therapy or medical care. Keep autonomy central.
