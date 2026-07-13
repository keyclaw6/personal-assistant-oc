# Hermes migration

Albert now runs through Hermes Agent on the `codex/hermes-migration` branch.
The old OpenClaw files are retained as migration reference until this branch is
merged and verified in daily use.

## Local migration command

```bash
npm run hermes:migrate
```

The script is idempotent and does not print secret values. It:

- links `hermes/plugins/messenger-platform` into `~/.hermes/plugins`
- links `hermes/plugins/composio-limited` into `~/.hermes/plugins`
- links `hermes/plugins/cognee-memory` into `~/.hermes/plugins`
- imports the current Codex CLI OAuth login from `~/.codex/auth.json` into
  `~/.hermes/auth.json`
- selects `gpt-5.6-luna` with `xhigh` reasoning
- copies Messenger, Tavily, Cognee, and Composio locations from the local
  OpenClaw/Cognee setup into `~/.hermes/.env`
- configures Hermes to use `albert/` as the working directory
- enables the Hermes curator loop

## Verification

These checks should pass before cutting over production traffic:

```bash
hermes status
hermes plugins list
hermes memory status
hermes --ignore-rules -z 'Reply exactly HERMES_SMOKE_OK.'
timeout 10s hermes gateway run --accept-hooks
node hermes/plugins/composio-limited/bridge.mjs status
```

Cognee search currently authenticates against the local Cognee API, but the
existing vector store may return a Lance/Ladybug initialization error. The
Hermes memory provider therefore searches Cognee first and falls back to direct
file search over `albert/memory/` when the vector index is unhealthy.

## Production cutover notes

- Keep the OpenClaw gateway stopped while testing Hermes Messenger delivery.
- Messenger uses the existing page token, app secret, verify token, and inferred
  home recipient; no credential rediscovery should be needed.
- Composio uses the existing `~/.composio` install and connection profiles.
- File memory remains the durable source of truth under `albert/memory/`.
