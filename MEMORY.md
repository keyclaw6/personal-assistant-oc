# MEMORY.md — How memory works

Files are the source of truth. The Cognee plugin sits on top.

## Source of truth

Everything durable about Kristian lives as plain Markdown under `memory/`:

```
memory/
├── profile/        values, current context, learning style, shadow themes, belief philosophy
├── beliefs/        one file per belief (slug); _index.md is the human table
├── shadow/         named patterns; interpretive notes (hypotheses)
├── sessions/       YYYY-MM-DD/transcript.md + clarification.md (two-pass discipline)
├── life/           commitments.md + briefings/YYYY-MM-DD.md
├── sources/        books/<slug>/notes.md + belief-map.md
└── conflicts.md    one file; things currently contested
```

Plain Markdown, hand-editable, committable to git, portable. If the Cognee
plugin is removed tomorrow, every durable thing survives.

## Retrieval

The OpenClaw plugin `@cognee/cognee-openclaw` (manifest id `memory-cognee`)
indexes `memory/` and `MEMORY.md` into a knowledge graph (Kuzu) + vector
store (LanceDB) and injects relevant graph-search results into the agent's
context before each run. The agent does **not** call Cognee directly — it
reads files when it needs to and trusts the plugin's pre-run context.

## Writing

- **Capture by writing a file.** No promotion ceremony.
- **Aggressive auto-capture.** After each meaningful Messenger conversation,
  write `memory/sessions/YYYY-MM-DD/transcript.md` and `clarification.md`.
- **Acknowledgment loop.** Morning brief lists "captured yesterday" so
  Kristian can correct.
- **Conflicts.** When new information contradicts existing memory, append a
  one-liner to `memory/conflicts.md` with pointers. Don't silently overwrite.
- **Forget shortcut.** Kristian can message `forget: <fact>` or edit/delete
  the file. The Cognee plugin re-syncs automatically.

## Two-pass session discipline

- `transcript.md` — raw conversation, unedited.
- `clarification.md` — deterministic fact-only summary drawn only from the
  transcript. No coaching flourish, no speculative pattern claims.

Later pattern analysis reads only clarifications, never live impressions.
This separation prevents the model from drifting its own narratives into
"patterns."

## Privacy

`<private>…</private>` blocks are stripped from any compiled artifact. Never
quote them into shared output.

Secrets, tokens, OAuth credentials, and `.cognee_system/` runtime data are
gitignored. `memory/` is committed to a private repo.
