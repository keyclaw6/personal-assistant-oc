#!/usr/bin/env python3
"""Heartbeat (every 10 min): sweep the roster (verified + probation) for new
posts, extract claims, match to OPEN Polymarket markets, log signal rows with
the price at detection (PROGRAM.md §0.4). Probation signals are tracked, never
bet. Judge runs separately on `pending_judge` rows.
"""
from __future__ import annotations

import argparse

import polymarket as pm
from lib import (append_tsv, domain_dir, gen_id, load_config, log_result,
                 now_iso, read_tsv, unix_to_iso, iso_to_unix, write_tsv, ROOT)
from llm import call_json
from sources import fetch_posts


def sweep_roster(leakers: list[dict]) -> list[dict]:
    """Unique leakers with any row in (verified, probation)."""
    seen, out = set(), []
    for r in leakers:
        if r["status"] not in ("verified", "probation"):
            continue
        key = (r["platform"], r["handle"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def is_verified(leakers: list[dict], leaker_id: str, call_class: str) -> bool:
    return any(r["leaker_id"] == leaker_id and r["call_class"] == call_class
               and r["status"] == "verified" for r in leakers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    ddir = domain_dir(args.domain)
    brief = (ddir / "domain.md").read_text(encoding="utf-8")
    prompt_t = (ROOT / "prompts" / "heartbeat.md").read_text(encoding="utf-8")
    leakers = read_tsv(ddir / "leakers.tsv")
    signals = read_tsv(ddir / "signals.tsv")
    known_posts = {s["post_url"] for s in signals}

    roster = sweep_roster(leakers)
    if not roster:
        log_result("heartbeat", args.domain,
                   "roster empty (no verified/probation leakers) — run explorer.py")
        return

    n_posts = n_claims = n_pending = n_tracked = n_nomarket = 0
    for lk in roster:
        since = max((r.get("last_seen_ts") or "" for r in leakers
                     if r["leaker_id"] == lk["leaker_id"]), default="")
        if not since:
            since = unix_to_iso(iso_to_unix(now_iso()) - 86400)
        try:
            posts = [p for p in fetch_posts(lk["platform"], lk["handle"], since, 15, cfg)
                     if p["url"] not in known_posts and p["ts"] > since]
        except Exception as e:  # noqa: BLE001
            print(f"  [heartbeat] fetch {lk['handle']}: {e}")
            continue
        if not posts:
            continue
        n_posts += len(posts)

        post_block = "\n".join(f"- [{p['ts']}] {p['url']}\n  {p['text'][:500]}" for p in posts)
        prompt = (prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
                  + f"\n\n## LEAKER\n{lk['platform']}/{lk['handle']}"
                  + "\n\n## NEW POSTS\n" + post_block
                  + "\n\n## REQUEST\nExtract claims now. JSON only.")
        j = call_json("heartbeat", prompt, cfg) or {}
        claims = j.get("claims", [])[:5]
        n_claims += len(claims)

        for c in claims:
            sig = {
                "signal_id": gen_id("sig"), "ts_detected": now_iso(),
                "domain": args.domain, "leaker_id": lk["leaker_id"],
                "platform": lk["platform"], "post_url": c.get("post_url", ""),
                "post_ts": c.get("post_ts", ""), "claim": c.get("claim", ""),
                "call_class": c.get("call_class", "unclassified"),
                "hedged": str(bool(c.get("hedged", False))).lower(),
                "resolved_outcome": "", "note": "",
            }
            markets = pm.search_markets(str(c.get("market_query", ""))[:80],
                                        closed=False, limit=5)
            chosen, side = None, ""
            if markets:
                mk_block = "\n".join(
                    f"- claim_index 0 | market_id {m['id']} | {m['question']} | "
                    f"criteria: {m['description'][:200]}" for m in markets)
                mp = call_json("heartbeat",
                               prompt_t + "\n\n## CLAIMS\n- [0] " + sig["claim"]
                               + "\n\n## CANDIDATE (claim, market) PAIRS\n" + mk_block
                               + "\n\n## REQUEST\nPerform market mapping now. JSON only.",
                               cfg) or {}
                for m_ in mp.get("mappings", []):
                    if m_.get("match") and str(m_.get("implied_side", "")).upper() in ("YES", "NO"):
                        chosen = next((mm for mm in markets
                                       if mm["id"] == str(m_.get("market_id"))), None)
                        side = str(m_["implied_side"]).upper()
                        break
            if not chosen:
                sig.update({"status": "no_market",
                            "note": f"top candidate: {markets[0]['question'][:80]}" if markets else ""})
                n_nomarket += 1
            else:
                price_yes = pm.midpoint(chosen["yes_token"])
                if price_yes is None:
                    price_yes = chosen["yes_price"]
                if price_yes is None:
                    sig.update({"status": "no_market", "note": "no price available — skipped (§6)"})
                    n_nomarket += 1
                else:
                    verified = is_verified(leakers, lk["leaker_id"], sig["call_class"])
                    liq_ok = chosen["liquidity"] >= th["min_liquidity_usd"]
                    sig.update({
                        "market_id": chosen["id"], "market_question": chosen["question"],
                        "token_id": chosen["yes_token"], "side": side,
                        "price_at_signal": f"{price_yes:.3f}",
                        "liquidity_usd": f"{chosen['liquidity']:.0f}",
                        "status": "pending_judge" if (verified and liq_ok) else "tracked_probation",
                        "note": "" if liq_ok else "below min liquidity",
                    })
                    if sig["status"] == "pending_judge":
                        n_pending += 1
                    else:
                        n_tracked += 1
            append_tsv(ddir / "signals.tsv", sig)
            known_posts.add(sig["post_url"])

        newest = max(p["ts"] for p in posts)
        for r in leakers:
            if r["leaker_id"] == lk["leaker_id"] and newest > (r.get("last_seen_ts") or ""):
                r["last_seen_ts"] = newest

    write_tsv(ddir / "leakers.tsv", leakers)
    log_result("heartbeat", args.domain,
               f"swept {len(roster)} leakers, {n_posts} new posts, {n_claims} claims → "
               f"{n_pending} pending_judge, {n_tracked} probation-tracked, {n_nomarket} no_market")


if __name__ == "__main__":
    main()
