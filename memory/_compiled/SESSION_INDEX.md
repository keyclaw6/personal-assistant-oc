# Session Memory Index

This is the first file to scan. It shows what memory exists and the approximate read cost. Fetch details only when useful.

## Retrieval Protocol

1. Scan the page index below.
2. Read only the one or two source pages that match the current task.
3. Search raw logs under `memory/` only when the wiki does not answer the question.
4. Keep new durable facts in `memory/inbox/` until they can be promoted with evidence.
5. After memory edits, run `npm run memory:refresh` and check the report.

## Page Index

| ID | Type | Status | Conf | Cost | Page | Path |
| --- | --- | --- | ---: | ---: | --- | --- |
| profile.kristian | profile | draft | 0.65 | ~275 | Profile | `PROFILE.md` |
| preferences.kristian | preferences | draft | 0.70 | ~311 | Preferences | `PREFERENCES.md` |
| stack.local-openclaw | stack | active | 0.80 | ~293 | Stack | `STACK.md` |
| projects.active | projects | active | 0.70 | ~230 | Projects | `PROJECTS.md` |
| decisions.main | decisions | active | 0.80 | ~535 | Decisions | `DECISIONS.md` |
| people.main | people | draft | 0.60 | ~199 | People | `PEOPLE.md` |
| working.current | working | active | 0.75 | ~298 | Working | `WORKING.md` |
| entity.personal-assistant-oc | entity | active | 0.80 | ~225 | Personal Assistant OC | `entities/personal-assistant-oc.md` |
| concept.file-based-memory | concept | active | 0.85 | ~265 | File-Based Memory | `concepts/file-based-memory.md` |
| synthesis.memory-architecture | synthesis | active | 0.85 | ~419 | Memory Architecture | `syntheses/memory-architecture.md` |
| source.research-file-memory-2026-04-25 | source | active | 0.80 | ~187 | Research Source Note - File Memory | `sources/research-file-memory-2026-04-25.md` |

## High-Signal Claims

| ID | Status | Conf | Claim | Path |
| --- | --- | ---: | --- | --- |
| profile.kristian.file-memory-goal | active | 0.85 | Kristian wants the assistant memory to be file-based, inspectable, and low-infrastructure. | `PROFILE.md` |
| profile.kristian.timezone | active | 0.80 | Kristian's working timezone is Europe/Copenhagen. | `PROFILE.md` |
| preference.memory.no-vector-db | active | 0.95 | Use file-based memory without a vector database by default. | `PREFERENCES.md` |
| preference.memory.no-extra-api-keys | active | 0.90 | Do not require a separate memory or embedding API key for baseline memory. | `PREFERENCES.md` |
| preference.memory.conflicts-visible | active | 0.85 | Surface memory conflicts instead of silently overwriting them. | `PREFERENCES.md` |
| stack.openclaw.local-gateway | active | 0.80 | OpenClaw is expected to run locally through the loopback gateway. | `STACK.md` |
| stack.memory.node-scripts | active | 0.85 | Memory maintenance uses dependency-free Node scripts. | `STACK.md` |
| stack.memory.vector-db-disabled | active | 0.95 | The starter disables vector database storage by default. | `STACK.md` |
| project.personal-assistant-oc.active | active | 0.90 | The active project is the `personal-assistant-oc` OpenClaw workspace. | `PROJECTS.md` |
| project.personal-assistant-oc.file-only | active | 0.95 | The repository should work without a vector database or memory API service. | `PROJECTS.md` |
| decision.file-memory-default | active | 0.95 | Personal Assistant OC uses Markdown and JSONL files as the primary memory store. | `DECISIONS.md` |
| decision.progressive-disclosure | active | 0.85 | The assistant should scan an index first and fetch details on demand. | `DECISIONS.md` |
| decision.no-heavy-storage | active | 0.90 | The starter borrows lifecycle ideas from heavier systems without adopting SQLite, Chroma, or workers. | `DECISIONS.md` |
| decision.conflicts-explicit | active | 0.90 | Contradictory memories become conflict notes until resolved. | `DECISIONS.md` |
| person.kristian.primary-user | active | 0.85 | Kristian Bilstrup is the primary user of this assistant. | `PEOPLE.md` |
| people.add-sparingly | active | 0.80 | Other people should be added only when useful and safe. | `PEOPLE.md` |
| working.memory-polish | active | 0.85 | The file-only memory system has been polished for robust, minimal operation. | `WORKING.md` |
| entity.personal-assistant-oc.workspace | active | 0.85 | The repository is an OpenClaw personal assistant workspace. | `entities/personal-assistant-oc.md` |
| entity.personal-assistant-oc.file-memory | active | 0.95 | The repository's baseline memory is file-only. | `entities/personal-assistant-oc.md` |
| concept.file-memory.transparent | active | 0.90 | File-based memory is transparent, auditable, and model-agnostic. | `concepts/file-based-memory.md` |
| concept.file-memory.progressive | active | 0.85 | File-based memory should be retrieved progressively rather than loaded all at once. | `concepts/file-based-memory.md` |
| synthesis.memory.three-lane | active | 0.85 | The architecture separates raw capture, curated wiki, and compiled context. | `syntheses/memory-architecture.md` |
| synthesis.memory.index-first | active | 0.90 | The default retrieval path is index first, page second, raw logs last. | `syntheses/memory-architecture.md` |
| synthesis.memory.robust-personal | active | 0.80 | The architecture is robust for personal assistant memory when maintenance checks are run after edits. | `syntheses/memory-architecture.md` |
