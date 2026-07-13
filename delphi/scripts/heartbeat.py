#!/usr/bin/env python3
"""Heartbeat (every 10 min): sweep the roster (verified + probation) for new
posts, extract claims, match to OPEN Polymarket markets, log signal rows with
the price at detection. Probation signals are tracked, never bet.

Round-2 review fixes baked in:
- F5: posts are processed OLDEST-FIRST with a per-post atomic commit — the
  cursor advances only through posts whose claims ALL reached a terminal row,
  so backlogs drain across sweeps and no sibling claim is ever dropped.
- F4: strict output structure ("claims" list required, else retry); post
  provenance (ts/url) is copied from the indexed source post, never trusted
  from LLM echo.
"""
from __future__ import annotations

import argparse
import time

import cognee
import polymarket as pm
from lib import (ROOT, agent_context, append_lessons, append_tsv, domain_dir,
                 gen_id, iso_to_unix, load_config, log_result, normalize_class,
                 now_iso, read_tsv, unix_to_iso, write_note, write_tsv)
from llm import call_json
from sources import fetch_posts

MAX_POSTS_PER_SWEEP = 15   # backlog drains at this rate per 10-min sweep
MAX_CLAIMS_PER_POST = 4


def sweep_roster(leakers: list[dict]) -> list[dict]:
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


def leaker_classes(leakers: list[dict], leaker_id: str) -> list[str]:
    return sorted({r["call_class"] for r in leakers
                   if r["leaker_id"] == leaker_id and r["call_class"] != "-"})


def is_verified(leakers: list[dict], leaker_id: str, call_class: str) -> bool:
    return any(r["leaker_id"] == leaker_id and r["call_class"] == call_class
               and r["status"] == "verified" for r in leakers)


def logged_empty_today() -> bool:
    today = time.strftime("%Y-%m-%d")
    rows = read_tsv(ROOT / "ledger" / "results.tsv")
    return any(r["script"] == "heartbeat" and r["ts"].startswith(today)
               and "roster empty" in r["summary"] for r in rows)


def build_claim_row(domain, lk, post, c, cls):
    return {
        "signal_id": gen_id("sig"), "ts_detected": now_iso(),
        "domain": domain, "leaker_id": lk["leaker_id"],
        "platform": lk["platform"], "post_url": post["url"],
        "post_ts": post["ts"], "claim": c.get("claim", ""),
        "call_class": cls,
        "hedged": str(bool(c.get("hedged", False))).lower(),
        "resolved_outcome": "", "stat_counted": "", "note": "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    taxonomy = (cfg.get("call_classes") or {}).get(args.domain) or []
    ddir = domain_dir(args.domain)
    brief = (ddir / "domain.md").read_text(encoding="utf-8")
    ctx = agent_context("heartbeat", max_notes=0)
    prompt_t = (ROOT / "prompts" / "heartbeat.md").read_text(encoding="utf-8")
    leakers = read_tsv(ddir / "leakers.tsv")
    signals = read_tsv(ddir / "signals.tsv")
    known_posts = {s["post_url"] for s in signals}

    roster = sweep_roster(leakers)
    if not roster:
        if not logged_empty_today():
            log_result("heartbeat", args.domain,
                       "roster empty (no verified/probation leakers) — run explorer.py")
        return

    n_posts = n_claims = n_pending = n_tracked = n_nomarket = n_deferred = 0
    lessons_all: list[str] = []
    events: list[str] = []
    for lk in roster:
        since = max((r.get("last_seen_ts") or "" for r in leakers
                     if r["leaker_id"] == lk["leaker_id"]), default="")
        if not since:
            since = unix_to_iso(iso_to_unix(now_iso()) - 86400)
        try:
            fetched = [p for p in fetch_posts(lk["platform"], lk["handle"], since, 50, cfg)
                       if p["url"] not in known_posts and p["ts"] > since]
        except Exception as e:  # noqa: BLE001
            print(f"  [heartbeat] fetch {lk['handle']}: {e}")
            continue
        # F5: OLDEST-FIRST, bounded batch — leftovers stay beyond the cursor
        posts = sorted(fetched, key=lambda p: p["ts"])[:MAX_POSTS_PER_SWEEP]
        if not posts:
            continue
        n_posts += len(posts)

        post_block = "\n".join(f"- post_index {i} | [{p['ts']}] {p['url']}\n  {p['text'][:500]}"
                               for i, p in enumerate(posts))
        prompt = (ctx + "\n\n" + prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
                  + "\n\n## FIXED CALL-CLASS TAXONOMY (use ONLY these)\n"
                  + ", ".join(taxonomy)
                  + f"\n\n## LEAKER\n{lk['platform']}/{lk['handle']}"
                  + "\n\n## THIS LEAKER'S EXISTING CALL CLASSES\n"
                  + (", ".join(leaker_classes(leakers, lk["leaker_id"])) or "none yet")
                  + "\n\n## NEW POSTS\n" + post_block
                  + "\n\n## REQUEST\nExtract claims now. JSON only.")
        j = call_json("heartbeat", prompt, cfg)
        if j is None or not isinstance(j.get("claims"), list):  # F4: strict — retry
            print(f"  [heartbeat] extraction unusable for {lk['handle']} — will retry")
            continue
        lessons_all += j.get("lessons") or []

        # Group claims by post via post_index; provenance copied from source.
        claims_by_post: dict[int, list[dict]] = {}
        for c in j["claims"]:
            try:
                pi = int(c["post_index"])
            except (KeyError, ValueError, TypeError):
                continue
            if 0 <= pi < len(posts) and str(c.get("claim", "")).strip():
                claims_by_post.setdefault(pi, []).append(c)

        # F5: per-post atomic commit, cursor advances through committed posts only.
        committed_ts = ""
        for pi, post in enumerate(posts):
            group = claims_by_post.get(pi, [])[:MAX_CLAIMS_PER_POST]
            rows, deferred = [], False
            for c in group:
                cls = normalize_class(c.get("call_class", ""), cfg, args.domain)
                sig = build_claim_row(args.domain, lk, post, c, cls)
                n_claims += 1
                markets = pm.search_markets(str(c.get("market_query", ""))[:80],
                                            closed=False, limit=5)
                if markets is None:  # transient API failure → defer whole post
                    deferred = True
                    break
                chosen, side = None, ""
                if markets:
                    mk_block = "\n".join(
                        f"- claim_index 0 | market_id {m['id']} | {m['question']} | "
                        f"criteria: {m['description'][:200]}" for m in markets)
                    mp = call_json("heartbeat",
                                   ctx + "\n\n" + prompt_t + "\n\n## CLAIMS\n- [0] " + sig["claim"]
                                   + "\n\n## CANDIDATE (claim, market) PAIRS\n" + mk_block
                                   + "\n\n## REQUEST\nPerform market mapping now. JSON only.",
                                   cfg)
                    if mp is None or not isinstance(mp.get("mappings"), list):
                        deferred = True
                        break
                    for m_ in mp["mappings"]:
                        if m_.get("match") and str(m_.get("implied_side", "")).upper() in ("YES", "NO"):
                            chosen = next((mm for mm in markets
                                           if mm["id"] == str(m_.get("market_id"))), None)
                            side = str(m_["implied_side"]).upper()
                            break
                if not chosen:
                    sig.update({"status": "no_market",
                                "note": f"top candidate: {markets[0]['question'][:80]}" if markets else "no candidates"})
                else:
                    price_yes = pm.midpoint(chosen["yes_token"])
                    if price_yes is None:
                        price_yes = chosen["yes_price"]
                    if price_yes is None:  # transient — defer whole post
                        deferred = True
                        break
                    verified = is_verified(leakers, lk["leaker_id"], cls)
                    liq_ok = chosen["liquidity"] >= th["min_liquidity_usd"]
                    sig.update({
                        "market_id": chosen["id"], "event_id": chosen.get("event_id", ""),
                        "market_question": chosen["question"],
                        "token_id": chosen["yes_token"], "side": side,
                        "price_at_signal": f"{price_yes:.3f}",
                        "liquidity_usd": f"{chosen['liquidity']:.0f}",
                        "status": "pending_judge" if (verified and liq_ok) else "tracked_probation",
                        "note": "" if liq_ok else "below min liquidity",
                    })
                rows.append(sig)
            if deferred:  # nothing from this post is committed; retry next sweep
                n_deferred += 1
                break  # posts after this one stay beyond the cursor too
            for sig in rows:
                append_tsv(ddir / "signals.tsv", sig)
                known_posts.add(sig["post_url"])
                events.append(f"{lk['handle']}: {sig['claim'][:90]} → {sig['status']}")
                if sig["status"] == "pending_judge":
                    n_pending += 1
                elif sig["status"] == "tracked_probation":
                    n_tracked += 1
                elif sig["status"] == "no_market":
                    n_nomarket += 1
            committed_ts = post["ts"]

        if committed_ts:
            for r in leakers:
                if r["leaker_id"] == lk["leaker_id"] and committed_ts > (r.get("last_seen_ts") or ""):
                    r["last_seen_ts"] = committed_ts

    write_tsv(ddir / "leakers.tsv", leakers)
    append_lessons("heartbeat", lessons_all)
    if events:
        note = "Signals this sweep:\n- " + "\n- ".join(events)
        write_note("heartbeat", "signals", note)
        cognee.add(note, meta=f"heartbeat {args.domain}")
    log_result("heartbeat", args.domain,
               f"swept {len(roster)} leakers, {n_posts} new posts, {n_claims} claims → "
               f"{n_pending} pending_judge, {n_tracked} probation-tracked, "
               f"{n_nomarket} no_market, {n_deferred} posts deferred-transient")


if __name__ == "__main__":
    main()
