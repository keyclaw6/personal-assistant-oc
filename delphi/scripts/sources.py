#!/usr/bin/env python3
"""Post fetchers. Returns normalized posts: {ts, url, text}, newest first.

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

from lib import load_config, unix_to_iso


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

def reddit_user_posts(handle: str, limit: int = 50, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    ua = cfg["sources"]["reddit_user_agent"]
    url = f"https://www.reddit.com/user/{urllib.parse.quote(handle)}/submitted.json?limit={limit}&raw_json=1"
    try:
        data = _get_json(url, {"User-Agent": ua})
    except Exception as e:  # noqa: BLE001 — deliberate boundary
        _warn(f"reddit user {handle}: {e}")
        return []
    return _reddit_children(data)


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
            "ts": unix_to_iso(d.get("created_utc", 0)),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
            "text": text[:1500],
        })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return posts


# ---------- X / Twitter ----------

def x_posts(handle: str, since_iso: str | None = None, limit: int = 25,
            cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    backend = cfg["sources"].get("x_backend", "exa")
    if backend == "x_api" and os.environ.get(cfg["sources"]["x_bearer_env"]):
        return _x_api(handle, since_iso, limit, cfg)
    if os.environ.get(cfg["sources"]["exa_api_key_env"]):
        return _x_exa(handle, since_iso, limit, cfg)
    if os.environ.get(cfg["sources"]["x_bearer_env"]):
        return _x_api(handle, since_iso, limit, cfg)
    _warn(f"x/{handle}: no EXA_API_KEY or X_BEARER_TOKEN set — X coverage disabled")
    return []


def _x_exa(handle: str, since_iso: str | None, limit: int, cfg: dict) -> list[dict]:
    key = os.environ[cfg["sources"]["exa_api_key_env"]]
    body = {
        "query": f"from:{handle}",
        "category": "tweet",
        "numResults": min(limit, 100),
        "includeDomains": ["x.com", "twitter.com"],
        "contents": {"text": True},
        "livecrawl": "always",
    }
    if since_iso:
        body["startPublishedDate"] = since_iso
    try:
        data = _post_json("https://api.exa.ai/search", body, {"x-api-key": key})
    except Exception as e:  # noqa: BLE001
        _warn(f"exa x/{handle}: {e}")
        return []
    posts = []
    for r in data.get("results", []):
        posts.append({
            "ts": (r.get("publishedDate") or "")[:20].rstrip(".") or "",
            "url": r.get("url", ""),
            "text": ((r.get("title") or "") + "\n" + (r.get("text") or "")).strip()[:1500],
        })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return posts


def _x_api(handle: str, since_iso: str | None, limit: int, cfg: dict) -> list[dict]:
    token = os.environ[cfg["sources"]["x_bearer_env"]]
    hdr = {"Authorization": f"Bearer {token}"}
    try:
        u = _get_json(f"https://api.x.com/2/users/by/username/{urllib.parse.quote(handle)}", hdr)
        uid = u["data"]["id"]
        q = f"max_results={min(max(limit, 5), 100)}&tweet.fields=created_at"
        if since_iso:
            q += f"&start_time={urllib.parse.quote(since_iso)}"
        tw = _get_json(f"https://api.x.com/2/users/{uid}/tweets?{q}", hdr)
    except Exception as e:  # noqa: BLE001
        _warn(f"x api {handle}: {e}")
        return []
    posts = []
    for t in tw.get("data", []) or []:
        posts.append({
            "ts": (t.get("created_at") or "")[:20].rstrip("."),
            "url": f"https://x.com/{handle}/status/{t.get('id')}",
            "text": (t.get("text") or "")[:1500],
        })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return posts


# ---------- dispatch ----------

def fetch_posts(platform: str, handle: str, since_iso: str | None = None,
                limit: int = 25, cfg: dict | None = None) -> list[dict]:
    if platform == "reddit":
        posts = reddit_user_posts(handle, limit, cfg)
        if since_iso:
            posts = [p for p in posts if p["ts"] > since_iso]
        return posts
    if platform == "x":
        return x_posts(handle, since_iso, limit, cfg)
    _warn(f"unknown platform {platform}")
    return []
