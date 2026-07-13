# Delphi — leaker-driven Polymarket paper trader

Self-contained research system living entirely in `delphi/`. It is **not** part
of Albert or the Hermes runtime: no file outside this directory is read or
written, no Hermes plugin is registered, and the personal assistant is not
aware of it. (Named Delphi because `hermes/` is the runtime's plugin
directory.)

**What it does:** an explorer agent finds accounts that leak inside information
(AI/model releases first), back-tests their historical calls against resolved
Polymarket markets — would following them have beaten the price at post time? —
and promotes the ones that pass. A 10-minute heartbeat sweeps the qualified
roster; a strong-model judge turns verified leakers' new calls into **paper**
bets behind deterministic gates. An hourly orchestrator watches the whole
machine and improves the harness through small logged experiments.

**Paper only.** There is no live-trading code path. Going live would be a
separate founder decision after the ledger proves positive expectancy.

Read `PROGRAM.md` first — it is the loop law (invariants, authority tiers,
gates, memory system).

## Layout

```
delphi/
  PROGRAM.md            # the loop law
  config.json           # models, thresholds, kickstart, cognee, orchestrator authority
  prompts/              # task prompts per role (self-improvement surface)
  agents/<name>/        # per-agent workspaces: AGENT.md + MEMORY.md + memory/ notes
  domains/ai-releases/  # domain brief + roster + signals + positions + resolved
  ledger/               # learnings.md (amendments) + results.tsv (run log)
  scripts/              # stdlib-only Python runners (3.11+), no dependencies
  crontab.example       # 10-min heartbeat, hourly orchestrator, kickstart explorer
  REVIEW-PROMPT.md      # paste into an external reviewer chatbot
```

## Agents & authority (PROGRAM §1)

| Agent | Model | Tier |
|---|---|---|
| orchestrator (hourly) | GPT-5.6 xhigh via `codex exec` | T3 — may amend prompts/config/memory, one experiment per run |
| judge | Claude Opus via OpenRouter (default) | T2 — probability judgment |
| explorer / heartbeat | GPT-5.6-Luna high via `codex exec` | T1 — extraction, matching, discovery |
| scripts | — | T0 — gates, accounting, allowlists |

Each agent workspace follows the Hermes pattern: `AGENT.md` (identity/mandate),
`MEMORY.md` (curated lessons, always in context), `memory/` (dated run notes).
Agents append lessons; the orchestrator curates.

## Memory: files + Cognee (PROGRAM §5)

Files are the source of truth. For retrieval, Delphi uses the SAME local
Cognee server as the assistant (`http://127.0.0.1:8000`, see
`docs/cognee-setup.md`) but exclusively its own **`delphi-trading` dataset** —
Albert's datasets are never touched, and Delphi never starts/stops the server.
If the server is down, everything degrades gracefully to files. Optional env:
`DELPHI_COGNEE_URL`, `DELPHI_COGNEE_TOKEN`. **Verify on first run**: the
client targets the standard Cognee REST shape (`/api/v1/add|cognify|search`);
if your server version differs, fix `scripts/cognee.py` once.

## Setup (one time)

```bash
dotenvx set OPENROUTER_API_KEY <key> -f .env.delphi   # judge
dotenvx set EXA_API_KEY <key> -f .env.delphi          # X/Twitter reading
mkdir -p delphi/tmp
python3 delphi/scripts/explorer.py                    # first qualification run
python3 delphi/scripts/orchestrator.py --dry-run      # first diagnosis, applies nothing
```

Luna/orchestrator roles need no key (Codex CLI subscription OAuth). To run the
judge on subscription too, switch `roles.judge.backend` to `codex-cli`.
Then install `crontab.example`.

**Kickstart:** until `config.kickstart.active_until` (default: first ~4 days)
the explorer runs every 3 h with a raised candidate cap to build the roster
fast. Afterwards switch to the daily cron line (or let the orchestrator end
kickstart via config patch).

## Data sources (honest notes)

| Source | Backend | Reliability |
|---|---|---|
| Reddit | public JSON, no auth | high |
| X / Twitter | Exa API (`EXA_API_KEY`) or official API (`X_BEARER_TOKEN`) | medium — minutes of latency, coverage gaps; measured by the ledger |
| Polymarket | Gamma + CLOB public read-only | high (no auth) |

Signal-detection latency is a recorded column; upgrade the X backend only if
the ledger says Exa loses signals.

## External review

`REVIEW-PROMPT.md` is a ready-to-paste prompt for an external reviewer chatbot.
It scopes the review strictly to `delphi/` (never the personal assistant) and
asks for an evidence-gated feedback report.

## House-convention compliance

Additive only (nothing outside `delphi/` modified); secrets via dotenvx;
YAGNI: stdlib-only Python, no framework, no database — TSVs and markdown in
git; daily snapshot commit scoped to `delphi/`.
