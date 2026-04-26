# Two-Agent OpenClaw Setup

This machine uses two isolated OpenClaw agents on the same Gateway.

## Agents

- `main`: personal assistant and coding project coordinator.
- `belief`: belief-work agent using `C:\Users\Kristian Bilstrup\Documents\Belief Change System`.

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

## Computer Nodes

Keep computer nodes as execution surfaces for the `main` personal/coder agent. A node can run coding tasks, tests, IDE automation, or local commands, but it should not become another independent personal assistant unless that is deliberately configured later.
