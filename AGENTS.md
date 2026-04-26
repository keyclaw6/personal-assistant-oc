# AGENTS.md - Workspace Rules

This folder is home for the personal assistant. Treat memory as a filesystem, not as a hidden database.

## Session Startup

At the start of a main/direct session:

1. Use runtime-provided startup context first.
2. If `MEMORY.md` was not provided, read it.
3. Scan `memory/_compiled/SESSION_INDEX.md`; if it is missing, run `npm run memory:compile`.
4. Fetch the smallest relevant wiki page(s), not the whole vault.
5. Read `memory-wiki/WORKING.md` only when the task needs current focus.
6. Use `memory/_compiled/STARTUP.md` only when a fuller digest is needed.

Do not load private memory in shared channels unless the user explicitly asks and the channel is safe.

## Workspace Isolation

Operate from this workspace by default. Do not inspect, summarize, or write into other OpenClaw agent workspaces or private domain systems unless Kristian explicitly names the path and asks for that crossover.

If a request belongs in a separate specialist channel, keep this agent's answer brief and ask Kristian to continue there. Do not assume access to that channel's memory.

## Memory Layers

- `memory/events/YYYY-MM-DD.jsonl`: append-only event log. Raw, timestamped, source-heavy.
- `memory/daily/YYYY-MM-DD.md`: daily working note. Messy is acceptable.
- `memory/inbox/`: unreviewed facts and observations.
- `memory/conflicts/`: unresolved contradictions. Never bury a conflict.
- `memory-wiki/`: curated, reviewed, durable knowledge.
- `memory/_compiled/SESSION_INDEX.md`: cheap progressive-disclosure index.
- `memory/_compiled/STARTUP.md`: fuller generated startup digest.

## Write Policy

Safe to update or regenerate without asking:

- `memory/events/`
- `memory/daily/`
- `memory/inbox/`
- `memory/conflicts/`
- `memory-wiki/WORKING.md`
- generated memory reports
- `memory/_compiled/`

Ask or clearly state what you changed when editing stable memory:

- `memory-wiki/PROFILE.md`
- `memory-wiki/PREFERENCES.md`
- `memory-wiki/PROJECTS.md`
- `memory-wiki/STACK.md`
- `memory-wiki/PEOPLE.md`
- `memory-wiki/DECISIONS.md`
- `memory-wiki/entities/`
- `memory-wiki/concepts/`
- `memory-wiki/syntheses/`

Never hand-edit generated ignored reports. Change source memory, then rerun `npm run memory:refresh`. Human review notes in `memory-wiki/reports/` are normal source files.

## Conflict Handling

When new information contradicts existing memory:

1. Do not overwrite the old claim silently.
2. Create `memory/conflicts/YYYY-MM-DD-short-name.md`.
3. Include both claims, evidence, confidence, and recommended resolution.
4. Mark affected wiki claims as `status: contested` or add an open question.
5. Run `npm run memory:refresh`.

## Promotion Rules

Promote memory from raw logs into `memory-wiki/` only when it is likely to matter again.

Good candidates:

- persistent user preferences
- project goals and constraints
- architectural decisions
- recurring tasks
- names and relationships
- lessons from mistakes
- operating procedures

Poor candidates:

- secrets
- one-off chatter
- temporary emotional color with no future use
- facts without enough evidence

## Retrieval Rules

Use progressive disclosure:

1. Start with `memory/_compiled/SESSION_INDEX.md`.
2. Fetch one or two relevant wiki pages.
3. Use `memory/_compiled/STARTUP.md` only when broad context is needed.
4. Only then inspect raw daily/event logs.
5. Stop searching when you have enough context.

This keeps context cheap while preserving depth when needed.

## Privacy Tags

Source files may contain `<private>...</private>` blocks. Compiled artifacts strip those blocks. Do not quote or promote private blocks unless Kristian explicitly asks.

## Safety

Private things stay private. Ask before sending messages, posting externally, deleting data, or changing accounts/integrations.
