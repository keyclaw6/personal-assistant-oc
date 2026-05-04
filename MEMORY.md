# MEMORY.md - Load First

This is the tiny always-loaded memory entrypoint. Do not treat it as the full memory and do not load the whole vault by default.

## Read Order

1. Scan `memory/_compiled/SESSION_INDEX.md`; if it is missing, run `npm run mem -- refresh`.
2. Search with `npm run mem -- search "query"` when the right page is not obvious.
3. Fetch only the specific page or claim needed with `npm run mem -- get <id-or-path>`.
4. Read `memory-wiki/WORKING.md` only when the task needs current focus.
5. Use `memory/_compiled/STARTUP.md` only when a broader digest is needed.
6. Search raw logs in `memory/events/` or `memory/daily/` only as a last step.

## Write Order

1. Capture raw facts with `npm run mem -- put --type observation --title "..." --summary "..."`.
2. Promote durable facts to `memory-wiki/` with evidence.
3. Refresh generated context with `npm run mem -- refresh`.
4. Check with `npm run mem -- check`.

Skip capture for one-off chatter, secrets, or facts that are unlikely to matter again.

## Privacy

Anything wrapped in `<private>...</private>` is stripped from compiled artifacts. Do not store secrets unless Kristian explicitly asks and provides a safe storage location.
