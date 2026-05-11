# Research Notes

This project design was informed by:

- OpenClaw's local-first agent workspace model, root prompt files, and workspace skills.
- OpenClaw's note that workspace skills live under `<workspace>/skills` and can override lower-precedence skills.
- OpenClaw's security guidance that channel inputs and third-party skills should be treated as untrusted.
- OpenClaw heartbeat guidance: a workspace `HEARTBEAT.md` file can contain a small checklist or `tasks:` block, and non-empty due tasks are included in heartbeat prompts.
- OpenClaw sub-agent guidance: sub-agents run in separate sessions, can keep long tasks out of the main context, and by default receive only `AGENTS.md` and `TOOLS.md`, so spawned tasks need explicit file instructions.
- The Freedom Model's emphasis on beliefs, preferences, personal choice, and the idea that people change behavior by changing how they understand their options.
- Cognitive and behavioral change practices such as behavioral experiments, cognitive restructuring, and implementation intentions.

## Design Consequences

- The workspace has root `AGENTS.md`, `SOUL.md`, and `TOOLS.md` files because OpenClaw injects root prompt files into agent sessions.
- The system includes `skills/belief_change_system/SKILL.md` because OpenClaw loads workspace skills from `<workspace>/skills`.
- Session folders separate transcript, interpretation, deterministic clarification, and next actions so later agents can analyze stable records instead of vibes.
- Book ingestion extracts belief candidates and daily-life implications rather than only summaries.
- The system keeps "completion" user-owned because belief change should not be imposed by the agent.

## Source Links

- OpenClaw GitHub: https://github.com/openclaw/openclaw
- OpenClaw skills docs: https://docs.openclaw.ai/tools/skills
- OpenClaw creating skills docs: https://docs.openclaw.ai/tools/creating-skills
- OpenClaw configuration docs: https://docs.openclaw.ai/gateway/configuration
- OpenClaw heartbeat docs: https://docs.openclaw.ai/gateway/heartbeat
- OpenClaw automation overview: https://docs.openclaw.ai/automation
- OpenClaw sub-agents docs: https://docs.openclaw.ai/tools/subagents
- The Freedom Model book page: https://www.thefreedommodel.org/freedommodelforaddictions/
- The Freedom Model differences page: https://www.thefreedommodel.org/differences/
- The Freedom Model benefits/PDP page: https://www.thefreedommodel.org/solving-addiction-benefits/
- Behavioral experiments in cognitive therapy: https://pmc.ncbi.nlm.nih.gov/articles/PMC7611432/
- Implementation intentions overview/meta-analysis discussion: https://pmc.ncbi.nlm.nih.gov/articles/PMC8149892/
