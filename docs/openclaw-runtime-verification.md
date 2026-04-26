# OpenClaw Runtime Verification

Date: 2026-04-26

This note records the live OpenClaw runtime checks completed after configuring the two-agent setup.

## Runtime State

- OpenClaw version: `2026.4.24`
- Gateway: running on `127.0.0.1:18789`
- Gateway probe: `ok`
- Gateway capability: `admin-capable`
- Main model: `openai-codex/gpt-5.5`
- Auth mode: Codex OAuth profile through `openai-codex`
- Local discovery: `bonjour` disabled because the bundled mDNS advertiser was crashing the gateway with `CIAO PROBING CANCELLED`

## Agent Tests

### Personal/Coder OC

Command path: OpenClaw gateway agent turn

Session: `codex-smoke-main-20260426`

Result:

```text
MAIN_OK, Personal/Coder OC, openai-codex/gpt-5.5
```

Capability session: `codex-main-capability-20260426`

Verified:

- Agent identified itself as `Personal/Coder OC`.
- Agent resolved the `personal-assistant-oc` workspace.
- Agent described a concrete coding-project coordination behavior.
- Run metadata reported provider `openai-codex` and model `gpt-5.5`.

### Belief Agent

Command path: OpenClaw gateway agent turn

Session: `codex-smoke-belief-20260426`

Result:

```text
BELIEF_OK - Belief Agent - openai-codex/gpt-5.5
```

Capability session: `codex-belief-capability-20260426`

Verified:

- Agent identified itself as `Belief Agent`.
- Agent resolved the `Belief Change System` workspace.
- Agent loaded the `belief_change_system` skill context.
- Agent answered with a suitable first belief-work question for "I am behind": "Behind compared to what?"
- Run metadata reported provider `openai-codex` and model `gpt-5.5`.

## Dashboard Check

The local Control UI loads at:

```text
http://127.0.0.1:18789/chat?session=main
```

The dashboard requires the gateway token before it can attach to the running gateway. The token was not written into this repository.

## Notes

- The earlier `No API key found for provider "openai"` error was caused by using `openai/gpt-5.5` while the machine was authenticated through Codex OAuth. The working provider/model is `openai-codex/gpt-5.5`.
- The remaining `QQ Bot: not configured` warning is unrelated to the two local agents and did not block either tested agent turn.
