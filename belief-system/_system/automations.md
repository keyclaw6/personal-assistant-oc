# Automations

This project is intended for future OpenClaw use. Do not create Codex app automations for this workspace unless the user explicitly asks for a Codex-specific reminder.

## OpenClaw Heartbeat

File:

```text
HEARTBEAT.md
```

Purpose:

- Same weekly inactivity check, designed for OpenClaw heartbeat.

Requirement:

- OpenClaw heartbeat must be enabled in the live OpenClaw config.
- Delivery must be configured, for example with `target: "last"` or a specific channel.

## Removed Codex Automation

On 2026-04-24, a Codex app automation named `Belief work weekly check` was briefly created during hardening and then deleted at the user's request. Future reminder setup should be OpenClaw-only.
