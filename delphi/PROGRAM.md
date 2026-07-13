# DELPHI PROGRAM — the fixed loop (v0.1)

Delphi is a paper-trading research system: it discovers **leakers** (accounts that
post inside information before it is public), qualifies them against **historical
Polymarket outcomes**, and paper-trades open markets when a qualified leaker posts
a new call. This file is the law of the loop. Intelligence goes into the calls and
the diagnosis — never into redesigning the loop mid-run.

## §0 Non-negotiables

1. **Paper only.** No wallet, no keys, no live orders. `positions.tsv` is the book.
2. **Deterministic accounting.** Edge, Kelly sizing, hit rates, Brier scores are
   computed by scripts, never by an LLM. LLMs extract, match, and estimate
   probabilities; scripts do all arithmetic and all gating.
3. **Isolation.** Delphi lives entirely under `delphi/`. It never reads or writes
   `albert/`, `hermes/`, or any runtime file of the personal assistant. Albert is
   not aware of Delphi.
4. **The market price at signal time is sacred.** Every signal row records the
   price when the signal was detected. Accuracy without price context is
   meaningless: a leaker is valuable only if their hit rate beats the price the
   market offered at post time.
5. **Mechanical failures are fixed mechanically.** A parse error, a dead endpoint,
   a rate limit — one-line fix or skip-and-log. Never a semantic event, never a
   reason to redesign.

## §1 The loop

| Stage | Cadence | Model | What it does |
|---|---|---|---|
| **explorer** | daily | GPT-5.6-Luna (high), via `codex exec` | Proposes new candidate leakers; pulls each candidate's post history; extracts dated claims; matches them to **resolved** Polymarket markets; scripts compute per-call-class hit rate vs price-at-post-time; promotes to `verified` when gates pass |
| **heartbeat** | every 10 min | GPT-5.6-Luna (high), via `codex exec` | Sweeps the roster (verified + probation) for new posts; extracts claims; matches to **open** markets; logs signal rows with price-at-detection |
| **judge** | after each heartbeat | Strong model (default: Opus via OpenRouter) | For signals from verified leakers only: independent probability estimate → scripts compute edge and size → paper bet or pass |
| **resolve** | every 6 h | none (scripts only) | Detects resolved markets; closes positions (P&L, Brier); updates per-leaker per-call-class stats from **all** resolved signals, bet or not |

## §2 Gates (exact, deterministic)

**Verification gate** (leaker × call_class promoted to `verified`):
```
n_calls ≥ verify_min_calls (10)  AND  est_edge = hit_rate − avg_price_at_call ≥ verify_min_edge (0.05)
```
Historical calls found by the explorer count toward `n_calls` — this is what lets
us start betting soon. Calls without a retrievable price-at-post-time count toward
`hit_rate` but are flagged `unpriced` and weighted only via the conservative
fallback: `avg_price_at_call` for unpriced calls is assumed **0.50 or the market's
final pre-resolution consensus, whichever is higher** — never lower.

**Judge gate** (a signal reaches the judge):
```
leaker status = verified (for its call_class)  AND  matched open market  AND  liquidity ≥ min_liquidity_usd
```

**Bet gate** (paper position opened):
```
edge = p_side − price_side − slippage (0.02)  ≥  min_edge (0.10)
AND judge confidence ≥ judge_min_conf (0.6)
size = min( kelly_fraction (0.25) × kelly(p, price) × bankroll , max_stake_frac (0.05) × bankroll )
```
Probation leakers' signals are logged and scored but **never bet** — that is the
probation pipeline accruing evidence for free.

## §3 Roles and boundaries

- **Gatherer prompts** (`prompts/explorer.md`, `prompts/heartbeat.md`) do
  mechanical work only: discover handles, extract dated claims, propose market
  matches, emit implied side. They never output probabilities of world events.
- **Judge prompt** (`prompts/judge.md`) outputs `p_yes`, `confidence`, `rationale`
  — nothing else. It is explicitly forbidden from computing edge or size.
- **Scripts** own all math, all thresholds, all file writes.

## §4 State files (all TSV, append-oriented, git-versioned)

| File | One row per | Key columns |
|---|---|---|
| `domains/<d>/leakers.tsv` | leaker × call_class | status, n_calls, hits, hit_rate, avg_price_at_call, est_edge, last_seen_ts |
| `domains/<d>/candidates.tsv` | proposed leaker | handle, rationale, status |
| `domains/<d>/signals.tsv` | detected call | post_url, claim, call_class, market_id, side, price_at_signal, status, judge_p, edge, resolved_outcome |
| `domains/<d>/positions.tsv` | paper bet | entry_price, size_usd, shares, status |
| `domains/<d>/resolved.tsv` | closed bet | outcome, pnl_usd, brier |
| `ledger/results.tsv` | script run | script, domain, summary |
| `ledger/learnings.md` | amendment | what changed, evidence, expected effect |

## §5 Self-improvement law

The only mutable surfaces are `prompts/*.md`, `config.json`, and
`domains/*/domain.md`. Amendments follow the house pattern:

1. Evidence first: an amendment must cite ledger rows (missed signals, bad
   matches, overconfident judge classes, dead sources).
2. **One amendment per review cycle.** Never batch lever pulls.
3. Every amendment is one row in `ledger/learnings.md`: date, change, evidence,
   expected effect. Revert if the next review shows regression.
4. The loop structure itself (this file, the gates' *shape*) changes only by
   founder decision, never mid-run.

## §6 Failure handling

- Source unreachable → log to results.tsv, skip leaker, continue sweep.
- LLM output not parseable as JSON → one retry with a terse "JSON only" nudge,
  then skip item and log.
- Polymarket endpoint failure → skip item; never invent a price.
- A signal with no matching market → logged with status `no_market` (kept: these
  become explorer fodder and matching-quality evidence).
- Known weak spots expected to need the first amendments: claim→market matching
  precision, Exa X-coverage latency, Gamma search recall. Measure, then amend.
