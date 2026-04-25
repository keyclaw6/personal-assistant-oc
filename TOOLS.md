# TOOLS.md - Local Setup Notes

## OpenClaw

- CLI: `openclaw`
- Gateway dashboard: use `openclaw dashboard`
- Local gateway URL: `http://127.0.0.1:18789/`
- Default model currently configured by OpenClaw: `openai/gpt-5.5`
- Model auth still needs user login/API key.

## Memory Maintenance

- Capture a memory candidate: `npm run memory:capture -- --type observation --title "Short title" --summary "What should be remembered"`
- Compile digest: `npm run memory:compile`
- Report stale/conflicting memory: `npm run memory:report`
- Refresh compile/report/maintenance prompt: `npm run memory:refresh`
- Check memory health in CI/local scripts: `npm run memory:check`
- Smoke test capture/privacy behavior: `npm run memory:smoke`

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
