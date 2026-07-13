#!/usr/bin/env python3
"""Explorer (daily): discover candidate leakers and qualify them against
HISTORICAL resolved Polymarket markets, so betting can start on evidence soon
(PROGRAM.md §1). LLM does extraction/matching; all stats math is deterministic.
"""
from __future__ import annotations

import argparse
import re

import polymarket as pm
from lib import (append_tsv, domain_dir, ensure_leaker_row, iso_to_unix,
                 leaker_row, load_config, log_result, now_iso, read_tsv,
                 write_tsv, update_leaker_stats, ROOT)
from llm import call_json
from sources import fetch_posts, reddit_sub_new


def sweep_subs(brief: str) -> list[str]:
    return re.findall(r"reddit:r/([A-Za-z0-9_]+)", brief)


def propose_candidates(cfg, domain, brief, leakers, candidates) -> int:
    known = {r["handle"].lower() for r in leakers} | {c["handle"].lower() for c in candidates}
    chatter = []
    for sub in sweep_subs(brief)[:3]:
        chatter += [p["text"].split("\n")[0][:140] for p in reddit_sub_new(sub, 20, cfg)]
    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    n_max = cfg["sources"]["explorer_max_candidates_per_run"]
    prompt = (prompt_t.replace("{max_candidates}", str(n_max))
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
    return added


def qualify(cfg, domain, brief, leakers, cand_row) -> str:
    """Qualify one candidate from history. Returns a short summary string."""
    th = cfg["thresholds"]
    src = cfg["sources"]
    platform, handle = cand_row["platform"], cand_row["handle"]
    leaker_id = f"{platform}-{handle}".lower()
    base = {"leaker_id": leaker_id, "platform": platform, "handle": handle,
            "domain": domain, "call_class": "-", "status": "candidate",
            "n_calls": 0, "hits": 0, "notes": cand_row.get("rationale", "")}
    if not leaker_row(leakers, leaker_id, "-"):
        row = {c: "" for c in ("leaker_id platform handle domain call_class status "
                               "n_calls hits hit_rate avg_price_at_call est_edge "
                               "last_seen_ts notes").split()}
        row.update(base)
        leakers.append(row)

    posts = fetch_posts(platform, handle, limit=src["history_max_posts"], cfg=cfg)
    if not posts:
        return f"{handle}: no history fetched"

    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    post_block = "\n".join(f"- [{p['ts']}] {p['url']}\n  {p['text'][:400]}" for p in posts)
    prompt = (prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
              + f"\n\n## CANDIDATE\n{platform}/{handle}"
              + "\n\n## POST HISTORY\n" + post_block
              + "\n\n## REQUEST\nPerform Task B now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}
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
    prompt = (prompt_t + "\n\n## CLAIMS\n" + claim_block
              + "\n\n## CANDIDATE (claim, market) PAIRS\n" + map_block
              + "\n\n## REQUEST\nPerform Task C now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}

    scored = verified = 0
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
        winner = pm.winning_side(market)
        if winner is None:
            continue
        price_yes = pm.price_at(market["yes_token"], iso_to_unix(claim.get("post_ts", "")))
        price_side = None if price_yes is None else (price_yes if side == "YES" else 1 - price_yes)
        hit = (side == winner)
        cls = str(claim.get("call_class", "unclassified")).strip() or "unclassified"
        row = ensure_leaker_row(leakers, base, cls)
        update_leaker_stats(row, hit, price_side, th)
        scored += 1
        if row["status"] == "verified":
            verified += 1
    return f"{handle}: {len(claims)} claims, {scored} scored calls, {verified} verified classes"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    ddir = domain_dir(args.domain)
    brief = (ddir / "domain.md").read_text(encoding="utf-8")
    leakers = read_tsv(ddir / "leakers.tsv")
    candidates = read_tsv(ddir / "candidates.tsv")

    added = propose_candidates(cfg, args.domain, brief, leakers, candidates)

    candidates = read_tsv(ddir / "candidates.tsv")
    queue = [c for c in candidates if c["status"] == "new"]
    queue += [{"platform": r["platform"], "handle": r["handle"], "status": "seed",
               "rationale": r.get("notes", "")}
              for r in leakers if r["call_class"] == "-" and r["status"] == "candidate"
              and not any(x["call_class"] != "-" for x in leakers
                          if x["leaker_id"] == r["leaker_id"])]
    queue = queue[:cfg["sources"]["explorer_max_candidates_per_run"]]

    summaries = []
    for cand in queue:
        try:
            summaries.append(qualify(cfg, args.domain, brief, leakers, cand))
        except Exception as e:  # noqa: BLE001 — skip-and-log boundary (§6)
            summaries.append(f"{cand.get('handle')}: FAILED {e}")
        for c in candidates:
            if c.get("handle") == cand.get("handle") and c.get("status") == "new":
                c["status"] = "checked"
    write_tsv(ddir / "candidates.tsv", candidates)
    write_tsv(ddir / "leakers.tsv", leakers)
    log_result("explorer", args.domain,
               f"proposed {added} new candidates; " + ("; ".join(summaries) or "no qualification run"))


if __name__ == "__main__":
    main()
