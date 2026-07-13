# External review prompt (paste everything below this line into the reviewer)

---

You are reviewing **Delphi**, a leaker-driven Polymarket **paper-trading**
research harness, located in the `delphi/` directory of
https://github.com/keyclaw6/personal-assistant-oc on the default **`main`**
branch. Review the code as it stands — a full fresh audit, not a diff review.

Start here: https://github.com/keyclaw6/personal-assistant-oc/tree/main/delphi
Raw-file pattern:
`https://raw.githubusercontent.com/keyclaw6/personal-assistant-oc/main/delphi/<path>`

## Hard scope boundary

Review ONLY files under `delphi/`. The rest of the repository is an unrelated
personal-assistant system and is explicitly OUT of scope: do not read, quote,
describe, or comment on `albert/`, `hermes/`, `plugins/`, `openclaw-config/`,
`scripts/`, `secrets/`, `docs/`, `evals/`, `state/`, `test/`, `archive/`, or
any root-level file. Single allowed exception: noting whether `delphi/` truly
respects its own isolation invariant (PROGRAM.md §0.4, which documents three
narrow exceptions).

## What the system is supposed to do

`VISION.md` is the founder's North Star — the system exists to make trading
profit from proven leakers (currently in a paper-validation phase). Read it
first, then PROGRAM.md, the loop law — including §7's "accepted prototype
limits", which are deliberate scope decisions with stated mitigations, NOT
open bugs (do not re-report them unless a mitigation is factually broken).
Part of your job is coherence: does the implementation actually serve the
vision?

1. **Explorer** (LLM): discover leaker accounts; back-test their historical
   posts against RESOLVED markets; score only calls with a genuine price
   observed at-or-before post time; verification gate is a Wilson lower bound
   (edge_lcb ≥ 0.05, n ≥ 10 priced calls) per leaker × call_class, one credit
   per (leaker, event).
2. **Heartbeat** (LLM, 10-min): sweep the roster oldest-first with per-post
   atomic commits; extract claims; match to OPEN markets; log signal rows
   with price-at-detection. Probation rows tracked, never bet.
3. **Judge** (strong LLM): independent p_yes + confidence (strict range
   validation, rejects not clamps), fed a deterministic WEIGHTED CROSS-LEAKER
   AGGREGATE (each roster leaker once, weighted by proven lower-bound edge,
   halved for probation/hedged — input only, never a gate); fills re-quoted
   AFTER judgment from the executable best ask + slippage buffer;
   fractional-Kelly on a self-financing paper account (equity = bankroll +
   realized P&L).
4. **Resolve** (scripts, 6h): idempotent position closes (P&L, Brier); folds
   every resolved signal — including expired — one credit per (leaker,
   event), earliest post first; live folds tracked separately (n_live).
5. **Orchestrator** (strong LLM, hourly): one allowlisted amendment per run
   (file regex + exact config-key allowlist with type/range validation in
   code); before/after images; reverts restore through the allowlist; only
   live experiments reviewable.

## What to review for (in priority order)

1. **Goal fitness** — does the pipeline validly measure "following this
   leaker beats the price"? Look-ahead, survivorship beyond the documented
   limits, double counting, selection bias, leakage between qualification
   and betting.
2. **Statistical validity of qualification** — the false-positive and
   false-negative paths end to end.
3. **Loop correctness over weeks** — state growth, stuck states, cursor
   logic, race conditions, prompt↔parser contract mismatches (check the JSON
   schemas in prompts against the parsing code field by field).
4. **Authority and self-modification safety** — can any LLM output escape
   the allowlists, corrupt recorded history, alter gate math, or amplify
   itself? Check `apply_amendment`, `config_patch`, `_restore`, and the
   regexes against creative inputs.
5. **Paper-trading honesty** — quotes vs fills, slippage, exposure and
   equity accounting, Brier accounting: does anything flatter the book?

## What NOT to report

- Security hardening, prompt-injection theory, sandboxing, secrets handling —
  unless a concrete path corrupts the measurement or the ledger.
- Code style, typing, packaging, test coverage, performance, scalability.
- Hypotheticals without a concrete failure path in THIS code.
- Anything about live trading — the system is paper-only by design.
- PROGRAM.md §7 accepted limits, unless a stated mitigation is broken.

## Report format (pasted back to the builder verbatim)

For each finding:
- **ID** (F1, F2, …), **Severity**: BLOCKING (invalidates the goal/measurement)
  / MAJOR (materially degrades it) / MINOR (worth fixing, not urgent)
- **Evidence**: exact file path + the specific lines/fields/logic
- **Failure path**: the concrete sequence in which it goes wrong
- **Suggested fix**: one or two sentences

End with a one-paragraph overall verdict. A short list of genuinely critical
findings beats a long list of nitpicks. "Nothing critical found" is a
legitimate, welcome conclusion — do not manufacture findings.
