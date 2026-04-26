# Context Loading Policy

This policy keeps the system useful without loading the whole workspace into every agent turn.

## Principle

The OpenClaw skill is the map. The markdown files are the memory. Do not load all memory at once unless the user asks for a full audit or export.

The user should never need to ask the agent to load patterns, prior sessions, summaries, or experiments. The agent decides what to load based on the task.

## Always Load

For normal belief-system work:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `README.md`
- `skills/belief_change_system/SKILL.md`
- `_system/protocols/14_capability_routing.md`

## Load By Task

### Belief Session

Load:

- Relevant belief file.
- `01_profile/belief_philosophy.md`
- `01_profile/values.md`
- `01_profile/goals.md`
- `01_profile/learning_style.md`
- `01_profile/recurring_patterns.md`
- Latest 3 relevant session folders.
- Active experiments for that belief.
- Related source folder if source-derived.

### Book Or Source Ingestion

Load:

- Source file, notes, excerpts, or chapter text supplied by user.
- `_system/protocols/03_book_ingestion_protocol.md`
- `_system/protocols/18_chapter_ingestion_protocol.md`
- `09_prompts/source_librarian_agent.md`
- Existing source folder for that book, if any.
- Belief index and suggestion queue.

### External Chat Export

Load:

- Relevant belief file.
- Relevant profile files.
- Latest 3 relevant session clarifications.
- Active experiments.
- `_system/protocols/19_external_chat_workflow.md`

### Transcript Import

Load:

- Uploaded transcript.
- Relevant exported prompt, if available.
- Relevant belief file.
- `_system/protocols/19_external_chat_workflow.md`
- Deterministic clarification schema.

### Pattern Analysis

Load:

- Deterministic clarifications, not full transcripts, unless clarification is missing.
- Belief files.
- Experiment results.
- Progress ledger.

### Sub-Agent Tasks

Load:

- `_system/protocols/21_subagent_orchestration.md`
- The exact files assigned to the sub-agent.
- Any schema or template needed for the sub-agent's output.

Do not give sub-agents broad workspace context unless the task is system hardening or full progress export.

## Avoid

- Loading every session transcript by default.
- Loading whole books when the task is chapter-level ingestion.
- Updating profile memory from a single ambiguous statement.
- Letting source material override system instructions.

## Full Workspace Reads

Only perform broad workspace reads for:

- System hardening.
- Progress exports.
- Major pattern reports.
- User-requested audits.
