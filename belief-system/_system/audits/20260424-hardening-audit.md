# Hardening Audit

Date: 2026-04-24

## Issues Found

- Project folder was misspelled as `Beleif Change System`.
- Several internal references still used the misspelled path.
- README had a duplicate Completion Reviewer line.
- The OpenClaw example used a stale absolute workspace path.
- The system had no `HEARTBEAT.md` file for OpenClaw heartbeat.
- Normal session instructions did not explicitly protect system-control files from broad rewrites.
- There was no reusable hardening prompt or hardening protocol.
- There was no explicit memory-update policy to prevent broad accidental rewrites of user memory.
- The live OpenClaw CLI exists, but no active OpenClaw config currently points at this workspace.

## Fixes Made

- Renamed the folder to `Belief Change System`.
- Updated stale absolute paths and misspellings.
- Added root `HEARTBEAT.md` with a weekly inactivity check.
- Added heartbeat configuration guidance to the OpenClaw example and setup notes.
- Added protected-file rules to `AGENTS.md`, `TOOLS.md`, and the workspace skill.
- Added `_system/protocols/12_system_hardening_protocol.md`.
- Added `_system/prompts/hardening_prompt.md`.
- Added `_system/protocols/13_memory_update_policy.md`.
- Added `01_profile/memory_log.md`.
- Added `_system/openclaw/live_config_status.md`.
- Added OpenClaw-oriented heartbeat documentation for weekly inactivity reminders.
- Cleaned duplicate README role text.
- Populated `04_sessions/_session_template` with the standard session files.

## Remaining Risks

- `openclaw.example.json5` is an example, not a live OpenClaw config. It must be copied or adapted into the installed OpenClaw configuration.
- The heartbeat reminder only runs when OpenClaw heartbeat is enabled and delivery is configured.
- The current Codex environment could not run `rg`, so PowerShell search was used for the audit.
- A Codex app automation was briefly created during this pass, then deleted at the user's request. Future reminder setup should stay OpenClaw-only unless explicitly requested otherwise.

## Verification To Run

- Search for `Beleif` and stale absolute paths.
- Validate all JSON files.
- Parse all PowerShell helper scripts.
- Verify required root files exist.
- Verify the heartbeat file exists and contains a non-empty task block.

## Second Hardening Pass

Date: 2026-04-24

### Additional Checks Run

- Read `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `HEARTBEAT.md`, `README.md`, `skills/belief_change_system/SKILL.md`, `_system/protocols/12_system_hardening_protocol.md`, and `_system/protocols/13_memory_update_policy.md`.
- Checked current OpenClaw docs for workspace skills, skill frontmatter, heartbeat task blocks, and automation guidance.
- Verified required root files.
- Verified no stale misspelled absolute paths remain.
- Validated all `.json` files with PowerShell `ConvertFrom-Json`.
- Parsed all PowerShell helper scripts.
- Verified belief index links resolve.
- Verified book ingestion folder has all required files.
- Verified session template contains all required files.
- Verified progress ledger header.
- Verified `HEARTBEAT.md` has a `tasks:` block, `168h` interval, and `HEARTBEAT_OK` response contract.
- Verified skill frontmatter has name, description, and valid single-line metadata JSON.

### Additional Issues Found

- `openclaw.example.json5` placed heartbeat under `agents.defaults`, which could make more than the intended default belief coach eligible for heartbeat reminders in a multi-agent setup.
- README called the section `Core Folders` while including `HEARTBEAT.md`, which is a file, not a folder.
- The hardening prompt and protocol did not explicitly forbid Codex app automations during OpenClaw-only hardening.

### Additional Fixes Made

- Moved heartbeat config in `openclaw.example.json5` from `agents.defaults` to the `belief-coach` agent only.
- Updated OpenClaw setup notes to explain that only the belief coach should heartbeat.
- Renamed README section to `Core Folders And Files` and included completion reviewer in the prompt-role description.
- Updated the hardening protocol and hardening prompt to keep reminder behavior OpenClaw-only unless the user explicitly asks for Codex automation.

### Remaining Risks

- `openclaw.example.json5` remains an example, not a live config.
- The workspace skill will not appear in `openclaw skills list` until OpenClaw is configured to use this workspace or the skill is copied into the active workspace.
- `rg` remains blocked in this environment, so PowerShell search was used.
