# MEMORY.md - Load First

This is the tiny always-loaded memory entrypoint. Do not treat it as the full memory and do not load the whole vault by default.

## Read Order

1. Scan `memory/_compiled/SESSION_INDEX.md`; if it is missing, run `npm run memory:compile`.
2. Fetch only the specific wiki page(s) needed for the task.
3. Read `memory-wiki/WORKING.md` only when the task needs current focus.
4. Use `memory/_compiled/STARTUP.md` only when a broader digest is needed.
5. Search raw logs in `memory/events/` or `memory/daily/` only as a last step.

## Write Order

1. Capture raw facts with `npm run memory:capture -- --type observation --title "..." --summary "..."`.
2. Promote durable facts to `memory-wiki/` with evidence.
3. Refresh generated context with `npm run memory:refresh`.
4. Check with `npm run memory:check`.

Skip capture for one-off chatter, secrets, or facts that are unlikely to matter again.

## Privacy

Anything wrapped in `<private>...</private>` is stripped from compiled artifacts. Do not store secrets unless Kristian explicitly asks and provides a safe storage location.
