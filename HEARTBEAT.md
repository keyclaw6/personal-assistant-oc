# HEARTBEAT.md

On heartbeat, do one small useful thing:

- check whether `memory-wiki/WORKING.md` is stale
- compile memory if durable files changed
- run `npm run memory:report`
- run `npm run memory:maintain` when inbox or daily notes changed
- summarize unresolved conflicts
- stay quiet if nothing changed
