# HEARTBEAT.md

On heartbeat, do one small useful thing:

- check whether `memory-wiki/WORKING.md` is stale
- compile memory if durable files changed
- run `npm run memory:report`
- summarize unresolved conflicts
- stay quiet if nothing changed
