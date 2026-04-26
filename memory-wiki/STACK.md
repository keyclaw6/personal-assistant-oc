---
id: stack.local-openclaw
type: stack
status: active
confidence: 0.8
freshness: quarterly
review_after: 2026-07-01
sources:
  - TOOLS.md
---

# Stack

## Startup Summary

OpenClaw runs locally on Windows with Node and a loopback gateway. Memory is maintained with Markdown files and dependency-free Node scripts.

## Claims

| ID | Status | Confidence | Evidence | Claim |
| --- | --- | ---: | --- | --- |
| stack.openclaw.local-gateway | active | 0.80 | TOOLS.md | OpenClaw is expected to run locally through the loopback gateway. |
| stack.memory.node-scripts | active | 0.85 | package.json | Memory maintenance uses dependency-free Node scripts. |
| stack.memory.vector-db-disabled | active | 0.95 | memory-wiki/.openclaw-wiki/config.json | The starter disables vector database storage by default. |
| stack.model.openai-codex | active | 0.90 | 2026-04-26 runtime verification | The verified working model is `openai-codex/gpt-5.5` using Codex OAuth. |

## Local Runtime

- OS: Windows
- Shell: PowerShell
- Node: required by OpenClaw and these scripts
- OpenClaw CLI: `openclaw`
- Gateway: loopback, port `18789`
- Dashboard: launch via `openclaw dashboard`

## Memory Runtime

- Storage: Markdown and JSONL files
- Search: `rg` / plain text
- Compile: `npm run memory:compile`
- Health report: `npm run memory:report`
- Vector DB: intentionally absent

## Model Runtime

- Default configured model: `openai-codex/gpt-5.5`
- Auth status: Codex OAuth verified locally
