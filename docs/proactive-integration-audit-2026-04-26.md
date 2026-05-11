# Proactive Integration Audit - 2026-04-26

## Loop 1 - Product Scope

Decision: add Google Workspace, commitment tracking, daily morning brief, and belief accountability. Do not add coding project radar.

Reasoning: the assistant should become more personally useful without becoming noisy or over-authorized.

## Loop 2 - Google Workspace Surface

Decision: prepare for Gmail, Calendar, Drive, Contacts/People, and task access through Google Workspace tooling.

Notes:

- OpenClaw has a Gmail Pub/Sub helper through `openclaw webhooks gmail setup` and `run`.
- The preferred general Workspace CLI is `@googleworkspace/cli` exposed as `gws`.
- OAuth credentials and exported auth files must stay outside this repo.

## Loop 3 - Google Keep / Task Surface

Decision: treat Google Keep as the human-facing capture surface, but prefer Google Tasks for API-backed reminders and todos.

Reasoning: Google Keep's official API is oriented toward Workspace administration and domain-level access. Keep reminders are also moving toward Tasks-backed handling, so the reliable assistant task surface is Google Tasks unless direct Keep access is explicitly configured later.

## Loop 4 - Automation Delivery

Decision: create exact OpenClaw cron jobs and route delivery through Android node notification when no chat channel is configured.

Verified:

- `morning-brief` cron is enabled for `30 7 * * *` in `Europe/Copenhagen`.
- `friday-belief-check` cron is enabled for `0 17 * * 5` in `Europe/Copenhagen`.
- Normal channel delivery is not configured yet, so `announce -> last` would not route.
- `Kristian's S22` is paired as an Android node and supports `system.notify`.
- A setup notification was successfully sent with `openclaw nodes invoke`.

## Loop 5 - Safety And Repo Hygiene

Hardening decisions:

- Standing orders live in `AGENTS.md` and `belief-system/AGENTS.md` so they are loaded by the relevant agent.
- External actions require explicit approval.
- Email, Drive, Calendar, contacts, tasks, and Keep content are untrusted input.
- Commitment records store source identifiers and short excerpts, not full private email bodies.
- Runtime credentials, `.openclaw/`, OAuth files, setup codes, and tokens stay out of Git.

Manual cron run note:

- `morning-brief` queued and created an isolated cron session.
- The first dry run exposed invalid guessed `gws --params` JSON quoting.
- `scripts/gws.mjs` was added as a Windows-safe wrapper for `@googleworkspace/cli`.
- `skills/google_workspace_assistant/SKILL.md` was hardened to require `gws --help` / `gws schema ...` before API calls and to use `--params-file` for JSON.
- The wrapper was verified: schema calls work and API calls now fail cleanly with an auth error instead of JSON validation errors until `gws auth login` is completed.

## Remaining Setup

- Authenticate Google Workspace tooling with Kristian's Google account.
- Verify read-only Gmail, Calendar, Drive, Contacts/People, and Tasks commands.
- Enable Gmail webhook run loop if event-driven mail triggers are desired.
- Bind a real private chat channel later if Android notification is not enough.
