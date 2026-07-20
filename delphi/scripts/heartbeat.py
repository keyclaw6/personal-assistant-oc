#!/usr/bin/env python3
"""Heartbeat (every 10 min): sweep the roster (verified + probation) for new
posts, extract claims, match to OPEN Polymarket markets, log signal rows with
the price at detection. Probation signals are tracked, never bet.

Posts are processed OLDEST-FIRST with a per-post atomic commit. Every terminal
claim row and a post-completion marker enter signals.tsv in the same rewrite;
that marker is the compound (timestamp + stable post id) cursor. A crash can
therefore retry a post, but can never advance past uncommitted sibling claims.
"""
from __future__ import annotations

import argparse
import time

import cognee
import polymarket as pm
from lib import (ROOT, agent_context, append_lessons, domain_dir,
                 gen_id, iso_to_unix, load_config, log_result, normalize_class,
                 now_iso, read_tsv, unix_to_iso, write_note, write_tsv)
from llm import call_json
from source_timestamps import (SourceTimestampError, utc_now,
                               validate_source_posts,
                               validate_source_timestamp)
from sources import fetch_posts

MAX_POSTS_PER_SWEEP = 15   # backlog drains at this rate per 10-min sweep
POST_COMPLETE = "post_complete"
POST_ID_PREFIX = "post_id="
MAPPING_FIELDS = {"claim_id", "market_id", "match", "implied_side"}


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
        "post_ts": post["ts"], "source_post_id": post.get("id", ""),
        "claim": c.get("claim", ""),
        "call_class": cls,
        "hedged": str(bool(c.get("hedged", False))).lower(),
        "resolved_outcome": "", "stat_counted": "", "note": "",
    }


def post_id(post: dict) -> str:
    return str(post.get("id") or post.get("url") or "").strip()


def post_key(post: dict) -> tuple[str, str]:
    return str(post.get("ts") or ""), post_id(post)


def marker_post_id(row: dict) -> str:
    note = str(row.get("note") or "")
    return note[len(POST_ID_PREFIX):] if note.startswith(POST_ID_PREFIX) else ""


def watermark(signals: list[dict], leakers: list[dict], leaker_id: str,
              *, now=None) -> tuple[str, str]:
    """Latest atomically-completed post, with legacy timestamp fallback."""
    reference = now if now is not None else utc_now()
    markers = []
    for row in signals:
        if (row.get("leaker_id") != leaker_id
                or row.get("status") != POST_COMPLETE):
            continue
        try:
            timestamp = validate_source_timestamp(
                row.get("post_ts"), now=reference)
        except SourceTimestampError:
            continue
        markers.append((timestamp,
                        marker_post_id(row) or row.get("post_url") or ""))
    if markers:
        return max(markers)
    legacy = []
    for row in leakers:
        if row.get("leaker_id") != leaker_id:
            continue
        ts, _, pid = str(row.get("last_seen_ts") or "").partition("|")
        try:
            timestamp = validate_source_timestamp(ts, now=reference)
        except SourceTimestampError:
            continue
        legacy.append((timestamp, pid))
    return max(legacy, default=("", ""))


def build_completion_row(domain: str, lk: dict, post: dict) -> dict:
    return {
        "signal_id": gen_id("seen"), "ts_detected": now_iso(),
        "domain": domain, "leaker_id": lk["leaker_id"],
        "platform": lk["platform"], "post_url": post["url"],
        "post_ts": post["ts"], "source_post_id": post.get("id", ""),
        "claim": "", "call_class": "-",
        "hedged": "false", "status": POST_COMPLETE,
        "resolved_outcome": "", "stat_counted": "",
        "note": POST_ID_PREFIX + post_id(post),
    }


def claim_key(row: dict) -> tuple[str, str, str]:
    claim = " ".join(str(row.get("claim") or "").lower().split())
    return str(row.get("platform") or ""), str(row.get("post_url") or ""), claim


def canonical_mapping_id(value) -> bool:
    return (type(value) is str and bool(value) and value == value.strip()
            and all(character.isprintable() and not character.isspace()
                    for character in value))


def validated_mappings(response, inputs: list[dict]):
    """Return one validated market decision per unambiguous input claim ID."""
    expected = {}
    for item in inputs:
        if not isinstance(item, dict):
            return None
        claim_id = item.get("claim_id")
        markets = item.get("markets")
        if (not canonical_mapping_id(claim_id) or claim_id in expected
                or not isinstance(markets, list)):
            return None
        candidates = {}
        for market in markets:
            if not isinstance(market, dict):
                return None
            market_id = market.get("id")
            if (not canonical_mapping_id(market_id) or market_id in candidates):
                return None
            candidates[market_id] = market
        expected[claim_id] = candidates

    if (not isinstance(response, dict) or set(response) != {"mappings"}
            or not isinstance(response["mappings"], list)
            or len(response["mappings"]) != len(expected)):
        return None

    accepted = {}
    for record in response["mappings"]:
        if not isinstance(record, dict) or set(record) != MAPPING_FIELDS:
            return None
        claim_id = record["claim_id"]
        market_id = record["market_id"]
        match = record["match"]
        side = record["implied_side"]
        if (not canonical_mapping_id(claim_id) or claim_id not in expected
                or claim_id in accepted or type(market_id) is not str
                or type(match) is not bool or type(side) is not str):
            return None
        if match:
            if (not canonical_mapping_id(market_id)
                    or market_id not in expected[claim_id]
                    or side not in ("YES", "NO")):
                return None
            accepted[claim_id] = (expected[claim_id][market_id], side)
        else:
            if market_id or side:
                return None
            accepted[claim_id] = (None, "")
    return accepted if set(accepted) == set(expected) else None


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
    signals_path = ddir / "signals.tsv"
    signals = read_tsv(signals_path)
    source_now = utc_now()
    # A durable completion marker, not a standalone claim row, proves that a
    # post committed. Persisted unmarked rows are append-only legacy evidence
    # and never suppress retry work. This set receives rows only after their
    # whole post transaction and marker commit successfully in this sweep.
    known_claims = set()

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
        cursor = watermark(signals, leakers, lk["leaker_id"], now=source_now)
        since = cursor[0] or unix_to_iso(iso_to_unix(now_iso()) - 86400)
        try:
            fetched = fetch_posts(lk["platform"], lk["handle"], since,
                                  MAX_POSTS_PER_SWEEP, cfg,
                                  oldest_first=True, after_id=cursor[1])
        except Exception as e:  # noqa: BLE001
            print(f"  [heartbeat] fetch {lk['handle']}: {e}")
            continue
        fetched, rejected = validate_source_posts(fetched, now=source_now)
        if rejected:
            print(f"  [heartbeat] rejected {rejected} invalid source timestamps "
                  f"for {lk['handle']}")
        if any(post_key(first) > post_key(second)
               for first, second in zip(fetched, fetched[1:])):
            print(f"  [heartbeat] provider ordering invalid for {lk['handle']} "
                  "— cursor unchanged")
            continue
        # Compound ordering handles multiple posts with the same timestamp. The
        # source guarantees this is a complete oldest prefix or returns [].
        posts = sorted((p for p in fetched if post_key(p) > cursor), key=post_key)
        posts = posts[:MAX_POSTS_PER_SWEEP]
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

        # Per-post transaction: all terminal claims + completion marker in ONE
        # atomic rewrite. No marker exists for a deferred/partially-built post.
        for pi, post in enumerate(posts):
            group = claims_by_post.get(pi, [])
            prepared, rows, deferred = [], [], False
            post_claims = set(known_claims)
            for c in group:
                cls = normalize_class(c.get("call_class", ""), cfg, args.domain)
                key = claim_key({"platform": lk["platform"],
                                 "post_url": post["url"],
                                 "claim": c.get("claim", "")})
                if key in post_claims:
                    continue
                markets = pm.search_markets(str(c.get("market_query", ""))[:80],
                                            closed=False, limit=5)
                if markets is None:  # transient API failure → defer whole post
                    deferred = True
                    break
                claim_id = f"claim-{len(prepared)}"
                prepared.append({"claim_id": claim_id, "claim": c, "class": cls,
                                 "markets": markets})
                post_claims.add(key)
            if deferred:
                n_deferred += 1
                break

            mapping_inputs = [item for item in prepared if item["markets"]]
            mappings = {}
            if mapping_inputs:
                claims_block = "\n".join(
                    f"- claim_id {item['claim_id']} | {item['claim']['claim']}"
                    for item in mapping_inputs)
                mk_block = "\n".join(
                    f"- claim_id {item['claim_id']} | market_id {market['id']} | "
                    f"{market['question']} | criteria: {market['description'][:200]}"
                    for item in mapping_inputs for market in item["markets"])
                response = call_json(
                    "heartbeat",
                    ctx + "\n\n" + prompt_t + "\n\n## CLAIMS\n" + claims_block
                    + "\n\n## CANDIDATE (claim, market) PAIRS\n" + mk_block
                    + "\n\n## REQUEST\nPerform market mapping now. JSON only.",
                    cfg,
                )
                mappings = validated_mappings(response, mapping_inputs)
                if mappings is None:
                    n_deferred += 1
                    break

            for item in prepared:
                c, cls, markets = item["claim"], item["class"], item["markets"]
                sig = build_claim_row(args.domain, lk, post, c, cls)
                chosen, side = mappings.get(item["claim_id"], (None, ""))
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
            committed = rows + [build_completion_row(args.domain, lk, post)]
            write_tsv(signals_path, signals + committed)
            signals.extend(committed)
            for sig in rows:
                known_claims.add(claim_key(sig))
                n_claims += 1
                events.append(f"{lk['handle']}: {sig['claim'][:90]} → {sig['status']}")
                if sig["status"] == "pending_judge":
                    n_pending += 1
                elif sig["status"] == "tracked_probation":
                    n_tracked += 1
                elif sig["status"] == "no_market":
                    n_nomarket += 1

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
