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
  domains/ai-releases/  # domain brief + roster + signals + positions + judge journal + resolved
  ledger/               # learnings.md (amendments) + results.tsv (run log)
  scripts/              # stdlib-only Python runners (3.11+), no dependencies
  crontab.example       # 10-min heartbeat, hourly orchestrator, kickstart explorer
  REVIEW-PROMPT.md      # paste into an external reviewer chatbot
```

## Agents & authority (PROGRAM §1)

| Agent | Model | Tier |
|---|---|---|
| orchestrator (hourly) | GPT-5.6 xhigh via `codex exec` | T3 — may amend prompts/config/memory, one experiment per run |
| judge | GPT-5.6-Luna high via `codex exec` | T2 — probability judgment |
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
codex login status                                      # must report ChatGPT login
cp ~/.config/dotenvx/public.env .env.delphi             # one shared keypair
dotenvx set EXA_API_KEY <key> -f .env.delphi \
  -fk ~/.config/dotenvx/.env.keys --no-create           # X/Twitter reading
mkdir -p delphi/tmp
python3 delphi/scripts/explorer.py                    # first qualification run
python3 delphi/scripts/orchestrator.py --dry-run      # first diagnosis, applies nothing
```

All four model roles, including Judge, reuse the logged-in Codex CLI's ChatGPT
OAuth through `codex exec`; no LLM API key is required. Before installing
`crontab.example`, verify the exact cron-like environment can see both the CLI
and login: `env -i HOME=/home/kab CODEX_HOME=/home/kab/.codex
PATH=/home/kab/.local/bin:/usr/local/bin:/usr/bin:/bin codex login status`.
Cron passes `-fk ~/.config/dotenvx/.env.keys` explicitly so the encrypted
root `.env.delphi` reuses the machine's shared keypair without putting a
private key in the repository or crontab.
The committed `delphi/.env.delphi.example` lists non-LLM provider names only.
`OPENCODE_API_KEY` is an empty placeholder for a possible future OpenCode Go
provider and is not consumed by the current runtime.

**Kickstart:** until the strictly canonical UTC timestamp at
`config.kickstart.active_until`, the explorer runs every 3 h with a raised
candidate cap to build the roster fast. `scripts/schedule_gate.py` reads that
field directly for both cron lines, so it is the only schedule source of truth;
invalid config fails closed and runs neither cadence. The current
`2026-07-19T00:00:00Z` cutoff includes all of July 18 UTC and is 02:00 on July
19 in Europe/Copenhagen. At the cutoff the kickstart line stops, and the next
normal explorer is the daily 06:07 Europe/Copenhagen run. The two lines cannot
overlap semantically.

**Daily snapshot safety:** the installed 20:49 job starts disabled. It refuses
to stage or commit unless the encrypted root `.env.delphi` is already tracked,
the git index is clean, and `.git/delphi-snapshot-ready` is an exact regular
file containing `enabled` plus a newline. After intentionally reviewing and
committing the entire current baseline (including `.env.delphi`), enable future
snapshots once with:

```bash
printf 'enabled\n' > "$(git rev-parse --git-path delphi-snapshot-ready)"
```

Do not create that sentinel before the baseline commit. The snapshot includes
`.env.delphi`, runtime TSV/ledger/memory/experiment state, and the exact
prompt/config/domain/agent files the T3 orchestrator may amend. It excludes
scripts, tests, governance, and other arbitrary repository changes; it also
refuses a pre-existing dirty index. This is deliberately narrower than a raw
`git add delphi` so an unattended run cannot commit unreviewed remediation or
unrelated code. It rejects a symlink in any existing component of an
allowlisted path: parents must be real directories and final files must be
regular. The env file must contain exactly the five canonical encrypted dotenvx
assignments in order and decrypt every required provider name through the
configured shared key; validation emits and captures names/status only, never
values. The transaction holds the standard real Git index lock throughout,
stages and validates only in an isolated index, runs the pre-commit hook against
that index, creates the tree/commit object without moving `HEAD`, then installs
the index and advances `HEAD` with guarded rollback. A failed hook, race, or
transaction phase leaves the real index and `HEAD` byte-identical and never
rolls back worktree changes; a failed rollback deliberately leaves the lock as
an explicit fail-stop for recovery.

## Data sources (honest notes)

| Source | Backend | Reliability |
|---|---|---|
| Reddit | public JSON, no auth | medium — cursor-capable, but may rate-limit or block (403); failures are isolated per feed |
| X / Twitter | Exa API (`EXA_API_KEY`) or official API (`X_BEARER_TOKEN`) | medium — minutes of latency, coverage gaps; measured by the ledger |
| Polymarket | Gamma + CLOB public read-only | high (no auth) |

Explorer candidate discovery visits every `reddit:r/<feed>` configured in the
domain brief. It cursor-paginates those feeds in deterministic round-robin order
under `sources.discovery_evidence_budget`; `discovery_page_size`,
`discovery_max_pages_per_source`, and `discovery_evidence_chars` bound provider
and prompt work. The bounded page set is inspected before item selection so a
later-page identity conflict cannot hide behind a full evidence budget. Evidence
retains canonical Reddit ID/URL, full bounded
title/body text, publisher, linked-source identity, and every feed provenance.
A broken feed is isolated; malformed or duplicate entries do not spend the
unique-evidence budget. Proposed identities must bind exactly to that evidence,
and the script enforces the configured candidate cap. This is a current
discovery sweep, not an exhaustive historical archive; Exa history coverage-gap
semantics remain unchanged.

Configuration validation also rejects aggregate discovery work above 100 page
requests, 8,000 raw response items, 4,000,000 scanned evidence characters, or
100,000 serialized prompt-evidence characters per run, including bounded IDs,
URLs, publishers, linked sources, JSON syntax/escaping, and feed provenance.
The exact serialized block is also limited to 100,000 UTF-8 bytes before a
model call. Aggregate checks happen before any provider request and report the
exceeded bound.

Signal-detection latency is a recorded column; upgrade the X backend only if
the ledger says Exa loses signals.

## Score-credit migration

Startup/Resolve replay automatically recomputes `stat_counted` for persisted
signal rows, so legacy event-level deduplication of sibling markets is repaired
from `signals.tsv`. Replay cannot reconstruct calls that the old Explorer
suppressed before appending a signal. For an affected leaker and history window,
deliberately requeue historical qualification and reset only its corresponding
provider/leaker/call-class row in `domains/<domain>/explorer-history.tsv` so the
Explorer revisits that window; replay alone is insufficient.

Resolve materializes `leakers.tsv` as a deterministic best-to-worst roster.
Status ranks `verified`, `probation`, `candidate`, then `retired`; within each
status, canonical `edge_lcb` and priced `n_calls` rank descending, followed by
the `(leaker_id, call_class)` identity ascending. Malformed ranking cells or a
duplicate scorecard identity stop the projection instead of being coerced.
Resolve preflights the exact roster header, row shape, and lowercase
provider-derived IDs before any market request or ledger mutation.

## Judge decision journal

Each domain has an append-only `judge-decisions.tsv` with this exact header:

```
signal_id	domain	market_id	market_question	token_id	side	state	ts_decided	position_id	intended_status	judge_p	judge_conf	edge	quote_price	slippage	entry_price	available_usd	total_equity_usd	kelly_fraction	max_stake_frac	min_edge	judge_min_conf	size_usd	shares	note
```

One `prepared` row is the source of truth for a Judge decision's immutable
trade identity, terminal status, and economics. The position and terminal
signal fields are replayable projections of that evidence; the original signal
must still match the prepared identity byte-for-byte. After both projections
exist, one `final` row repeats every byte of the prepared evidence and changes
only `state`. Rows are literal one-line tab serialization, never CSV-quoted.
Any malformed, torn, noncanonical, duplicate, reordered, orphaned, or
contradictory evidence stops Judge retryably before any recovery write or new
model work.

Judge sizing records both account inputs. Fractional Kelly is applied to
`available_usd`, while `max_stake_frac` is applied to `total_equity_usd`; the
smaller exact-cent value is the paper position size. This keeps open-position
capital unavailable without shrinking the portfolio-level five-percent cap.

## External review

`REVIEW-PROMPT.md` is a ready-to-paste prompt for an external reviewer chatbot.
It scopes the review strictly to `delphi/` (never the personal assistant) and
asks for an evidence-gated feedback report.

## House-convention compliance

Additive only (nothing outside `delphi/` modified except the intentional
encrypted root `.env.delphi`); secrets via dotenvx;
YAGNI: stdlib-only Python, no framework, no database — TSVs and markdown in
git; daily snapshot commit scoped to the guarded allowlist under `delphi/` plus
the encrypted root `.env.delphi`.
