# Integrated Architecture

## Runtime Model

This repo is a single Git source of truth for two isolated OpenClaw workspaces.

- Root workspace: `main` agent, named `Personal/Coder OC`.
- Nested workspace: `belief-system/`, used by the `belief` agent.
- Shared Gateway: local OpenClaw Gateway on `127.0.0.1:18789`.
- Shared model auth: `openai-codex/gpt-5.5` through Codex OAuth.

The agents should not talk to each other directly. If a crossover is needed, Kristian names the source path and desired output explicitly.

## Main Agent Contract

The main agent owns:

- personal assistant work
- project and coding coordination
- memory maintenance in `memory/` and `memory-wiki/`
- repo setup and documentation
- later calendar, email, todo, and computer-node workflows

The main agent does not run belief sessions by default.

## Belief Agent Contract

The belief agent owns:

- belief-change conversations
- source and book ingestion for belief work
- deterministic clarifications
- experiments and reviews
- progress tracking and completion marks

Its rules live in `belief-system/AGENTS.md`, with protocols under `belief-system/_system/`.

## Memory Contract

The main memory system uses progressive disclosure:

1. `MEMORY.md`
2. `memory/_compiled/SESSION_INDEX.md`
3. one or two relevant `memory-wiki/` pages
4. `memory/_compiled/STARTUP.md` only for broad context
5. raw logs only if necessary

Belief memory is separate. It lives inside `belief-system/` and should be loaded by the belief agent according to that workspace's own context-loading policy.

## Practical Assistant Growth Path

Capabilities should be added only after they have a small documented contract:

- Calendar: read events first, draft changes, ask before creating or deleting.
- Todos: keep one canonical task source, record due dates and stale items.
- Email: summarize and draft first; send only after explicit approval.
- Files: prefer workspace-scoped reads and writes; never search secrets casually.
- Coding nodes: use the main agent as coordinator; nodes execute bounded tasks.
- Automations: start with weekly reviews and reminders before always-on actions.
- Morning brief: run by cron at 07:30 Europe/Copenhagen with narrow read-only Google Workspace authority.
- Commitment tracking: maintain local files under `memory/commitments/`; surface due and waiting items in the morning brief.
- Belief accountability: run a Friday cron through the `belief` agent; remind Kristian only if no qualifying belief work happened that week.

## Repository Boundary

Tracked files should be safe to push to a private GitHub repository. Machine state, auth profiles, tokens, credentials, and runtime logs belong in `.openclaw/` or `~/.openclaw/`, not in this repo.
