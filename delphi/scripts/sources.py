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
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from lib import load_config
from source_timestamps import (SourceTimestampError, utc_now,
                               validate_source_posts,
                               validate_source_timestamp)


MAX_PAGES = 20
EXA_PAGE_SIZE = 100
EXA_MAX_REQUESTS = 64
EXA_BOUNDARY_OVERLAP = timedelta(microseconds=1)
X_API_MAX_ACCESSIBLE_POSTS = 3200
X_RESERVED_ROUTES = frozenset({
    # Static platform surfaces only; do not grow this from fetched content.
    "about", "account", "ads", "business", "communities", "compose",
    "developers", "download", "explore", "hashtag", "help", "home", "i",
    "intent", "jobs", "login", "logout", "messages", "notifications",
    "oauth", "premium", "privacy", "search", "settings", "share", "signup",
    "tos", "web",
})


@dataclass
class HistoryPage:
    """One backward Explorer page with an explicit completeness contract.

    ``posts`` is a newest-first, contiguous provider prefix older than the
    requested compound boundary.  ``exhausted`` is true only when the provider
    explicitly ended the configured window.  A gap or retryable error makes
    the posts observational only: Explorer must not advance its boundary.
    """

    posts: list[dict]
    exhausted: bool
    provider: str
    coverage_gap: str = ""
    retryable_error: str = ""
    prefix_complete: bool = True


@dataclass
class HistoryUpdates:
    """Oldest-first posts newer than, or unseen at, a timestamp frontier."""

    posts: list[dict]
    caught_up: bool
    provider: str
    coverage_gap: str = ""
    retryable_error: str = ""


@dataclass
class DiscoveryPage:
    """One bounded page from a community source used to find originators."""

    items: list[dict]
    next_cursor: str
    failed: bool = False


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
    previous_oldest_ts = ""
    reference = utc_now()
    for _ in range(MAX_PAGES):
        url = (f"https://www.reddit.com/user/{urllib.parse.quote(handle)}/submitted.json"
               f"?limit=100&raw_json=1" + (f"&after={after}" if after else ""))
        try:
            data = _get_json(url, {"User-Agent": ua})
        except Exception as e:  # noqa: BLE001 — deliberate boundary
            _warn(f"reddit user {handle}: {e}")
            break
        page, rejected = validate_source_posts(
            _reddit_children(data), now=reference)
        if rejected:
            _warn(f"reddit user {handle}: rejected {rejected} invalid source timestamps")
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            _warn(f"reddit user {handle}: {order_issue}; cursor unchanged")
            return []
        if page:
            previous_oldest_ts = page[-1]["ts"]
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


_DISCOVERY_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_REDDIT_POST_ID_RE = re.compile(r"[a-z0-9]{1,32}")
_DISCOVERY_RAW_TEXT_FIELD_CHARS = 1500


def _has_unsafe_control(value: str) -> bool:
    return any(unicodedata.category(char).startswith("C")
               and char not in "\n\r\t" for char in value)


def _safe_web_url(value) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or _has_unsafe_control(value)):
        return ""
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return ""
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or port is not None):
        return ""
    return value


def _decoded_route_segments(path: str) -> list[str] | None:
    """Decode without collapsing malformed empty or embedded separators."""
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        return None
    raw_segments = path.split("/")[1:]
    if raw_segments and raw_segments[-1] == "":
        raw_segments.pop()
    if not raw_segments or any(not segment for segment in raw_segments):
        return None

    decoded = []
    for raw in raw_segments:
        value = raw
        for _ in range(8):
            next_value = urllib.parse.unquote(value)
            if next_value == value:
                break
            value = next_value
        else:
            return None
        if (not value or "/" in value or "\\" in value
                or _has_unsafe_control(value)):
            return None
        decoded.append(value)
    return decoded


def _linked_source_identity(url: str) -> str:
    safe = _safe_web_url(url)
    if not safe:
        return ""
    parsed = urllib.parse.urlsplit(safe)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    parts = _decoded_route_segments(parsed.path)
    if parts is None:
        return "x.com" if host in ("x.com", "twitter.com") else host
    if host in ("x.com", "twitter.com"):
        if not parts:
            return "x.com"
        handle = parts[0]
        valid_route = (len(parts) == 1
                       or (len(parts) == 3
                           and parts[1].casefold() == "status"
                           and parts[2].isdigit()))
        if (valid_route and handle.casefold() not in X_RESERVED_ROUTES
                and re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle)):
            return f"x/@{handle}"
        return "x.com"
    if host in ("reddit.com", "old.reddit.com") and len(parts) == 2 \
            and parts[0].lower() in ("u", "user") \
            and _DISCOVERY_NAME_RE.fullmatch(parts[1]):
        return f"reddit/u/{parts[1]}"
    return host


def _decoded_permalink_segments(permalink: str) -> list[str] | None:
    parsed = urllib.parse.urlsplit(permalink)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or not parsed.path.startswith("/") or parsed.path.startswith("//")):
        return None
    decoded = _decoded_route_segments(parsed.path)
    if not decoded:
        return None
    for value in decoded:
        if (value in (".", "..") or "/" in value or "\\" in value
                or _has_unsafe_control(value)
                or any(char.isspace() for char in value)
                or re.search(r"%[0-9A-Fa-f]{2}", value)):
            return None
    return decoded


def _canonical_reddit_post_url(permalink, stable_id: str,
                               expected_sub: str) -> str:
    if (not isinstance(permalink, str) or permalink != permalink.strip()
            or _has_unsafe_control(permalink)):
        return ""
    segments = _decoded_permalink_segments(permalink)
    if segments is None or len(segments) not in (4, 5):
        return ""
    marker, subreddit, comments, permalink_id = segments[:4]
    if (marker.casefold() != "r" or comments.casefold() != "comments"
            or subreddit.casefold() != expected_sub.casefold()
            or not _DISCOVERY_NAME_RE.fullmatch(subreddit)
            or permalink_id != stable_id
            or not _REDDIT_POST_ID_RE.fullmatch(permalink_id)):
        return ""
    return (f"https://www.reddit.com/r/{subreddit.casefold()}"
            f"/comments/{stable_id}/")


def _reddit_discovery_item(data: dict, text_chars: int,
                           expected_sub: str) -> dict | None:
    stable_id = str(data.get("id") or "")
    permalink = data.get("permalink")
    canonical_url = _canonical_reddit_post_url(permalink, stable_id,
                                                expected_sub)
    if not _REDDIT_POST_ID_RE.fullmatch(stable_id) or not canonical_url:
        return None

    title = data.get("title") or ""
    body = data.get("selftext") or ""
    if not isinstance(title, str) or not isinstance(body, str):
        return None
    raw_limit = min(text_chars, _DISCOVERY_RAW_TEXT_FIELD_CHARS)
    title = title[:raw_limit]
    body = body[:raw_limit]
    if _has_unsafe_control(title) or _has_unsafe_control(body):
        return None
    text = (title.strip() + "\n" + body.strip()).strip()
    if not text:
        return None

    author = data.get("author") or ""
    if not isinstance(author, str) or not _DISCOVERY_NAME_RE.fullmatch(author):
        return None

    outbound = data.get("url_overridden_by_dest")
    if outbound is None:
        outbound = data.get("url") or ""
    if outbound and not _safe_web_url(outbound):
        return None

    return {
        "canonical_id": f"reddit:{stable_id}",
        "canonical_url": canonical_url,
        "text": text[:text_chars],
        "publisher": f"reddit/u/{author}",
        "linked_source": _linked_source_identity(outbound) if outbound else "",
    }


def reddit_sub_page(sub: str, after: str, limit: int,
                    cfg: dict | None = None) -> DiscoveryPage:
    """Return one cursor page with safe, originator-relevant evidence.

    Invalid siblings are dropped independently. Provider failure is explicit so
    Explorer can preserve evidence already collected from every other source.
    """
    cfg = cfg or load_config()
    if (not _DISCOVERY_NAME_RE.fullmatch(sub)
            or type(limit) is not int or not 1 <= limit <= 100
            or after and (not isinstance(after, str) or after != after.strip()
                          or any(char.isspace() for char in after)
                          or _has_unsafe_control(after))):
        return DiscoveryPage([], "", failed=True)
    ua = cfg["sources"]["reddit_user_agent"]
    url = (f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/new.json"
           f"?limit={limit}&raw_json=1"
           + (f"&after={urllib.parse.quote(after)}" if after else ""))
    try:
        data = _get_json(url, {"User-Agent": ua})
    except Exception as exc:  # noqa: BLE001 - deliberate provider boundary
        _warn(f"reddit r/{sub}: {exc}")
        return DiscoveryPage([], "", failed=True)

    text_chars = cfg["sources"].get("discovery_evidence_chars", 800)
    payload = data.get("data") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        return DiscoveryPage([], "", failed=True)
    children = payload.get("children", [])
    if not isinstance(children, list):
        return DiscoveryPage([], "", failed=True)
    items = []
    for child in children[:limit]:
        raw = child.get("data") if isinstance(child, dict) else None
        item = (_reddit_discovery_item(raw, text_chars, sub)
                if isinstance(raw, dict) else None)
        if item is not None:
            items.append(item)

    next_cursor = payload.get("after") or ""
    if (not isinstance(next_cursor, str) or next_cursor != next_cursor.strip()
            or any(char.isspace() for char in next_cursor)
            or _has_unsafe_control(next_cursor)):
        return DiscoveryPage(items, "", failed=True)
    return DiscoveryPage(items, next_cursor)


def _reddit_children(data) -> list[dict]:
    posts = []
    for child in (data or {}).get("data", {}).get("children", []):
        d = child.get("data", {})
        text = (d.get("title", "") + "\n" + d.get("selftext", "")).strip()
        posts.append({
            "id": str(d.get("id") or d.get("permalink") or ""),
            "ts": _normalize_unix(d.get("created_utc")),
            "url": "https://www.reddit.com" + d.get("permalink", ""),
            "text": text[:1500],
        })
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
        "contents": {"text": True, "maxAgeHours": 0},
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
    try:
        return validate_source_timestamp(value, normalize_provider=True)
    except SourceTimestampError:
        return ""


def _normalize_unix(value) -> str:
    if value is None or value == "" or isinstance(value, bool):
        return ""
    try:
        parsed = datetime.fromtimestamp(float(value), timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return ""
    return _normalize_iso(parsed.isoformat())


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
    previous_oldest_ts = ""
    reference = utc_now()
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
        raw = []
        for t in tw.get("data", []) or []:
            tid = str(t.get("id") or "")
            raw.append({
                "id": tid,
                "ts": _normalize_iso(t.get("created_at") or ""),
                "url": f"https://x.com/{handle}/status/{tid}",
                "text": (t.get("text") or "")[:1500],
            })
        page, rejected = validate_source_posts(raw, now=reference)
        if rejected:
            _warn(f"x api {handle}: rejected {rejected} invalid source timestamps")
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            _warn(f"x api {handle}: {order_issue}; cursor unchanged")
            return []
        if page:
            previous_oldest_ts = page[-1]["ts"]
        posts.extend(page)
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


def post_key(post: dict) -> tuple[str, str]:
    """Stable total order used by both live and historical cursors."""
    return str(post.get("ts") or ""), str(post.get("id") or post.get("url") or "")


_post_key = post_key


def _reverse_chronology_issue(
        posts: list[dict], previous_oldest_ts: str = "") -> str:
    """Return evidence that a newest-first provider prefix regressed."""
    timestamps = [post["ts"] for post in posts]
    if any(newer < older for newer, older in zip(timestamps, timestamps[1:])):
        return "provider page violated reverse chronological ordering"
    if timestamps and previous_oldest_ts and timestamps[0] > previous_oldest_ts:
        return "provider pagination violated chronological page bounds"
    return ""


def provider_id_key(provider: str, stable_id: str) -> tuple[int, int, str]:
    """Provider-native ID order with a deterministic nonnumeric fallback."""
    value = str(stable_id or "")
    try:
        if provider == "reddit":
            return 0, int(value, 36), ""
        if provider == "x_api":
            return 0, int(value, 10), ""
    except ValueError:
        pass
    # The frontier stores every seen ID at its newest timestamp, so fallback
    # ordering is used only for deterministic page selection, never as proof
    # that an unlisted same-timestamp ID was already inspected.
    return 1, len(value), value


def history_post_key(provider: str, post: dict):
    return str(post.get("ts") or ""), provider_id_key(provider, post.get("id", ""))


def history_boundary_key(provider: str, timestamp: str, stable_id: str):
    return str(timestamp or ""), provider_id_key(provider, stable_id)


def _unique_posts(posts: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str], dict] = {}
    for post in posts:
        key = _post_key(post)
        if key[0] and key[1]:
            by_key[key] = post
    return list(by_key.values())


# ---------- Explorer backward-history contract ----------

def history_provider(platform: str, cfg: dict) -> str:
    """Return the concrete provider whose durable boundary must be isolated."""
    if platform == "reddit":
        return "reddit"
    if platform != "x":
        return platform
    src = cfg.get("sources") or {}
    backend = src.get("x_backend", "exa")
    bearer_name = src.get("x_bearer_env", "")
    exa_name = src.get("exa_api_key_env", "")
    has_bearer = bool(bearer_name and os.environ.get(bearer_name))
    has_exa = bool(exa_name and os.environ.get(exa_name))
    if backend == "x_api" and has_bearer:
        return "x_api"
    if has_exa:
        return "exa"
    if has_bearer:
        return "x_api"
    return backend if backend in ("exa", "x_api") else "x"


def _history_posts(posts: list[dict], provider: str) -> tuple[list[dict], str]:
    """Validate a newest-first provider page before any local reordering."""
    valid, rejected = validate_source_posts(posts)
    if rejected:
        return [], "provider returned an invalid source timestamp"
    for post in valid:
        stable_id = str(post.get("id") or "")
        if not stable_id:
            return [], "provider returned a post without timestamp and stable ID"
    order_issue = _reverse_chronology_issue(valid)
    if order_issue:
        return [], order_issue
    unique = _unique_posts(valid)
    unique.sort(key=lambda post: history_post_key(provider, post), reverse=True)
    return unique, ""


def _reddit_history_page(handle: str, start_iso: str,
                         before: tuple[str, str] | None, limit: int,
                         cfg: dict) -> HistoryPage:
    """Read a complete newest prefix using Reddit's ordered ``after`` cursor."""
    ua = cfg["sources"]["reddit_user_agent"]
    collected: list[dict] = []
    before_key = (history_boundary_key("reddit", *before) if before else None)
    after = ""
    reached_window_start = False
    crossed_window_start = False
    previous_oldest_ts = ""
    for _ in range(MAX_PAGES):
        url = (f"https://www.reddit.com/user/{urllib.parse.quote(handle)}/submitted.json"
               "?sort=new&t=all&limit=100&raw_json=1"
               + (f"&after={urllib.parse.quote(after)}" if after else ""))
        try:
            data = _get_json(url, {"User-Agent": ua})
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return HistoryPage([], False, "reddit", retryable_error=str(exc))
        page, identity_gap = _history_posts(_reddit_children(data), "reddit")
        if identity_gap:
            return HistoryPage([], False, "reddit", coverage_gap=identity_gap)
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            return HistoryPage([], False, "reddit", coverage_gap=order_issue)
        if page:
            previous_oldest_ts = page[-1]["ts"]
        reached_window_start = (reached_window_start
                                or any(post["ts"] <= start_iso for post in page))
        crossed_window_start = (crossed_window_start
                                or any(post["ts"] < start_iso for post in page))
        eligible = [post for post in page
                    if post["ts"] >= start_iso
                    and (before_key is None
                         or history_post_key("reddit", post) < before_key)]
        collected = _unique_posts(collected + eligible)
        collected.sort(key=lambda post: history_post_key("reddit", post), reverse=True)

        after = str((data or {}).get("data", {}).get("after") or "")
        provider_terminal = not page or not after
        window_complete = (crossed_window_start
                           or (reached_window_start and provider_terminal))
        if len(collected) > limit:
            return HistoryPage(collected[:limit], False, "reddit")
        if len(collected) == limit:
            if window_complete:
                return HistoryPage(collected, True, "reddit")
            if provider_terminal:
                return HistoryPage(
                    collected, False, "reddit",
                    coverage_gap="Reddit listing ended before window_start")
            return HistoryPage(collected, False, "reddit")
        if window_complete:
            return HistoryPage(collected, True, "reddit")
        if provider_terminal:
            return HistoryPage(
                collected, False, "reddit",
                coverage_gap="Reddit listing ended before window_start")

    return HistoryPage(
        collected, False, "reddit",
        coverage_gap=f"Reddit pagination exceeded {MAX_PAGES} pages before a complete prefix")


def _x_api_history_page(handle: str, start_iso: str,
                        before: tuple[str, str] | None, limit: int,
                        cfg: dict) -> HistoryPage:
    """Read a complete newest prefix from X's reverse-chronological timeline."""
    token = os.environ[cfg["sources"]["x_bearer_env"]]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        user = _get_json(
            f"https://api.x.com/2/users/by/username/{urllib.parse.quote(handle)}",
            headers)
        uid = user["data"]["id"]
    except Exception as exc:  # noqa: BLE001 - provider boundary
        return HistoryPage([], False, "x_api", retryable_error=str(exc))

    collected: list[dict] = []
    before_key = (history_boundary_key("x_api", *before) if before else None)
    next_token = ""
    reached_window_start = False
    crossed_window_start = False
    retrieved = 0
    previous_oldest_ts = ""
    max_pages = X_API_MAX_ACCESSIBLE_POSTS // 100
    for _ in range(max_pages):
        params = {
            "max_results": "100",
            "tweet.fields": "created_at",
            # Query with overlap, then enforce the configured bound locally.
            "start_time": (_parse_iso(start_iso) - timedelta(seconds=1))
            .isoformat().replace("+00:00", "Z"),
        }
        if before:
            params["end_time"] = (_parse_iso(before[0]) + timedelta(seconds=1)) \
                .isoformat().replace("+00:00", "Z")
        if next_token:
            params["pagination_token"] = next_token
        try:
            timeline = _get_json(
                f"https://api.x.com/2/users/{uid}/tweets?{urllib.parse.urlencode(params)}",
                headers)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return HistoryPage([], False, "x_api", retryable_error=str(exc))

        raw = []
        for tweet in timeline.get("data", []) or []:
            tid = str(tweet.get("id") or "")
            raw.append({
                "id": tid,
                "ts": _normalize_iso(tweet.get("created_at") or ""),
                "url": f"https://x.com/{handle}/status/{tid}",
                "text": (tweet.get("text") or "")[:1500],
            })
        page, identity_gap = _history_posts(raw, "x_api")
        if identity_gap:
            return HistoryPage([], False, "x_api", coverage_gap=identity_gap)
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            return HistoryPage([], False, "x_api", coverage_gap=order_issue)
        if page:
            previous_oldest_ts = page[-1]["ts"]
        retrieved += len(raw)
        reached_window_start = (reached_window_start
                                or any(post["ts"] <= start_iso for post in page))
        crossed_window_start = (crossed_window_start
                                or any(post["ts"] < start_iso for post in page))
        eligible = [post for post in page
                    if post["ts"] >= start_iso
                    and (before_key is None
                         or history_post_key("x_api", post) < before_key)]
        collected = _unique_posts(collected + eligible)
        collected.sort(key=lambda post: history_post_key("x_api", post), reverse=True)

        next_token = str((timeline.get("meta") or {}).get("next_token") or "")
        provider_terminal = not next_token
        window_complete = (crossed_window_start
                           or (reached_window_start and provider_terminal))
        if len(collected) > limit:
            return HistoryPage(collected[:limit], False, "x_api")
        if len(collected) == limit:
            if window_complete:
                return HistoryPage(collected, True, "x_api")
            if provider_terminal:
                return HistoryPage(
                    collected, False, "x_api",
                    coverage_gap="X API timeline ended before window_start")
            return HistoryPage(collected, False, "x_api")
        if window_complete:
            return HistoryPage(collected, True, "x_api")
        if provider_terminal:
            return HistoryPage(
                collected, False, "x_api",
                coverage_gap="X API timeline ended before window_start")
        if retrieved >= X_API_MAX_ACCESSIBLE_POSTS:
            return HistoryPage(
                collected, False, "x_api",
                coverage_gap=("X API reached its 3,200-post accessible timeline "
                              "limit before window_start"))

    return HistoryPage(
        collected, False, "x_api",
        coverage_gap=("X API reached its 3,200-post accessible timeline limit "
                      "before a complete prefix"))


def _exa_history_page(handle: str, start_iso: str,
                      before: tuple[str, str] | None, limit: int,
                      cfg: dict) -> HistoryPage:
    """Expose Exa observations without pretending search is an archive cursor."""
    end_iso = before[0] if before else None
    raw = _exa_query(handle, start_iso, end_iso, cfg, min(limit, EXA_PAGE_SIZE))
    if raw is None:
        return HistoryPage([], False, "exa",
                           retryable_error="Exa request failed transiently")
    posts, identity_gap = _history_posts(raw, "exa")
    if identity_gap:
        return HistoryPage([], False, "exa", coverage_gap=identity_gap)
    posts = [post for post in posts
             if post["ts"] >= start_iso
             and (before is None
                  or history_post_key("exa", post)
                  < history_boundary_key("exa", *before))]
    return HistoryPage(
        posts[:limit], False, "exa",
        coverage_gap=("Exa search exposes no exhaustive ordering, continuation "
                      "cursor, or total; durable history cannot advance"),
        prefix_complete=False)


def _reddit_history_updates(handle: str, newest_ts: str, seen_ids: set[str],
                            limit: int, cfg: dict) -> HistoryUpdates:
    """Return the complete oldest prefix newer than a Reddit watermark."""
    ua = cfg["sources"]["reddit_user_agent"]
    collected: list[dict] = []
    after = ""
    crossed_timestamp = False
    observed_seen: set[str] = set()
    previous_oldest_ts = ""
    for _ in range(MAX_PAGES):
        url = (f"https://www.reddit.com/user/{urllib.parse.quote(handle)}/submitted.json"
               "?sort=new&t=all&limit=100&raw_json=1"
               + (f"&after={urllib.parse.quote(after)}" if after else ""))
        try:
            data = _get_json(url, {"User-Agent": ua})
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return HistoryUpdates([], False, "reddit", retryable_error=str(exc))
        page, identity_gap = _history_posts(_reddit_children(data), "reddit")
        if identity_gap:
            return HistoryUpdates([], False, "reddit", coverage_gap=identity_gap)
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            return HistoryUpdates([], False, "reddit", coverage_gap=order_issue)
        if page:
            previous_oldest_ts = page[-1]["ts"]
        crossed_timestamp = (crossed_timestamp
                             or any(post["ts"] < newest_ts for post in page))
        observed_seen.update(post["id"] for post in page
                             if post["ts"] == newest_ts and post["id"] in seen_ids)
        collected.extend(post for post in page
                         if post["ts"] > newest_ts
                         or (post["ts"] == newest_ts and post["id"] not in seen_ids))
        after = str((data or {}).get("data", {}).get("after") or "")
        provider_terminal = not page or not after
        if crossed_timestamp:
            break
        if provider_terminal:
            if seen_ids and not seen_ids.issubset(observed_seen):
                return HistoryUpdates(
                    [], False, "reddit",
                    coverage_gap="Reddit listing lost the newest timestamp frontier")
            break
    else:
        return HistoryUpdates(
            [], False, "reddit",
            coverage_gap=f"Reddit updates exceeded {MAX_PAGES} cursor pages")

    posts = _unique_posts(collected)
    posts.sort(key=lambda post: history_post_key("reddit", post))
    return HistoryUpdates(posts[:limit], len(posts) <= limit, "reddit")


def _x_api_history_updates(handle: str, newest_ts: str, seen_ids: set[str],
                           limit: int, cfg: dict) -> HistoryUpdates:
    """Return an oldest-first X prefix after proving the old watermark overlap."""
    token = os.environ[cfg["sources"]["x_bearer_env"]]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        user = _get_json(
            f"https://api.x.com/2/users/by/username/{urllib.parse.quote(handle)}",
            headers)
        uid = user["data"]["id"]
    except Exception as exc:  # noqa: BLE001 - provider boundary
        return HistoryUpdates([], False, "x_api", retryable_error=str(exc))

    collected: list[dict] = []
    next_token = ""
    retrieved = 0
    crossed_timestamp = False
    observed_seen: set[str] = set()
    previous_oldest_ts = ""
    for _ in range(X_API_MAX_ACCESSIBLE_POSTS // 100):
        params = {
            "max_results": "100", "tweet.fields": "created_at",
            "start_time": (_parse_iso(newest_ts) - timedelta(seconds=1))
            .isoformat().replace("+00:00", "Z"),
        }
        if next_token:
            params["pagination_token"] = next_token
        try:
            timeline = _get_json(
                f"https://api.x.com/2/users/{uid}/tweets?{urllib.parse.urlencode(params)}",
                headers)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return HistoryUpdates([], False, "x_api", retryable_error=str(exc))
        raw = []
        for tweet in timeline.get("data", []) or []:
            tid = str(tweet.get("id") or "")
            raw.append({
                "id": tid, "ts": _normalize_iso(tweet.get("created_at") or ""),
                "url": f"https://x.com/{handle}/status/{tid}",
                "text": (tweet.get("text") or "")[:1500],
            })
        page, identity_gap = _history_posts(raw, "x_api")
        if identity_gap:
            return HistoryUpdates([], False, "x_api", coverage_gap=identity_gap)
        order_issue = _reverse_chronology_issue(page, previous_oldest_ts)
        if order_issue:
            return HistoryUpdates([], False, "x_api", coverage_gap=order_issue)
        if page:
            previous_oldest_ts = page[-1]["ts"]
        retrieved += len(page)
        crossed_timestamp = (crossed_timestamp
                             or any(post["ts"] < newest_ts for post in page))
        observed_seen.update(post["id"] for post in page
                             if post["ts"] == newest_ts and post["id"] in seen_ids)
        collected.extend(post for post in page
                         if post["ts"] > newest_ts
                         or (post["ts"] == newest_ts and post["id"] not in seen_ids))
        next_token = str((timeline.get("meta") or {}).get("next_token") or "")
        provider_terminal = not next_token
        if crossed_timestamp:
            break
        if provider_terminal:
            if seen_ids and not seen_ids.issubset(observed_seen):
                return HistoryUpdates(
                    [], False, "x_api",
                    coverage_gap="X API lost the newest timestamp frontier")
            break
        if retrieved >= X_API_MAX_ACCESSIBLE_POSTS:
            return HistoryUpdates(
                [], False, "x_api",
                coverage_gap=("X API reached its 3,200-post accessible timeline "
                              "limit before the newest watermark"))
    else:
        return HistoryUpdates(
            [], False, "x_api",
            coverage_gap=("X API reached its 3,200-post accessible timeline "
                          "limit before the newest watermark"))

    posts = _unique_posts(collected)
    posts.sort(key=lambda post: history_post_key("x_api", post))
    return HistoryUpdates(posts[:limit], len(posts) <= limit, "x_api")


def fetch_history_updates(platform: str, handle: str,
                          newest_ts: str, seen_ids: set[str], limit: int,
                          cfg: dict | None = None) -> HistoryUpdates:
    """Fetch arrivals newer than a timestamp or unseen at that timestamp."""
    cfg = cfg or load_config()
    provider = history_provider(platform, cfg)
    try:
        validate_source_timestamp(newest_ts)
    except SourceTimestampError as exc:
        return HistoryUpdates(
            [], False, provider,
            coverage_gap=f"invalid durable newest timestamp: {exc}")
    if provider == "reddit":
        return _reddit_history_updates(handle, newest_ts, seen_ids, limit, cfg)
    if provider == "x_api":
        src = cfg.get("sources") or {}
        token_name = src.get("x_bearer_env", "")
        if not token_name or not os.environ.get(token_name):
            return HistoryUpdates([], False, "x_api",
                                  retryable_error="X_BEARER_TOKEN is unavailable")
        return _x_api_history_updates(handle, newest_ts, seen_ids, limit, cfg)
    if provider == "exa":
        return HistoryUpdates(
            [], False, "exa",
            coverage_gap=("Exa search cannot prove a complete arrival prefix "
                          "after the newest watermark"))
    return HistoryUpdates([], False, provider,
                          coverage_gap=f"unsupported history provider: {provider}")


def fetch_history_page(platform: str, handle: str, start_iso: str,
                       before: tuple[str, str] | None, limit: int,
                       cfg: dict | None = None) -> HistoryPage:
    """Fetch one durable Explorer page under a provider-explicit contract."""
    cfg = cfg or load_config()
    provider = history_provider(platform, cfg)
    try:
        validate_source_timestamp(start_iso)
        if before:
            validate_source_timestamp(before[0])
    except SourceTimestampError as exc:
        return HistoryPage(
            [], False, provider,
            coverage_gap=f"invalid durable history timestamp: {exc}")
    if provider == "reddit":
        return _reddit_history_page(handle, start_iso, before, limit, cfg)
    if provider == "x_api":
        src = cfg.get("sources") or {}
        token_name = src.get("x_bearer_env", "")
        if not token_name or not os.environ.get(token_name):
            return HistoryPage([], False, "x_api",
                               retryable_error="X_BEARER_TOKEN is unavailable")
        return _x_api_history_page(handle, start_iso, before, limit, cfg)
    if provider == "exa":
        src = cfg.get("sources") or {}
        key_name = src.get("exa_api_key_env", "")
        if not key_name or not os.environ.get(key_name):
            return HistoryPage([], False, "exa",
                               retryable_error="EXA_API_KEY is unavailable")
        return _exa_history_page(handle, start_iso, before, limit, cfg)
    return HistoryPage([], False, provider,
                       coverage_gap=f"unsupported history provider: {provider}",
                       prefix_complete=False)


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
