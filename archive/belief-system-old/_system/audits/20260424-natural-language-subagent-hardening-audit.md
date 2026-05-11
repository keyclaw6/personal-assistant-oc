# Natural Language And Sub-Agent Hardening Audit

Date: 2026-04-24

## Audit Checklist

Before editing, this pass audited:

- Whether the user must remember commands, protocol names, or exact phrases.
- Whether session closure can be inferred from natural language.
- Whether the system automatically loads patterns, prior sessions, summaries, experiments, and relevant beliefs without being asked.
- Whether OpenClaw sub-agents are allowed for bounded specialist tasks.
- Whether sub-agents have conservative limits and explicit scope.
- Whether the main belief coach retains ownership of live coaching and final durable memory updates.
- Whether sub-agent context limitations are documented.
- Whether OpenClaw example config reflects sub-agent policy.
- Whether protected system files remain protected.
- Whether user memory is unchanged.
- Whether validation still passes after edits.

## Issues Found

### User-facing command dependence

Some files still said the user should say exactly `end` or implied that `end` was a special required command.

Risk:

- The user would need to remember workflow commands, which conflicts with the desired natural-language interface.

### Missing natural-language interface layer

The system had routing and context policies, but no explicit rule that the agent should infer intent from ordinary language and run the framework automatically.

Risk:

- Future agents might ask the user to choose protocols or remember internal mechanics.

### Missing sub-agent orchestration policy

The system had specialist role prompts, but no clear rule for when OpenClaw sub-agents should be used, what they may read/write, or what remains owned by the main agent.

Risk:

- Sub-agents could either be underused, causing large context loads, or overused, causing unreviewed memory changes.

### OpenClaw example lacked sub-agent settings

The example config did not yet encode conservative sub-agent defaults or the belief coach's allowed specialist agents.

Risk:

- Future OpenClaw setup might use defaults that are too broad or unclear.

## Fixes Made

- Added `_system/protocols/20_natural_language_interface.md`.
- Added `_system/protocols/21_subagent_orchestration.md`.
- Updated `AGENTS.md` to route through natural language and sub-agent policies.
- Updated `_system/protocols/02_session_protocol.md` so natural closure phrases trigger the end protocol.
- Updated `README.md` so daily use is described as natural language, not commands.
- Updated `skills/belief_change_system/SKILL.md` with natural-language routing and sub-agent rules.
- Updated `_system/protocols/14_capability_routing.md` with natural-language and sub-agent capabilities.
- Updated `_system/protocols/17_context_loading_policy.md` with sub-agent context rules.
- Updated `_system/MINIMAL_OPERATING_MODEL.md` to start from natural language and define sub-agent boundaries.
- Updated `_system/openclaw/openclaw.example.json5` with conservative sub-agent defaults.
- Updated `_system/openclaw/setup_notes.md` with sub-agent setup guidance.
- Updated `09_prompts/belief_coach_agent.md`, `09_prompts/auditor_agent.md`, and `09_prompts/pattern_analyst_agent.md`.
- Updated `_system/protocols/12_system_hardening_protocol.md` and `_system/prompts/hardening_prompt.md` so future hardening checks natural-language use and sub-agent policy.
- Updated `_system/research_notes.md` with OpenClaw sub-agent documentation notes.
- Updated `_system/templates/external_chat_prompt.md` so external sessions can close naturally.

## Sub-Agent Policy

Allowed:

- Chapter ingestion.
- Source-to-belief extraction.
- Deterministic clarification.
- Pattern analysis.
- Experiment design.
- Completion readiness review.
- Safety/integrity audit.
- Progress export drafting.
- System hardening audit.

Not delegated:

- Live belief-change conversation.
- User-owned completion decisions.
- Final durable memory updates without main-agent review.
- Broad system redesign unless explicitly requested.

Recommended OpenClaw settings:

```json5
subagents: {
  maxConcurrent: 3,
  maxChildrenPerAgent: 3,
  maxSpawnDepth: 1,
  runTimeoutSeconds: 900
}
```

## Natural-Language Policy

The user can now say ordinary things like:

- "I want to work on this belief."
- "Let's stop here."
- "Can you save this?"
- "Here is a chapter."
- "Make me a prompt for another chat app."
- "What should I work on next?"

The agent should infer the workflow, load the right context, and save/update records automatically.

## Remaining Risks

- The OpenClaw config file remains an example, not a live config.
- Sub-agent tool permissions ultimately depend on the future OpenClaw deployment.
- Sub-agent results are best treated as draft work until the main agent reviews them.
- Historical audit files still mention older command-based behavior as past findings, but current control files now use natural closure.

## Verification

Verification was run after edits:

- JSON files parse.
- PowerShell helper scripts parse.
- Required new protocols exist.
- No stale misspelled absolute paths found.
- Skill frontmatter remains valid.
- `HEARTBEAT.md` still has a task block and `HEARTBEAT_OK` contract.
