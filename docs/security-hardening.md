# Security Hardening

## Trust Boundaries

OpenClaw is powerful because it can read files, run tools, browse, and connect channels. That same power means the security boundary is mostly about who can reach the agent, what content it reads, what tools it can use, and where secrets live.

Default posture for this repo:

- Gateway stays on loopback unless a remote access plan is documented.
- Single agent (Albert) with Messenger as primary channel.
- `.openclaw/`, auth profiles, tokens, credentials, logs, and local runtime state stay out of Git.
- Third-party skills are treated as code, not harmless prompts.
- External content is treated as untrusted even when it arrives from Kristian.

## Routine Checks

Run these after OpenClaw upgrades, channel changes, tool changes, or major repo edits:

```bash
openclaw status --json
openclaw models status --json
openclaw security audit --deep
npm run check
```

If `openclaw security audit --deep` asks for the Gateway token, do not paste or commit it. Use the interactive dashboard or local config only when necessary.

## Channel Policy

- Messenger is the primary user-facing channel.
- OpenClaw dashboard / CLI are maintenance-only.
- Do not expose the Gateway on `0.0.0.0` without auth, firewalling, and a reason.
- Keep `/reasoning` and verbose/debug output out of shared channels.

## Tool Policy

- Ask before sending messages, posting, deleting, buying, moving large folders, or changing accounts.
- Keep risky tools (`exec`, browser, web fetch/search, filesystem writes) limited to trusted agents and explicit tasks.
- Use a read-first flow for untrusted documents, emails, web pages, and imported books.
- Prefer draft outputs for email/calendar/message actions until the exact approval phrase is given.

## Memory Policy

- Do not store API keys, passwords, cookies, private keys, session tokens, or OAuth tokens in memory.
- Use `<private>...</private>` blocks only for sensitive notes that should be stripped from compiled artifacts.
- Conflicts go to `albert/memory/conflicts.md`; do not silently overwrite old claims.
- `.cognee_system/`, `.cognee_data/`, `.env.cognee` are gitignored.

## Git Policy

Before pushing:

```bash
git status --short
npm run check
```

Only commit files that are intended to become part of the private source of truth. Do not commit `.openclaw/`, `node_modules/`, raw provider credentials, dashboard URLs with tokens, or generated local runtime state.
