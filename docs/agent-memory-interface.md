# Agent Memory Interface

This workspace keeps the durable memory system file-first, but exposes a small model-facing facade.

## Design Goal

The agent should not need to reason about compile scripts, reports, caches, or schema internals during normal work. It needs four verbs:

| Verb | Command | When To Use |
| --- | --- | --- |
| `mem search` | `npm run mem -- search "query"` | Find candidate pages or claims. |
| `mem get` | `npm run mem -- get <id-or-path>` | Fetch the selected memory. |
| `mem put` | `npm run mem -- put --title "..." --summary "..."` | Capture a raw, unreviewed fact. |
| `mem check` | `npm run mem -- check` | Verify health after edits. |

`npm run mem -- refresh` is available after durable edits, but it is a maintenance action rather than the default recall path.

## Why This Shape

Agent benchmark work keeps pointing to the harness as a major performance lever: shorter context, clearer action affordances, fewer irrelevant tools, and better trace feedback. The memory interface follows that:

- Names stay short but semantic. Prefer `mem search` over opaque aliases such as `ms`.
- The default surface is four verbs. Maintenance commands remain available but are not shown first.
- Recall is progressive. Search first, fetch one page or claim, then stop when there is enough context.
- Output defaults to Markdown because OpenClaw agents can read it cheaply. JSON remains available with `--format json` for scripted flows.

## Prompt Contract

Use this pattern in agent instructions:

1. Start from `memory/_compiled/SESSION_INDEX.md`.
2. If needed, run `npm run mem -- search "task keywords"`.
3. Run `npm run mem -- get <id-or-path>` for only the selected memory.
4. Capture new durable candidates with `npm run mem -- put ...`.
5. After memory edits, run `npm run mem -- refresh` and `npm run mem -- check`.

Do not expose `memory:compile`, `memory:report`, `memory:eval`, or `memory:smoke` as normal agent tools. Those are development and maintenance commands.

## Benchmark Notes

- Terminal-Bench-style work suggests that the same model can perform differently depending on harness design, tool affordances, prompt structure, and context budget.
- Meta-harness approaches improve results by deciding what to store, retrieve, and show instead of loading everything.
- OpenAI Agents SDK guidance recommends small, namespaced tool groups when tool surfaces grow.

For this repository, that means the best next optimization is a thin memory facade, not more memory machinery.
