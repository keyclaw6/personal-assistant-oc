# External review prompt v2 (paste everything below this line into the reviewer)

---

You are RE-REVIEWING **Delphi**, a leaker-driven Polymarket **paper-trading**
research harness, located in the `delphi/` directory of
https://github.com/keyclaw6/personal-assistant-oc on the default **`main`**
branch.

Start here: https://github.com/keyclaw6/personal-assistant-oc/tree/main/delphi
Raw-file pattern:
`https://raw.githubusercontent.com/keyclaw6/personal-assistant-oc/main/delphi/<path>`

This is the second review round. Your previous report produced findings F1–F8,
and the builder claims all eight are fixed. Your job now: (A) verify each fix
actually holds in the current code, and (B) hunt for NEW problems — especially
ones the fixes themselves may have introduced.

## Part A — verify the eight claimed fixes

- **F1** (was: look-ahead / stale prices; outcome-dependent unpriced fallback):
  `polymarket.price_at` must now return only observations at-or-before post
  time within a freshness bound, and `lib.update_leaker_stats` must exclude
  unpriced calls from all verification arithmetic (audit-only `n_unpriced`).
- **F2** (was: double-counting): one market per claim in explorer Task C
  handling; one credit per (leaker, market) pair ever, enforced across both
  historical scoring and live folding via `stat_counted`.
- **F3** (was: point-estimate gate, unused history window): Wilson lower-bound
  gate (`edge_lcb`), frozen call-class taxonomy (`normalize_class`), paginated
  date-bounded history fetch in `sources.py`, deepen mode using older windows.
- **F4** (was: cron races, non-idempotent resolve): single shared lock in
  `crontab.example`, atomic `write_tsv`, resolve skips positions already in
  `resolved.tsv`.
- **F5** (was: stuck class lifecycle, class-string mismatch): deepen targets
  any partially-scored non-verified leaker; heartbeat injects the leaker's
  existing classes + fixed taxonomy and normalizes before the verified gate.
- **F6** (was: cursor skips, permanent transient failures, unfolded expired):
  cursor advances only on clean batches; `search_markets` distinguishes None
  (transient) from [] (genuine no-match); resolve folds `expired` and stale
  `pending_judge` signals.
- **F7** (was: denylist config patch, self-edit, fake reverts): exact
  allowlist with type/range validation in `lib.CONFIG_PATCH_ALLOWED`;
  editable-files regex excludes orchestrator's own AGENT.md/prompt; every
  amendment stores a before-image and `revert` restores it.
- **F8** (was: unslipped fills, non-self-financing bankroll): shares/entry/P&L
  from the slippage-adjusted fill on a side-specific quote (NO token book when
  available); equity = bankroll + realized P&L − open cost drives sizing.

For each: CONFIRMED, PARTIAL (what remains), or NOT FIXED (evidence).

## Part B — fresh review

Same priorities as before: (1) goal fitness — does the measurement remain
valid end-to-end; (2) statistical validity of qualification; (3) loop
correctness over weeks (state growth, stuck states, prompt↔parser contract
mismatches, checked field by field); (4) authority/self-modification safety;
(5) paper-book honesty. Pay special attention to seams the fixes created:
new columns vs old rows, None-propagation from the stricter price/search
functions, cursor logic under repeated transient failures, allowlist regex
vs the orchestrator prompt's claims.

## Hard scope boundary

Review ONLY files under `delphi/`. Everything else in the repository
(`albert/`, `hermes/`, `plugins/`, `openclaw-config/`, `scripts/`, `secrets/`,
`docs/`, `evals/`, `state/`, `test/`, `archive/`, root files) is an unrelated
personal-assistant system and is OUT of scope — do not read, quote, describe,
or comment on it. Single allowed exception: noting whether `delphi/` truly
avoids touching anything outside itself.

## What NOT to report

- Security hardening, prompt-injection theory, sandboxing, secrets handling —
  unless a concrete path corrupts the measurement or the ledger.
- Code style, typing, packaging, test coverage, performance, scalability.
- Hypotheticals without a concrete failure path in THIS code.
- Anything about live trading — the system is paper-only by design.

## Report format (pasted back to the builder verbatim)

Part A: one line per F1–F8 (CONFIRMED / PARTIAL / NOT FIXED + evidence if not
confirmed). Part B: findings as before — ID (G1, G2, …), Severity
(BLOCKING / MAJOR / MINOR), Evidence (file + lines/logic), Failure path,
Suggested fix. End with a one-paragraph verdict. "All fixes confirmed, nothing
new found" is a legitimate, welcome conclusion — do not manufacture findings.
