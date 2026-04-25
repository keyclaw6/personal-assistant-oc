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

- Default configured model: `openai/gpt-5.5`
- Auth status: requires provider login/API key
