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

- Agent-facing search: `npm run mem -- search "query"`
- Agent-facing fetch: `npm run mem -- get <id-or-path>`
- Agent-facing capture: `npm run mem -- put --type observation --title "Short title" --summary "What should be remembered"`
- Agent-facing health check: `npm run mem -- check`
- Maintenance refresh: `npm run mem -- refresh`
- Compile digest directly: `npm run memory:compile`
- Report stale/conflicting memory directly: `npm run memory:report`
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

Primary CLI entrypoint is ClawHub/OpenClaw `gog`:

```powershell
gog --help
gog auth status --json --no-input
gog schema --json --no-input
```

Useful safety flags:

- `--json --no-input` for scripted reads.
- `--gmail-no-send` for Gmail triage/draft workflows.
- `--dry-run` before supported write actions.
- `--enable-commands` / `--disable-commands` to narrow a run's command surface.

Setup requires OAuth client credentials stored outside this repository:

```powershell
gog auth credentials set C:\path\outside\repo\client_secret.json
gog auth add you@gmail.com --services gmail,calendar,drive,contacts,tasks,people,docs,sheets --readonly
```

Fallback CLI entrypoint:

```powershell
npm run gws -- --help
```

Use `scripts/gws.mjs` instead of raw `npx ... --params` on Windows when passing JSON. Prefer `--params-file` and `--json-file`; inline JSON flags such as `--params-json` are mostly for shells with reliable quoting.

```powershell
@'
{"calendarId":"primary","maxResults":10}
'@ | Set-Content -LiteralPath .gws-params.json -Encoding UTF8
npm run gws -- calendar events list --params-file .gws-params.json
Remove-Item -LiteralPath .gws-params.json -Force
```

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
