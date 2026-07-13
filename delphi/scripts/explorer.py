#!/usr/bin/env python3
"""Explorer: discover candidate leakers and qualify them against HISTORICAL
resolved Polymarket markets (would following them have beaten the price at
post time?). Seeds first; deepens thin probation leakers when the queue is
empty; every scored historical call becomes a `historical` signal row (the
FP/FN audit trail) and is never re-scored. Kickstart mode raises throughput.
LLM does extraction/matching; all stats math is deterministic (PROGRAM §0).
"""
from __future__ import annotations

import argparse

import cognee
import polymarket as pm
from lib import (ROOT, agent_context, append_lessons, append_tsv, domain_dir,
                 ensure_leaker_row, gen_id, iso_to_unix, kickstart_active,
                 leaker_row, load_config, log_result, now_iso, read_tsv,
                 update_leaker_stats, write_note, write_tsv)
from llm import call_json
from sources import fetch_posts, reddit_sub_new

import re


def sweep_subs(brief: str) -> list[str]:
    return re.findall(r"reddit:r/([A-Za-z0-9_]+)", brief)


def candidate_cap(cfg) -> int:
    if kickstart_active(cfg):
        return cfg["kickstart"]["explorer_max_candidates_per_run"]
    return cfg["sources"]["explorer_max_candidates_per_run"]


def propose_candidates(cfg, ctx, domain, brief, leakers, candidates) -> int:
    known = {r["handle"].lower() for r in leakers} | {c["handle"].lower() for c in candidates}
    chatter = []
    for sub in sweep_subs(brief)[:3]:
        chatter += [p["text"].split("\n")[0][:140] for p in reddit_sub_new(sub, 20, cfg)]
    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    prompt = (ctx + "\n\n" + prompt_t.replace("{max_candidates}", str(candidate_cap(cfg)))
              + "\n\n## DOMAIN BRIEF\n" + brief
              + "\n\n## CURRENT ROSTER (do not re-propose)\n" + ", ".join(sorted(known))
              + "\n\n## RECENT DOMAIN CHATTER (titles)\n- " + "\n- ".join(chatter[:40])
              + "\n\n## REQUEST\nPerform Task A now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}
    added = 0
    for c in j.get("candidates", []):
        h = str(c.get("handle", "")).lstrip("@").strip()
        p = str(c.get("platform", "")).strip().lower()
        if not h or p not in ("x", "reddit") or h.lower() in known:
            continue
        append_tsv(domain_dir(domain) / "candidates.tsv", {
            "ts": now_iso(), "domain": domain, "platform": p, "handle": h,
            "proposed_by": "explorer", "rationale": c.get("rationale", ""), "status": "new"})
        known.add(h.lower())
        added += 1
    append_lessons("explorer", j.get("lessons"))
    return added


def qualify(cfg, ctx, domain, brief, leakers, cand, scored_pairs, posts_limit) -> str:
    """Qualify one candidate/leaker from history. Returns a short summary."""
    th = cfg["thresholds"]
    ddir = domain_dir(domain)
    platform, handle = cand["platform"], cand["handle"]
    leaker_id = f"{platform}-{handle}".lower()
    base = {"leaker_id": leaker_id, "platform": platform, "handle": handle,
            "domain": domain, "call_class": "-", "status": "candidate",
            "n_calls": 0, "hits": 0, "notes": cand.get("rationale", "")}
    if not leaker_row(leakers, leaker_id, "-"):
        row = {c: "" for c in ("leaker_id platform handle domain call_class status "
                               "n_calls hits hit_rate avg_price_at_call est_edge "
                               "last_seen_ts notes").split()}
        row.update(base)
        leakers.append(row)

    posts = fetch_posts(platform, handle, limit=posts_limit, cfg=cfg)
    if not posts:
        return f"{handle}: no history fetched"

    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    post_block = "\n".join(f"- [{p['ts']}] {p['url']}\n  {p['text'][:400]}" for p in posts)
    prompt = (ctx + "\n\n" + prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
              + f"\n\n## CANDIDATE\n{platform}/{handle}"
              + "\n\n## POST HISTORY\n" + post_block
              + "\n\n## REQUEST\nPerform Task B now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}
    append_lessons("explorer", j.get("lessons"))
    claims = [c for c in j.get("claims", []) if c.get("checkable")][:20]
    if not claims:
        return f"{handle}: 0 checkable claims in {len(posts)} posts"

    pairs, market_by_id = [], {}
    for i, c in enumerate(claims):
        for m in pm.search_markets(str(c.get("market_query", ""))[:80], closed=True, limit=3):
            market_by_id[m["id"]] = m
            pairs.append((i, m))
    if not pairs:
        return f"{handle}: {len(claims)} claims, 0 resolved-market candidates"

    map_block = "\n".join(
        f"- claim_index {i} | market_id {m['id']} | {m['question']} | criteria: {m['description'][:200]}"
        for i, m in pairs)
    claim_block = "\n".join(f"- [{i}] {c['claim']}" for i, c in enumerate(claims))
    prompt = (ctx + "\n\n" + prompt_t + "\n\n## CLAIMS\n" + claim_block
              + "\n\n## CANDIDATE (claim, market) PAIRS\n" + map_block
              + "\n\n## REQUEST\nPerform Task C now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}

    scored = verified = skipped_dupe = 0
    for mp in j.get("mappings", []):
        if not mp.get("match"):
            continue
        try:
            claim = claims[int(mp["claim_index"])]
        except (KeyError, ValueError, IndexError):
            continue
        market = market_by_id.get(str(mp.get("market_id", "")))
        side = str(mp.get("implied_side", "")).upper()
        if not market or side not in ("YES", "NO"):
            continue
        pair_key = (claim.get("post_url", ""), market["id"])
        if pair_key in scored_pairs:  # never double-count across runs (PROGRAM §2)
            skipped_dupe += 1
            continue
        winner = pm.winning_side(market)
        if winner is None:
            continue
        price_yes = pm.price_at(market["yes_token"], iso_to_unix(claim.get("post_ts", "")))
        price_side = None if price_yes is None else (price_yes if side == "YES" else 1 - price_yes)
        hit = (side == winner)
        cls = str(claim.get("call_class", "unclassified")).strip() or "unclassified"
        row = ensure_leaker_row(leakers, base, cls)
        update_leaker_stats(row, hit, price_side, th)
        append_tsv(ddir / "signals.tsv", {
            "signal_id": gen_id("hist"), "ts_detected": now_iso(), "domain": domain,
            "leaker_id": leaker_id, "platform": platform,
            "post_url": claim.get("post_url", ""), "post_ts": claim.get("post_ts", ""),
            "claim": claim.get("claim", ""), "call_class": cls, "hedged": "false",
            "market_id": market["id"], "market_question": market["question"],
            "token_id": market["yes_token"], "side": side,
            "price_at_signal": "" if price_yes is None else f"{price_yes:.3f}",
            "liquidity_usd": f"{market['liquidity']:.0f}",
            "status": "historical", "resolved_outcome": winner,
            "note": "unpriced-fallback" if price_yes is None else "back-test",
        })
        scored_pairs.add(pair_key)
        scored += 1
        if row["status"] == "verified":
            verified += 1
    return (f"{handle}: {len(claims)} claims, {scored} scored, {skipped_dupe} dupes skipped, "
            f"{verified} verified classes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    src = cfg["sources"]
    ddir = domain_dir(args.domain)
    brief = (ddir / "domain.md").read_text(encoding="utf-8")
    ctx = agent_context("explorer")
    leakers = read_tsv(ddir / "leakers.tsv")
    candidates = read_tsv(ddir / "candidates.tsv")
    scored_pairs = {(s["post_url"], s["market_id"])
                    for s in read_tsv(ddir / "signals.tsv") if s["status"] == "historical"}

    added = propose_candidates(cfg, ctx, args.domain, brief, leakers, candidates)
    candidates = read_tsv(ddir / "candidates.tsv")

    # Queue: SEEDS FIRST (a human vouched for them), then new proposals.
    queue = [{"platform": r["platform"], "handle": r["handle"], "status": "seed",
              "rationale": r.get("notes", "")}
             for r in leakers if r["call_class"] == "-" and r["status"] == "candidate"
             and not any(x["call_class"] != "-" for x in leakers
                         if x["leaker_id"] == r["leaker_id"])]
    queue += [c for c in candidates if c["status"] == "new"]
    queue = queue[:candidate_cap(cfg)]
    mode = "qualify"

    # Deepen mode: queue empty → push the thinnest probation leaker toward the gate.
    posts_limit = src["history_max_posts"]
    if not queue:
        probation = [r for r in leakers if r["status"] == "probation"]
        if probation:
            thin = min(probation, key=lambda r: int(r.get("n_calls") or 0))
            queue = [{"platform": thin["platform"], "handle": thin["handle"],
                      "status": "deepen", "rationale": "deepen thinnest probation leaker"}]
            posts_limit = src["history_max_posts"] * 2
            mode = f"deepen:{thin['handle']}"

    summaries = []
    for cand in queue:
        try:
            summaries.append(qualify(cfg, ctx, args.domain, brief, leakers, cand,
                                     scored_pairs, posts_limit))
        except Exception as e:  # noqa: BLE001 — skip-and-log boundary (§7)
            summaries.append(f"{cand.get('handle')}: FAILED {e}")
        for c in candidates:
            if c.get("handle") == cand.get("handle") and c.get("status") == "new":
                c["status"] = "checked"
    write_tsv(ddir / "candidates.tsv", candidates)
    write_tsv(ddir / "leakers.tsv", leakers)

    summary = (f"mode={mode}; proposed {added} candidates; "
               + ("; ".join(summaries) or "nothing to qualify"))
    note = (f"Run mode: {mode} (kickstart={kickstart_active(cfg)}).\n"
            f"Proposed {added} new candidates.\nResults:\n- " + "\n- ".join(summaries or ["idle"]))
    write_note("explorer", "run", note)
    cognee.add(note, meta=f"explorer {args.domain}")
    log_result("explorer", args.domain, summary)


if __name__ == "__main__":
    main()
