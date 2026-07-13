# Delphi — leaker-driven Polymarket paper trader

Self-contained research system living entirely in `delphi/`. It is **not** part of
Albert or the Hermes runtime: no file outside this directory is read or written,
no Hermes plugin is registered, and the personal assistant is not aware of it.
(Named Delphi because `hermes/` is the runtime's plugin directory.)

**What it does:** an explorer agent finds accounts that leak inside information
(AI/model releases first), back-tests their historical calls against resolved
Polymarket markets, and promotes the ones whose hit rate beats the price the
market offered at post time. A 10-minute heartbeat sweeps the qualified roster;
when a verified leaker posts a relevant call, a strong-model judge estimates the
probability and the scripts open a **paper** position if the edge clears the gate.
Everything is TSV files in git. See `PROGRAM.md` for the loop law.

**Paper only.** There is no live-trading code path. Going live would be a separate
founder decision after the ledger proves positive expectancy.

## Layout

```
delphi/
  PROGRAM.md            # the loop law — read this first
  config.json           # models, thresholds, cadences, sources
  prompts/              # explorer / heartbeat / judge (the self-improvement surface)
  domains/ai-releases/  # domain brief + roster + signals + positions + resolved
  ledger/               # learnings.md (amendments) + results.tsv (run log)
  scripts/              # stdlib-only Python runners (3.11+), no dependencies
  crontab.example       # 10-min heartbeat, daily explorer, 6-h resolve
```

## Setup (one time)

1. **Models.** Explorer + heartbeat run GPT-5.6-Luna (reasoning high) through the
   already-authenticated Codex CLI (`codex exec`, subscription OAuth — no API
   key). The judge defaults to Claude Opus via OpenRouter. Keys live in a
   dotenvx-encrypted env file, per house convention:

   ```bash
   dotenvx set OPENROUTER_API_KEY <key> -f .env.delphi
   dotenvx set EXA_API_KEY <key> -f .env.delphi          # X/Twitter reading backend
   # optional instead of Exa: dotenvx set X_BEARER_TOKEN <key> -f .env.delphi
   ```

   No key at all is needed for the Luna roles. To run the judge on subscription
   too, set `roles.judge.backend` to `codex-cli` in `config.json` (one line).

2. **Cron.** `crontab -e`, paste from `crontab.example` (adjust repo path).

3. **Sanity check without cron:**

   ```bash
   python3 delphi/scripts/explorer.py --domain ai-releases   # discover + qualify
   python3 delphi/scripts/heartbeat.py --domain ai-releases  # sweep roster once
   python3 delphi/scripts/judge.py --domain ai-releases      # decide pending signals
   python3 delphi/scripts/resolve.py --domain ai-releases    # score resolutions
   ```

## Data sources (honest notes)

| Source | Backend | Reliability |
|---|---|---|
| Reddit | public JSON endpoints, no auth | high |
| X / Twitter | Exa API (`EXA_API_KEY`) or official API (`X_BEARER_TOKEN`) | medium — minutes of latency, coverage gaps; fine for paper trading; measured by the ledger |
| Polymarket | Gamma + CLOB public read-only APIs | high (no auth needed) |

Signal-detection latency is a recorded column — if Exa's X coverage proves too
laggy, upgrading to the official X API is the first infra spend worth considering,
decided on ledger evidence.

## Seed roster

`domains/ai-releases/leakers.tsv` ships with a few well-known candidate handles,
**all status `candidate` with empty stats** — the explorer must qualify them from
their actual historical record before anything is trusted. Do not hand-promote.

## House-convention compliance

- Additive only: no edits to `albert/`, `hermes/`, `package.json`, `scripts/`.
- Secrets via dotenvx (`.env.delphi`); nothing plaintext, nothing in code.
- YAGNI: stdlib-only Python, no framework, no database — TSVs in git.
- Daily state snapshot commit is in `crontab.example` (scopes `git add` to
  `delphi/` only).
