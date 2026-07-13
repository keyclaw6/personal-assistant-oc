#!/usr/bin/env python3
"""Resolve (every 6 h): close paper positions on resolved markets (P&L, Brier)
and fold EVERY resolved signal — bet or not — into per-leaker per-call-class
stats. This is the probation engine: tracked signals accrue evidence for free
(PROGRAM.md §1, §2).
"""
from __future__ import annotations

import argparse

import polymarket as pm
from lib import (append_tsv, domain_dir, ensure_leaker_row, load_config,
                 log_result, now_iso, read_tsv, side_values, write_tsv,
                 update_leaker_stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    ddir = domain_dir(args.domain)
    signals = read_tsv(ddir / "signals.tsv")
    leakers = read_tsv(ddir / "leakers.tsv")
    positions = read_tsv(ddir / "positions.tsv")

    market_cache: dict[str, dict | None] = {}

    def market(mid: str):
        if mid not in market_cache:
            market_cache[mid] = pm.get_market(mid)
        return market_cache[mid]

    # 1) close positions
    n_closed, pnl_total = 0, 0.0
    sig_by_id = {s["signal_id"]: s for s in signals}
    for p in positions:
        if p.get("status") != "open":
            continue
        m = market(p["market_id"])
        if not m or not m["closed"]:
            continue
        winner = pm.winning_side(m)
        if winner is None:
            p["note"] = (p.get("note", "") + " closed but ambiguous — held (§6)").strip()
            continue
        win = (p["side"] == winner)
        shares = float(p["shares"])
        size = float(p["size_usd"])
        exit_value = shares if win else 0.0
        pnl = exit_value - size
        p_yes = float(p.get("judge_p") or 0.5)
        p_side, _ = side_values(p["side"], p_yes, 0.5)
        brier = (p_side - (1.0 if win else 0.0)) ** 2
        sig = sig_by_id.get(p["signal_id"], {})
        append_tsv(ddir / "resolved.tsv", {
            "position_id": p["position_id"], "signal_id": p["signal_id"],
            "ts_resolved": now_iso(), "market_id": p["market_id"],
            "side": p["side"], "entry_price": p["entry_price"],
            "size_usd": f"{size:.2f}", "exit_value": f"{exit_value:.2f}",
            "pnl_usd": f"{pnl:.2f}", "brier": f"{brier:.4f}",
            "leaker_id": sig.get("leaker_id", ""), "call_class": sig.get("call_class", ""),
        })
        p["status"] = "closed"
        n_closed += 1
        pnl_total += pnl

    # 2) score all resolved signals into leaker stats
    n_scored = 0
    promotions = []
    for s in signals:
        if not s.get("market_id") or s.get("resolved_outcome"):
            continue
        if s["status"] not in ("bet", "pass", "tracked_probation", "pending_judge"):
            continue
        m = market(s["market_id"])
        if not m or not m["closed"]:
            continue
        winner = pm.winning_side(m)
        if winner is None:
            continue
        s["resolved_outcome"] = winner
        if s["status"] == "pending_judge":
            s["status"] = "expired"
        if s["side"] not in ("YES", "NO"):
            continue
        hit = (s["side"] == winner)
        try:
            price_yes = float(s["price_at_signal"])
            _, price_side = side_values(s["side"], 0.5, price_yes)
        except (TypeError, ValueError):
            price_side = None
        base = {"leaker_id": s["leaker_id"], "platform": s["platform"],
                "handle": s["leaker_id"].split("-", 1)[-1], "domain": args.domain,
                "call_class": s["call_class"], "status": "candidate",
                "n_calls": 0, "hits": 0, "notes": ""}
        row = ensure_leaker_row(leakers, base, s["call_class"])
        before = row.get("status")
        update_leaker_stats(row, hit, price_side, th)
        if before != "verified" and row["status"] == "verified":
            promotions.append(f"{s['leaker_id']}/{s['call_class']}")
        n_scored += 1

    write_tsv(ddir / "positions.tsv", positions)
    write_tsv(ddir / "signals.tsv", signals)
    write_tsv(ddir / "leakers.tsv", leakers)

    resolved_all = read_tsv(ddir / "resolved.tsv")
    lifetime_pnl = sum(float(r.get("pnl_usd") or 0) for r in resolved_all)
    log_result("resolve", args.domain,
               f"closed {n_closed} positions (pnl {pnl_total:+.2f}); scored {n_scored} signals; "
               f"promotions: {', '.join(promotions) or 'none'}; "
               f"lifetime paper pnl {lifetime_pnl:+.2f} on bankroll {cfg['bankroll_usd']}")


if __name__ == "__main__":
    main()
