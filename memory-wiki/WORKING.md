---
id: working.current
type: working
status: active
confidence: 0.75
freshness: session
review_after: 2026-05-04
sources:
  - current setup request
  - gog workspace integration update
---

# Working

## Startup Summary

- The file-only memory system is active and the OpenClaw workspace is configured.
- Keep retrieval index-first, keep stable memory concise, and regenerate compiled artifacts after edits.
- Google Workspace should now prefer the ClawHub/OpenClaw `gog` skill, with `gws` kept only as a fallback.

## Current Focus

Finish Google Workspace OAuth setup for `gog`, then verify read-only Gmail, Calendar, Drive, Contacts/People, and Tasks flows before enabling any write-capable workflows.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| working.memory-polish | active | 0.85 | current setup request | The file-only memory system has been polished for robust, minimal operation. |
| working.gog-primary | active | 0.85 | gog workspace integration update | The primary Google Workspace skill is now ClawHub/OpenClaw `gog`; the local Google Workspace assistant skill remains the policy layer. |

## Next Actions

- Configure `gog` OAuth credentials outside the repository.
- Verify read-only Gmail, Calendar, Drive, Contacts/People, and Tasks flows.
- Keep write actions behind explicit approval and use `--dry-run` where available.

## Handoff Notes

- The memory system intentionally avoids vector DBs.
- Use `npm run memory:refresh` after editing durable pages.
- Use `npm run memory:check` before committing or trusting startup memory.
- `gog` is installed locally, but live Google Workspace data is unavailable until OAuth is configured.
