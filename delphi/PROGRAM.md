# DELPHI PROGRAM — the loop law (v0.2)

**The goal this law serves lives in [`VISION.md`](VISION.md) — read it first.**

Delphi discovers **leakers** (accounts posting inside information before it is
public), qualifies them against **historical Polymarket outcomes** (would
following them have made money at the price offered at post time?), and
paper-trades open markets when a qualified leaker posts a new call.

Agents are intelligent and are expected to act like it: they hold their own
workspaces, accumulate lessons, and exercise discretion inside their mandate.
The scoreboard, however, is not a player: recorded history and gate arithmetic
stay deterministic. **Agents think; the scoreboard counts.**

## §0 Invariants (no agent may change these)

1. **Paper only.** No wallet, no keys, no live orders, no live-trading code path.
2. **Recorded history is immutable.** No agent edits or deletes existing rows in
   signals/positions/resolved/results. Append only.
3. **Gate arithmetic is script-owned.** Edge, Kelly, hit rates, Brier — computed
   by scripts, never by an LLM.
4. **Isolation.** Delphi never reads or writes Albert's or the Hermes
   runtime's files; Albert is not aware of Delphi. In Cognee, Delphi touches
   only its own dataset (§5). Documented narrow exceptions: the dotenvx env
   file `.env.delphi` at the repo root (read-only, via `dotenvx run`), the
   daily git snapshot commit (staged paths scoped to `delphi/` only), and LLM
   subprocesses launched with `delphi/` as their working directory.
5. **The price at signal/post time is sacred.** A leaker's value is beating the
   price the market offered when they posted — accuracy alone is meaningless.
6. This file changes only by founder decision.

## §1 Agents, workspaces, authority

Each agent has a Hermes-style workspace under `agents/<name>/`:

| File | Role (Albert-workspace analogue) |
|---|---|
| `AGENT.md` | identity, mandate, discretion, authority tier (≈ SOUL/IDENTITY) |
| `MEMORY.md` | curated long-term lessons — always in context (≈ MEMORY.md) |
| `memory/*.md` | dated run notes, append-only episodic record (≈ memory notes) |

Files are the source of truth; Cognee indexes them for retrieval (§5) — the
same philosophy as the assistant's memory system.

**Authority is proportional to model capability:**

| Tier | Agent (model) | May do | May not do |
|---|---|---|---|
| T3 | **orchestrator** (GPT-5.6 xhigh) | observe everything; ONE amendment per run to prompts / AGENT.md / MEMORY.md curation / domain briefs / guarded config keys; run small logged experiments | touch §0 invariants, ledger history, roles/model config, its own governance block, anything outside `delphi/` |
| T2 | **judge** (strong, default Opus) | probability + confidence judgment; discretion in weighing evidence; write lessons/notes in own workspace | compute edge/size; open positions directly; edit files outside its workspace |
| T1 | **explorer / heartbeat** (GPT-5.6-Luna high) | extraction, matching, candidate discovery; discretion in what to chase, how to phrase queries, which leaker to deepen; lessons/notes in own workspace | probabilities of world events; any file outside own workspace |
| T0 | **scripts** | gates, accounting, file integrity, allowlist enforcement | — |

## §2 The loop

| Stage | Cadence | What it does |
|---|---|---|
| **explorer** | every 3 h during kickstart, then daily | Qualifies seeds first, then new candidates; when the queue is empty it deepens ANY partially-scored, non-verified leaker with an OLDER, paginated history window. Extracts dated claims → maps each claim to at most one resolved market → scripts score hit-rate vs price-at-post-time (priced calls only) → promotion at the §3 gate. Every scored call is a `status=historical` signal row — the FP/FN audit trail — with one credit per (leaker, market) pair, ever. |
| **heartbeat** | every 10 min | Sweeps verified+probation roster for new posts, processed OLDEST-FIRST with a per-post atomic commit — the cursor advances only through fully-processed posts, so backlogs drain across sweeps and transient failures never skip a post. Claims → open-market match → signal rows with price-at-detection. Probation rows tracked, never bet. |
| **judge** | after each heartbeat | Verified signals only. Skips markets Delphi already holds (no exposure stacking). Independent p_yes + confidence with: leaker scorecard, own calibration record, the deterministic **weighted cross-leaker aggregate** for the market (each roster leaker once, weighted by proven lower-bound edge — input, never a gate), and retrieved past cases → scripts gate and size. |
| **resolve** | every 6 h | Closes positions idempotently (P&L, Brier); folds EVERY resolved signal — tracked, passed, bet, and expired — into per-leaker per-call-class stats, one credit per (leaker, market), earliest post wins; feeds summaries to Cognee. |
| **orchestrator** | hourly | §6. |

All state-mutating jobs serialize on ONE shared lock (`tmp/state.lock`) and
all table rewrites are atomic — concurrent runs can never erase each other's
rows.

**Kickstart mode** (config `kickstart`, active until its date): explorer runs
aggressively (higher candidate cap, 3-hourly cron) to build the roster fast.
The orchestrator may end or extend kickstart via config patch.

## §3 Gates (exact, deterministic — unchanged by any agent)

```
verification: n_calls ≥ 10 PRICED calls AND edge_lcb ≥ 0.05    (per leaker × call_class)
              where edge_lcb = wilson_lower(hits, n, z=1.2816) − avg_price_at_call
              (90% one-sided lower bound — a 6/10 coin-flipper does not verify)
priced call:  a price observation existed AT OR BEFORE post time, ≤48h stale.
              No look-ahead: post-event prices are never used. Unpriced calls
              are audit-only (n_unpriced) and never move the gate.
one credit:   at most ONE market per claim, and at most one scored call per
              (leaker, market) pair ever — repeats and overlapping contracts
              cannot double-count. Chosen row carries stat_counted=true.
judge gate:   leaker verified for call_class AND open market matched AND
              liquidity ≥ min AND no open position on that market
bet gate:     fill = FRESH EXECUTABLE best ask for the token being bought
              (fetched AFTER judgment, never a stale midpoint) + slippage
              buffer;  edge = p_side − fill ≥ 0.10 AND confidence ≥ 0.60.
              No fresh quote → the signal stays pending. Judge outputs with
              out-of-range p/confidence are REJECTED, never clamped.
sizing:       min(0.25 × kelly(p_side, fill) × available, 5% × bankroll);
              shares = size / fill;  P&L settles those shares at 0/1.
              (No depth walking: max stake is 5% of a $1k book vs a $1k
              liquidity floor; the ask+buffer fill is conservative.)
account:      self-financing — equity = bankroll + realized P&L;
              available = equity − open cost. Status is recomputed on every
              fold, so live results can demote a verified leaker.
```
False-positive control: mapping precision beats recall everywhere; a wrong
match poisons a scorecard, a missed match only delays qualification. The
call-class taxonomy is FROZEN per domain (config `call_classes`); anything
else normalizes to `unclassified`.

## §4 State

As v0.1 (TSVs under `domains/<d>/`, run log in `ledger/results.tsv`,
amendments in `ledger/learnings.md`) plus:

- `signals.tsv` gains `status=historical` rows (explorer's scored back-test
  calls; audit trail for false-positive/false-negative review) and a
  `stat_counted` column marking exactly which row carried each (leaker,
  market) credit. `positions.tsv` records both `quote_price` and the
  slippage-adjusted `entry_price` (the fill). `leakers.tsv` carries
  `edge_lcb` and `n_unpriced`.
- `agents/<name>/` workspaces (§1). Lessons are appended by the owning agent
  (≤3 per run, only when genuinely new); MEMORY.md curation (dedupe, tighten,
  reorganize) is the orchestrator's job — higher authority curates.

## §5 Memory & Cognee (shared server, isolated dataset)

- Delphi uses the SAME local Cognee server as the assistant
  (`http://127.0.0.1:8000`) but exclusively the **`delphi-trading` dataset**.
  Every add/search call names that dataset explicitly. Albert's datasets are
  never read, written, or cognified by Delphi.
- Ingested: agents' memory notes, resolved-signal summaries, qualification
  summaries. Retrieved: by judge (similar past calls before estimating), by
  explorer (prior qualification work), by orchestrator (cross-agent search).
- Cognee is retrieval only; files remain the source of truth. Server down or
  API mismatch → skip silently and continue on files (same fallback philosophy
  as the assistant's cognee-memory plugin). Delphi never starts/stops the
  server — that is assistant infrastructure.

## §6 Self-improvement & the orchestrator

The orchestrator is the top-level maintainer/goal-direction agent. Hourly:

1. Reads: goal (its AGENT.md), run log tail, every agent's MEMORY.md + latest
   note, roster/signals/positions summaries, active experiments, learnings.
2. Diagnoses against the goal: is the machine finding leakers? qualifying
   them? are signals reaching the judge? are matches precise (FP/FN check on
   `historical` rows)? is anything stuck or drifting?
3. May apply **at most ONE amendment per run** (script-enforced), chosen from:
   - rewrite one T1/T2 task prompt or `AGENT.md`, or curate one `MEMORY.md`
     (its own `MEMORY.md` included; its own `AGENT.md` and task prompt are
     NOT editable — no self-amplification)
   - update one domain brief
   - patch config via the exact ALLOWLIST in `scripts/lib.py`
     (`CONFIG_PATCH_ALLOWED`, type/range validated: kickstart, source volumes,
     x backend, cognee toggles). Gates, sizing, roles, bankroll and isolation
     are NOT patchable by any agent — founder-only.
4. Frames amendments as experiments: rationale, success metric, review-after.
   Every amendment stores a before-image under
   `agents/orchestrator/experiments/`; a `revert` verdict RESTORES that
   before-image — reverts are real, not bookkeeping. Everything is logged:
   one `ledger/learnings.md` row + a dated note in its workspace.

Mechanical failures (parse error, dead endpoint, rate limit) are fixed
mechanically or skipped-and-logged — never treated as semantic events.

## §7 Known weak spots and accepted prototype limits

Expected first experiment targets (measure, then amend): claim→market matching
precision; Exa X-coverage latency/gaps; Gamma search recall; unpriced-history
conservatism slowing verification. Evidence lives in `historical` and
`no_market` signal rows and results.tsv.

Accepted limits — deliberate scope decisions for a paper prototype, each with
its mitigation, NOT open bugs:

- **Survivorship in historical feeds** (deleted posts, bounded X search):
  historical qualification is therefore provisional by design; every verified
  leaker keeps being re-tested prospectively on live folds (`n_live` column),
  and the Wilson gate demotes on live underperformance automatically.
- **Extraction outcome-awareness**: the LLM extracting historical claims may
  know outcomes. Mitigated by the extract-everything instruction, the removal
  of the LLM scoreability gate, and prospective re-testing — not eliminable
  in a prototype without immutable archives.
- **No order-book depth walking**: stakes are capped at 5% of a $1k paper book
  against a $1k liquidity floor; fills use the executable best ask plus a
  conservative buffer. Bias is against the book, never for it.
- **Serialized jobs**: heartbeat sweeps may skip while explorer holds the
  state lock; the oldest-first cursor drains any backlog afterwards.
