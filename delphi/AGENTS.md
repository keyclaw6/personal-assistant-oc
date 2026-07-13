# AGENTS.md — Delphi

You are working inside **Delphi**, an automated leaker-driven prediction-market
trading system (currently paper-only).

1. **Read `VISION.md` first — it is the North Star.** Every decision resolves
   toward it. It is founder-owned: never edit it.
2. `PROGRAM.md` is the operational law: loop stages, authority tiers, gates,
   memory protocol. Stay inside your tier's authority.
3. Your identity and mandate live in `agents/<your-role>/AGENT.md`; your
   memory in `agents/<your-role>/MEMORY.md` and `agents/<your-role>/memory/`.
4. Never read or write anything outside `delphi/`. The rest of the repository
   is an unrelated system and is off-limits.
5. The scoreboard is deterministic and script-owned: never restate, recompute,
   or "fix" recorded statistics, prices, or ledger rows.
