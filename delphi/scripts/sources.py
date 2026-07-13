#!/usr/bin/env python3
"""Post fetchers. Returns normalized posts: {id, ts, url, text}.

- Reddit: public JSON endpoints, no auth (custom User-Agent per Reddit etiquette).
- X/Twitter: pluggable backend — 'exa' (EXA_API_KEY) or 'x_api' (X_BEARER_TOKEN).
  If neither key is present, X fetches return [] with a warning; the ledger will
  show the gap (PROGRAM.md §6 — measure, then amend).

Fetchers never raise to callers: on failure they warn and return [].
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from lib import load_config, unix_to_iso


MAX_PAGES = 20
EXA_PAGE_SIZE = 100
EXA_MAX_REQUESTS = 64
EXA_BOUNDARY_OVERLAP = timedelta(microseconds=1)


def _get_json(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _post_json(url: str, body: dict, headers: dict, timeout: int = 60):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _warn(msg: str):
    print(f"  [sources] WARN: {msg}")


# ---------- Reddit ----------

def reddit_user_posts(handle: str, limit: int = 50, cfg: dict | None = None,
                      start_iso: str | None = None,
                      oldest_first: bool = False,
                      after_id: str = "") -> list[dict]:
    """Paginates with Reddit's ``after`` cursor.

    The normal path stops at ``limit``. The oldest-first cursor path continues
    through ``start_iso`` before selecting its bounded prefix.
    """
    cfg = cfg or load_config()
    ua = cfg["sources"]["reddit_user_agent"]
    posts: list[dict] = []
    after = ""
    complete = False
    for _ in range(MAX_PAGES):
        url = (f"https://www.reddit.com/user/{urllib.parse.quote(handle)}/submitted.json"
               f"?limit=100&raw_json=1" + (f"&after={after}" if after else ""))
        try:
            data = _get_json(url, {"User-Agent": ua})
        except Exception as e:  # noqa: BLE001 — deliberate boundary
            _warn(f"reddit user {handle}: {e}")
            break
        page = _reddit_children(data)
        posts += page
        after = (data or {}).get("data", {}).get("after") or ""
        if not page or not after:
            complete = True
            break
        if start_iso and page[-1]["ts"] and page[-1]["ts"] < start_iso:
            complete = True
            break
        if not oldest_first and len(posts) >= limit:
            complete = True
            break
    if oldest_first and not complete:
        _warn(f"reddit user {handle}: pagination exceeded {MAX_PAGES} pages; "
              "refusing an incomplete oldest-first prefix")
        return []
    if start_iso:
        posts = [p for p in posts if p["ts"] >= start_iso]
    posts = _unique_posts(posts)
    if oldest_first and start_iso:
        posts = [p for p in posts if _post_key(p) > (start_iso, after_id)]
    posts.sort(key=_post_key, reverse=not oldest_first)
    return posts[:limit]


def reddit_sub_new(sub: str, limit: int = 25, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    ua = cfg["sources"]["reddit_user_agent"]
    url = f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/new.json?limit={limit}&raw_json=1"
    try:
        data = _get_json(url, {"User-Agent": ua})
    except Exception as e:  # noqa: BLE001
        _warn(f"reddit r/{sub}: {e}")
        return []
    return _reddit_children(data)


def _reddit_children(data) -> list[dict]:
    posts = []
    for child in (data or {}).get("data", {}).get("children", []):
        d = child.get("data", {})
        text = (d.get("title", "") + "\n" + d.get("selftext", "")).strip()
        posts.append({
            "id": str(d.get("id") or d.get("permalink") or ""),
            "ts": unix_to_iso(d.get("created_utc", 0)),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
            "text": text[:1500],
        })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return posts


# ---------- X / Twitter ----------

def x_posts(handle: str, since_iso: str | None = None, limit: int = 25,
            cfg: dict | None = None, end_iso: str | None = None,
            oldest_first: bool = False, after_id: str = "") -> list[dict]:
    cfg = cfg or load_config()
    backend = cfg["sources"].get("x_backend", "exa")
    if backend == "x_api" and os.environ.get(cfg["sources"]["x_bearer_env"]):
        return _x_api(handle, since_iso, limit, cfg, oldest_first, after_id)
    if os.environ.get(cfg["sources"]["exa_api_key_env"]):
        return _x_exa(handle, since_iso, limit, cfg, end_iso, oldest_first,
                      after_id)
    if os.environ.get(cfg["sources"]["x_bearer_env"]):
        return _x_api(handle, since_iso, limit, cfg, oldest_first, after_id)
    _warn(f"x/{handle}: no EXA_API_KEY or X_BEARER_TOKEN set — X coverage disabled")
    return []


def _exa_query(handle: str, start_iso: str | None, end_iso: str | None,
               cfg: dict, limit: int) -> list[dict] | None:
    key = os.environ[cfg["sources"]["exa_api_key_env"]]
    body = {
        "query": f"from:{handle}",
        "category": "tweet",
        "numResults": min(max(limit, 10), EXA_PAGE_SIZE),
        "includeDomains": ["x.com", "twitter.com"],
        "contents": {"text": True},
        "livecrawl": "always",
    }
    if start_iso:
        body["startPublishedDate"] = start_iso
    if end_iso:
        body["endPublishedDate"] = end_iso
    try:
        data = _post_json("https://api.exa.ai/search", body, {"x-api-key": key})
    except Exception as e:  # noqa: BLE001
        _warn(f"exa x/{handle}: {e}")
        return None
    posts = []
    for r in data.get("results", []):
        url = r.get("url", "")
        posts.append({
            "id": str(_id_from_url(url) or r.get("id") or url),
            "ts": _normalize_iso(r.get("publishedDate") or ""),
            "url": url,
            "text": ((r.get("title") or "") + "\n" + (r.get("text") or "")).strip()[:1500],
        })
    return posts


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _normalize_iso(value: str) -> str:
    if not value:
        return ""
    try:
        return _parse_iso(value).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ""


def _x_exa_oldest(handle: str, since_iso: str, end_iso: str, limit: int,
                  cfg: dict, after_id: str = "") -> list[dict]:
    """Find a complete oldest prefix despite Exa's cursorless 100-result cap.

    Saturated windows are bisected by date. A saturated one-second window or
    exhausted request budget fails closed so heartbeat cannot skip unseen posts.
    """
    requests = 0
    failed = False

    def collect(start: datetime, end: datetime, need: int) -> list[dict]:
        nonlocal requests, failed
        if failed or need <= 0:
            return []
        if requests >= EXA_MAX_REQUESTS:
            failed = True
            return []
        requests += 1
        page = _exa_query(handle, start.isoformat().replace("+00:00", "Z"),
                          end.isoformat().replace("+00:00", "Z"), cfg,
                          EXA_PAGE_SIZE)
        if page is None:
            failed = True
            return []
        saturated = len(page) >= EXA_PAGE_SIZE
        page = _unique_posts(page)
        page = [post for post in page
                if _post_key(post) > (since_iso, after_id)]
        if not saturated:
            page.sort(key=_post_key)
            return page[:need]
        if end - start <= timedelta(seconds=1):
            failed = True
            return []
        middle = start + (end - start) / 2
        # Exa's bounds are strict (> start, < end). Overlap both halves by one
        # microsecond so an exact-midpoint post is present, then dedupe by key.
        older = collect(start, middle + EXA_BOUNDARY_OVERLAP, need)
        if failed or len(older) >= need:
            return older[:need]
        newer = collect(middle - EXA_BOUNDARY_OVERLAP, end,
                        need - len(older))
        return _unique_posts(older + newer)

    # Exa excludes the bounds themselves. Widen once so posts exactly at the
    # timestamp watermark remain available for the stable-id half of the cursor.
    query_start = _parse_iso(since_iso) - EXA_BOUNDARY_OVERLAP
    query_end = _parse_iso(end_iso) + EXA_BOUNDARY_OVERLAP
    posts = collect(query_start, query_end, limit)
    if failed:
        _warn(f"exa x/{handle}: could not prove a complete oldest-first prefix "
              f"within {EXA_MAX_REQUESTS} date-slice requests; cursor unchanged")
        return []
    posts.sort(key=_post_key)
    return posts[:limit]


def _x_exa(handle: str, since_iso: str | None, limit: int, cfg: dict,
           end_iso: str | None = None, oldest_first: bool = False,
           after_id: str = "") -> list[dict]:
    if oldest_first:
        start = since_iso or "1970-01-01T00:00:00Z"
        end = end_iso or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return _x_exa_oldest(handle, start, end, limit, cfg, after_id)
    posts = _exa_query(handle, since_iso, end_iso, cfg, limit) or []
    posts = _unique_posts(posts)
    posts.sort(key=_post_key, reverse=True)
    return posts[:limit]


def _x_api(handle: str, since_iso: str | None, limit: int, cfg: dict,
           oldest_first: bool = False, after_id: str = "") -> list[dict]:
    token = os.environ[cfg["sources"]["x_bearer_env"]]
    hdr = {"Authorization": f"Bearer {token}"}
    try:
        u = _get_json(f"https://api.x.com/2/users/by/username/{urllib.parse.quote(handle)}", hdr)
        uid = u["data"]["id"]
    except Exception as e:  # noqa: BLE001
        _warn(f"x api {handle}: {e}")
        return []
    posts = []
    next_token = ""
    complete = False
    for _ in range(MAX_PAGES if oldest_first else 1):
        page_size = 100 if oldest_first else min(max(limit, 5), 100)
        q = f"max_results={page_size}&tweet.fields=created_at"
        if since_iso:
            q += f"&start_time={urllib.parse.quote(since_iso)}"
        if next_token:
            q += f"&pagination_token={urllib.parse.quote(next_token)}"
        try:
            tw = _get_json(f"https://api.x.com/2/users/{uid}/tweets?{q}", hdr)
        except Exception as e:  # noqa: BLE001
            _warn(f"x api {handle}: {e}")
            return []
        for t in tw.get("data", []) or []:
            tid = str(t.get("id") or "")
            posts.append({
                "id": tid,
                "ts": _normalize_iso(t.get("created_at") or ""),
                "url": f"https://x.com/{handle}/status/{tid}",
                "text": (t.get("text") or "")[:1500],
            })
        next_token = str((tw.get("meta") or {}).get("next_token") or "")
        if not next_token:
            complete = True
            break
    if oldest_first and not complete:
        _warn(f"x api {handle}: pagination exceeded {MAX_PAGES} pages; "
              "refusing an incomplete oldest-first prefix")
        return []
    posts = _unique_posts(posts)
    if oldest_first and since_iso:
        posts = [p for p in posts if _post_key(p) > (since_iso, after_id)]
    posts.sort(key=_post_key, reverse=not oldest_first)
    return posts[:limit]


def _id_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else ""


def _post_key(post: dict) -> tuple[str, str]:
    return str(post.get("ts") or ""), str(post.get("id") or post.get("url") or "")


def _unique_posts(posts: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str], dict] = {}
    for post in posts:
        key = _post_key(post)
        if key[0] and key[1]:
            by_key[key] = post
    return list(by_key.values())


# ---------- dispatch ----------

def fetch_posts(platform: str, handle: str, since_iso: str | None = None,
                limit: int = 25, cfg: dict | None = None,
                end_iso: str | None = None,
                oldest_first: bool = False, after_id: str = "") -> list[dict]:
    """Normalized posts ordered as requested.

    ``oldest_first`` is for cursor consumers: it returns only a proven-complete
    oldest prefix, or ``[]`` when a provider pagination cap prevents that.
    ``end_iso`` enables the explorer's deepen mode to fetch older slices.
    """
    if platform == "reddit":
        posts = reddit_user_posts(handle, limit, cfg, start_iso=since_iso,
                                  oldest_first=oldest_first, after_id=after_id)
        if end_iso:
            posts = [p for p in posts if p["ts"] <= end_iso]
        return posts
    if platform == "x":
        return x_posts(handle, since_iso, limit, cfg, end_iso, oldest_first,
                       after_id)
    _warn(f"unknown platform {platform}")
    return []
