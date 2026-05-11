# Architecture — Companion

> Single personal agent for Kristian Bilstrup. One agent, one workspace,
> three intertwined responsibilities: life ops, belief change, shadow /
> self-knowledge. Read `PHILOSOPHY.md` before this doc.

## Shape

```
Facebook Messenger  ──▶  OpenClaw gateway  ──▶  Companion (single agent)
                                │
                                ├─ cognee-openclaw plugin  ── reads/indexes ─▶  memory/ + MEMORY.md
                                │                            (LanceDB + Kuzu + SQLite under .cognee_system/)
                                │
                                ├─ openclaw-messenger plugin  ── primary channel
                                ├─ gog skill                  ── Google Workspace
                                └─ scripts/morning-brief.mjs  ── 07:30 Europe/Copenhagen cron
```

- **One workspace:** `/home/kab/personal-assistant-oc`. No second agent. No
  belief sub-workspace; belief content lives under `memory/beliefs/` in this
  same workspace and is read by the same agent.
- **Files are source of truth.** Everything durable is Markdown under
  `memory/`. The Cognee plugin sits on top to index and inject retrieval
  context; if it disappeared tomorrow, no durable knowledge would be lost.
- **OpenRouter** is the LLM provider (single API key). DeepSeek high-reasoning
  for chat. OpenRouter embeddings primary, Ollama `nomic-embed-text`
  fallback.
- **Messenger** is the only user-facing channel. OpenClaw dashboard / CLI
  are maintenance only.

## Memory directory

```
memory/
├── profile/        values, current-context, learning-style, shadow-themes, belief-philosophy
├── beliefs/        _index.md + <slug>.md per belief (frontmatter: stage, started, last_touched, completion)
├── shadow/         <pattern-slug>.md (frontmatter: framing, confidence, first/last_observed)
├── sessions/       YYYY-MM-DD/{transcript.md, clarification.md}  ← two-pass discipline
├── life/           commitments.md + briefings/YYYY-MM-DD.md
├── sources/        books/<slug>/{notes.md, belief-map.md}
└── conflicts.md    single file; things currently contested
```

## Posture

Active interlocutor (see `PHILOSOPHY.md`, §"The agent's posture"). Not a
mirror, not an oracle. Proposes interpretations as hypotheses, draws
cross-session parallels unprompted, offers multiple reframings, names what's
avoided, designs experiments, flags contradictions, disagrees gently.
Confidence is stated. Corrections are remembered.

Kristian owns belief-completion marks. The agent may recommend
`ready_for_user_decision`; it cannot complete.

## Two-pass session discipline

Live Messenger conversation is interpretive and warm. After the session ends
(5+ minute pause), two files land under `memory/sessions/YYYY-MM-DD/`:

1. `transcript.md` — raw, unedited.
2. `clarification.md` — deterministic, fact-only summary.

Later pattern analysis reads only clarifications. Never live impressions.

## Morning brief

Daily 07:30 Europe/Copenhagen via Messenger. Falls back to Android
`system.notify` on Kristian's S22; final fallback writes
`memory/life/briefings/YYYY-MM-DD.md` and surfaces in the next heartbeat.

Sections: schedule, priorities, commitments, beliefs in progress, captured
yesterday, mail headline.

## Archived material

`archive/memory-old/`, `archive/memory-wiki-old/`, `archive/belief-system-old/`,
`archive/templates-old/` hold the previous structure for reference. They are
**not** indexed by the Cognee plugin and **not** loaded by the agent. Content
is migrated forward only when Kristian explicitly names it.
