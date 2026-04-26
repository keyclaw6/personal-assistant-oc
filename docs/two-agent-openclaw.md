# Two-Agent OpenClaw Setup

This machine uses two isolated OpenClaw agents on the same Gateway.

## Agents

- `main`: personal assistant and coding project coordinator.
- `belief`: belief-work agent using `C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc\belief-system`.

The agents should not delegate to each other or read each other's workspaces by default. They are separate surfaces for different kinds of conversation.

## Channel Model

Use one main personal channel for `main`.

Use a separate private belief channel for `belief`.

Do not use free-form agent-to-agent chat as the control layer. If a rare crossover is needed, Kristian should explicitly name the source path and destination.

## Routing

OpenClaw routing bindings pin inbound channel traffic to a specific agent. Bind the belief channel only after the final Discord, Telegram, or other channel account ID is known.

Examples:

```powershell
openclaw agents bind --agent belief --bind discord:<belief-channel-or-account>
openclaw agents bind --agent main --bind discord:<main-channel-or-account>
```

List current agents and bindings:

```powershell
openclaw agents list --bindings
openclaw agents bindings
```

## Workspace Config

The default workspace is the repo root. The belief agent workspace is the nested `belief-system/` folder.

```powershell
openclaw config set agents.defaults.workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc"
openclaw config set agents.list[1].workspace "C:\Users\Kristian Bilstrup\Documents\Codex\2026-04-24\please-remove-that-is-currenly-on\personal-assistant-oc\belief-system"
openclaw gateway restart
```

## Computer Nodes

Keep computer nodes as execution surfaces for the `main` personal/coder agent. A node can run coding tasks, tests, IDE automation, or local commands, but it should not become another independent personal assistant unless that is deliberately configured later.
