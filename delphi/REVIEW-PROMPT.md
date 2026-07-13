# External review prompt (paste everything below this line into the reviewer)

---

You are reviewing **Delphi**, a leaker-driven Polymarket **paper-trading**
research harness, located in the `delphi/` directory of
https://github.com/keyclaw6/personal-assistant-oc — on the **`delphi-trader`
branch, NOT `main`**.

## Branch discipline (read first)

- Review the `delphi-trader` branch ONLY. Start here:
  https://github.com/keyclaw6/personal-assistant-oc/tree/delphi-trader/delphi
- Every file you open must have `/delphi-trader/` in its URL. Raw-file
  pattern: `https://raw.githubusercontent.com/keyclaw6/personal-assistant-oc/delphi-trader/delphi/<path>`
- GitHub defaults to `main` — if a URL you are reading contains `/main/`, you
  are on the wrong code; switch to `delphi-trader` and re-read before drawing
  any conclusion.

## Hard scope boundary

Review ONLY files under `delphi/`. The rest of the repository is an unrelated
personal-assistant system and is explicitly OUT of scope: do not read, quote,
describe, or comment on `albert/`, `hermes/`, `plugins/`, `openclaw-config/`,
`scripts/`, `secrets/`, `docs/`, `evals/`, `state/`, `test/`, `archive/`, or
any root-level file. If a finding would require discussing those paths, drop
it. The single allowed exception: you may note whether `delphi/` truly avoids
touching anything outside itself, since isolation is one of its stated
invariants.

## What the system is supposed to do

1. **Explorer** (LLM, every 3h during kickstart): discover accounts that post
   inside information; back-test their historical posts against RESOLVED
   Polymarket markets; score each call against the market price AT POST TIME.
   A leaker×call_class is verified at n≥10 calls and hit_rate −
   avg_price_at_call ≥ 0.05.
2. **Heartbeat** (LLM, every 10 min): sweep verified+probation leakers for new
   posts; extract falsifiable claims; match to OPEN markets; log signal rows
   with price-at-detection. Probation rows are tracked, never bet.
3. **Judge** (strong LLM): for verified leakers' signals, output independent
   p_yes + confidence; scripts compute edge = p_side − price_side − slippage
   and open PAPER positions when edge ≥ 0.10 and confidence ≥ 0.60,
   fractional-Kelly sized.
4. **Resolve** (scripts, 6h): close positions on resolution (P&L, Brier); fold
   EVERY resolved signal into per-leaker per-call-class stats.
5. **Orchestrator** (strong LLM, hourly): observes everything; applies at most
   ONE allowlisted amendment per run (prompts, agent memory curation, domain
   briefs, guarded config keys), framed as an experiment with metric and
   review date; may not touch invariants, ledger history, roles, or bankroll.

Key files: `PROGRAM.md` (the law), `config.json`, `prompts/*.md`,
`agents/*/AGENT.md|MEMORY.md`, `scripts/*.py` (stdlib-only Python),
`domains/ai-releases/*.tsv` (state), `ledger/`.

## What to review for (in priority order)

1. **Goal fitness** — will this actually measure whether following qualified
   leakers beats the Polymarket price? Look for anything that silently
   invalidates the measurement (look-ahead bias, survivorship, price-at-wrong-
   time, double counting, leakage between qualification and betting).
2. **Statistical validity of leaker qualification** — the false-positive and
   false-negative paths: mapping a claim to the wrong market, crediting
   amplifiers over originators, the unpriced-history fallback (hit→0.85,
   miss→0.50), n≥10 gate, per-call-class splitting. Would you trust a
   "verified" leaker from this pipeline? What is the weakest link?
3. **Loop correctness over time** — trace each agent's behavior across weeks:
   state growth, stuck states, missing re-entry paths, race conditions between
   the cron jobs, prompt/JSON contract mismatches between prompts and the
   Python that parses them (check the schemas in prompts against the parsing
   code field by field).
4. **Authority and self-modification safety** — can the orchestrator (or any
   LLM output) escape its allowlist, corrupt recorded history, alter gate
   math, or amplify itself? Check `apply_amendment`, `config_patch`, and the
   regex allowlist against creative inputs.
5. **Paper-trading honesty** — entry prices, slippage haircut, exposure
   accounting, Brier accounting: is the simulated book fair, or does it
   flatter the system?

## What NOT to report

- Security hardening, prompt-injection theory, sandboxing, or secrets handling
  — unless a concrete path corrupts the measurement or the ledger.
- Code style, typing, packaging, test coverage, performance, scalability.
- Hypotheticals without a concrete failure path in THIS code.
- Anything about live trading — the system is paper-only by design.

## Report format (I will paste your report back to the builder verbatim)

For each finding:
- **ID** (F1, F2, …), **Severity**: BLOCKING (invalidates the goal/measurement)
  / MAJOR (materially degrades it) / MINOR (worth fixing, not urgent)
- **Evidence**: exact file path + the specific lines/fields/logic
- **Failure path**: the concrete sequence in which it goes wrong
- **Suggested fix**: one or two sentences

End with a one-paragraph overall verdict. A short list of genuinely critical
findings beats a long list of nitpicks. "Nothing critical found" is a
legitimate, welcome conclusion — do not manufacture findings.
