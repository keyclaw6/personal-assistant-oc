# Delphi — Vision (the North Star)

*Founder-owned. Agents read this; only the founder changes it. When any
decision is unclear, resolve it toward this document.*

## The goal

**Make trading profit from leakers.** Certain public accounts consistently
post inside information — upcoming model releases, announcements, events —
before it is public and before prediction markets have priced it. Where the
leak and a tradable market can be connected, following a *proven* leaker
should beat the market price. Delphi is an automated LLM system built to
find those people, prove their edge on data, and trade it.

The ultimate goal is real profit. The current phase is paper trading: the
system must first PROVE, on an honest ledger, that following its verified
leakers would have made money. Going live is a founder decision taken only
after the paper book shows positive expectancy. Nothing in the system may
blur that line on its own.

## The method — three layers plus a maintainer

**1. Explore (find and prove leakers).**
Deep and wide discovery of candidate leakers across public platforms, run
regularly — aggressively kickstarted at the beginning to build the roster
fast. For every promising candidate: go back through their post history
(target: the last year), deliberately and carefully, extract every
falsifiable call they made, connect each call to the prediction market that
would have traded it, and answer one question with clean statistics —
**would following this account have generated profit at the price the market
offered at post time?** Leakers that pass become the roster; the bar is
statistical (lower-bound edge over price), not vibes.

**2. Follow (watch the proven roster).**
Rank the verified leakers by measured edge — best to worst. Cheap checker
agents sweep the roster continuously (every ~10 minutes) for new posts. A
new post is mechanically turned into: the claim, the matching market, the
price right now. Checkers gather; they never judge. Signals from multiple
leakers on the same market are surfaced together so the decision layer sees
the aggregate weight of evidence, weighted by each leaker's measured
reliability.

**3. Decide (the smartest model takes the trade).**
A frontier-strength judge (Fable-class / Sol-class — the best available)
makes the final call on every signal from a verified leaker: independent
probability, confidence, and whether the edge over the executable price
clears the gate. Deterministic scripts — never the model — compute edge,
size the position (fractional Kelly on a self-financing book), and keep the
ledger. Intelligence decides; arithmetic settles.

**The maintainer (self-healing).**
An orchestrator agent oversees the whole operation on an hourly heartbeat.
It never trades. It watches the logs and ledgers of all agents, diagnoses
against this vision, and makes at most ONE small, reversible, logged change
per run — then watches whether the change actually improved things, keeping
or reverting on evidence. Strict prompt, hard allowlists: it can tune the
harness, never the scoreboard, never itself, never this file.

## Division of intelligence (and cost)

| Layer | Model class | Why |
|---|---|---|
| Explorer | Clever mid-tier (Luna-class, high reasoning) | Discovery and careful back-testing matter |
| Checkers | Same or cheaper | Gathering is not a difficult task |
| Judge | Strongest available (Fable / Sol class) | The trade decision is where judgment pays |
| Orchestrator | Strong, xhigh reasoning | Small changes, high stakes |

## What success looks like

1. A roster of leakers each proven profitable-to-follow on ≥10 priced
   historical calls (Wilson lower-bound edge over price ≥ 5 points).
2. New leaker posts reach the judge within minutes, decisions within the
   same heartbeat.
3. A paper ledger with honest executable fills showing positive expectancy
   and calibrated judgments (Brier tracked per call class).
4. Then — and only then — the founder flips the live switch.

## Standing guardrails

- Paper only until the founder explicitly decides otherwise.
- The measurement is sacred: prices at post time, executable fills, one
  credit per prediction, misses counted as diligently as hits.
- Historical verification is provisional — every leaker keeps being
  re-tested prospectively and is demoted automatically when live results
  fall short.
- One domain proven end-to-end (ai-releases) before parallelizing to more.
- The operational law implementing this vision is `PROGRAM.md`; if the two
  ever disagree, the founder resolves it — agents don't.
