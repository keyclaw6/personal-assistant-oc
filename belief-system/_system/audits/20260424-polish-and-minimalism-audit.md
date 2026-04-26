# Polish And Minimalism Audit

Date: 2026-04-24

## Question

Can the system be more robust and more minimal while keeping the same function?

## Assessment

The system should not be minimal by deleting its protocols. It should be minimal in runtime behavior: load only the relevant files, route tasks clearly, and use the smallest context that can do the job.

The prior structure was strong but could lead future agents to think every markdown file should be loaded. This pass adds an explicit context-loading policy and a minimal operating model.

## Issues Found

- Book ingestion could still encourage whole-book summaries that miss detail.
- The system did not yet define chapter-by-chapter ingestion.
- The system did not yet support external chat prompt export and transcript import.
- It was not explicit that OpenClaw skills are a routing layer, not a command to load the whole workspace.
- There was no minimal operating model explaining how to use the many files without bloating context.

## Changes Made

- Added `_system/protocols/17_context_loading_policy.md`.
- Added `_system/protocols/18_chapter_ingestion_protocol.md`.
- Added `_system/protocols/19_external_chat_workflow.md`.
- Added `_system/templates/external_chat_prompt.md`.
- Added `_system/templates/chapter_manifest.json`.
- Added `10_exports/prompts/README.md`.
- Added `00_inbox/session_requests/README.md`.
- Added `_system/MINIMAL_OPERATING_MODEL.md`.
- Updated book ingestion protocol to prefer chapter-by-chapter or section-by-section ingestion for long sources.
- Updated source librarian prompt with chapter mode.
- Updated skill routing for chapter ingestion, external chat export/import, and context loading.
- Updated README with external prompt/export/import use.

## Design Decision

The best version is:

- Many stable files on disk.
- Small context per task.
- Chapter-level ingestion before whole-book synthesis.
- External chat prompts that are focused and portable.
- Transcript imports that become normal session folders.

## Remaining Improvements

- Add a helper script to create chapter folders from `chapter_manifest.json`.
- Add a helper script to export an external prompt from a belief slug.
- After actual sessions exist, test the external transcript import workflow end to end.
