# Capability Audit

Date: 2026-04-24

## Purpose

This audit walks through what the Belief Change System should be able to do, whether each capability is structurally supported, and what was tightened during this pass.

## Capability List

The system should support:

1. Start a belief session.
2. Load previous memory and relevant context.
3. Coach a belief-change conversation.
4. Reframe a belief through multiple lenses.
5. End a session and save all records.
6. Produce deterministic session clarification.
7. Update belief files and lifecycle status.
8. Design real-world experiments.
9. Track progress and experiments.
10. Ingest books and sources.
11. Extract belief candidates from books.
12. Translate books into daily-life implications.
13. Add source-derived beliefs to the tracker and suggestion queue.
14. Analyze patterns across many sessions.
15. Suggest what belief to work on next.
16. Review and mark beliefs complete.
17. Run weekly, monthly, and quarterly reviews.
18. Maintain user memory safely.
19. Protect system files from accidental rewrite.
20. Run OpenClaw heartbeat inactivity reminders.
21. Audit and harden itself.

## Task Walkthrough

### 1. Start A Belief Session

Status: ready

Core files:

- `AGENTS.md`
- `09_prompts/belief_coach_agent.md`
- `_system/protocols/02_session_protocol.md`

Assessment:

The system can identify or create a belief slug, load prior context, recap status, and begin with a useful question. The prompt was tightened to include lifecycle status, prior sessions, experiments, and source-derived context.

### 2. Load Previous Memory And Context

Status: ready

Core files:

- `AGENTS.md`
- `_system/protocols/13_memory_update_policy.md`
- `01_profile/memory_log.md`
- `03_beliefs/_indexes/belief_index.md`
- `03_beliefs/_indexes/suggestion_queue.md`

Assessment:

The read order is explicit. The memory policy now prevents broad self-model rewrites and requires traceability to a session, source, experiment, or user decision.

### 3. Coach A Belief-Change Conversation

Status: ready, improved

Core files:

- `09_prompts/belief_coach_agent.md`
- `SOUL.md`
- `_system/protocols/15_belief_change_effectiveness.md`

Assessment:

The coaching prompt now focuses on preference logic, protective function, cost, evidence, alternative models, and daily-life behavior. It clearly avoids treating insight as integration.

### 4. Reframe A Belief

Status: ready

Core files:

- `_system/protocols/10_reframing_material_protocol.md`
- `09_prompts/belief_coach_agent.md`

Assessment:

The reframing protocol covers preference, protection, cost, evidence, identity, social, future, daily-life, experiment, and book lenses. The coach prompt now explicitly routes into these lenses.

### 5. End A Session

Status: ready

Core files:

- `_system/protocols/02_session_protocol.md`
- `04_sessions/_session_template`

Assessment:

The required session files are defined and the session template folder has all eight required files. The end command is explicit.

### 6. Produce Deterministic Clarification

Status: ready, improved

Core files:

- `09_prompts/deterministic_clarifier_agent.md`
- `_system/protocols/09_deterministic_clarification_protocol.md`
- `_system/schemas/session_clarification.schema.json`

Assessment:

The clarifier prompt now gives field-level guidance and stricter anti-speculation rules. This makes pattern analysis more reliable.

### 7. Update Belief Files And Lifecycle Status

Status: ready

Core files:

- `_system/protocols/01_belief_lifecycle.md`
- `_system/templates/belief.md`
- `_system/schemas/belief.schema.json`
- `03_beliefs/_indexes/belief_index.md`

Assessment:

The lifecycle is clear and completion types are explicit. Future improvement could add a helper script for moving beliefs between lifecycle folders while updating indexes.

### 8. Design Real-World Experiments

Status: ready, improved

Core files:

- `09_prompts/experiment_designer_agent.md`
- `_system/templates/experiment.md`
- `_system/schemas/experiment.schema.json`

Assessment:

The experiment prompt now requires old and new predictions, evidence interpretation, poorly-designed-experiment criteria, and review conditions. This makes experiments more useful for actual belief change.

### 9. Track Progress And Experiments

Status: ready

Core files:

- `08_metrics/progress_ledger.csv`
- `08_metrics/metric_definitions.md`
- `_system/rubrics/belief_progress_scoring.md`
- `05_experiments/README.md`

Assessment:

The progress ledger header is stable. The system can track belief scores, lifecycle movement, experiments, and completion marks.

### 10. Ingest Books And Sources

Status: ready, improved

Core files:

- `09_prompts/source_librarian_agent.md`
- `_system/protocols/03_book_ingestion_protocol.md`
- `_system/schemas/book_breakdown.schema.json`

Assessment:

The source librarian prompt now requires source-claim separation, anti-surface-reading extraction, source indexing, suggestion queue updates, and candidate creation for strong source-derived beliefs.

### 11. Extract Belief Candidates From Books

Status: ready, improved

Core files:

- `02_sources/books/README.md`
- `_system/protocols/03_book_ingestion_protocol.md`
- `09_prompts/source_librarian_agent.md`

Assessment:

The system now explicitly extracts old beliefs challenged, new beliefs proposed, daily-life shifts, experiments, confidence, and adoption status.

### 12. Translate Books Into Daily-Life Implications

Status: ready

Core files:

- `_system/protocols/03_book_ingestion_protocol.md`
- `_system/protocols/15_belief_change_effectiveness.md`

Assessment:

The anti-surface-reading standard is now central: "If I actually understood this, then in normal life I would..."

### 13. Add Source-Derived Beliefs To Tracker

Status: ready, improved

Core files:

- `skills/belief_change_system/SKILL.md`
- `03_beliefs/_indexes/suggestion_queue.md`
- `_system/protocols/08_suggestion_ranking_protocol.md`

Assessment:

The skill now explicitly says source-derived beliefs should be added to the source folder and suggestion queue, with candidate belief files for the strongest or user-requested beliefs.

### 14. Analyze Patterns Across Sessions

Status: ready, improved

Core files:

- `09_prompts/pattern_analyst_agent.md`
- `_system/protocols/04_pattern_analysis_protocol.md`

Assessment:

The pattern analyst prompt now includes evidence counting, repeated themes, protective functions, stuck points, evidence types, values comparison, and ranking next beliefs.

### 15. Suggest What Belief To Work On Next

Status: ready

Core files:

- `_system/protocols/08_suggestion_ranking_protocol.md`
- `03_beliefs/_indexes/suggestion_queue.md`

Assessment:

The ranking system covers leverage, recurrence, cost, readiness, evidence availability, and source momentum. It is adequate for early use.

### 16. Review And Mark Beliefs Complete

Status: ready, improved

Core files:

- `09_prompts/completion_reviewer_agent.md`
- `_system/protocols/05_completion_protocol.md`
- `_system/templates/completion_review.md`

Assessment:

The completion reviewer prompt now distinguishes insight from integration and reinforces that completion requires explicit user ownership.

### 17. Run Periodic Reviews

Status: ready, improved

Core files:

- `_system/protocols/11_review_cadence.md`
- `_system/templates/weekly_review.md`
- `_system/templates/monthly_review.md`
- `_system/templates/quarterly_review.md`
- `06_reviews/README.md`

Assessment:

Review cadence exists and now has weekly, monthly, and quarterly templates.

### 18. Maintain User Memory Safely

Status: ready

Core files:

- `_system/protocols/13_memory_update_policy.md`
- `01_profile/memory_log.md`
- `AGENTS.md`

Assessment:

The system now distinguishes user memory from system memory and requires traceable, marginal updates.

### 19. Protect System Files

Status: ready

Core files:

- `TOOLS.md`
- `AGENTS.md`
- `skills/belief_change_system/SKILL.md`

Assessment:

Protected-file rules are explicit. Normal sessions should not rewrite root instructions, protocols, schemas, OpenClaw examples, heartbeat, or skills.

### 20. Run OpenClaw Heartbeat Reminders

Status: ready for future OpenClaw setup

Core files:

- `HEARTBEAT.md`
- `_system/openclaw/openclaw.example.json5`
- `_system/openclaw/setup_notes.md`

Assessment:

Heartbeat is OpenClaw-only. The example config now attaches heartbeat to `belief-coach` only. No Codex app automation is part of the live setup.

### 21. Audit And Harden Itself

Status: ready

Core files:

- `_system/protocols/12_system_hardening_protocol.md`
- `_system/prompts/hardening_prompt.md`
- `_system/audits`

Assessment:

The hardening path is explicit and now includes OpenClaw-only reminder constraints.

## Whole-System Assessment

The system is now structurally aligned with its purpose:

- It can ingest books into actionable belief-change material.
- It can run belief sessions with continuity.
- It can save session records.
- It can produce deterministic clarifications for later analysis.
- It can track beliefs through a lifecycle.
- It can suggest what to work on next.
- It can design experiments that test prediction and preference.
- It can distinguish insight from integration.
- It can protect itself from broad accidental rewrites.
- It has OpenClaw heartbeat instructions for weekly inactivity reminders.

The strongest improvement from this pass is that role prompts now define "done" for each task. This should make future agent behavior more consistent.

## Remaining Improvement Opportunities

- Add a helper script to move beliefs between lifecycle folders safely.
- After real sessions exist, run pattern analysis on actual deterministic clarifications and update the suggestion queue from evidence rather than initial assumptions.

## Files Changed During This Capability Pass

- `AGENTS.md`
- `skills/belief_change_system/SKILL.md`
- `09_prompts/belief_coach_agent.md`
- `09_prompts/source_librarian_agent.md`
- `09_prompts/deterministic_clarifier_agent.md`
- `09_prompts/pattern_analyst_agent.md`
- `09_prompts/auditor_agent.md`
- `09_prompts/experiment_designer_agent.md`
- `09_prompts/completion_reviewer_agent.md`
- `_system/protocols/14_capability_routing.md`
- `_system/protocols/15_belief_change_effectiveness.md`
- `_system/protocols/16_progress_export_protocol.md`
- `_system/templates/monthly_review.md`
- `_system/templates/quarterly_review.md`
- `_system/templates/source_ingestion_manifest.json`
- `02_sources/books/scheeren-slate-dunbar-the-freedom-model-for-addictions/00_manifest.json`
- `_system/audits/20260424-capability-audit.md`
