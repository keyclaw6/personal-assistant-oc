#!/usr/bin/env python3
"""Polymarket read-only client (Gamma + CLOB public APIs, no auth).

PAPER ONLY: there is deliberately no order/trading code in this file or anywhere
in Delphi (PROGRAM.md §0.1). Never invent a price: on endpoint failure return
None/[] and let callers skip (§6).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def _get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "delphi-paper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _maybe_list(v):
    """Gamma embeds JSON arrays as strings in several fields."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []
    return v or []


def norm_market(m: dict) -> dict:
    outcomes = [str(o) for o in _maybe_list(m.get("outcomes"))]
    prices = [float(p) for p in _maybe_list(m.get("outcomePrices")) or []]
    tokens = [str(t) for t in _maybe_list(m.get("clobTokenIds"))]
    yes_i = 0
    for i, o in enumerate(outcomes):
        if o.strip().lower() == "yes":
            yes_i = i
            break
    no_i = 1 - yes_i if len(tokens) > 1 else None
    event_id = ""
    evs = m.get("events")
    if isinstance(evs, list) and evs and isinstance(evs[0], dict):
        event_id = str(evs[0].get("id", ""))
    return {
        "id": str(m.get("id", "")),
        "event_id": event_id,
        "question": m.get("question", "") or m.get("title", ""),
        "description": (m.get("description") or "")[:1200],
        "end_date": m.get("endDate", "") or m.get("end_date", ""),
        "closed": bool(m.get("closed", False)),
        "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0),
        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
        "yes_price": prices[yes_i] if len(prices) > yes_i else None,
        "yes_token": tokens[yes_i] if len(tokens) > yes_i else "",
        "no_token": tokens[no_i] if no_i is not None and len(tokens) > no_i else "",
        "outcomes": outcomes,
    }


def _keyword_score(query: str, question: str) -> int:
    q_tokens = {w for w in query.lower().split() if len(w) > 2}
    text = question.lower()
    return sum(1 for w in q_tokens if w in text)


def search_markets(query: str, closed: bool, limit: int = 8) -> list[dict] | None:
    """Search Gamma. Tries /public-search first, falls back to listing+filtering.

    Returns None on API FAILURE (transient — callers must treat as retryable,
    F6) vs [] for a genuine no-match (permanent no_market is then honest).
    """
    results: list[dict] = []
    failed = 0
    try:
        url = f"{GAMMA}/public-search?q={urllib.parse.quote(query)}&limit_per_type=20"
        data = _get_json(url)
        for ev in (data.get("events") or []):
            for m in (ev.get("markets") or []):
                nm = norm_market(m)
                if not nm["event_id"]:
                    nm["event_id"] = str(ev.get("id", ""))
                results.append(nm)
    except Exception as e:  # noqa: BLE001
        failed += 1
        print(f"  [polymarket] public-search failed ({e}); falling back to /markets")
    if not results:
        try:
            url = (f"{GAMMA}/markets?closed={'true' if closed else 'false'}"
                   f"&limit=300&order=volumeNum&ascending=false")
            for m in _get_json(url):
                results.append(norm_market(m))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [polymarket] /markets failed: {e}")
    if not results and failed == 2:
        return None  # both endpoints down — transient, retry later
    results = [r for r in results if r["closed"] == closed]
    scored = [(_keyword_score(query, r["question"]), r) for r in results]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (x[0], x[1]["volume"]), reverse=True)
    return [r for _, r in scored[:limit]]


def get_market(market_id: str) -> dict | None:
    try:
        data = _get_json(f"{GAMMA}/markets/{urllib.parse.quote(str(market_id))}")
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] get_market {market_id}: {e}")
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    return norm_market(data) if data else None


def midpoint(token_id: str) -> float | None:
    try:
        data = _get_json(f"{CLOB}/midpoint?token_id={urllib.parse.quote(token_id)}")
        return float(data.get("mid"))
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] midpoint {token_id[:16]}…: {e}")
        return None


def _book_price(token_id: str, order_side: str) -> float | None:
    """CLOB /price. NOTE the semantics (live-verified 2026-07-13): `side`
    refers to the ORDERS in the book — side=sell returns the lowest SELL
    order (the ask you pay to buy), side=buy the highest BUY order (the bid
    you receive selling)."""
    if not token_id:
        return None
    try:
        data = _get_json(f"{CLOB}/price?token_id={urllib.parse.quote(token_id)}"
                         f"&side={urllib.parse.quote(order_side)}")
        p = float(data.get("price"))
        return p if 0.0 < p < 1.0 else None
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] price {order_side} {token_id[:16]}…: {e}")
        return None


def best_ask(token_id: str) -> float | None:
    """EXECUTABLE price to BUY this token now (round-2 F1: fills come from
    this, never from midpoints)."""
    return _book_price(token_id, "sell")


def best_bid(token_id: str) -> float | None:
    """Executable price to SELL this token now."""
    return _book_price(token_id, "buy")


def price_at(token_id: str, unix_ts: int, max_stale_hours: int = 48) -> float | None:
    """YES-token price observed AT OR BEFORE unix_ts, no staler than
    max_stale_hours. Returns None otherwise.

    F1: never returns a post-event observation (look-ahead — the leak may
    already have repriced the market) and never an arbitrarily stale one
    (the market must demonstrably have been trading near post time).
    """
    if not token_id or not unix_ts:
        return None
    start = unix_ts - max_stale_hours * 3600
    url = (f"{CLOB}/prices-history?market={urllib.parse.quote(token_id)}"
           f"&startTs={start}&endTs={unix_ts}&fidelity=60")
    try:
        hist = (_get_json(url) or {}).get("history") or []
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] prices-history {token_id[:16]}…: {e}")
        return None
    before = [h for h in hist if start <= h.get("t", 0) <= unix_ts]
    if not before:
        return None
    try:
        return float(before[-1]["p"])
    except (KeyError, TypeError, ValueError):
        return None


def winning_side(market: dict) -> str | None:
    """For a closed market: YES / NO from final outcome prices, else None."""
    if not market or not market.get("closed"):
        return None
    p = market.get("yes_price")
    if p is None:
        return None
    if p >= 0.95:
        return "YES"
    if p <= 0.05:
        return "NO"
    return None  # ambiguous / not yet settled — never guess (§6)
