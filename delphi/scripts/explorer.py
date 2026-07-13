#!/usr/bin/env python3
"""Explorer: discover candidate leakers and qualify them against HISTORICAL
resolved Polymarket markets (would following them have beaten the price at
post time?).

Review fixes baked in:
- F1: only genuinely priced-at-post-time calls count toward verification;
  unpriced calls become audit rows (stat_counted=false) and n_unpriced.
- F2: at most ONE market per claim, at most one credit per (leaker, market)
  pair ever — repeated posts and overlapping contracts cannot double-count.
- F3: date-bounded, paginated history windows; frozen call-class taxonomy.
- F5: deepen ANY partially-scored, non-verified, non-retired leaker.
"""
from __future__ import annotations

import argparse
import re

import cognee
import polymarket as pm
from lib import (ROOT, agent_context, append_lessons, append_tsv, domain_dir,
                 ensure_leaker_row, gen_id, iso_to_unix, kickstart_active,
                 leaker_row, load_config, log_result, normalize_class, now_iso,
                 read_tsv, unix_to_iso, update_leaker_stats, write_note,
                 write_tsv)
from llm import call_json
from sources import fetch_posts, reddit_sub_new


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


def qualify(cfg, ctx, domain, brief, leakers, cand, counted_pairs,
            posts_limit, start_iso, end_iso=None) -> str:
    """Qualify one candidate/leaker from one history window."""
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
                               "edge_lcb n_unpriced last_seen_ts notes").split()}
        row.update(base)
        leakers.append(row)

    posts = fetch_posts(platform, handle, since_iso=start_iso,
                        limit=posts_limit, cfg=cfg, end_iso=end_iso)
    if not posts:
        return f"{handle}: no history fetched in window"

    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    # F4 (round 2): posts get stable indices; scripts copy provenance from the
    # indexed source post — LLM-echoed timestamps/URLs are never trusted.
    post_block = "\n".join(f"- post_index {i} | [{p['ts']}] {p['url']}\n  {p['text'][:400]}"
                           for i, p in enumerate(posts))
    prompt = (ctx + "\n\n" + prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
              + f"\n\n## CANDIDATE\n{platform}/{handle}"
              + "\n\n## POST HISTORY\n" + post_block
              + "\n\n## REQUEST\nPerform Task B now. JSON only.")
    j = call_json("explorer", prompt, cfg)
    if j is None or not isinstance(j.get("claims"), list):
        return f"{handle}: extraction unparseable — retry next run (F4)"
    append_lessons("explorer", j.get("lessons"))
    # F2 (round 2): NO LLM checkable-gate — every falsifiable claim goes to the
    # deterministic resolved-market lookup, which decides scoreability.
    claims = []
    for c in j.get("claims", []):
        try:
            p = posts[int(c["post_index"])]
        except (KeyError, ValueError, TypeError, IndexError):
            continue  # no verifiable provenance → claim dropped
        if not str(c.get("claim", "")).strip():
            continue
        c["post_ts"], c["post_url"] = p["ts"], p["url"]  # canonical provenance
        claims.append(c)
    claims = claims[:40]
    if not claims:
        return f"{handle}: 0 usable claims in {len(posts)} posts"

    pairs, market_by_id, search_failed = [], {}, 0
    for i, c in enumerate(claims):
        found = pm.search_markets(str(c.get("market_query", ""))[:80], closed=True, limit=3)
        if found is None:  # transient API failure — this claim stays retryable (F6)
            search_failed += 1
            continue
        for m in found:
            market_by_id[m["id"]] = m
            pairs.append((i, m))
    if not pairs:
        return (f"{handle}: {len(claims)} claims, 0 resolved-market candidates"
                + (f" ({search_failed} searches failed transiently)" if search_failed else ""))

    map_block = "\n".join(
        f"- claim_index {i} | market_id {m['id']} | {m['question']} | criteria: {m['description'][:200]}"
        for i, m in pairs)
    claim_block = "\n".join(f"- [{i}] {c['claim']}" for i, c in enumerate(claims))
    prompt = (ctx + "\n\n" + prompt_t + "\n\n## CLAIMS\n" + claim_block
              + "\n\n## CANDIDATE (claim, market) PAIRS\n" + map_block
              + "\n\n## REQUEST\nPerform Task C now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}

    # F2: keep only the FIRST match per claim — one market per claim.
    best_by_claim: dict[int, dict] = {}
    for mp in (j.get("mappings") or []):
        if not mp.get("match"):
            continue
        try:
            ci = int(mp["claim_index"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= ci < len(claims) and ci not in best_by_claim:
            best_by_claim[ci] = mp

    # F3 (round 2): deterministic EARLIEST-POST-FIRST scoring order, so the
    # origination call takes the (leaker, event) credit — not whatever order
    # the LLM listed, and not a later correction.
    ordered = sorted(best_by_claim.items(),
                     key=lambda kv: claims[kv[0]].get("post_ts") or "9999")

    scored = unpriced = verified = skipped_dupe = 0
    for ci, mp in ordered:
        claim = claims[ci]
        market = market_by_id.get(str(mp.get("market_id", "")))
        side = str(mp.get("implied_side", "")).upper()
        if not market or side not in ("YES", "NO"):
            continue
        # F3 (round 2): credit key is the EVENT when known, so overlapping
        # deadline-ladder contracts of one event cannot multi-credit.
        event_key = market.get("event_id") or market["id"]
        pair_key = (leaker_id, event_key)
        if pair_key in counted_pairs:
            skipped_dupe += 1
            continue
        winner = pm.winning_side(market)
        if winner is None:
            continue
        price_yes = pm.price_at(market["yes_token"], iso_to_unix(claim.get("post_ts", "")))
        price_side = None if price_yes is None else (price_yes if side == "YES" else 1 - price_yes)
        hit = (side == winner)
        cls = normalize_class(claim.get("call_class", ""), cfg, domain)
        row = ensure_leaker_row(leakers, base, cls)
        update_leaker_stats(row, hit, price_side, th)  # F1: unpriced → n_unpriced only
        counted = price_side is not None
        append_tsv(ddir / "signals.tsv", {
            "signal_id": gen_id("hist"), "ts_detected": now_iso(), "domain": domain,
            "leaker_id": leaker_id, "platform": platform,
            "post_url": claim.get("post_url", ""), "post_ts": claim.get("post_ts", ""),
            "claim": claim.get("claim", ""), "call_class": cls, "hedged": "false",
            "market_id": market["id"], "event_id": market.get("event_id", ""),
            "market_question": market["question"],
            "token_id": market["yes_token"], "side": side,
            "price_at_signal": "" if price_yes is None else f"{price_yes:.3f}",
            "liquidity_usd": f"{market['liquidity']:.0f}",
            "status": "historical", "resolved_outcome": winner,
            "stat_counted": "true" if counted else "false",
            "note": "back-test" if counted else "unpriced — audit only, excluded from gate (F1)",
        })
        counted_pairs.add(pair_key)
        if counted:
            scored += 1
        else:
            unpriced += 1
        if row["status"] == "verified":
            verified += 1
    return (f"{handle}: {len(claims)} claims → {scored} priced calls scored, "
            f"{unpriced} unpriced (audit-only), {skipped_dupe} dupes blocked, "
            f"{verified} verified classes")


def deepen_targets(leakers: list[dict], cap: int) -> list[dict]:
    """F5: any partially-scored, non-verified, non-retired leaker is eligible."""
    by_leaker: dict[str, list[dict]] = {}
    for r in leakers:
        if r["call_class"] != "-":
            by_leaker.setdefault(r["leaker_id"], []).append(r)
    eligible = []
    for lid, rows in by_leaker.items():
        if any(r["status"] == "verified" for r in rows):
            continue
        if all(r["status"] == "retired" for r in rows):
            continue
        total_n = sum(int(r.get("n_calls") or 0) for r in rows)
        eligible.append((total_n, rows[0]))
    eligible.sort(key=lambda x: x[0])
    return [{"platform": r["platform"], "handle": r["handle"], "status": "deepen",
             "rationale": "deepen partially-scored leaker"} for _, r in eligible[:cap]]


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
    counted_pairs = {(s["leaker_id"], s.get("event_id") or s["market_id"])
                     for s in read_tsv(ddir / "signals.tsv")
                     if s["status"] == "historical" or s.get("stat_counted") == "true"}

    added = propose_candidates(cfg, ctx, args.domain, brief, leakers, candidates)
    candidates = read_tsv(ddir / "candidates.tsv")

    now_unix = iso_to_unix(now_iso())
    std_start = unix_to_iso(now_unix - src["history_days"] * 86400)

    # Queue: SEEDS FIRST (a human vouched for them), then new proposals.
    queue = [{"platform": r["platform"], "handle": r["handle"], "status": "seed",
              "rationale": r.get("notes", ""), "_start": std_start, "_end": None,
              "_limit": src["history_max_posts"]}
             for r in leakers if r["call_class"] == "-" and r["status"] == "candidate"
             and not any(x["call_class"] != "-" for x in leakers
                         if x["leaker_id"] == r["leaker_id"])]
    queue += [{**c, "_start": std_start, "_end": None, "_limit": src["history_max_posts"]}
              for c in candidates if c["status"] == "new"]
    queue = queue[:candidate_cap(cfg)]
    mode = "qualify"

    if not queue:  # deepen: OLDER window, more posts
        targets = deepen_targets(leakers, 2 if kickstart_active(cfg) else 1)
        for t in targets:
            t.update({"_start": unix_to_iso(now_unix - 2 * src["history_days"] * 86400),
                      "_end": std_start, "_limit": src["history_max_posts"] * 2})
        queue = targets
        mode = "deepen:" + ",".join(t["handle"] for t in targets) if targets else "idle"

    summaries = []
    for cand in queue:
        try:
            summaries.append(qualify(cfg, ctx, args.domain, brief, leakers, cand,
                                     counted_pairs, cand["_limit"],
                                     cand["_start"], cand["_end"]))
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
