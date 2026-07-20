# Comprehensive Delphi reviewer-agent prompt

Paste everything below the horizontal rule into a capable reviewer agent. Give
the reviewer read-only access to the checkout and, if available, permission to
run safe tests and read-only provider probes.

---

You are the independent launch-readiness reviewer for **Delphi**, a
leaker-driven Polymarket **paper-trading** research harness.

Review this exact target, and record the commit SHA you actually reviewed:

- Local checkout: `/home/kab/personal-assistant-oc/delphi`
- Remote branch:
  `https://github.com/keyclaw6/personal-assistant-oc/tree/codex/delphi-review-blockers/delphi`
- Raw-file pattern:
  `https://raw.githubusercontent.com/keyclaw6/personal-assistant-oc/codex/delphi-review-blockers/delphi/<path>`

Confirm the checkout is clean and its `HEAD` matches the pushed remote branch
SHA before reviewing. Record `git status --short --branch` and both SHAs. Do not
combine code from an uncommitted local tree with raw links from a different
remote commit; if they differ, stop and identify the mismatch as a review-input
problem rather than reviewing an indeterminate version.

Perform a **fresh audit of the complete current Delphi system**, not merely a
diff review and not merely a test review. Your central question is:

> Does the code, as actually configured and operated, perform every function
> required to advance `VISION.md` honestly enough to start the paper-validation
> phase and eventually determine whether following proven leakers can make
> trading profit?

## 1. Authority, scope, and non-mutation rules

1. Read `VISION.md` first. It is the founder-owned North Star and has priority
   whenever intent is unclear. Never edit it.
2. Then read `PROGRAM.md` in full. Treat §0–§7 as the founder-owned operational
   law. Never edit it.
3. Read `AGENTS.md` and each `agents/<role>/AGENT.md` before assessing role
   authority.
4. Review only `delphi/`. Everything else in the repository is an unrelated
   system and is out of scope. The sole permitted cross-boundary check is
   whether Delphi obeys the three narrow isolation exceptions documented in
   PROGRAM §0.4.
5. This is a read-only review. Do not edit code, prompts, config, workspaces,
   TSV state, ledgers, memories, cron, or founder documents. Never invoke a
   live-trading path, submit an order, expose credentials, or mutate a remote
   service.
6. You may run deterministic tests, compile/import checks, and safe read-only
   probes. Run stateful or fault-injection tests only in a temporary copy with
   fake fixtures and fake provider responses. Do not treat the live checkout's
   append-only state as test data.
7. Apply YAGNI to recommendations: identify the smallest change that fixes a
   demonstrated failure. Do not propose speculative infrastructure or a
   rewrite when a local correction suffices.

## 2. Required discovery method

Before judging behavior:

1. Act as the lead reviewer and protect your context window. Delegate bounded,
   independent audits to sub-agents where available—for example: VISION/PROGRAM
   traceability; Explorer/Heartbeat ingestion; Judge/Resolve accounting; and
   Orchestrator/provider/operations. Give each sub-agent the same read-only and
   `delphi/`-only boundaries. Require evidence, then personally reconcile their
   results against the code. You own the final verdict; do not paste together
   unchecked sub-agent claims.
2. Freshly index the current `delphi/` tree with code-based memory, if that
   capability is available. Use it for structural discovery, call paths, state
   writers/readers, and impact analysis. Use direct reads and literal search
   for Markdown, prompts, config, cron, TSV schemas, and exact strings.
3. Inventory every executable entry point, provider boundary, prompt/parser
   contract, mutable table, atomic-write boundary, cursor/watermark, lock,
   experiment record, and agent-owned workspace.
4. Trace all five loops individually—Explorer, Heartbeat, Judge, Resolve, and
   Orchestrator—plus their shared state and scheduled interactions. Heartbeat
   invokes Judge in the cron composition; Resolve and Orchestrator are
   independently scheduled, not downstream calls in one sequential chain.
5. Trace data lineage from a source post through claim extraction, market
   mapping, price capture, qualification, prospective signal, judgment,
   position, settlement, scorecard rebuild, and orchestration evidence.
6. Inspect at minimum: scripts, prompts, agent mandates, config, domain briefs,
   TSV schemas and current rows, ledger formats, tests, `crontab.example`, and
   external-provider adapters. Tests, comments, prompts, and documentation are
   claims to verify against reachable code; they are not proof by themselves.
7. Build a clause-by-clause traceability matrix for VISION and PROGRAM §0–§7.
   Mark every obligation `PASS`, `FAIL`, or `UNVERIFIED`. `PASS` requires direct
   code evidence plus an appropriate execution/test/probe; absence of a finding
   is not automatically a pass.

## 3. Vision-fitness questions

Determine whether the system, end to end:

- searches deeply and widely enough to discover actual information
  originators rather than commentators or accounts repeating public news;
- reviews the intended prior year deliberately across all history observable
  through the configured providers, including misses; exposes rather than
  conceals coverage gaps; and validly measures whether following a leaker beat
  the price available when the leaker posted. Judge the accepted deleted-post
  and bounded-X survivorship limit under PROGRAM §7 by whether its prospective
  demotion mitigation works, not by demanding inaccessible history;
- promotes and ranks only leaker × frozen-call-class records that satisfy the
  deterministic verification gate;
- keeps watching the verified roster, turns new posts into timely prospective
  signals, and preserves probation evidence without allowing probation bets;
- aggregates different leakers' views once each with the required proven-edge
  weighting while keeping that aggregate informative rather than a gate;
- delegates discretionary probability/confidence judgment to the strongest
  configured judge model while keeping edge, sizing, gates, and accounting in
  deterministic scripts;
- allows the orchestrator to make one small, measured, reversible improvement
  without corrupting history, changing governance, or escaping its authority;
- produces honest paper evidence capable of establishing or rejecting positive
  expectancy, rather than merely demonstrating that scripts can execute.

Separate these three verdicts throughout the report:

1. **Code correctness** — the implemented logic matches VISION/PROGRAM.
2. **Operational paper-launch readiness** — the configured jobs can run safely
   and repeatedly on the target machine today.
3. **Positive-expectancy evidence** — accumulated prospective results actually
   support a profit claim. Do not infer this from code correctness.

## 4. Functional audit by loop

### Explorer — discover and prove

Prove or falsify each of these behaviors:

- Seeds are qualified first; candidate discovery and deepening occur as PROGRAM
  §2 specifies, including kickstart behavior.
- Each source adapter paginates through all observable coverage needed for the
  intended one-year review, respects provider bounds, deduplicates stable post
  identities, handles equal timestamps, exposes known coverage gaps, and does
  not silently turn a truncated or incomplete provider response into complete
  history. Apply PROGRAM §7's accepted survivorship limit and verify its stated
  prospective mitigation separately.
- Long histories are chunked without dropping posts or claims. All required
  chunks complete before globally sorting/scoring the oldest calls first.
  Failed chunks/posts remain retryable and cannot advance durable progress.
- Historical extraction captures **all concrete wins and misses** without an
  LLM deciding which claims are scoreable based on known outcomes.
- Every claim remains attached to the correct canonical source post throughout
  extraction: stable post ID, timestamp, URL/source, author/leaker, text, and
  call class where those inputs exist. Trace indices and pairings through
  chunking, parsing, sorting, mapping, and persistence. Require persistence of
  the exact PROGRAM/TSV contract fields—not speculative extra columns—and
  require a stable post ID wherever cursor identity depends on it.
- Source post IDs and timestamps are validated enough that empty/malformed IDs,
  invalid or future timestamps, and non-monotonic provider data cannot advance
  a cursor, poison price-at-post selection, or falsely improve detection
  latency.
- A claim maps to at most one genuinely resolving Polymarket market. Check the
  market question, resolution criteria, relevant event, side, and resolved
  outcome—not keyword similarity alone. Mapping precision must dominate recall.
- Historical price observations are at or before the post timestamp and no more
  than 48 hours stale. Post-event prices are never used. Unpriced claims remain
  visible for audit but never affect gate arithmetic.
- Call classes normalize only to the frozen domain taxonomy.
- At most one row receives score credit for the required deduplication key; the
  chosen row is deterministic and `stat_counted=true`. Explicitly reconcile any
  disagreement among PROGRAM, prompts, code, and tests about whether the key is
  `(leaker, market)` or `(leaker, event)`.
- Wilson lower-bound edge, counts, averages, promotion, and demotion are
  deterministic script behavior and match PROGRAM §3 exactly. Audit roster
  ranking separately against VISION's best-to-worst requirement because §3
  does not define a ranking algorithm.

### Heartbeat — follow the roster

Prove or falsify each of these behaviors:

- Every verified and probation roster entry is swept; probation calls are
  tracked but can never be bet.
- Each provider drains a complete, deterministic **oldest unprocessed prefix**
  across repeated capped sweeps, even for large backlogs, multiple pages,
  equal timestamps, overlapping date windows, and unstable API ordering.
- Watermarks/cursors include the stable post ID where timestamps alone are
  ambiguous. Backend-specific pagination semantics cannot skip or loop posts.
- A post's complete set of extracted claim rows and its completion marker are
  committed atomically. The marker/cursor never advances when extraction,
  matching, pricing, parsing, or persistence fails transiently.
- Extraction does not impose an undocumented claims-per-post cap.
- Claims map only to genuinely matching open markets. Price-at-detection is
  recorded with correct side orientation and sufficient provenance.
- Repeated sweeps are idempotent: they neither duplicate signals nor suppress a
  distinct claim merely because it shares a URL or resembles historical data.

### Judge — decide and size

Prove or falsify each of these behaviors:

- Only currently eligible verified signals can become bets, and Delphi never
  stacks exposure on a market it already holds.
- The weighted cross-leaker aggregate includes each relevant roster leaker at
  most once, uses the correct proven lower-bound edge, applies the documented
  probation/hedged weighting only as input, and is never used as a hard gate.
- The judge receives the required scorecard, calibration record, retrieved past
  cases, market evidence, and aggregate without prompt/parser field drift.
- The configured model is genuinely the strongest decision model intended by
  VISION, and the execution path does not silently fall back to a materially
  weaker model while recording success.
- Output parsing strictly rejects missing, malformed, or out-of-range `p_yes`
  and confidence; it never clamps them into validity.
- Because the LLM call is slow, market openness, resolution, existing exposure,
  liquidity, signal eligibility, and all other mutable predicates are checked
  both before and after judgment.
- The post-judgment quote is a fresh, executable, **side-specific best ask** for
  the token being bought. Verify order-book orientation for YES and NO. No
  midpoint, stale detection price, or bid-as-ask can become the fill.
- Slippage, side probability, minimum edge, confidence, fractional Kelly,
  bankroll cap, equity, available capital, shares, and position rows match
  PROGRAM §3 exactly and remain deterministic.
- No fresh valid quote leaves the signal retryable/pending rather than falsely
  passed, failed, or filled.

### Resolve — settle and rebuild truth

Prove or falsify each of these behaviors:

- Settlement is idempotent and exactly once across partial writes, crashes,
  reruns, repeated provider outcomes, and ambiguous/unresolved markets.
- Position settlement uses the recorded shares and entry price to calculate
  0/1 P&L and Brier correctly without rewriting immutable history.
- Every resolved signal status required by PROGRAM—including historical,
  tracked, passed, bet, and expired—can reach the deterministic fold.
- Earliest eligible credit wins for the required leaker/market-or-event key;
  duplicates and overlapping contracts cannot inflate scorecards.
- Leaker scorecards rebuild deterministically from the append-only signal
  ledger. Rebuilding twice produces identical state and heals a crash between
  signal settlement and scorecard materialization without double counting.
- Historical and prospective/live counts remain distinct; prospective `n_live`
  results affect current status and can demote a formerly verified leaker.
- Qualification summaries sent to retrieval memory cannot become the source of
  truth or overwrite the file-derived scorecard.

### Orchestrator — improve without taking control

Prove or falsify each of these behaviors:

- The orchestrator sees the evidence PROGRAM §6 requires: goal, run-log tail,
  agent memories/latest notes, roster/signals/positions summaries, active
  experiments, learnings, and isolated retrieval context.
- At most one amendment can be applied per run. File-target regexes and exact
  config-key/type/range allowlists withstand path traversal, prefix/suffix,
  newline, collision, symlink, and creative structured-output inputs.
- It cannot edit VISION/PROGRAM, §0 invariants, gate/sizing math, model/role
  configuration, ledger history, another system, its governance prompt, or any
  other forbidden target.
- A byte-exact before-image is durably stored **before** mutation, with unique
  experiment identity and enough metadata for deterministic review.
- Only live experiments can be reviewed. Success metrics and `review_after`
  are respected; one experiment cannot be confused with another.
- A revert performs a real allowlist-validated restoration and verifies the
  file/config read-back before recording `revert`. A failed restoration stays
  retryable and is never presented as completed bookkeeping.
- Mechanical failures are skipped/fixed/logged as mechanical events, not
  interpreted as evidence that an amendment improved the trading system.

## 5. Mandatory regression audit of the repaired blockers

Do not assume a prior fix is correct. Create focused reproductions for all
eight regression families and report `PASS`, `FAIL`, or `UNVERIFIED` for each:

1. **Startup/import path:** every documented script starts from the cron/root
   working directory without a missing `extract_json`/module-path failure.
2. **Explorer provenance/mapping:** chunk-local indices cannot be mistaken for
   global post indices or cause a claim to inherit another post's timestamp,
   URL, text, or mapping.
3. **Explorer completeness/retry:** no four-claim truncation; all chunks finish
   before global oldest-first scoring; a failed chunk remains retryable and
   cannot commit later history past the gap.
4. **Heartbeat atomicity:** all claim rows and the post-completion marker commit
   together; injected failure cannot leave a marker that suppresses missing
   claims on retry.
5. **Provider pagination:** Reddit, X, and Exa drain complete oldest prefixes
   across caps/pages/bounds, equal timestamps, stable IDs, overlaps, and
   provider errors; incomplete fetches fail closed.
6. **Judge time-of-check/time-of-use:** eligibility, openness, exposure,
   liquidity, and the executable quote are rechecked after the LLM returns.
7. **Resolve deterministic replay:** scorecards reconstruct idempotently from
   the immutable signal ledger after a simulated crash at each persistence
   boundary.
8. **Orchestrator recovery:** before-images exist before mutation, restoration
   is read-back verified, and failed reverts are not marked complete.

Do not count a unit test as proof unless you inspect that its fixture accurately
models the real state transition and provider contract and also verify the
production path it purports to exercise.

## 6. Cross-cutting failure, integrity, and contract review

### Crash and retry safety

In a temporary copy with fixtures, fault-inject each external-call boundary and
each persistence boundary. Demonstrate whether reruns lose or duplicate posts,
claims, completion markers, signals, positions, settlements, score credits,
experiment snapshots, amendments, or verdicts. Verify atomic replace/append
behavior and the one-shared-lock assumption under the actual cron command
composition, including heartbeat-plus-judge behavior and lock timeouts/skips.

### Prompt/parser contracts

For every LLM call, compare the prompt's JSON schema field by field with parser
requirements, validation, normalization, defaults, and downstream consumers.
Malformed, fenced, partial, extra, duplicated, adversarial, and out-of-range
outputs must produce an honest retry/skip/rejection, never invented success.

### External contracts

Verify current behavior against authoritative documentation and, where safe,
read-only probes for Reddit, X, Exa, Polymarket Gamma/CLOB, Cognee, and Codex
CLI. Check pagination, maximum result limits, inclusive/exclusive time bounds,
timestamp precision, stable IDs, rate-limit/error shapes, market resolution
fields, token/side mapping, order-book orientation, saved OAuth availability,
requested model, schema-constrained subprocess output, and cleanup behavior. A
mock counts only if it reproduces the relevant real contract. If credentials or
network access are unavailable, mark the
claim `UNVERIFIED`; do not silently infer `PASS`.

### Accounting and measurement honesty

Audit for look-ahead, survivorship beyond accepted §7 limits, selective claim
extraction, false market matches, repeated-credit inflation, stale or favorable
fills, side inversion, dropped failures, exposure stacking, P&L/equity errors,
calibration/Brier errors, and any state transition that makes the paper book or
qualification record look better than reality.

## 7. Operational paper-launch readiness

Verify the real deployment path rather than only isolated functions:

- the checkout/cwd assumed by imports and subprocesses;
- `crontab.example` paths, cadence, shell/PATH, `flock`, timeouts, log location,
  tmp-directory creation, and post-kickstart operator step;
- the actual installed scheduler and entries on the target machine, their
  restart/reboot persistence, recent invocation evidence, and recent logs—not
  merely whether `crontab.example` looks plausible;
- `dotenvx run -f .env.delphi` wiring and presence of required non-LLM provider
  key names without printing or decrypting secret values into the report;
- configured models and installed/logged-in Codex CLI from the cron-like
  `PATH`/`CODEX_HOME` environment, without reading or copying Codex auth files,
  plus honest behavior when any dependency is unavailable;
- Polymarket reachability, market/price data semantics, and rate-limit handling;
- Cognee's `delphi-trading` dataset isolation and file-source-of-truth fallback;
- writable paths, atomic rename assumptions, shared-lock availability, logs,
  and enough observable evidence to diagnose a stuck loop;
- a safe end-to-end fixture or temporary-copy run from source post through
  settlement and scorecard rebuild, plus an orchestrator apply/review/revert
  cycle using only disposable files.
- separately, a disposable-copy integration smoke using the real configured
  adapters and safe read-only provider calls plus the actual configured LLM
  backends. Never place a live order. If credentials, cost authorization,
  network, or permissions prevent this, mark operational integration
  `UNVERIFIED` rather than substituting an all-fake test.

Explicitly verify, rather than overlooking, these current-checkout facts:

- `crontab.example` targets `/home/kab/...` and exports the explicit `PATH` and
  `CODEX_HOME` needed to reuse the Codex CLI's ChatGPT login. Verify those
  assumptions from a clean cron-like environment without inspecting auth data.
- Re-check whether the target machine has a scheduler and `delphi/tmp/`; do not
  infer installation or recent execution from the example file alone.
- `candidates.tsv`, `positions.tsv`, `resolved.tsv`, `signals.tsv`, and
  `ledger/results.tsv` currently contain only headers; `leakers.tsv` has roster
  rows but this is not prospective trading evidence.

State precisely whether each fact is an installation precondition, a launch
blocker, or merely a lack of expectancy evidence. Never claim positive
expectancy without sufficient prospective resolved observations.

## 8. False-positive controls for findings

- Every finding must have a concrete reachable failure path in this code.
- Do not report style, typing, packaging, generic test coverage, optional
  scalability, theoretical prompt injection, or generic security hardening
  unless it concretely corrupts measurement, authority, or the ledger.
- Do not re-report PROGRAM §7 accepted prototype limits unless the documented
  mitigation is absent or broken. If broken, report the broken mitigation, not
  the accepted limit itself.
- Do not call a deliberate paper-only restriction a missing live-trading
  feature. Any wallet, key, live order, or live-trading path is instead a
  violation of PROGRAM §0.1.
- Use `BLOCKING` only when a required loop cannot run, qualification/profit
  measurement is invalid, immutable state can be materially corrupted, or the
  paper launch cannot safely start. Use `MAJOR` for reachable material loss,
  bias, stuck progress, or dishonest accounting. Use `MINOR` only for a real
  bounded defect worth correcting.
- Do not use vague “might” or “could” language without the inputs and state
  sequence that make the failure reachable.
- `UNVERIFIED` is not `PASS`. “No defect found” is legitimate. Never invent a
  finding to make the report look comprehensive.

## 9. Required evidence for every finding

For each finding provide:

- **ID and severity:** `F1`, `F2`, … and `BLOCKING`, `MAJOR`, or `MINOR`.
- **Violated requirement:** exact VISION statement and/or PROGRAM section.
- **Evidence:** exact `delphi/...` file path and line(s), plus relevant state or
  provider contract. Quote only the minimum code needed.
- **Reachable failure path:** starting inputs/state, ordered execution steps,
  and the exact incorrect state/output.
- **Consequence:** effect on profit measurement, qualification, prospective
  trading, accounting, recoverability, authority, or operability.
- **Reproduction:** smallest deterministic test, command, or safe read-only
  probe that demonstrates it, with observed output. Distinguish observed facts
  from inference.
- **Smallest YAGNI fix:** one or two concrete sentences; no speculative system.
- **Confidence:** `high`, `medium`, or `low`, and what remains unverified.

Do not include a finding that lacks this evidence. Put unresolved hypotheses in
the unverified-assumptions section instead.

## 10. Required final report

Return the report in this order:

1. **Executive verdict** — one concise paragraph answering the central question.
2. **Three independent verdicts** — code correctness; operational paper-launch
   readiness; positive-expectancy evidence. Use `READY`, `NOT READY`, or
   `UNVERIFIED` and explain each briefly.
3. **VISION/PROGRAM traceability matrix** — clause/obligation, implementation
   location, evidence run, and `PASS`/`FAIL`/`UNVERIFIED`.
4. **Findings by severity** — all evidence fields from §9, blockers first.
5. **Five-loop functional matrix** — Explorer, Heartbeat, Judge, Resolve,
   Orchestrator with inputs, outputs, persistence, recovery, and verdict.
6. **Eight-fix regression matrix** — one row per regression family in §5 with
   reproduction and verdict.
7. **Operational launch blockers and preconditions** — exact commands/config or
   environment facts, without secret values.
8. **Tests and probes executed** — command, purpose, observed result, and what it
   does not prove.
9. **Remaining unverified assumptions** — the evidence needed to resolve each.
10. **YAGNI repair order** — only genuine defects, smallest blockers first.

Finish with one explicit sentence:

> **Final launch judgment:** Delphi is/is not ready to begin honest unattended
> paper validation on the target machine, because ...

Be rigorous, skeptical, and concise. The purpose is not to generate a long bug
list; it is to determine, with evidence, whether Delphi actually fulfills its
documented functions in service of the vision.
