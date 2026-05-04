# Retrieval Protocol

The memory system uses progressive disclosure: scan cheap indexes first, then fetch only what matters.

## L0 - Session Index

Start with:

```powershell
Get-Content memory/_compiled/SESSION_INDEX.md
```

This file tells the assistant what exists, where to fetch it, status, confidence, and approximate read cost.

If the index is missing or stale after edits, run:

```powershell
npm run mem -- refresh
```

## L1 - Search And Page Summary

Use lexical search when the right page is not obvious:

```powershell
npm run mem -- search "file memory vector database"
npm run mem -- search "progressive disclosure index first" --format md
```

Search covers durable wiki pages and structured claim rows. It is deterministic and dependency-free; scores combine query hits, title/path boosts, claim boosts, confidence, status, importance, review freshness, and token cost.

Compiled startup memory and durable pages should prefer compact `## L0` or `## L1` sections when present. Legacy `## Startup Summary` and `## Summary` sections are still supported.

## L2 - Canonical Page And Evidence

Read one or two relevant pages under `memory-wiki/`.

Examples:

```powershell
npm run mem -- get preferences.kristian
npm run mem -- get memory-wiki/syntheses/memory-architecture.md --level L2
```

Use cited source files or raw logs only when the canonical wiki does not answer the question:

```powershell
Get-Content memory/events/2026-04-25.jsonl
Get-Content memory/daily/2026-04-25.md
```

## Why This Shape

This borrows Claude-Mem's key idea: context is expensive, so the assistant should see an index and choose what to fetch. It avoids the opposite failure mode where a huge memory blob is loaded on every session.

Stop once there is enough context to act. More memory is not better if it does not change the answer.

## Agent Tool Surface

For OpenClaw, keep the normal memory action surface to four verbs:

| Verb | Use |
| --- | --- |
| `mem search` | Find candidate pages or claims. |
| `mem get` | Fetch one selected page or claim. |
| `mem put` | Capture a raw unreviewed memory. |
| `mem check` | Verify memory health after edits. |

The longer `memory:*` scripts remain available for maintainers and CI, but they are intentionally not the first interface shown to the model.
