# AGENTS.md - Workspace Rules

This folder is home for the personal assistant. Treat memory as a filesystem, not as a hidden database.

## Session Startup

At the start of a main/direct session:

1. Read `memory/_compiled/STARTUP.md` if present.
2. Read `SOUL.md`, `USER.md`, and `TOOLS.md` only when startup context is missing or the user asks.
3. Read `memory-wiki/WORKING.md` for current focus.
4. If a question depends on durable context, search `memory-wiki/` with `rg` before wandering through unrelated files.

Do not load private memory in shared channels unless the user explicitly asks and the channel is safe.

## Memory Layers

- `memory/events/YYYY-MM-DD.jsonl`: append-only event log. Raw, timestamped, source-heavy.
- `memory/daily/YYYY-MM-DD.md`: daily working note. Messy is acceptable.
- `memory/inbox/`: unreviewed facts and observations.
- `memory/conflicts/`: unresolved contradictions. Never bury a conflict.
- `memory-wiki/`: curated, reviewed, durable knowledge.
- `memory/_compiled/STARTUP.md`: compact generated startup context.

## Write Policy

Safe to update without asking:

- `memory/events/`
- `memory/daily/`
- `memory/inbox/`
- `memory/conflicts/`
- `memory-wiki/WORKING.md`
- `memory-wiki/reports/`
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

## Conflict Handling

When new information contradicts existing memory:

1. Do not overwrite the old claim silently.
2. Create `memory/conflicts/YYYY-MM-DD-short-name.md`.
3. Include both claims, evidence, confidence, and recommended resolution.
4. Mark affected wiki claims as `status: contested` or add an open question.
5. Run `npm run memory:report`.

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

1. Start with `memory/_compiled/STARTUP.md`.
2. Search the index or wiki filenames.
3. Read one or two relevant pages.
4. Only then inspect raw daily/event logs.

This keeps context cheap while preserving depth when needed.

## Safety

Private things stay private. Ask before sending messages, posting externally, deleting data, or changing accounts/integrations.
