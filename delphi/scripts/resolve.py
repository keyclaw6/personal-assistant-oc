#!/usr/bin/env python3
"""Resolve (every 6 h): close paper positions on resolved markets (P&L, Brier)
and fold resolved signals into per-leaker per-call-class stats.

Review fixes baked in:
- F4: idempotent — a position already present in resolved.tsv is never paid
  again, even after a crash between append and status persistence.
- F6: `expired` (and stale pending_judge on closed markets) signals ARE folded
  — fast-resolving calls are not selectively omitted.
- F2: at most ONE fold per (leaker, market) pair, earliest post wins; the
  chosen row is marked stat_counted=true, duplicates false.
- F8: P&L uses recorded shares bought at the slippage-adjusted fill.
"""
from __future__ import annotations

import argparse

import cognee
import polymarket as pm
from lib import (append_tsv, domain_dir, ensure_leaker_row, load_config,
                 log_result, now_iso, read_tsv, side_values, update_leaker_stats,
                 write_tsv)


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
    already_resolved = {r["position_id"] for r in read_tsv(ddir / "resolved.tsv")}

    market_cache: dict[str, dict | None] = {}

    def market(mid: str):
        if mid not in market_cache:
            market_cache[mid] = pm.get_market(mid)
        return market_cache[mid]

    # 1) close positions (idempotent, F4)
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
            p["note"] = (p.get("note", "") + " closed but ambiguous — held (§7)").strip()
            continue
        if p["position_id"] in already_resolved:  # crash recovery: paid already
            p["status"] = "closed"
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
        already_resolved.add(p["position_id"])
        p["status"] = "closed"
        n_closed += 1
        pnl_total += pnl
        cognee.add(f"Resolved paper bet: {p['side']} on '{p['market_question'][:100]}' "
                   f"entry {p['entry_price']}, judged p={p.get('judge_p')}, outcome {winner}, "
                   f"pnl {pnl:+.2f}, leaker {sig.get('leaker_id')} class {sig.get('call_class')}",
                   meta="resolved bet")
    write_tsv(ddir / "positions.tsv", positions)  # persist closes before anything else

    # 2) fill outcomes on resolved signals (incl. expired / stale pending, F6)
    foldable_statuses = ("bet", "pass", "tracked_probation", "expired", "pending_judge")
    newly_resolved: list[dict] = []
    for s in signals:
        if not s.get("market_id") or s.get("resolved_outcome"):
            continue
        if s["status"] not in foldable_statuses:
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
        if s["side"] in ("YES", "NO"):
            newly_resolved.append(s)

    # 3) fold with one credit per (leaker, market), earliest post wins (F2)
    counted_pairs = {(x["leaker_id"], x["market_id"]) for x in signals
                     if x.get("stat_counted") == "true"}
    n_scored = 0
    promotions = []
    newly_resolved.sort(key=lambda x: x.get("post_ts") or x["ts_detected"])
    for s in newly_resolved:
        pair = (s["leaker_id"], s["market_id"])
        if pair in counted_pairs:
            s["stat_counted"] = "false"
            s["note"] = (s.get("note", "") + " duplicate call on market — not scored (F2)").strip()
            continue
        hit = (s["side"] == s["resolved_outcome"])
        try:
            price_yes = float(s["price_at_signal"])
            _, price_side = side_values(s["side"], 0.5, price_yes)
        except (TypeError, ValueError):
            price_side = None  # audit-only fold → n_unpriced (F1)
        base = {"leaker_id": s["leaker_id"], "platform": s["platform"],
                "handle": s["leaker_id"].split("-", 1)[-1], "domain": args.domain,
                "call_class": s["call_class"], "status": "candidate",
                "n_calls": 0, "hits": 0, "notes": ""}
        row = ensure_leaker_row(leakers, base, s["call_class"])
        before = row.get("status")
        update_leaker_stats(row, hit, price_side, th)
        s["stat_counted"] = "true" if price_side is not None else "false"
        counted_pairs.add(pair)
        if before != "verified" and row["status"] == "verified":
            promotions.append(f"{s['leaker_id']}/{s['call_class']}")
            cognee.add(f"Leaker promoted to verified: {s['leaker_id']} on {s['call_class']} "
                       f"(hit_rate {row['hit_rate']}, edge_lcb {row['edge_lcb']}, "
                       f"n={row['n_calls']})", meta="promotion")
        n_scored += 1

    write_tsv(ddir / "signals.tsv", signals)
    write_tsv(ddir / "leakers.tsv", leakers)

    if n_closed or n_scored:
        cognee.cognify()  # refresh the delphi dataset graph — never per-heartbeat

    resolved_all = read_tsv(ddir / "resolved.tsv")
    lifetime_pnl = sum(float(r.get("pnl_usd") or 0) for r in resolved_all)
    log_result("resolve", args.domain,
               f"closed {n_closed} positions (pnl {pnl_total:+.2f}); scored {n_scored} signals; "
               f"promotions: {', '.join(promotions) or 'none'}; "
               f"equity {cfg['bankroll_usd'] + lifetime_pnl:.2f} "
               f"(lifetime pnl {lifetime_pnl:+.2f})")


if __name__ == "__main__":
    main()
