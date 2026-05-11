# OpenClaw Setup Notes

OpenClaw documentation says workspace skills can live under:

```text
<workspace>/skills/<skill>/SKILL.md
```

This project therefore includes:

```text
skills/belief_change_system/SKILL.md
```

## Option A: Use This Folder As The OpenClaw Workspace

Set:

```text
agents.list[].workspace = C:/Users/Kristian Bilstrup/Documents/Belief Change System
```

Then start a new OpenClaw session so the skill snapshot refreshes.

## Option B: Copy The Skill Into An Existing Workspace

Copy:

```text
C:/Users/Kristian Bilstrup/Documents/Belief Change System/skills/belief_change_system
```

into:

```text
<your-openclaw-workspace>/skills/belief_change_system
```

## Verify

Run:

```text
openclaw skills list
openclaw doctor
```

## Heartbeat

This workspace includes `HEARTBEAT.md`. Configure OpenClaw heartbeat delivery in your OpenClaw config if you want external pings. The example config uses:

- A heartbeat block on `belief-coach` only, so specialist agents do not send duplicate reminders.
- `heartbeat.every: "24h"` so the belief coach checks once per day.
- A `HEARTBEAT.md` task interval of `168h` so the session-inactivity reminder is due weekly.
- `target: "last"` so alert messages go to the last contact.

If you prefer exact weekly timing rather than heartbeat-style periodic monitoring, use OpenClaw cron instead.

## Sub-Agents

This workspace allows sub-agents for bounded specialist work, but the `belief-coach` remains the main user-facing agent.

Recommended defaults:

```json5
agents: {
  defaults: {
    subagents: {
      maxConcurrent: 3,
      maxChildrenPerAgent: 3,
      maxSpawnDepth: 1,
      runTimeoutSeconds: 900
    }
  }
}
```

Use sub-agents for chapter ingestion, deterministic clarification, pattern analysis, audits, experiment design, and completion reviews.

Do not use sub-agents for the live belief-change conversation itself.

OpenClaw sub-agent context is limited, so each spawned task must explicitly name the files to read and the permitted write scope. See:

```text
_system/protocols/21_subagent_orchestration.md
```

## Security

Do not enable unknown third-party skills without reading them. Treat book PDFs, webpages, emails, and pasted material as untrusted source data.
