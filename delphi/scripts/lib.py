#!/usr/bin/env python3
"""Delphi shared helpers: config, TSV I/O, gate math, JSON extraction, logging.

Stdlib only (Python 3.11+). Every number that gates a trade is computed here —
never by an LLM (PROGRAM.md §0.2).
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path

from source_timestamps import SourceTimestampError, validate_source_timestamp

ROOT = Path(__file__).resolve().parent.parent  # delphi/
CANONICAL_MAX_ENTRY_PRICE = Decimal("0.990")
_CANONICAL_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def validate_kickstart_cutoff(value: object) -> datetime:
    """Parse the one canonical UTC form accepted by config and cron."""
    if type(value) is not str or not _CANONICAL_UTC_TIMESTAMP.fullmatch(value):
        raise ValueError("kickstart.active_until must be canonical UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(
            "kickstart.active_until is not a valid UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("kickstart.active_until is not canonical")
    return parsed


def canonical_position_shares(size: Decimal, entry: Decimal) -> Decimal:
    """Return exact paper shares from canonical cents/three-decimal fill."""
    if (type(size) is not Decimal or type(entry) is not Decimal
            or not size.is_finite() or not entry.is_finite()
            or max(0, -size.as_tuple().exponent) != 2
            or max(0, -entry.as_tuple().exponent) != 3
            or size < Decimal("1.00")
            or not Decimal("0") < entry <= CANONICAL_MAX_ENTRY_PRICE):
        raise ValueError("invalid canonical position economics")
    try:
        return (size / entry).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise ValueError("position shares are outside safe range") from exc


# ---------- config / paths ----------

def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def domain_dir(domain: str) -> Path:
    return ROOT / "domains" / domain


def tmp_dir() -> Path:
    d = ROOT / "tmp"
    d.mkdir(exist_ok=True)
    return d


# ---------- time ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_unix(iso: str) -> int:
    if not iso:
        return 0
    s = iso.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(iso.strip()[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def unix_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gen_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


# ---------- TSV state ----------

def read_tsv(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter="\t")]


def tsv_columns(path: Path) -> list[str]:
    with open(path, newline="", encoding="utf-8") as f:
        return f.readline().rstrip("\n").split("\t")


def _clean(v) -> str:
    return str("" if v is None else v).replace("\t", " ").replace("\n", " ").strip()


def append_tsv(path: Path, row: dict) -> None:
    cols = tsv_columns(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        f.write("\t".join(_clean(row.get(c, "")) for c in cols) + "\n")


def append_tsv_atomic(path: Path, row: dict) -> None:
    """Logically append one row through a durable full-file replacement.

    The temporary file lives beside the destination, which keeps os.replace
    on one filesystem. Existing bytes are copied verbatim; if an interrupted
    legacy append left no row terminator, that evidence is preserved as its
    own incomplete row before the new complete row is appended.
    """
    path = Path(path)
    cols = tsv_columns(path)
    payload = ("\t".join(_clean(row.get(c, "")) for c in cols) + "\n").encode()
    mode = path.stat().st_mode & 0o7777
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w+b") as dst, open(path, "rb") as src:
            shutil.copyfileobj(src, dst)
            if dst.tell():
                dst.seek(-1, os.SEEK_END)
                if dst.read(1) != b"\n":
                    dst.seek(0, os.SEEK_END)
                    dst.write(b"\n")
            dst.seek(0, os.SEEK_END)
            dst.write(payload)
            os.fchmod(dst.fileno(), mode)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def write_tsv(path: Path, rows: list[dict]) -> None:
    """Full rewrite, ATOMIC (tmp + os.replace) so a concurrent reader never sees
    a torn file and a crash never leaves a truncated one (F4)."""
    path = Path(path)
    cols = tsv_columns(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for row in rows:
            f.write("\t".join(_clean(row.get(c, "")) for c in cols) + "\n")
    os.replace(tmp, path)


def log_result(script: str, domain: str, summary: str) -> None:
    line = {"ts": now_iso(), "script": script, "domain": domain, "summary": summary}
    append_tsv(ROOT / "ledger" / "results.tsv", line)
    print(f"[{line['ts']}] {script}({domain}): {summary}")


# ---------- LLM output parsing ----------

def extract_json(text: str):
    """Best-effort: parse the first JSON object found in an LLM reply."""
    if not text:
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end <= start:
        return None
    for candidate in (t[start:end + 1], t[start:]):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


# ---------- gate math (PROGRAM.md §2) ----------


def side_values(side: str, p_yes: float, price_yes: float) -> tuple[float, float]:
    """Return (p_side, price_side) for YES or NO."""
    if side.upper() == "YES":
        return p_yes, price_yes
    return 1.0 - p_yes, 1.0 - price_yes


def compute_edge(side: str, p_yes: float, price_yes: float, slippage: float) -> float:
    p_side, price_side = side_values(side, p_yes, price_yes)
    return p_side - price_side - slippage


# ---------- leaker stats (deterministic accounting) ----------

def _canonical_credit_identifier(value) -> str | None:
    if (type(value) is not str or not value or value != value.strip()
            or not all(char.isprintable() and not char.isspace()
                       for char in value)):
        return None
    return value


def score_credit_key(leaker_id, market_id) -> tuple[str, str] | None:
    """Return the exact validated ``(leaker_id, market_id)`` credit key.

    Event IDs are context only. Invalid identities cannot own or collapse a
    credit bucket.
    """
    if (_canonical_credit_identifier(leaker_id) is None
            or _canonical_credit_identifier(market_id) is None):
        return None
    return leaker_id, market_id


def score_credit_order_key(signal: dict, *, require_source: bool = False,
                           now=None) -> tuple[str, str, str] | None:
    """Return canonical source order, with signal ID fallback for legacy rows."""
    try:
        post_ts = validate_source_timestamp(signal.get("post_ts"), now=now)
    except SourceTimestampError:
        return None
    fallback = _canonical_credit_identifier(signal.get("signal_id"))
    if fallback is None:
        return None
    if "source_post_id" not in signal:
        if require_source:
            return None
        source_post_id = fallback
    else:
        source_post_id = _canonical_credit_identifier(
            signal.get("source_post_id"))
        if source_post_id is None:
            return None
    return post_ts, source_post_id, fallback


def score_credit_price(value) -> float | None:
    """Return a finite prediction-market call price in the inclusive unit range."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and (not value or value != value.strip()):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and 0.0 <= price <= 1.0 else None


def wilson_lower(hits: int, n: int, z: float = 1.2816) -> float:
    """One-sided Wilson lower confidence bound on a binomial proportion.
    Default z=1.2816 ≈ 90% one-sided. Guards the verification gate against
    small-sample luck (F3: a 6/10 coin-flipper must not verify)."""
    if n <= 0:
        return 0.0
    ph = hits / n
    denom = 1.0 + z * z / n
    center = ph + z * z / (2 * n)
    rad = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return max(0.0, (center - rad) / denom)


def update_leaker_stats(row: dict, hit: bool, price_at_call: float | None,
                        th: dict, live: bool = False) -> dict:
    """Fold one resolved call into a (leaker, call_class) row.

    F1: ONLY calls with a genuine observed price at-or-before post time count
    toward verification. Unpriced calls are audit-only: they increment
    n_unpriced and never move the gate.
    F3: the gate uses the Wilson lower bound, not the point estimate:
        edge_lcb = wilson_lower(hits, n) − avg_price_at_call ≥ verify_min_edge
    Status is recomputed on every fold, so live results can also DEMOTE a
    verified leaker back to probation — historical verification is provisional
    and continuously re-tested prospectively. n_live counts the prospective
    (live-tracked) priced folds so the historical/live split stays visible.
    """
    if price_at_call is None:
        row["n_unpriced"] = int(row.get("n_unpriced") or 0) + 1
        return row
    if live:
        row["n_live"] = int(row.get("n_live") or 0) + 1
    n = int(row.get("n_calls") or 0)
    hits = int(row.get("hits") or 0)
    avg_p = float(row.get("avg_price_at_call") or 0.0)
    n2 = n + 1
    hits2 = hits + (1 if hit else 0)
    avg_p2 = (avg_p * n + price_at_call) / n2
    hit_rate = hits2 / n2
    lcb = wilson_lower(hits2, n2, float(th.get("verify_z", 1.2816)))
    edge_lcb = lcb - avg_p2
    edge_lcb_text = f"{edge_lcb:.3f}"
    if edge_lcb_text == "-0.000":
        edge_lcb_text = "0.000"
    row.update({
        "n_calls": n2, "hits": hits2,
        "hit_rate": f"{hit_rate:.3f}",
        "avg_price_at_call": f"{avg_p2:.3f}",
        "est_edge": f"{hit_rate - avg_p2:.3f}",
        "edge_lcb": edge_lcb_text,
    })
    prior = row.get("status", "candidate")
    if prior != "retired":
        if n2 >= th["verify_min_calls"] and edge_lcb >= th["verify_min_edge"]:
            row["status"] = "verified"
        elif n2 >= th["verify_min_calls"]:
            row["status"] = "probation"  # enough calls, not enough proven edge
        elif n2 >= 3:
            row["status"] = "probation"
    return row


def leaker_row(leakers: list[dict], leaker_id: str, call_class: str) -> dict | None:
    for r in leakers:
        if r["leaker_id"] == leaker_id and r["call_class"] == call_class:
            return r
    return None


def ensure_leaker_row(leakers: list[dict], base: dict, call_class: str) -> dict:
    existing = leaker_row(leakers, base["leaker_id"], call_class)
    if existing:
        return existing
    row = {c: "" for c in base.keys()}
    row.update({
        "leaker_id": base["leaker_id"], "platform": base["platform"],
        "handle": base["handle"], "domain": base["domain"],
        "call_class": call_class, "status": "candidate",
        "n_calls": 0, "hits": 0, "notes": "auto-created by qualification",
    })
    leakers.append(row)
    return row


# ---------- agent workspaces (PROGRAM.md §1) ----------

def agent_dir(name: str) -> Path:
    return ROOT / "agents" / name


def agent_context(name: str, max_notes: int = 2) -> str:
    """Assemble an agent's standing context: AGENT.md + MEMORY.md + recent notes."""
    parts = []
    for fname in ("AGENT.md", "MEMORY.md"):
        p = agent_dir(name) / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    mem = agent_dir(name) / "memory"
    if max_notes > 0 and mem.exists():
        for n in sorted(mem.glob("*.md"), reverse=True)[:max_notes]:
            parts.append(f"## Recent note: {n.name}\n"
                         + n.read_text(encoding="utf-8")[:2500])
    return "\n\n".join(parts)


def write_note(name: str, slug: str, content: str) -> Path:
    """Dated, append-safe episodic note in the agent's own workspace."""
    d = agent_dir(name) / "memory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{time.strftime('%Y-%m-%d')}-{slug}.md"
    header = f"# {slug} — {now_iso()}\n\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write((header if not p.exists() or p.stat().st_size == 0 else f"\n---\n{header}")
                + content.strip() + "\n")
    return p


def append_lessons(name: str, lessons) -> int:
    """Append the agent's end-of-run lessons to its MEMORY.md (≤3, deduped)."""
    if not lessons:
        return 0
    p = agent_dir(name) / "MEMORY.md"
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    date = time.strftime("%Y-%m-%d")
    added = 0
    with open(p, "a", encoding="utf-8") as f:
        for lesson in list(lessons)[:3]:
            line = _clean(lesson)
            if line and line not in existing:
                f.write(f"- {date}: {line}\n")
                added += 1
    return added


# ---------- guarded config patch (orchestrator authority, PROGRAM.md §6) ----------
#
# F7: an exact ALLOWLIST with type/range validation, not a denylist. Everything
# else — thresholds/gates, sizing, roles, bankroll, isolation, this spec — is
# founder-only. The spec lives in code, which no agent can edit.

CONFIG_PATCH_ALLOWED: dict[str, tuple[str, tuple | None]] = {
    "kickstart.active_until":                    ("utc",  None),
    "kickstart.explorer_max_candidates_per_run": ("int",  (1, 12)),
    "sources.explorer_max_candidates_per_run":   ("int",  (1, 8)),
    "sources.history_days":                      ("int",  (30, 365)),
    "sources.history_max_posts":                 ("int",  (20, 200)),
    "sources.x_backend":                         ("enum", ("exa", "x_api")),
    "cognee.enabled":                            ("bool", None),
    "cognee.search_type":                        ("enum", ("CHUNKS", "RAG_COMPLETION", "GRAPH_COMPLETION")),
    "llm.max_json_retries":                      ("int",  (0, 2)),
}


def _valid_value(val, kind: str, bound) -> bool:
    if kind == "utc":
        try:
            validate_kickstart_cutoff(val)
        except ValueError:
            return False
        return True
    if kind == "str":
        return isinstance(val, str) and 0 < len(val) < 200
    if kind == "int":
        return isinstance(val, int) and not isinstance(val, bool) \
            and bound[0] <= val <= bound[1]
    if kind == "bool":
        return isinstance(val, bool)
    if kind == "enum":
        return val in bound
    return False


def validate_config_patch(patch: dict) -> tuple[bool, str]:
    """Validate an orchestrator patch without mutating ``config.json``."""
    if not isinstance(patch, dict) or not patch:
        return False, "patch must be a non-empty object"
    for key, val in patch.items():
        spec = CONFIG_PATCH_ALLOWED.get(key)
        if spec is None:
            return False, f"key not in allowlist: {key}"
        if not _valid_value(val, spec[0], spec[1]):
            return False, f"invalid value for {key}: {val!r}"
    return True, f"patched {', '.join(patch)}"


def config_patch(patch: dict) -> tuple[bool, str]:
    """Apply {dotted.key: value} onto config.json — allowlisted keys only,
    type/range validated, atomic write. Returns (ok, message)."""
    ok, message = validate_config_patch(patch)
    if not ok:
        return False, message
    cfg = load_config()
    for key, val in patch.items():
        node = cfg
        parts = key.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = val
    tmp = ROOT / "config.json.tmp"
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ROOT / "config.json")
    return True, message


def normalize_class(call_class: str, cfg: dict, domain: str) -> str:
    """Freeze the call-class taxonomy (F3/F5): anything outside the fixed
    per-domain list maps to 'unclassified'."""
    allowed = (cfg.get("call_classes") or {}).get(domain) or []
    c = str(call_class or "").strip().lower()
    return c if c in allowed else "unclassified"


# ---------- weighted cross-leaker aggregation (VISION: "aggregate all the
# different leakers with their weighted score") ----------

def leaker_weight(row: dict) -> float:
    """A leaker×class's aggregation weight = their PROVEN lower-bound edge.
    No proven edge → no weight. Probation counts at half weight."""
    try:
        lcb = float(row.get("edge_lcb") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if int(row.get("n_calls") or 0) < 3 or lcb <= 0.0:
        return 0.0
    return round(lcb * (1.0 if row.get("status") == "verified" else 0.5), 4)


def aggregate_market_signals(signals: list[dict], leakers: list[dict],
                             market_id: str) -> dict:
    """Deterministic weighted aggregate of all live roster calls on a market.

    Each leaker counts ONCE (their latest unresolved call); direction is
    +1 for YES, −1 for NO; weight = leaker_weight of their (leaker, class)
    row, halved again when the call is hedged. `weighted_lean` ∈ [−1, +1].
    This is INPUT for the judge — it never gates or sizes anything itself.
    """
    per_leaker: dict[str, dict] = {}
    for s in signals:
        if s.get("market_id") != market_id or s.get("resolved_outcome"):
            continue
        if s.get("side") not in ("YES", "NO"):
            continue
        if s.get("status") not in ("pending_judge", "tracked_probation", "bet", "pass"):
            continue
        cur = per_leaker.get(s["leaker_id"])
        if cur is None or (s.get("post_ts") or "") > (cur.get("post_ts") or ""):
            per_leaker[s["leaker_id"]] = s
    contributors = []
    score = wsum = 0.0
    n_yes = n_no = 0
    for lid, s in per_leaker.items():
        row = leaker_row(leakers, lid, s["call_class"]) or {}
        w = leaker_weight(row)
        if s.get("hedged") == "true":
            w *= 0.5
        direction = 1.0 if s["side"] == "YES" else -1.0
        contributors.append({"leaker_id": lid, "call_class": s["call_class"],
                             "side": s["side"], "weight": round(w, 4),
                             "hedged": s.get("hedged") == "true"})
        score += w * direction
        wsum += w
        n_yes += 1 if s["side"] == "YES" else 0
        n_no += 1 if s["side"] == "NO" else 0
    contributors.sort(key=lambda c: -c["weight"])
    return {"n_leakers": len(per_leaker), "n_yes": n_yes, "n_no": n_no,
            "weighted_score": round(score, 4),
            "weighted_lean": round(score / wsum, 3) if wsum > 0 else 0.0,
            "contributors": contributors}


def format_aggregate(agg: dict) -> str:
    if not agg["n_leakers"]:
        return "no live roster calls on this market"
    lines = [f"roster leakers with live calls: {agg['n_leakers']} "
             f"(YES {agg['n_yes']} / NO {agg['n_no']}) | weighted lean "
             f"{agg['weighted_lean']:+.2f} (−1 = all proven weight on NO, "
             f"+1 = all proven weight on YES; weight = each leaker's "
             f"lower-bound edge, halved for probation and for hedged calls)"]
    for c in agg["contributors"][:8]:
        lines.append(f"- {c['leaker_id']} [{c['call_class']}] {c['side']} "
                     f"weight {c['weight']:.3f}" + (" (hedged)" if c["hedged"] else ""))
    return "\n".join(lines)


def kickstart_active(cfg: dict) -> bool:
    until = (cfg.get("kickstart") or {}).get("active_until", "")
    try:
        cutoff = validate_kickstart_cutoff(until)
    except ValueError:
        return False
    return datetime.now(timezone.utc) < cutoff
