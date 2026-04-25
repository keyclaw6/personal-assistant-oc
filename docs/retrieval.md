# Retrieval Protocol

The memory system uses progressive disclosure: scan cheap indexes first, then fetch only what matters.

## Layer 1 - Index

Start with:

```powershell
Get-Content memory/_compiled/SESSION_INDEX.md
```

This file tells the assistant what exists, where to fetch it, status, confidence, and approximate read cost.

If the index is missing or stale after edits, run:

```powershell
npm run memory:refresh
```

## Layer 2 - Canonical Page

Read one or two relevant pages under `memory-wiki/`.

Examples:

```powershell
Get-Content memory-wiki/PREFERENCES.md
Get-Content memory-wiki/syntheses/memory-architecture.md
```

## Layer 3 - Raw Timeline

Use raw logs only when the canonical wiki does not answer the question:

```powershell
Get-Content memory/events/2026-04-25.jsonl
Get-Content memory/daily/2026-04-25.md
```

## Why This Shape

This borrows Claude-Mem's key idea: context is expensive, so the assistant should see an index and choose what to fetch. It avoids the opposite failure mode where a huge memory blob is loaded on every session.

Stop once there is enough context to act. More memory is not better if it does not change the answer.
