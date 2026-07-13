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
    return {
        "id": str(m.get("id", "")),
        "question": m.get("question", "") or m.get("title", ""),
        "description": (m.get("description") or "")[:1200],
        "end_date": m.get("endDate", "") or m.get("end_date", ""),
        "closed": bool(m.get("closed", False)),
        "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0),
        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
        "yes_price": prices[yes_i] if len(prices) > yes_i else None,
        "yes_token": tokens[yes_i] if len(tokens) > yes_i else "",
        "outcomes": outcomes,
    }


def _keyword_score(query: str, question: str) -> int:
    q_tokens = {w for w in query.lower().split() if len(w) > 2}
    text = question.lower()
    return sum(1 for w in q_tokens if w in text)


def search_markets(query: str, closed: bool, limit: int = 8) -> list[dict]:
    """Search Gamma. Tries /public-search first, falls back to listing+filtering."""
    results: list[dict] = []
    try:
        url = f"{GAMMA}/public-search?q={urllib.parse.quote(query)}&limit_per_type=20"
        data = _get_json(url)
        for ev in (data.get("events") or []):
            for m in (ev.get("markets") or []):
                results.append(norm_market(m))
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] public-search failed ({e}); falling back to /markets")
    if not results:
        try:
            url = (f"{GAMMA}/markets?closed={'true' if closed else 'false'}"
                   f"&limit=300&order=volumeNum&ascending=false")
            for m in _get_json(url):
                results.append(norm_market(m))
        except Exception as e:  # noqa: BLE001
            print(f"  [polymarket] /markets failed: {e}")
            return []
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


def price_at(token_id: str, unix_ts: int, window_days: int = 4) -> float | None:
    """Historical YES-token price nearest to (and preferably before) unix_ts."""
    if not token_id:
        return None
    day = 86400
    url = (f"{CLOB}/prices-history?market={urllib.parse.quote(token_id)}"
           f"&startTs={unix_ts - window_days * day}&endTs={unix_ts + day}&fidelity=60")
    try:
        hist = (_get_json(url) or {}).get("history") or []
    except Exception as e:  # noqa: BLE001
        print(f"  [polymarket] prices-history {token_id[:16]}…: {e}")
        return None
    if not hist:
        return None
    before = [h for h in hist if h.get("t", 0) <= unix_ts]
    pick = before[-1] if before else hist[0]
    try:
        return float(pick["p"])
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
