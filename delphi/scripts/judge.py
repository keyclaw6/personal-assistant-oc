#!/usr/bin/env python3
"""Judge (after each heartbeat): strong-model probability estimate for pending
signals from verified leakers; scripts compute edge and size and open PAPER
positions.

Review fixes baked in:
- Shares/entry/P&L use the slippage-adjusted FILL price on a side-specific
  quote (NO-side book via its own token when available); the paper account is
  self-financing: equity = bankroll + realized P&L − nothing imaginary.
- Deterministic eligibility is checked immediately before judgment and again
  before a position append. Transient lookup/quote failures remain retryable.
- Exposure-stacking guard: one open position per market.
"""
from __future__ import annotations

import argparse

import cognee
import polymarket as pm
from lib import (ROOT, agent_context, aggregate_market_signals, append_lessons,
                 append_tsv, domain_dir, format_aggregate, gen_id, leaker_row,
                 load_config, log_result, now_iso, position_size, read_tsv,
                 side_values, write_note, write_tsv)
from llm import call_json

MAX_PER_RUN = 10


def calibration_record(signals: list[dict]) -> str:
    agg: dict[str, list[float]] = {}
    for s in signals:
        if not s.get("judge_p") or s.get("resolved_outcome") not in ("YES", "NO"):
            continue
        try:
            p_yes = float(s["judge_p"])
        except ValueError:
            continue
        outcome = 1.0 if s["resolved_outcome"] == "YES" else 0.0
        agg.setdefault(s["call_class"], []).append((p_yes - outcome) ** 2)
    if not agg:
        return "no resolved judged signals yet"
    return "; ".join(f"{cls}: mean Brier {sum(v)/len(v):.3f} over {len(v)}"
                     for cls, v in sorted(agg.items()))


def executable_ask(market: dict, side: str) -> float | None:
    """Current executable ask for the side Delphi would buy."""
    token = market["yes_token"] if side == "YES" else market.get("no_token", "")
    ask = pm.best_ask(token) if token else None
    if ask is None and side == "NO":
        bid_yes = pm.best_bid(market["yes_token"])
        ask = 1.0 - bid_yes if bid_yes is not None else None
    return ask if ask is not None and 0.0 < ask < 1.0 else None


def eligibility(signal: dict, leakers: list[dict], positions: list[dict],
                thresholds: dict) -> tuple[dict | None, float | None, str | None, str]:
    """Return market/ask when eligible, otherwise terminal status (or None
    for a transient retry) and an explicit reason."""
    row = leaker_row(leakers, signal["leaker_id"], signal["call_class"])
    if not row or row.get("status") != "verified":
        return None, None, "pass", "leaker class is no longer verified"
    if any(p.get("status") == "open" and p.get("market_id") == signal["market_id"]
           for p in positions):
        return None, None, "pass", "already positioned on this market — stacking guard"
    market = pm.get_market(signal["market_id"])
    if market is None:
        return None, None, None, "market lookup failed — retrying next run"
    if market["closed"]:
        return None, None, "expired", "market closed before trade"
    if float(market.get("liquidity") or 0) < thresholds["min_liquidity_usd"]:
        return None, None, "pass", "market liquidity fell below minimum"
    ask = executable_ask(market, signal["side"])
    if ask is None:
        return None, None, None, "no fresh executable quote — retrying next run"
    return market, ask, None, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    ddir = domain_dir(args.domain)
    ctx = agent_context("judge")
    prompt_t = (ROOT / "prompts" / "judge.md").read_text(encoding="utf-8")
    signals = read_tsv(ddir / "signals.tsv")
    leakers = read_tsv(ddir / "leakers.tsv")
    positions = read_tsv(ddir / "positions.tsv")
    resolved = read_tsv(ddir / "resolved.tsv")

    pending = [s for s in signals if s["status"] == "pending_judge"][:MAX_PER_RUN]
    if not pending:
        return  # quiet — heartbeat already logged the sweep

    # F8: self-financing paper account.
    realized = sum(float(r.get("pnl_usd") or 0) for r in resolved)
    equity = cfg["bankroll_usd"] + realized
    open_cost = sum(float(p.get("size_usd") or 0) for p in positions
                    if p.get("status") == "open")
    available = max(0.0, equity - open_cost)
    calib = calibration_record(signals)
    slippage = th["slippage"]
    n_bet = n_pass = 0
    lessons_all: list[str] = []
    events: list[str] = []

    for s in pending:
        market, quote_side, terminal, reason = eligibility(s, leakers, positions, th)
        if market is None:
            s["note"] = reason
            if terminal:
                s["status"] = terminal
                n_pass += terminal == "pass"
            continue
        quote_yes_disp = quote_side if s["side"] == "YES" else 1.0 - quote_side

        lk = leaker_row(leakers, s["leaker_id"], s["call_class"]) or {}
        scorecard = (f"n_calls={lk.get('n_calls')}, hit_rate={lk.get('hit_rate')}, "
                     f"avg_price_at_call={lk.get('avg_price_at_call')}, "
                     f"edge_lcb={lk.get('edge_lcb')}, n_unpriced={lk.get('n_unpriced')}, "
                     f"n_live={lk.get('n_live')}")
        # VISION: deterministic weighted aggregate across ALL roster leakers
        # with live calls on this market — input to the judge, never a gate.
        agg_block = format_aggregate(
            aggregate_market_signals(signals, leakers, s["market_id"]))
        past = cognee.search(f"{s['call_class']} {market['question'][:80]}", 3)

        prompt = (ctx + "\n\n" + prompt_t
                  + f"\n\n## MARKET\nquestion: {market['question']}"
                  + f"\nresolution criteria: {market['description']}"
                  + f"\nend date: {market['end_date']}"
                  + f"\ncurrent YES price: {quote_yes_disp:.3f}"
                  + f" | liquidity: {market['liquidity']:.0f} USD"
                  + f"\n\n## LEAKER POST\nleaker: {s['leaker_id']} (hedged: {s['hedged']})"
                  + f"\nposted: {s['post_ts']} | detected: {s['ts_detected']}"
                  + f"\nclaim: {s['claim']}"
                  + f"\nimplied side: {s['side']}"
                  + f"\n\n## LEAKER SCORECARD ({s['call_class']})\n{scorecard}"
                  + f"\n\n## YOUR CALIBRATION RECORD\n{calib}"
                  + "\n\n## WEIGHTED CROSS-LEAKER AGGREGATE (this market)\n"
                  + agg_block
                  + "\n\n## RETRIEVED PAST CASES\n" + ("\n".join(past) or "none")
                  + "\n\n## REQUEST\nEstimate now. JSON only.")
        j = call_json("judge", prompt, cfg)
        if not j or "p_yes" not in j:
            s["note"] = (s.get("note", "") + " judge output unparseable — skipped").strip()
            continue
        # F4 (round 2): STRICT range validation — out-of-range values (e.g.
        # percentages like 87) are REJECTED, never clamped into a bet.
        try:
            p_yes = float(j["p_yes"])
            conf = float(j.get("confidence", -1))
        except (TypeError, ValueError):
            p_yes, conf = -1.0, -1.0
        if not (0.0 < p_yes < 1.0) or not (0.0 <= conf <= 1.0):
            s["status"] = "pass"
            s["note"] = f"judge output out of range (p_yes={j.get('p_yes')!r}, conf={j.get('confidence')!r}) — rejected"
            n_pass += 1
            continue
        p_yes = min(0.99, max(0.01, p_yes))
        lessons_all += j.get("lessons") or []

        # Re-read script-owned state and re-fetch both market and ask after the
        # slow judgment. No predicate from the pre-judgment check is trusted.
        current_leakers = read_tsv(ddir / "leakers.tsv")
        current_positions = read_tsv(ddir / "positions.tsv")
        market, ask, terminal, reason = eligibility(
            s, current_leakers, current_positions, th)
        if market is None:
            s["note"] = reason
            if terminal:
                s["status"] = terminal
                n_pass += terminal == "pass"
            continue

        p_side, _ = side_values(s["side"], p_yes, 0.5)
        fill = min(0.99, ask + slippage)  # executable ask + conservative buffer
        edge = p_side - fill
        s["judge_p"] = f"{p_yes:.3f}"
        s["judge_conf"] = f"{conf:.2f}"
        s["edge"] = f"{edge:.3f}"
        quote_side = ask  # recorded quote = the executable ask, not a midpoint
        rationale = str(j.get("rationale", ""))[:180]

        if edge >= th["min_edge"] and conf >= th["judge_min_conf"]:
            size = position_size(p_side, fill, available, th)  # Kelly on the FILL
            if size >= 1.0:
                pos = {
                    "position_id": gen_id("pos"), "signal_id": s["signal_id"],
                    "ts_open": now_iso(), "market_id": s["market_id"],
                    "market_question": s["market_question"], "token_id": s["token_id"],
                    "side": s["side"], "quote_price": f"{quote_side:.3f}",
                    "entry_price": f"{fill:.3f}",
                    "size_usd": f"{size:.2f}", "shares": f"{size / fill:.2f}",
                    "judge_p": f"{p_yes:.3f}", "status": "open", "note": rationale,
                }
                append_tsv(ddir / "positions.tsv", pos)
                positions.append(pos)
                available -= size
                s["status"] = "bet"
                s["note"] = rationale
                n_bet += 1
                events.append(f"BET {s['side']} {size:.2f} @ fill {fill:.3f} "
                              f"(quote {quote_side:.3f}) — {s['market_question'][:65]} "
                              f"(p={p_yes:.2f}, edge={edge:.2f})")
            else:
                s["status"] = "pass"
                s["note"] = "size below minimum after caps/equity"
                n_pass += 1
        else:
            s["status"] = "pass"
            s["note"] = rationale
            n_pass += 1
            events.append(f"PASS — {s['market_question'][:70]} (p={p_yes:.2f}, "
                          f"edge={edge:.2f}, conf={conf:.2f})")

    write_tsv(ddir / "signals.tsv", signals)
    append_lessons("judge", lessons_all)
    if events:
        note = "Decisions this run:\n- " + "\n- ".join(events)
        write_note("judge", "decisions", note)
        cognee.add(note, meta=f"judge {args.domain}")
    log_result("judge", args.domain,
               f"{len(pending)} pending → {n_bet} paper bets, {n_pass} passes; "
               f"equity {equity:.2f} (realized {realized:+.2f}), available {available:.2f}")


if __name__ == "__main__":
    main()
