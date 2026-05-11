# Capability Routing

This protocol maps user requests to system tasks.

Use `_system/protocols/20_natural_language_interface.md` first. The user should not need to name this protocol or any other protocol.

## Capabilities

### Work On A Belief

Use:

- `09_prompts/belief_coach_agent.md`
- `_system/protocols/02_session_protocol.md`
- `_system/protocols/10_reframing_material_protocol.md`

Done when the session is saved, belief updates are written, and next action or experiment exists.

### Ingest A Book Or Source

Use:

- `09_prompts/source_librarian_agent.md`
- `_system/protocols/03_book_ingestion_protocol.md`
- `_system/protocols/18_chapter_ingestion_protocol.md` for long or detail-sensitive sources

Done when the source folder has required files, belief candidates, daily-life implications, exercises, related beliefs, and suggestion-queue updates.

### Export External Chat Prompt

Use:

- `_system/protocols/19_external_chat_workflow.md`
- `_system/templates/external_chat_prompt.md`

Done when a focused prompt exists in `10_exports/prompts`.

### Import External Chat Transcript

Use:

- `_system/protocols/19_external_chat_workflow.md`
- `09_prompts/deterministic_clarifier_agent.md`

Done when the external transcript has been converted into a normal session folder and durable updates are traceable.

### End A Session

Use:

- `_system/protocols/02_session_protocol.md`
- `09_prompts/deterministic_clarifier_agent.md`

Done when the session folder has all required files and `08_metrics/progress_ledger.csv` is updated or explicitly marked unavailable.

### Clarify A Session

Use:

- `09_prompts/deterministic_clarifier_agent.md`
- `_system/protocols/09_deterministic_clarification_protocol.md`

Done when `04_deterministic_clarification.json` parses and uses confidence labels.

### Analyze Patterns

Use:

- `09_prompts/pattern_analyst_agent.md`
- `_system/protocols/04_pattern_analysis_protocol.md`

Done when pattern claims cite session IDs and include confidence and disconfirming evidence.

### Suggest What To Work On Next

Use:

- `_system/protocols/08_suggestion_ranking_protocol.md`
- `03_beliefs/_indexes/suggestion_queue.md`

Done when a ranked list includes scores, why now, first question, likely experiment, and deferral reasons.

### Design Experiments

Use:

- `09_prompts/experiment_designer_agent.md`
- `_system/templates/experiment.md`

Done when the experiment tests predictions and has success, learning, and review criteria.

### Mark Completion

Use:

- `09_prompts/completion_reviewer_agent.md`
- `_system/protocols/05_completion_protocol.md`

Done when the user makes an explicit completion mark and the review includes remaining risk and reopen condition.

### Run Reviews

Use:

- `_system/protocols/11_review_cadence.md`
- `09_prompts/pattern_analyst_agent.md`
- `_system/protocols/08_suggestion_ranking_protocol.md`

Done when weekly or monthly review files are written and next focus is clear.

### Run Heartbeat

Use:

- `HEARTBEAT.md`

Done when the agent either sends the weekly inactivity reminder or replies `HEARTBEAT_OK`.

### Harden The System

Use:

- `_system/protocols/12_system_hardening_protocol.md`
- `_system/prompts/hardening_prompt.md`

Done when an audit report is written and local validation passes.

### Use Sub-Agents

Use:

- `_system/protocols/21_subagent_orchestration.md`

Done when bounded specialist tasks are delegated with explicit read/write scope and reviewed by the main agent before durable memory is updated.

## Routing Rule

If a request spans multiple capabilities, run them in this order:

1. Source ingestion.
2. Belief candidate creation.
3. Coaching session.
4. Experiment design.
5. Deterministic clarification.
6. Pattern analysis.
7. Completion review.
8. System hardening.

Do not skip deterministic clarification when later pattern analysis will depend on the session.
