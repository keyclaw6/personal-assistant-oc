# Hardening Prompt

Use this prompt when asking an agent to harden this workspace again:

```text
You are inside the Belief Change System workspace. Perform a full hardening audit without changing the user's belief content unless needed to fix structural defects.

Read AGENTS.md, SOUL.md, TOOLS.md, HEARTBEAT.md, README.md, skills/belief_change_system/SKILL.md, and _system/protocols/12_system_hardening_protocol.md.

Audit:
- Folder name and absolute path references.
- OpenClaw compatibility with workspace skills, root files, HEARTBEAT.md, and agent config examples.
- JSON schema validity.
- PowerShell helper script syntax.
- Belief index links.
- Session protocol completeness.
- Book ingestion completeness.
- Memory safety rules.
- Whether normal belief sessions are prevented from rewriting protected system files.
- Whether heartbeat reminders are configured in files but not overly intrusive.
- Whether OpenClaw reminder behavior is kept OpenClaw-only and no Codex app automation is created unless explicitly requested.
- Whether the system can be used entirely with natural language and does not require the user to remember commands.
- Whether sub-agents are allowed for bounded specialist work with explicit scope, while the main agent keeps ownership of live coaching and final memory updates.

Then harden the system with marginal, traceable edits. Add or update an audit report under _system/audits/YYYYMMDD-hardening-audit.md. Do not delete user memory, prior sessions, archived beliefs, or source notes. Summarize issues found, changes made, verification performed, and remaining risks.
```
