# TOOLS.md - Local Setup Notes

## OpenClaw

- CLI: `openclaw`
- Gateway dashboard: use `openclaw dashboard`
- Local gateway URL: `http://127.0.0.1:18789/`
- Default model currently configured by OpenClaw: `openai-codex/gpt-5.5`
- Auth: Codex OAuth through the `openai-codex` provider.
- Check model/auth state: `openclaw models status --json`
- Check runtime state: `openclaw status --json`
- Security audit: `openclaw security audit --deep`

## Memory Maintenance

- Capture a memory candidate: `npm run memory:capture -- --type observation --title "Short title" --summary "What should be remembered"`
- Compile digest: `npm run memory:compile`
- Report stale/conflicting memory: `npm run memory:report`
- Refresh compile/report/maintenance prompt: `npm run memory:refresh`
- Check memory health in CI/local scripts: `npm run memory:check`
- Smoke test capture/privacy behavior: `npm run memory:smoke`
- Full local repo check: `npm run check`

## Search

Use `rg` first when it is available:

```powershell
rg -n "keyword" memory-wiki memory
```

Fallback on Windows:

```powershell
Get-ChildItem memory-wiki,memory -Recurse -File | Select-String -Pattern "keyword"
```

## Secrets

Do not commit API keys, tokens, passwords, cookies, private SSH keys, or OpenClaw runtime config files.

## Google Workspace

Preferred CLI entrypoint:

```powershell
npm run gws -- --help
```

Use `scripts/gws.mjs` instead of raw `npx ... --params` on Windows when passing JSON. It supports `--params-file`, `--json-file`, `--params-json`, and `--body-json`.

OpenClaw Gmail webhook helper:

```powershell
openclaw webhooks gmail setup --account you@example.com --tailscale serve --json
openclaw webhooks gmail run --account you@example.com --tailscale serve
```

Google Workspace credentials and exported auth files must live outside this repository.

Authenticate locally:

```powershell
npm run gws -- auth login
```

## Proactive Jobs

List scheduled jobs:

```powershell
openclaw cron list --json
```

Expected jobs:

- `morning-brief`: daily at 07:30 Europe/Copenhagen.
- `friday-belief-check`: Friday at 17:00 Europe/Copenhagen.
