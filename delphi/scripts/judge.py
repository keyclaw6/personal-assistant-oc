#!/usr/bin/env python3
"""Judge (after each heartbeat): strong-model probability estimate for
pending signals from verified leakers; scripts compute edge and size and open
PAPER positions (PROGRAM.md §2 bet gate). The judge never sizes bets.
"""
from __future__ import annotations

import argparse

import polymarket as pm
from lib import (append_tsv, compute_edge, domain_dir, gen_id, leaker_row,
                 load_config, log_result, now_iso, position_size, read_tsv,
                 side_values, write_tsv, ROOT)
from llm import call_json

MAX_PER_RUN = 10


def open_exposure(positions: list[dict]) -> float:
    return sum(float(p.get("size_usd") or 0) for p in positions
               if p.get("status") == "open")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    ddir = domain_dir(args.domain)
    prompt_t = (ROOT / "prompts" / "judge.md").read_text(encoding="utf-8")
    signals = read_tsv(ddir / "signals.tsv")
    leakers = read_tsv(ddir / "leakers.tsv")
    positions = read_tsv(ddir / "positions.tsv")

    pending = [s for s in signals if s["status"] == "pending_judge"][:MAX_PER_RUN]
    if not pending:
        log_result("judge", args.domain, "no pending signals")
        return

    bankroll = cfg["bankroll_usd"]
    available = max(0.0, bankroll - open_exposure(positions))
    n_bet = n_pass = 0

    for s in pending:
        market = pm.get_market(s["market_id"])
        if not market or market["closed"]:
            s["status"] = "expired"
            s["note"] = (s.get("note", "") + " market closed/unavailable at judge time").strip()
            continue
        price_yes = pm.midpoint(market["yes_token"])
        if price_yes is None:
            price_yes = market["yes_price"] or float(s["price_at_signal"])

        lk = leaker_row(leakers, s["leaker_id"], s["call_class"]) or {}
        scorecard = (f"n_calls={lk.get('n_calls')}, hit_rate={lk.get('hit_rate')}, "
                     f"avg_price_at_call={lk.get('avg_price_at_call')}, "
                     f"est_edge={lk.get('est_edge')}")
        corroboration = [
            f"[{x['ts_detected']}] {x['leaker_id']}: {x['claim'][:120]} (side {x['side']})"
            for x in signals
            if x["market_id"] == s["market_id"] and x["signal_id"] != s["signal_id"]
        ][-5:]

        prompt = (prompt_t
                  + f"\n\n## MARKET\nquestion: {market['question']}"
                  + f"\nresolution criteria: {market['description']}"
                  + f"\nend date: {market['end_date']}"
                  + f"\ncurrent YES price: {price_yes:.3f} | liquidity: {market['liquidity']:.0f} USD"
                  + f"\n\n## LEAKER POST\nleaker: {s['leaker_id']} (hedged: {s['hedged']})"
                  + f"\nposted: {s['post_ts']} | detected: {s['ts_detected']}"
                  + f"\nclaim: {s['claim']}"
                  + f"\nimplied side: {s['side']}"
                  + f"\n\n## LEAKER SCORECARD ({s['call_class']})\n{scorecard}"
                  + "\n\n## OTHER TRACKED SIGNALS ON THIS MARKET\n"
                  + ("\n".join(corroboration) or "none")
                  + "\n\n## REQUEST\nEstimate now. JSON only.")
        j = call_json("judge", prompt, cfg)
        if not j or "p_yes" not in j:
            s["note"] = (s.get("note", "") + " judge output unparseable — skipped").strip()
            continue
        try:
            p_yes = min(0.99, max(0.01, float(j["p_yes"])))
            conf = min(1.0, max(0.0, float(j.get("confidence", 0.0))))
        except (TypeError, ValueError):
            s["note"] = (s.get("note", "") + " judge output invalid — skipped").strip()
            continue

        edge = compute_edge(s["side"], p_yes, price_yes, th["slippage"])
        s["judge_p"] = f"{p_yes:.3f}"
        s["judge_conf"] = f"{conf:.2f}"
        s["edge"] = f"{edge:.3f}"
        rationale = str(j.get("rationale", ""))[:180]

        if edge >= th["min_edge"] and conf >= th["judge_min_conf"]:
            p_side, price_side = side_values(s["side"], p_yes, price_yes)
            size = position_size(p_side, price_side, min(bankroll, available), th)
            if size >= 1.0 and price_side > 0:
                pos = {
                    "position_id": gen_id("pos"), "signal_id": s["signal_id"],
                    "ts_open": now_iso(), "market_id": s["market_id"],
                    "market_question": s["market_question"], "token_id": s["token_id"],
                    "side": s["side"], "entry_price": f"{price_side:.3f}",
                    "size_usd": f"{size:.2f}", "shares": f"{size / price_side:.2f}",
                    "judge_p": f"{p_yes:.3f}", "status": "open", "note": rationale,
                }
                append_tsv(ddir / "positions.tsv", pos)
                available -= size
                s["status"] = "bet"
                s["note"] = rationale
                n_bet += 1
            else:
                s["status"] = "pass"
                s["note"] = "size below minimum after caps"
                n_pass += 1
        else:
            s["status"] = "pass"
            s["note"] = rationale
            n_pass += 1

    write_tsv(ddir / "signals.tsv", signals)
    log_result("judge", args.domain,
               f"{len(pending)} pending → {n_bet} paper bets, {n_pass} passes; "
               f"available bankroll {available:.2f}/{bankroll}")


if __name__ == "__main__":
    main()
