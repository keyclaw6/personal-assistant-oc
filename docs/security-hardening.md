# Security Hardening

## Trust Boundaries

Hermes is powerful because it can read files, run tools, browse, and connect channels. That same power means the security boundary is mostly about who can reach the agent, what content it reads, what tools it can use, and where secrets live.

Default posture for this repo:

- Gateway stays on loopback unless a remote access plan is documented.
- Single agent (Albert) with Messenger as primary channel.
- `.hermes/`, `.openclaw/`, auth profiles, tokens, credentials, logs, and local runtime state stay out of Git.
- Third-party skills are treated as code, not harmless prompts.
- External content is treated as untrusted even when it arrives from Kristian.

## Routine Checks

Run these after Hermes upgrades, channel changes, tool changes, or major repo edits:

```bash
hermes status
hermes plugins list
hermes doctor
npm run check
```

If diagnostics ask for a gateway token or OAuth credential, do not paste or commit it. Use local config only when necessary.

## Channel Policy

- Messenger is the primary user-facing channel.
- Hermes CLI / gateway are maintenance-only.
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
- `.cognee_system/` and `.cognee_data/` are gitignored. `.env.cognee` is tracked only in dotenvx-encrypted form; `.env.keys` stays outside Git.

## Git Policy

Before pushing:

```bash
git status --short
npm run check
```

Only commit files that are intended to become part of the private source of truth. Do not commit `.hermes/`, `.openclaw/`, `node_modules/`, raw provider credentials, dashboard URLs with tokens, or generated local runtime state.
