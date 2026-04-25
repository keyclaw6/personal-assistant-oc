# TOOLS.md - Local Setup Notes

## OpenClaw

- CLI: `openclaw`
- Gateway dashboard: use `openclaw dashboard`
- Local gateway URL: `http://127.0.0.1:18789/`
- Default model currently configured by OpenClaw: `openai/gpt-5.5`
- Model auth still needs user login/API key.

## Memory Maintenance

- Compile digest: `npm run memory:compile`
- Report stale/conflicting memory: `npm run memory:report`
- Check memory health in CI/local scripts: `npm run memory:check`

## Search

Use `rg` first:

```powershell
rg -n "keyword" memory-wiki memory
```

## Secrets

Do not commit API keys, tokens, passwords, cookies, private SSH keys, or OpenClaw runtime config files.
