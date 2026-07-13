# Delphi — Vision (the North Star)

*Founder-owned. Agents read this; only the founder changes it. When any
decision is unclear, resolve it toward this document. How this vision is
implemented at any given time lives in `PROGRAM.md` — this file states only
what we are trying to do.*

## The goal

**Make trading profit from leakers.** There are people who leak information
about upcoming releases and events — things that can be traded on prediction
markets. Where the leak and the trade can be connected, and the leaker's
track record can be observed, following a proven leaker should make money.
Delphi is an automated large-language-model system built to do exactly this,
across the public domains where such leakers exist.

## How it works

**Exploration — find the leakers and prove them.**
Do a deep and wide search for leakers, regularly — and kickstarted hard at
the beginning to find the relevant ones fast. When there are proposals, go
back through time — deliberately, carefully, making sure it is done
correctly — and compare their posts over the last year against what actually
happened on the prediction markets: would following their calls have
generated profit? That question decides who is actually good to use.

**Following — watch the proven roster.**
Keep a host of leakers who have shown themselves credible over time. Rank
them — best to worst. Agents continually look for new posts from them. Every
new post is analyzed and connected to the matching Polymarket market, and
the different leakers' views are aggregated with their weighted scores.

**Decision — the smartest model takes the trade.**
A smarter agent — Fable 5 / GPT-5.6 Sol Ultra class, the best available —
looks at the aggregated evidence and makes the final decision on whether to
take the trade.

**Self-improvement — the maintainer.**
An orchestrator/maintainer agent oversees the whole operation and keeps it
self-healing. It does no trades. It has a very strict prompt so it cannot
ruin anything: it simply makes a small change, then watches the logs of the
working agents to make sure the change actually was an improvement.

## Division of intelligence

The explorer agents can be quite clever — they are doing important work.
The checker agents that continually watch for new posts do not have to be —
gathering information is not a difficult task. The actual trade decision
gets the smartest model we have.

## The ultimate goal

To actually make profit from this.
