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
import json
import os
import re
import unicodedata
import urllib.parse

import cognee
import polymarket as pm
import resolve as resolver
from lib import (ROOT, agent_context, append_lessons, append_tsv, domain_dir,
                 ensure_leaker_row, gen_id, iso_to_unix, kickstart_active,
                 load_config, log_result, normalize_class, now_iso,
                 read_tsv, score_credit_key, score_credit_order_key,
                 score_credit_price, unix_to_iso, update_leaker_stats, write_note,
                 write_tsv)
from llm import call_json
from source_timestamps import (SourceTimestampError, utc_now,
                               validate_source_posts,
                               validate_source_timestamp)
from sources import (fetch_history_page, fetch_history_updates, fetch_posts,
                     history_boundary_key, history_post_key, history_provider,
                     post_key, provider_id_key, reddit_sub_page,
                     X_RESERVED_ROUTES)


EXTRACTION_POST_CHUNK_SIZE = 20
MAPPING_CLAIM_CHUNK_SIZE = 20
HISTORY_PROGRESS_FILE = "explorer-history.tsv"
HISTORY_PROGRESS_COLUMNS = (
    "provider", "platform", "handle", "call_class", "window_start",
    "newest_ts", "newest_ids", "before_ts", "before_id", "status", "detail",
    "updated_at",
)
HISTORY_PROGRESS_STATUSES = {
    "active", "exhausted", "coverage_gap", "retryable_error",
}


class HistoryProgressError(ValueError):
    """The durable cursor table cannot be trusted safely."""


class DiscoveryConfigError(ValueError):
    """Candidate-discovery bounds cannot safely visit configured sources."""


def _canonical_progress_iso(value, *, now=None) -> bool:
    try:
        validate_source_timestamp(value, now=now)
    except SourceTimestampError:
        return False
    return True


def _progress_updated_at(now=None) -> str:
    """Format progress timestamps from the same clock used to validate them."""
    reference = now if now is not None else utc_now()
    return reference.strftime("%Y-%m-%dT%H:%M:%SZ")


def _frontier_ids(value: str) -> set[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HistoryProgressError("invalid newest_ids JSON") from exc
    if (not isinstance(parsed, list) or not parsed
            or any(not isinstance(item, str) or not item or not item.isprintable()
                   for item in parsed)
            or len(set(parsed)) != len(parsed)):
        raise HistoryProgressError("invalid newest_ids set")
    return set(parsed)


def _dump_frontier_ids(provider: str, stable_ids: set[str]) -> str:
    ordered = sorted(stable_ids, key=lambda value: provider_id_key(provider, value))
    return json.dumps(ordered, separators=(",", ":"))


def validate_history_progress(progress: list[dict], *, now=None) -> None:
    """Validate every durable identity and compound boundary before use."""
    expected = set(HISTORY_PROGRESS_COLUMNS)
    seen: set[tuple[str, str, str, str]] = set()
    reference = now if now is not None else utc_now()
    for number, row in enumerate(progress, start=1):
        if set(row) != expected:
            raise HistoryProgressError(f"invalid row {number}: fields do not match header")
        identity = tuple(row[field]
                         for field in ("provider", "platform", "handle", "call_class"))
        if any(not isinstance(value, str) or not value
               or value != value.strip() or not value.isprintable()
               or any(char.isspace() for char in value)
               for value in identity):
            raise HistoryProgressError(f"invalid row {number}: required identity")
        if row["provider"] not in ("reddit", "x_api", "exa"):
            raise HistoryProgressError(f"invalid row {number}: provider")
        if row["platform"] not in ("reddit", "x"):
            raise HistoryProgressError(f"invalid row {number}: platform")
        if ((row["provider"] == "reddit") != (row["platform"] == "reddit")):
            raise HistoryProgressError(f"invalid row {number}: provider/platform")
        if identity in seen:
            raise HistoryProgressError(f"invalid row {number}: duplicate key")
        seen.add(identity)
        if not _canonical_progress_iso(row["window_start"], now=reference):
            raise HistoryProgressError(f"invalid row {number}: window_start")
        if not _canonical_progress_iso(row["updated_at"], now=reference):
            raise HistoryProgressError(f"invalid row {number}: updated_at")
        if row["status"] not in HISTORY_PROGRESS_STATUSES:
            raise HistoryProgressError(f"invalid row {number}: status")
        if not isinstance(row["detail"], str):
            raise HistoryProgressError(f"invalid row {number}: detail")
        newest_ts, newest_ids = row["newest_ts"], row["newest_ids"]
        if bool(newest_ts) != bool(newest_ids):
            raise HistoryProgressError(
                f"invalid row {number}: newest_ts/newest_ids must be paired")
        if newest_ts:
            if (not _canonical_progress_iso(newest_ts, now=reference)
                    or newest_ts < row["window_start"]):
                raise HistoryProgressError(f"invalid row {number}: newest_ts")
            try:
                _frontier_ids(newest_ids)
            except HistoryProgressError as exc:
                raise HistoryProgressError(f"invalid row {number}: {exc}") from exc
        before_ts, before_id = row["before_ts"], row["before_id"]
        if bool(before_ts) != bool(before_id):
            raise HistoryProgressError(
                f"invalid row {number}: before_ts/before_id must be paired")
        if before_ts and (not _canonical_progress_iso(before_ts, now=reference)
                          or before_ts < row["window_start"]
                          or before_id != before_id.strip()
                          or not before_id.isprintable()
                          or any(char.isspace() for char in before_id)):
            raise HistoryProgressError(f"invalid row {number}: before boundary")
        newest = (newest_ts, newest_ids)
        oldest = (row["before_ts"], row["before_id"])
        if all(oldest) and not all(newest):
            raise HistoryProgressError(
                f"invalid row {number}: backward boundary lacks newest watermark")
        if all(newest) and all(oldest) and oldest[0] > newest[0]:
            raise HistoryProgressError(f"invalid row {number}: inverted boundaries")
        if row["status"] in ("coverage_gap", "retryable_error") and not row["detail"]:
            raise HistoryProgressError(f"invalid row {number}: missing failure detail")


def ensure_history_progress_file(ddir):
    """Create the durable Explorer boundary table before its first use."""
    path = ddir / HISTORY_PROGRESS_FILE
    if path.exists():
        return path
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\t".join(HISTORY_PROGRESS_COLUMNS) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_history_progress(ddir) -> list[dict]:
    path = ensure_history_progress_file(ddir)
    with open(path, encoding="utf-8") as file:
        header = file.readline().rstrip("\n")
    if header.split("\t") != list(HISTORY_PROGRESS_COLUMNS):
        raise HistoryProgressError("invalid header: exact Explorer history schema required")
    progress = read_tsv(path)
    validate_history_progress(progress)
    return progress


def _progress_row(progress: list[dict], cand: dict, cfg: dict) -> dict:
    """Find/create provider+leaker+class state, inheriting a standard scan."""
    platform, handle = cand["platform"], cand["handle"]
    call_class = cand.get("_call_class") or "-"
    provider = cand.get("_provider") or history_provider(platform, cfg)

    def matches(row: dict, target_class: str) -> bool:
        return (row.get("platform") == platform and row.get("handle") == handle
                and row.get("call_class") == target_class
                and row.get("provider") in ("", provider))

    row = next((item for item in progress if matches(item, call_class)), None)
    if row is not None:
        row["provider"] = provider
        return row

    inherited = None
    if call_class != "-":
        inherited = next((item for item in progress if matches(item, "-")), None)
    row = {
        "provider": provider, "platform": platform, "handle": handle,
        "call_class": call_class,
        "window_start": ((inherited or {}).get("window_start")
                         or cand["_start"]),
        "newest_ts": (inherited or {}).get("newest_ts", ""),
        "newest_ids": (inherited or {}).get("newest_ids", ""),
        "before_ts": (inherited or {}).get("before_ts", ""),
        "before_id": (inherited or {}).get("before_id", ""),
        "status": (inherited or {}).get("status", "active"),
        "detail": (inherited or {}).get("detail", ""),
        "updated_at": _progress_updated_at(),
    }
    progress.append(row)
    return row


def _persist_progress(ddir, progress: list[dict], *, now=None) -> None:
    path = ensure_history_progress_file(ddir)
    validate_history_progress(progress, now=now)
    write_tsv(path, progress)


def _progress_issue(ddir, progress: list[dict], row: dict,
                    status: str, detail: str) -> None:
    reference = utc_now()
    row.update({"status": status, "detail": detail,
                "updated_at": _progress_updated_at(reference)})
    _persist_progress(ddir, progress, now=reference)


def reconcile_history_projection(ddir, leakers: list[dict], cfg: dict,
                                 domain: str) -> list[dict]:
    """Replay durable signals into leakers before trusting a persisted cursor.

    Replay can repair only rows that reached signals.tsv. Calls suppressed by
    the legacy event-level guard before append require historical requalification.
    """
    signals = read_tsv(ddir / "signals.tsv")
    resolver.rebuild_leaker_stats(signals, leakers, cfg["thresholds"], domain)
    write_tsv(ddir / "leakers.tsv", leakers)
    return signals


def _persist_leaker_projection(ddir, leakers: list[dict]) -> None:
    """Persist recoverable score effects before any history cursor moves."""
    path = ddir / "leakers.tsv"
    if path.exists():
        write_tsv(path, leakers)


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _validated_history_batch(posts: list[dict], *, newest_first: bool,
                             now) -> tuple[list[dict], str]:
    """Validate a provider batch before sorting or completeness decisions."""
    valid, rejected = validate_source_posts(posts, now=now)
    if rejected:
        return [], "provider returned an invalid source timestamp"
    timestamps = [post["ts"] for post in valid]
    pairs = zip(timestamps, timestamps[1:])
    if newest_first:
        invalid_order = any(first < second for first, second in pairs)
    else:
        invalid_order = any(first > second for first, second in pairs)
    if invalid_order:
        direction = "reverse chronological" if newest_first else "chronological"
        return [], f"provider violated {direction} batch ordering"
    return valid, ""


def _parse_index(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _canonical_claims(posts: list[dict], raw_claims, allowed_indices: set[int]) -> list[dict]:
    """Copy source provenance onto claims and reject indices not in this chunk."""
    claims = []
    for raw in raw_claims or []:
        try:
            post_index = _parse_index(raw["post_index"])
        except (KeyError, TypeError):
            continue
        if (post_index is None or post_index < 0 or post_index >= len(posts)
                or post_index not in allowed_indices):
            continue
        if not str(raw.get("claim", "")).strip():
            continue
        claim = dict(raw)
        claim["post_index"] = post_index
        claim["post_ts"] = posts[post_index]["ts"]
        claim["post_url"] = posts[post_index]["url"]
        claim["source_post_id"] = posts[post_index].get("id", "")
        claims.append(claim)
    return claims


def _accepted_mappings(raw_mappings, allowed_pairs: list[tuple[int, str]]):
    """Return first matched candidate per claim, or None until every pair is answered."""
    allowed = set(allowed_pairs)
    addressed: set[tuple[int, str]] = set()
    matched: dict[tuple[int, str], dict] = {}
    for raw in raw_mappings or []:
        try:
            claim_index = _parse_index(raw["claim_index"])
            if claim_index is None:
                continue
            pair = (claim_index, str(raw["market_id"]))
        except (KeyError, TypeError):
            continue
        if pair not in allowed:
            continue
        addressed.add(pair)
        if raw.get("match"):
            matched.setdefault(pair, raw)
    if addressed != allowed:
        return None
    best_by_claim: dict[int, dict] = {}
    for pair in allowed_pairs:
        if pair in matched and pair[0] not in best_by_claim:
            best_by_claim[pair[0]] = matched[pair]
    return best_by_claim


def _score_credit_pairs(signals: list[dict]) -> set[tuple[str, str]]:
    """Recompute eligible exact-market ownership without trusting projections."""
    eligible: list[tuple[tuple[str, str, str], tuple[str, str]]] = []
    for signal in signals:
        if (signal.get("resolved_outcome") not in ("YES", "NO")
                or signal.get("side") not in ("YES", "NO")):
            continue
        pair = score_credit_key(signal.get("leaker_id"), signal.get("market_id"))
        order = score_credit_order_key(signal)
        price = score_credit_price(signal.get("price_at_signal"))
        if pair is not None and order is not None and price is not None:
            eligible.append((order, pair))

    pairs: set[tuple[str, str]] = set()
    for _order, pair in sorted(eligible):
        pairs.add(pair)
    return pairs


def sweep_subs(brief: str) -> list[str]:
    found = re.findall(r"reddit:r/([A-Za-z0-9_-]+)", brief)
    seen = set()
    sources = []
    for sub in found:
        key = sub.lower()
        if key not in seen:
            seen.add(key)
            sources.append(sub)
    return sources


DISCOVERY_CONFIG_BOUNDS = {
    "discovery_evidence_budget": (1, 400),
    "discovery_page_size": (1, 100),
    "discovery_max_pages_per_source": (1, 20),
    "discovery_evidence_chars": (400, 1500),
}
DISCOVERY_AGGREGATE_BOUNDS = {
    "discovery request": 100,
    "discovery raw item": 8000,
    "scanned evidence character": 4_000_000,
    "retained evidence character/byte": 100_000,
}
DISCOVERY_PROMPT_EVIDENCE_LIMIT = 100_000
DISCOVERY_SOURCE_NAME_CHARS = 32
DISCOVERY_CANONICAL_ID_CHARS = len("reddit:") + 32
DISCOVERY_CANONICAL_URL_CHARS = 160
DISCOVERY_PUBLISHER_CHARS = len("reddit/u/") + 64
DISCOVERY_LINKED_SOURCE_CHARS = 96
DISCOVERY_PROVENANCE_CHARS = len("reddit:r/") + DISCOVERY_SOURCE_NAME_CHARS


def _max_serialized_evidence_size(settings: dict[str, int],
                                  source_count: int) -> int:
    """Price worst-case JSON chars and UTF-8 bytes before provider work."""
    common = {
        "canonical_id": "i" * DISCOVERY_CANONICAL_ID_CHARS,
        "publisher": "p" * DISCOVERY_PUBLISHER_CHARS,
        "linked_source": "l" * DISCOVERY_LINKED_SOURCE_CHARS,
        "source_provenance": [
            "s" * DISCOVERY_PROVENANCE_CHARS for _ in range(source_count)
        ],
    }
    char_item = {
        **common,
        # Quotes exercise the maximum permitted JSON character escaping.
        "canonical_url": '"' * DISCOVERY_CANONICAL_URL_CHARS,
        "text": '"' * settings["discovery_evidence_chars"],
    }
    byte_item = {
        **common,
        # Four-byte printable Unicode is the maximum UTF-8 width accepted.
        "canonical_url": "😀" * DISCOVERY_CANONICAL_URL_CHARS,
        "text": "😀" * settings["discovery_evidence_chars"],
    }
    serialized_chars = json.dumps(
        char_item, ensure_ascii=False, separators=(",", ":"))
    serialized_bytes = json.dumps(
        byte_item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    budget = settings["discovery_evidence_budget"]
    separators = max(0, budget - 1)
    return max(
        budget * len(serialized_chars) + separators,
        budget * len(serialized_bytes) + separators,
    )


def _discovery_settings(cfg: dict, sources: list[str]) -> dict[str, int]:
    source_cfg = cfg.get("sources")
    if not isinstance(source_cfg, dict):
        raise DiscoveryConfigError("sources config must be an object")
    settings = {}
    for name, (lower, upper) in DISCOVERY_CONFIG_BOUNDS.items():
        value = source_cfg.get(name)
        if type(value) is not int or not lower <= value <= upper:
            raise DiscoveryConfigError(
                f"sources.{name} must be an integer in [{lower}, {upper}]")
        settings[name] = value
    if any(not re.fullmatch(
            rf"[A-Za-z0-9_-]{{1,{DISCOVERY_SOURCE_NAME_CHARS}}}", source)
            for source in sources):
        raise DiscoveryConfigError(
            f"discovery source names must be 1-{DISCOVERY_SOURCE_NAME_CHARS} "
            "safe characters")
    if len(sources) > settings["discovery_evidence_budget"]:
        raise DiscoveryConfigError(
            "discovery_evidence_budget must be at least the configured source count")
    aggregate = {
        "discovery request": (
            len(sources) * settings["discovery_max_pages_per_source"]),
        "discovery raw item": (
            len(sources) * settings["discovery_max_pages_per_source"]
            * settings["discovery_page_size"]),
        "scanned evidence character": (
            len(sources) * settings["discovery_max_pages_per_source"]
            * settings["discovery_page_size"]
            * settings["discovery_evidence_chars"] * 3),
        "retained evidence character/byte": (
            _max_serialized_evidence_size(settings, len(sources))
            if sources else 0),
    }
    for name, value in aggregate.items():
        maximum = DISCOVERY_AGGREGATE_BOUNDS[name]
        if value > maximum:
            raise DiscoveryConfigError(
                f"aggregate {name} bound exceeded: {value} > {maximum}")
    return settings


def _unsafe_control(value: str) -> bool:
    return any(unicodedata.category(char).startswith("C")
               and char not in "\n\r\t" for char in value)


def _canonical_discovery_url(value) -> str:
    if (not isinstance(value, str) or not value
            or len(value) > DISCOVERY_CANONICAL_URL_CHARS
            or value != value.strip()
            or _unsafe_control(value)):
        return ""
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or host not in (
            "reddit.com", "www.reddit.com", "old.reddit.com")
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        return ""
    return value


def _discovery_text(value, limit: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        return ""
    bounded = value[:limit]
    if _unsafe_control(bounded):
        return ""
    clean = bounded.replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not clean:
        return ""
    return clean[:limit]


def _discovery_identity(value, limit: int, *, required: bool) -> str:
    if not isinstance(value, str) or len(value) > limit:
        return ""
    clean = _discovery_text(value, limit, required=required)
    if clean and (any(char.isspace() for char in clean) or not clean.isprintable()):
        return ""
    return clean


def _normalized_publisher(value) -> str:
    clean = _discovery_identity(
        value, DISCOVERY_PUBLISHER_CHARS, required=True)
    match = re.fullmatch(r"reddit/u/([A-Za-z0-9_-]{1,64})", clean,
                         flags=re.IGNORECASE)
    return f"reddit/u/{match.group(1)}" if match else ""


def _normalized_linked_source(value) -> str:
    clean = _discovery_identity(
        value, DISCOVERY_LINKED_SOURCE_CHARS, required=False)
    if not clean:
        return ""
    social = re.fullmatch(
        r"(x/@|reddit/u/)([A-Za-z0-9_-]{1,64})", clean,
        flags=re.IGNORECASE)
    if social:
        return social.group(1).lower() + social.group(2)
    if ("." in clean
            and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
                                 label)
                    for label in clean.split("."))):
        return clean.lower()
    return ""


def _normalize_discovery_entry(raw, text_chars: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    stable_id = raw.get("canonical_id")
    if (not isinstance(stable_id, str)
            or len(stable_id) > DISCOVERY_CANONICAL_ID_CHARS
            or not re.fullmatch(r"reddit:[A-Za-z0-9_-]{1,32}", stable_id)):
        return None
    canonical_url = _canonical_discovery_url(raw.get("canonical_url"))
    text = _discovery_text(raw.get("text"), text_chars)
    publisher = _normalized_publisher(raw.get("publisher"))
    linked_source = _normalized_linked_source(raw.get("linked_source", ""))
    if not canonical_url or not text or not publisher:
        return None
    return {
        "canonical_id": stable_id,
        "canonical_url": canonical_url,
        "text": text,
        "publisher": publisher,
        "linked_source": linked_source,
    }


def discovery_evidence(cfg: dict, brief: str, *, fetch_page=None) -> list[dict]:
    """Collect unique evidence fairly under one explicit per-run item budget.

    Each source contributes at most one accepted item per selection round.
    Cursor pages are fetched only when that source's current page is drained.
    Invalid rows and duplicates do not consume the unique-evidence budget.
    """
    source_names = sweep_subs(brief)
    settings = _discovery_settings(cfg, source_names)
    if not source_names:
        return []
    pager = fetch_page or reddit_sub_page
    page_size = settings["discovery_page_size"]
    max_pages = settings["discovery_max_pages_per_source"]
    budget = settings["discovery_evidence_budget"]
    text_chars = settings["discovery_evidence_chars"]
    states = [{
        "name": source, "cursor": "", "seen_cursors": set(),
        "pages": 0, "items": [], "done": False,
    } for source in source_names]
    groups: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    id_urls: dict[str, set[str]] = {}
    url_ids: dict[str, set[str]] = {}
    conflicts: set[tuple[str, str]] = set()
    selected: list[tuple[str, str]] = []
    selected_set: set[tuple[str, str]] = set()

    def register_page(state: dict, raw_items: list) -> None:
        """Normalize a whole page before selection so row order cannot win."""
        nonlocal selected, selected_set
        for raw in raw_items:
            item = _normalize_discovery_entry(raw, text_chars)
            if item is None:
                continue
            key = item["canonical_id"], item["canonical_url"]
            groups.setdefault(key, []).append((state["name"], item))
            id_urls.setdefault(key[0], set()).add(key[1])
            url_ids.setdefault(key[1], set()).add(key[0])
            state["items"].append(key)

        conflicted_ids = {stable_id for stable_id, urls in id_urls.items()
                          if len(urls) > 1}
        conflicted_urls = {url for url, stable_ids in url_ids.items()
                           if len(stable_ids) > 1}
        conflicts.update(
            key for key in groups
            if key[0] in conflicted_ids or key[1] in conflicted_urls)
        if conflicts.intersection(selected_set):
            selected = [key for key in selected if key not in conflicts]
            selected_set = set(selected)

    def fetch_into(state: dict) -> bool:
        """Fetch and register one page; return whether provider work occurred."""
        if state["done"]:
            return False
        if state["pages"] >= max_pages:
            state["done"] = True
            return False
        try:
            page = pager(state["name"], state["cursor"], page_size, cfg)
        except Exception:  # noqa: BLE001 - isolate one discovery source
            state["done"] = True
            return True

        state["pages"] += 1
        items = getattr(page, "items", None)
        if isinstance(items, list):
            register_page(state, items)
        else:
            state["done"] = True
        cursor = getattr(page, "next_cursor", "")
        failed = bool(getattr(page, "failed", False))
        if (not isinstance(cursor, str) or cursor != cursor.strip()
                or any(char.isspace() for char in cursor)
                or _unsafe_control(cursor)
                or cursor in state["seen_cursors"]):
            failed = True
            cursor = ""
        if cursor:
            state["seen_cursors"].add(cursor)
            state["cursor"] = cursor
        if failed or not cursor or state["pages"] >= max_pages:
            state["done"] = True
        return True

    # Discover the complete configured, bounded page set before selection so an
    # identity conflict on a later cursor page cannot be hidden by a full item
    # budget. Fetching remains round-robin and stops at max_pages per source.
    while True:
        progressed = False
        for state in states:
            if fetch_into(state):
                progressed = True
        if not progressed:
            break

    while len(selected) < budget:
        progressed = False
        for state in states:
            if len(selected) >= budget:
                break
            while state["items"]:
                key = state["items"].pop(0)
                if key in conflicts or key in selected_set:
                    continue
                selected.append(key)
                selected_set.add(key)
                progressed = True
                break
        if not progressed:
            break

    evidence = []
    for key in selected:
        records = groups[key]
        # Prefer the longest body, then a linked identity, with lexical
        # tie-breakers. This representation is invariant to row/feed order.
        _source, representative = min(
            records,
            key=lambda record: (
                -len(record[1]["text"]),
                -bool(record[1]["linked_source"]),
                record[1]["text"], record[1]["publisher"],
                record[1]["linked_source"],
            ))
        item = dict(representative)
        item["source_provenance"] = sorted(
            {f"reddit:r/{source}" for source, _item in records},
            key=str.casefold)
        evidence.append(item)
    return evidence


def _candidate_grounded(platform: str, handle: str,
                        evidence: list[dict]) -> bool:
    """Require the exact proposed identity to occur in bounded source evidence."""
    target = handle.casefold()
    for item in evidence:
        publisher = re.fullmatch(
            r"reddit/u/([A-Za-z0-9_-]+)", item["publisher"],
            flags=re.IGNORECASE)
        if (platform == "reddit" and publisher
                and publisher.group(1).casefold() == target):
            return True
        linked = item["linked_source"]
        linked_match = re.fullmatch(
            r"(x/@|reddit/u/)([A-Za-z0-9_-]+)", linked,
            flags=re.IGNORECASE)
        if linked_match:
            linked_platform = "x" if linked_match.group(1).lower() == "x/@" \
                else "reddit"
            if (linked_platform == platform
                    and linked_match.group(2).casefold() == target):
                return True

        if (platform, target) in _body_identity_keys(item["text"]):
            return True
    return False


_BODY_URL_TOKEN_RE = re.compile(
    r"(?:(?:https?://)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
    r"(?::[0-9]+)?(?:/[^\s<>{}\[\]\"']*)?)",
    flags=re.IGNORECASE,
)
_ADJOINING_URL_PUNCTUATION = ".,;:!?)]}"
_IDNA_DOT_EQUIVALENTS = frozenset((".", "\u3002", "\uff0e", "\uff61"))


def _identity_prefix_blocked(text: str, start: int, delimiters: str) -> bool:
    if start == 0:
        return False
    prefix = text[start - 1]
    category = unicodedata.category(prefix)
    return (prefix.isalnum() or prefix == "_" or prefix in delimiters
            or ("." in delimiters and prefix in _IDNA_DOT_EQUIVALENTS)
            or category in ("Mn", "Mc", "Me", "Pc"))


def _body_route_segments(path: str) -> list[str] | None:
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        return None
    raw_segments = path.split("/")[1:]
    if raw_segments and raw_segments[-1] == "":
        raw_segments.pop()
    if not raw_segments or any(not segment for segment in raw_segments):
        return None
    parts = []
    for raw in raw_segments:
        value = raw
        for _ in range(8):
            decoded = urllib.parse.unquote(value)
            if decoded == value:
                break
            value = decoded
        else:
            return None
        if (not value or "/" in value or "\\" in value
                or _unsafe_control(value)):
            return None
        parts.append(value)
    return parts


def _body_url_identity(token: str) -> tuple[str, str] | None:
    value = token.rstrip(_ADJOINING_URL_PUNCTUATION)
    parsed = urllib.parse.urlsplit(
        value if re.match(r"https?://", value, flags=re.IGNORECASE)
        else "https://" + value)
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme.lower() not in ("http", "https") or port is not None
            or parsed.username is not None or parsed.password is not None):
        return None
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    parts = _body_route_segments(parsed.path)
    if parts is None:
        return None
    if host in ("x.com", "twitter.com"):
        if not parts:
            return None
        candidate = parts[0]
        if (candidate.casefold() in X_RESERVED_ROUTES
                or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", candidate)):
            return None
        if not (len(parts) == 1
                or (len(parts) == 3 and parts[1].casefold() == "status"
                    and parts[2].isdigit())):
            return None
        return "x", candidate.casefold()
    if host == "reddit.com" and len(parts) == 2 \
            and parts[0].casefold() in ("u", "user") \
            and re.fullmatch(r"[A-Za-z0-9_-]{3,20}", parts[1]):
        return "reddit", parts[1].casefold()
    return None


def _body_identity_keys(text: str) -> set[tuple[str, str]]:
    identities = set()
    for match in re.finditer(
            r"@([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])", text):
        if not _identity_prefix_blocked(text, match.start(), "/@"):
            identities.add(("x", match.group(1).casefold()))
    for match in re.finditer(
            r"u/([A-Za-z0-9_-]{3,20})(?![A-Za-z0-9_-])",
            text, flags=re.IGNORECASE):
        if not _identity_prefix_blocked(text, match.start(), "./-"):
            identities.add(("reddit", match.group(1).casefold()))
    for match in _BODY_URL_TOKEN_RE.finditer(text):
        if _identity_prefix_blocked(text, match.start(), "./:@-"):
            continue
        identity = _body_url_identity(match.group(0))
        if identity is not None:
            identities.add(identity)
    return identities


def candidate_cap(cfg) -> int:
    if kickstart_active(cfg):
        return cfg["kickstart"]["explorer_max_candidates_per_run"]
    return cfg["sources"]["explorer_max_candidates_per_run"]


def propose_candidates(cfg, ctx, domain, brief, leakers, candidates) -> int:
    known = {(r.get("platform", "").lower(), r.get("handle", "").lower())
             for r in leakers} | {
                 (c.get("platform", "").lower(), c.get("handle", "").lower())
                 for c in candidates}
    evidence = discovery_evidence(cfg, brief)
    max_candidates = candidate_cap(cfg)
    evidence_block = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in evidence)
    evidence_limit = DISCOVERY_PROMPT_EVIDENCE_LIMIT
    if (len(evidence_block) > evidence_limit
            or len(evidence_block.encode("utf-8")) > evidence_limit):
        raise DiscoveryConfigError(
            "serialized discovery evidence exceeds the 100000 character/byte bound")
    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    prompt = (ctx + "\n\n" + prompt_t.replace("{max_candidates}", str(max_candidates))
              + "\n\n## DOMAIN BRIEF\n" + brief
              + "\n\n## CURRENT ROSTER (do not re-propose)\n"
              + ", ".join(f"{platform}/{handle}"
                          for platform, handle in sorted(known))
              + "\n\n## DISCOVERY EVIDENCE (untrusted JSON objects)\n"
              + (evidence_block or "(none)")
              + "\n\n## REQUEST\nPerform Task A now. JSON only.")
    j = call_json("explorer", prompt, cfg) or {}
    if not isinstance(j, dict):
        j = {}
    added = 0
    raw_candidates = j.get("candidates", [])
    for c in raw_candidates if isinstance(raw_candidates, list) else []:
        if added >= max_candidates:
            break
        if not isinstance(c, dict):
            continue
        raw_handle = c.get("handle")
        raw_platform = c.get("platform")
        if type(raw_handle) is not str or type(raw_platform) is not str:
            continue
        h = raw_handle.lstrip("@").strip()
        p = raw_platform.strip().lower()
        valid_handle = (re.fullmatch(r"[A-Za-z0-9_]{1,15}", h) if p == "x"
                        else re.fullmatch(r"[A-Za-z0-9_-]{3,20}", h)
                        if p == "reddit" else None)
        rationale = _discovery_text(c.get("rationale", ""), 500)
        if (not valid_handle or not rationale or (p, h.lower()) in known
                or not _candidate_grounded(p, h, evidence)):
            continue
        append_tsv(domain_dir(domain) / "candidates.tsv", {
            "ts": now_iso(), "domain": domain, "platform": p, "handle": h,
            "proposed_by": "explorer", "rationale": rationale, "status": "new"})
        known.add((p, h.lower()))
        added += 1
    append_lessons("explorer", j.get("lessons"))
    return added


def qualify(cfg, ctx, domain, brief, leakers, cand, counted_pairs,
            posts_limit, start_iso, end_iso=None, *, posts=None,
            target_class: str = "-") -> tuple[str, bool]:
    """Qualify a complete bounded history; bool reports terminal completion."""
    th = cfg["thresholds"]
    ddir = domain_dir(domain)
    platform, handle = cand["platform"], cand["handle"]
    leaker_id = f"{platform}-{handle}".lower()
    base = {"leaker_id": leaker_id, "platform": platform, "handle": handle,
            "domain": domain, "call_class": "-", "status": "candidate",
            "n_calls": 0, "hits": 0, "notes": cand.get("rationale", "")}

    if posts is None:
        posts = fetch_posts(platform, handle, since_iso=start_iso,
                            limit=posts_limit, cfg=cfg, end_iso=end_iso)
    if not posts:
        return f"{handle}: no history fetched in bounded window — retry next run", False
    posts, rejected = validate_source_posts(posts, now=utc_now())
    if not posts:
        return (f"{handle}: rejected {rejected} posts with invalid source timestamp"
                " — retry next run", False)
    posts = sorted(posts, key=post_key)

    prompt_t = (ROOT / "prompts" / "explorer.md").read_text(encoding="utf-8")
    claims = []
    indexed_posts = list(enumerate(posts))
    for post_chunk in _chunks(indexed_posts, EXTRACTION_POST_CHUNK_SIZE):
        post_block = "\n".join(
            f"- post_index {i} | [{p['ts']}] {p['url']}\n  {p['text'][:400]}"
            for i, p in post_chunk)
        prompt = (ctx + "\n\n" + prompt_t + "\n\n## DOMAIN BRIEF\n" + brief
                  + f"\n\n## CANDIDATE\n{platform}/{handle}"
                  + ((f"\n\n## TARGET CALL CLASS\n{target_class}"
                      "\nReturn only claims in this frozen class."
                      ) if target_class != "-" else "")
                  + "\n\n## POST HISTORY CHUNK\n" + post_block
                  + "\n\n## REQUEST\nPerform Task B now. JSON only.")
        j = call_json("explorer", prompt, cfg)
        if not isinstance(j, dict) or not isinstance(j.get("claims"), list):
            return f"{handle}: extraction chunk unparseable — retry next run", False
        append_lessons("explorer", j.get("lessons"))
        claims.extend(_canonical_claims(posts, j["claims"], {i for i, _ in post_chunk}))
    if target_class != "-":
        claims = [claim for claim in claims
                  if normalize_class(claim.get("call_class", ""), cfg, domain)
                  == target_class]
    claims.sort(key=lambda c: (c["post_ts"], c["post_url"], c["post_index"]))
    if not claims:
        return f"{handle}: 0 usable claims in {len(posts)} posts", True

    pairs: list[tuple[int, dict]] = []
    market_by_pair: dict[tuple[int, str], dict] = {}
    search_failed = 0
    for i, c in enumerate(claims):
        found = pm.search_markets(str(c.get("market_query", ""))[:80], closed=True, limit=3)
        if found is None:
            search_failed += 1
            continue
        for m in found:
            credit_key = score_credit_key(leaker_id, m.get("id"))
            if credit_key is None:
                continue
            pair = (i, credit_key[1])
            if pair not in market_by_pair:
                market_by_pair[pair] = m
                pairs.append((i, m))
    if search_failed:
        return (f"{handle}: {len(claims)} claims; {search_failed} market searches "
                "failed transiently — retry next run", False)
    if not pairs:
        return f"{handle}: {len(claims)} claims, 0 resolved-market candidates", True

    best_by_claim: dict[int, dict] = {}
    claim_indices = sorted({i for i, _ in pairs})
    for claim_chunk in _chunks(claim_indices, MAPPING_CLAIM_CHUNK_SIZE):
        chunk_set = set(claim_chunk)
        chunk_pairs = [(i, m) for i, m in pairs if i in chunk_set]
        allowed_pairs = [(i, str(m["id"])) for i, m in chunk_pairs]
        map_block = "\n".join(
            f"- claim_index {i} | market_id {m['id']} | {m['question']} | "
            f"criteria: {m['description'][:200]}" for i, m in chunk_pairs)
        claim_block = "\n".join(f"- [{i}] {claims[i]['claim']}" for i in claim_chunk)
        prompt = (ctx + "\n\n" + prompt_t + "\n\n## CLAIMS\n" + claim_block
                  + "\n\n## CANDIDATE (claim, market) PAIRS\n" + map_block
                  + "\n\n## REQUEST\nPerform Task C now. JSON only.")
        j = call_json("explorer", prompt, cfg)
        if not isinstance(j, dict) or not isinstance(j.get("mappings"), list):
            return f"{handle}: mapping chunk unparseable — retry next run", False
        accepted = _accepted_mappings(j["mappings"], allowed_pairs)
        if accepted is None:
            return f"{handle}: mapping chunk incomplete — retry next run", False
        best_by_claim.update(accepted)

    ordered = []
    for ci, mp in best_by_claim.items():
        signal_id = gen_id("hist")
        order = score_credit_order_key({
            "post_ts": claims[ci].get("post_ts"),
            "source_post_id": claims[ci].get("source_post_id"),
            "signal_id": signal_id,
        }, require_source=True)
        if order is not None:
            ordered.append((order, ci, mp, signal_id))
    ordered.sort(key=lambda item: item[0])

    scored = unpriced = verified = skipped_dupe = 0
    for _order, ci, mp, signal_id in ordered:
        claim = claims[ci]
        market = market_by_pair.get((ci, str(mp.get("market_id", ""))))
        side = str(mp.get("implied_side", "")).upper()
        if not market or side not in ("YES", "NO"):
            continue
        pair_key = score_credit_key(leaker_id, market.get("id"))
        if pair_key is None:
            continue
        if pair_key in counted_pairs:
            skipped_dupe += 1
            continue
        winner = pm.winning_side(market)
        if winner is None:
            continue
        price_yes = score_credit_price(
            pm.price_at(market["yes_token"], iso_to_unix(claim.get("post_ts", ""))))
        price_side = None if price_yes is None else (price_yes if side == "YES" else 1 - price_yes)
        hit = (side == winner)
        cls = normalize_class(claim.get("call_class", ""), cfg, domain)
        row = ensure_leaker_row(leakers, base, cls)
        update_leaker_stats(row, hit, price_side, th)  # F1: unpriced → n_unpriced only
        counted = price_side is not None
        append_tsv(ddir / "signals.tsv", {
            "signal_id": signal_id, "ts_detected": now_iso(), "domain": domain,
            "leaker_id": leaker_id, "platform": platform,
            "post_url": claim.get("post_url", ""), "post_ts": claim.get("post_ts", ""),
            "source_post_id": claim.get("source_post_id", ""),
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
        if counted:
            counted_pairs.add(pair_key)
            scored += 1
        else:
            unpriced += 1
        if row["status"] == "verified":
            verified += 1
    return (f"{handle}: {len(claims)} claims → {scored} priced calls scored, "
            f"{unpriced} unpriced (audit-only), {skipped_dupe} dupes blocked, "
            f"{verified} verified classes", True)


def run_history_page(cfg, ctx, domain, brief, leakers, cand, counted_pairs,
                     progress: list[dict]) -> tuple[str, bool]:
    """Fetch, fully qualify, then durably advance one backward history page.

    The compound boundary changes only after every extraction, lookup, mapping,
    and score in the page succeeds.  Provider gaps and transient errors are
    durable states with an unchanged boundary, so the same page stays retryable.
    """
    ddir = domain_dir(domain)
    row = _progress_row(progress, cand, cfg)
    target_class = cand.get("_call_class") or "-"
    provider = row["provider"]
    backward_exhausted = row.get("status") == "exhausted"
    arrival_summaries: list[str] = []
    source_now = utc_now()

    newest_ts = row.get("newest_ts") or ""
    newest_ids = _frontier_ids(row["newest_ids"]) if newest_ts else set()
    while newest_ts:
        try:
            updates = fetch_history_updates(
                cand["platform"], cand["handle"], newest_ts, newest_ids,
                cand["_limit"], cfg)
        except Exception as exc:  # noqa: BLE001 - provider retry boundary
            detail = f"arrival fetch failed: {exc}"
            _progress_issue(ddir, progress, row, "retryable_error", detail)
            return f"{cand['handle']}/{target_class}: {detail}", False
        update_posts, timestamp_issue = _validated_history_batch(
            updates.posts, newest_first=False, now=source_now)
        if timestamp_issue:
            _progress_issue(ddir, progress, row, "coverage_gap", timestamp_issue)
            return (f"{cand['handle']}/{target_class}: coverage gap — "
                    f"{timestamp_issue}", False)
        if updates.coverage_gap:
            _progress_issue(ddir, progress, row, "coverage_gap",
                            updates.coverage_gap)
            return (f"{cand['handle']}/{target_class}: coverage gap — "
                    f"{updates.coverage_gap}", False)
        if updates.retryable_error:
            _progress_issue(ddir, progress, row, "retryable_error",
                            updates.retryable_error)
            return (f"{cand['handle']}/{target_class}: provider retry — "
                    f"{updates.retryable_error}", False)
        unsafe = next((post for post in update_posts
                       if not post.get("ts") or not post.get("id")), None)
        if unsafe is not None:
            detail = "provider returned an arrival without timestamp and stable ID"
            _progress_issue(ddir, progress, row, "coverage_gap", detail)
            return f"{cand['handle']}/{target_class}: coverage gap — {detail}", False
        by_identity = {(post["ts"], post["id"]): post for post in update_posts}
        arrivals = [post for post in by_identity.values()
                    if post["ts"] >= row["window_start"]
                    and (post["ts"] > newest_ts
                         or (post["ts"] == newest_ts
                             and post["id"] not in newest_ids))]
        arrivals.sort(key=lambda post: history_post_key(provider, post))
        caught_up = updates.caught_up and len(arrivals) <= cand["_limit"]
        arrivals = arrivals[:cand["_limit"]]
        if not arrivals:
            if caught_up:
                break
            detail = "provider returned an empty non-terminal arrival page"
            _progress_issue(ddir, progress, row, "coverage_gap", detail)
            return f"{cand['handle']}/{target_class}: coverage gap — {detail}", False

        summary, completed = qualify(
            cfg, ctx, domain, brief, leakers, cand, counted_pairs,
            cand["_limit"], row["window_start"], posts=arrivals,
            target_class=target_class)
        if not completed:
            _progress_issue(ddir, progress, row, "retryable_error",
                            f"arrival qualification incomplete: {summary}")
            return summary, False
        new_newest_ts = max(post["ts"] for post in arrivals)
        ids_at_frontier = {post["id"] for post in arrivals
                           if post["ts"] == new_newest_ts}
        if new_newest_ts == newest_ts:
            ids_at_frontier |= newest_ids
        _persist_leaker_projection(ddir, leakers)
        row.update({
            "newest_ts": new_newest_ts,
            "newest_ids": _dump_frontier_ids(provider, ids_at_frontier),
            "status": "exhausted" if backward_exhausted else "active",
            "detail": f"processed {len(arrivals)} newer arrivals",
            "updated_at": _progress_updated_at(),
        })
        _persist_progress(ddir, progress)
        newest_ts, newest_ids = new_newest_ts, ids_at_frontier
        arrival_summaries.append(summary)
        # Re-read after processing even when that provider snapshot was caught
        # up: arrivals may have landed while extraction/scoring was running.

    if backward_exhausted:
        prefix = (f"drained {len(arrival_summaries)} arrival pages; "
                  if arrival_summaries else "")
        return (f"{cand['handle']}/{target_class}: {prefix}history already exhausted",
                True)

    before = None
    if row.get("before_ts") and row.get("before_id"):
        before = (row["before_ts"], row["before_id"])
    try:
        page = fetch_history_page(
            cand["platform"], cand["handle"], row["window_start"], before,
            cand["_limit"], cfg)
    except Exception as exc:  # noqa: BLE001 - keep provider failures retryable
        detail = f"provider fetch failed: {exc}"
        _progress_issue(ddir, progress, row, "retryable_error", detail)
        return f"{cand['handle']}/{target_class}: {detail}", False

    page_posts, timestamp_issue = _validated_history_batch(
        page.posts, newest_first=True, now=source_now)
    if timestamp_issue:
        _progress_issue(ddir, progress, row, "coverage_gap", timestamp_issue)
        return (f"{cand['handle']}/{target_class}: coverage gap — "
                f"{timestamp_issue}", False)
    terminal_gap = page.coverage_gap
    if terminal_gap and (not page.prefix_complete or not page.posts):
        _progress_issue(ddir, progress, row, "coverage_gap", page.coverage_gap)
        return (f"{cand['handle']}/{target_class}: coverage gap — "
                f"{page.coverage_gap}", False)
    if page.retryable_error:
        _progress_issue(ddir, progress, row, "retryable_error", page.retryable_error)
        return (f"{cand['handle']}/{target_class}: provider retry — "
                f"{page.retryable_error}", False)

    unsafe = next((post for post in page_posts
                   if not post.get("ts") or not post.get("id")), None)
    if unsafe is not None:
        detail = "provider returned a post without timestamp and stable ID"
        _progress_issue(ddir, progress, row, "coverage_gap", detail)
        return f"{cand['handle']}/{target_class}: coverage gap — {detail}", False

    by_identity = {(post["ts"], post["id"]): post for post in page_posts}
    before_key = history_boundary_key(provider, *before) if before else None
    eligible = [post for post in by_identity.values()
                if post["ts"] >= row["window_start"]
                and (before_key is None
                     or history_post_key(provider, post) < before_key)]
    eligible.sort(key=lambda post: history_post_key(provider, post), reverse=True)
    page_exhausted = page.exhausted and len(eligible) <= cand["_limit"]
    posts = eligible[:cand["_limit"]]
    if not posts:
        if page_exhausted:
            row.update({"status": "exhausted", "detail": "provider exhausted window",
                        "updated_at": _progress_updated_at()})
            _persist_progress(ddir, progress)
            return f"{cand['handle']}/{target_class}: history exhausted", True
        detail = "provider returned an empty non-terminal history page"
        _progress_issue(ddir, progress, row, "coverage_gap", detail)
        return f"{cand['handle']}/{target_class}: coverage gap — {detail}", False

    summary, completed = qualify(
        cfg, ctx, domain, brief, leakers, cand, counted_pairs,
        cand["_limit"], row["window_start"], posts=posts,
        target_class=target_class)
    if not completed:
        _progress_issue(ddir, progress, row, "retryable_error",
                        f"qualification incomplete: {summary}")
        return summary, False

    oldest_post = min(posts, key=lambda post: history_post_key(provider, post))
    oldest = (oldest_post["ts"], oldest_post["id"])
    if (before_key is not None
            and history_post_key(provider, oldest_post) >= before_key):
        detail = "provider page did not move behind the durable boundary"
        _progress_issue(ddir, progress, row, "coverage_gap", detail)
        return f"{cand['handle']}/{target_class}: coverage gap — {detail}", False
    page_newest_ts = max(post["ts"] for post in posts)
    page_newest_ids = {post["id"] for post in posts
                       if post["ts"] == page_newest_ts}
    current_newest_ts = row.get("newest_ts") or ""
    current_newest_ids = (_frontier_ids(row["newest_ids"])
                          if current_newest_ts else set())
    if current_newest_ts > page_newest_ts:
        durable_newest_ts, durable_newest_ids = (
            current_newest_ts, current_newest_ids)
    elif current_newest_ts == page_newest_ts:
        durable_newest_ts = current_newest_ts
        durable_newest_ids = current_newest_ids | page_newest_ids
    else:
        durable_newest_ts, durable_newest_ids = page_newest_ts, page_newest_ids
    _persist_leaker_projection(ddir, leakers)
    row.update({
        "newest_ts": durable_newest_ts,
        "newest_ids": _dump_frontier_ids(provider, durable_newest_ids),
        "before_ts": oldest[0], "before_id": oldest[1],
        "status": ("coverage_gap" if terminal_gap else
                   "exhausted" if page_exhausted else "active"),
        "detail": (terminal_gap or
                   ("provider exhausted window" if page_exhausted
                    else f"advanced through {len(posts)} posts")),
        "updated_at": _progress_updated_at(),
    })
    _persist_progress(ddir, progress)
    if arrival_summaries:
        summary = f"drained {len(arrival_summaries)} arrival pages; {summary}"
    return summary, page_exhausted and not terminal_gap


def deepen_targets(leakers: list[dict], cap: int,
                   progress: list[dict] | None = None,
                   cfg: dict | None = None) -> list[dict]:
    """Select each unverified leaker×call-class independently."""
    progress = progress or []

    def exhausted(row: dict) -> bool:
        provider = history_provider(row["platform"], cfg) if cfg else None
        matching = [state for state in progress
                    if state.get("platform") == row["platform"]
                    and state.get("handle") == row["handle"]
                    and state.get("call_class") in (row["call_class"], "-")
                    and (provider is None or state.get("provider") in ("", provider))]
        exact = next((state for state in matching
                      if state.get("call_class") == row["call_class"]), None)
        standard = next((state for state in matching
                         if state.get("call_class") == "-"), None)
        return (exact or standard or {}).get("status") == "exhausted"

    eligible = [row for row in leakers
                if row.get("call_class") != "-"
                and row.get("status") not in ("verified", "retired")
                and not exhausted(row)]
    eligible.sort(key=lambda row: (int(row.get("n_calls") or 0),
                                   row.get("leaker_id", ""),
                                   row.get("call_class", "")))
    return [{
        "platform": row["platform"], "handle": row["handle"],
        "status": "deepen", "_call_class": row["call_class"],
        "rationale": f"deepen unverified {row['call_class']} calls",
    } for row in eligible[:cap]]


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
    try:
        progress = load_history_progress(ddir)
    except HistoryProgressError as exc:
        summary = f"mode=coverage-gap; invalid Explorer history state: {exc}"
        write_note("explorer", "run", summary)
        log_result("explorer", args.domain, summary)
        return
    signals = reconcile_history_projection(ddir, leakers, cfg, args.domain)
    counted_pairs = _score_credit_pairs(signals)

    added = propose_candidates(cfg, ctx, args.domain, brief, leakers, candidates)
    candidates = read_tsv(ddir / "candidates.tsv")

    now_unix = iso_to_unix(now_iso())
    std_start = unix_to_iso(now_unix - src["history_days"] * 86400)

    # Queue: SEEDS FIRST (a human vouched for them), then new proposals.
    queue = [{"platform": r["platform"], "handle": r["handle"], "status": "seed",
              "rationale": r.get("notes", ""), "_start": std_start,
              "_limit": src["history_max_posts"], "_call_class": "-"}
             for r in leakers if r["call_class"] == "-" and r["status"] == "candidate"
             and not any(x["call_class"] != "-" for x in leakers
                         if x["leaker_id"] == r["leaker_id"])]
    queue += [{**c, "_start": std_start, "_limit": src["history_max_posts"],
               "_call_class": "-"}
              for c in candidates if c["status"] == "new"]
    queue = queue[:candidate_cap(cfg)]
    mode = "qualify"

    if not queue:
        targets = deepen_targets(leakers, 2 if kickstart_active(cfg) else 1,
                                 progress, cfg)
        for t in targets:
            t.update({"_start": std_start, "_limit": src["history_max_posts"]})
        queue = targets
        mode = ("deepen:" + ",".join(
            f"{t['handle']}/{t['_call_class']}" for t in targets)) if targets else "idle"

    summaries = []
    for cand in queue:
        completed = False
        try:
            result, completed = run_history_page(
                cfg, ctx, args.domain, brief, leakers, cand, counted_pairs,
                progress)
            summaries.append(result)
        except Exception as e:  # noqa: BLE001 — skip-and-log boundary (§7)
            summaries.append(f"{cand.get('handle')}: FAILED {e}")
        if completed:
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
