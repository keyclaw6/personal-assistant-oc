# Claim Health

Claims scanned: 31

## Claims

- `concept.file-memory.transparent` active 0.90 - File-based memory is transparent, auditable, and model-agnostic. (concepts/file-based-memory.md)
- `concept.file-memory.progressive` active 0.85 - File-based memory should be retrieved progressively rather than loaded all at once. (concepts/file-based-memory.md)
- `decision.file-memory-default` active 0.95 - Personal Assistant OC uses Markdown and JSONL files as the primary memory store. (DECISIONS.md)
- `decision.progressive-disclosure` active 0.85 - The assistant should scan an index first and fetch details on demand. (DECISIONS.md)
- `decision.no-heavy-storage` active 0.90 - The starter borrows lifecycle ideas from heavier systems without adopting SQLite, Chroma, or workers. (DECISIONS.md)
- `decision.conflicts-explicit` active 0.90 - Contradictory memories become conflict notes until resolved. (DECISIONS.md)
- `decision.two-agent-single-repo` active 0.90 - Keep `main` and `belief` as separate OpenClaw agents while storing both workspaces in this private repository. (DECISIONS.md)
- `entity.personal-assistant-oc.workspace` active 0.85 - The repository is an OpenClaw personal assistant workspace. (entities/personal-assistant-oc.md)
- `entity.personal-assistant-oc.file-memory` active 0.95 - The repository's baseline memory is file-only. (entities/personal-assistant-oc.md)
- `person.kristian.primary-user` active 0.85 - Kristian Bilstrup is the primary user of this assistant. (PEOPLE.md)
- `people.add-sparingly` active 0.80 - Other people should be added only when useful and safe. (PEOPLE.md)
- `preference.memory.no-vector-db` active 0.95 - Use file-based memory without a vector database by default. (PREFERENCES.md)
- `preference.memory.no-extra-api-keys` active 0.90 - Do not require a separate memory or embedding API key for baseline memory. (PREFERENCES.md)
- `preference.memory.conflicts-visible` active 0.85 - Surface memory conflicts instead of silently overwriting them. (PREFERENCES.md)
- `profile.kristian.file-memory-goal` active 0.85 - Kristian wants the assistant memory to be file-based, inspectable, and low-infrastructure. (PROFILE.md)
- `profile.kristian.timezone` active 0.80 - Kristian's working timezone is Europe/Copenhagen. (PROFILE.md)
- `project.personal-assistant-oc.active` active 0.90 - The active project is the `personal-assistant-oc` OpenClaw workspace. (PROJECTS.md)
- `project.personal-assistant-oc.file-only` active 0.95 - The repository should work without a vector database or memory API service. (PROJECTS.md)
- `project.belief-system.integrated` active 0.90 - The belief tracking system is now included under `belief-system/` in this repository as the separate `belief` agent workspace. (PROJECTS.md)
- `source.harness.small-surface` active 0.80 - Small semantic tool surfaces are easier for agents to navigate than exposing every maintenance command. (sources/harness-2026-04-27.md)
- `source.harness.progressive-memory` active 0.80 - Memory recall should search first, fetch one relevant item, and stop when enough context is available. (sources/harness-2026-04-27.md)
- `stack.openclaw.local-gateway` active 0.80 - OpenClaw is expected to run locally through the loopback gateway. (STACK.md)
- `stack.memory.node-scripts` active 0.85 - Memory maintenance uses dependency-free Node scripts. (STACK.md)
- `stack.memory.vector-db-disabled` active 0.95 - The starter disables vector database storage by default. (STACK.md)
- `stack.model.openai-codex` active 0.90 - The verified working model is `openai-codex/gpt-5.5` using Codex OAuth. (STACK.md)
- `synthesis.memory.three-lane` active 0.85 - The architecture separates raw capture, curated wiki, and compiled context. (syntheses/memory-architecture.md)
- `synthesis.memory.index-first` active 0.90 - The default retrieval path is index first, page second, raw logs last. (syntheses/memory-architecture.md)
- `synthesis.memory.short-facade` active 0.85 - OpenClaw agents should use the four-verb memory facade for normal memory work. (syntheses/memory-architecture.md)
- `synthesis.memory.robust-personal` active 0.80 - The architecture is robust for personal assistant memory when maintenance checks are run after edits. (syntheses/memory-architecture.md)
- `working.memory-polish` active 0.85 - The file-only memory system has been polished for robust, minimal operation. (WORKING.md)
- `working.gog-primary` active 0.85 - The primary Google Workspace skill is now ClawHub/OpenClaw `gog`; the local Google Workspace assistant skill remains the policy layer. (WORKING.md)

