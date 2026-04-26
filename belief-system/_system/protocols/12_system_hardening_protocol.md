# System Hardening Protocol

Use this when the user asks to audit, harden, polish, repair, or make the workspace more robust.

## Goals

- Preserve the user's belief memory.
- Improve structural reliability.
- Improve OpenClaw compatibility.
- Reduce accidental self-modification.
- Make future agent behavior more deterministic and auditable.

## Audit Checklist

1. Verify the project folder name and absolute paths.
2. Search for stale path references and misspellings.
3. Validate JSON files.
4. Parse PowerShell helper scripts.
5. Check OpenClaw skill frontmatter.
6. Confirm `HEARTBEAT.md` exists and is not empty.
7. Confirm root instructions protect system files during normal sessions.
8. Confirm schemas match templates.
9. Confirm belief indexes point to existing belief files.
10. Confirm book folders have required ingestion files.
11. Confirm progress ledger exists and has stable headers.
12. Confirm OpenClaw reminder behavior is documented through `HEARTBEAT.md`, not Codex app automation, unless the user explicitly requested otherwise.
13. Confirm natural-language usage does not require the user to remember special commands.
14. Confirm sub-agent use is allowed only for bounded specialist tasks with explicit scope.
15. Write an audit report under `_system/audits`.

## Editing Rules

- Use marginal edits.
- Preserve existing session and belief records.
- Do not rewrite user memory unless fixing a clear structural defect.
- Prefer adding a protocol, note, or audit file over changing meaning in old records.
- If a path is renamed, update all references in the workspace.
- Do not create Codex app automations during OpenClaw hardening unless the user explicitly asks for Codex-specific automation.

## Completion

Finish with:

- Files changed.
- Issues found.
- Issues fixed.
- Remaining risks.
- Verification commands run.
