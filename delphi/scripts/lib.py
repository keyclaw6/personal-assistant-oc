#!/usr/bin/env python3
"""Delphi shared helpers: config, TSV I/O, gate math, JSON extraction, logging.

Stdlib only (Python 3.11+). Every number that gates a trade is computed here —
never by an LLM (PROGRAM.md §0.2).
"""
from __future__ import annotations

import csv
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # delphi/


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


def write_tsv(path: Path, rows: list[dict]) -> None:
    """Full rewrite preserving the file's existing header order."""
    cols = tsv_columns(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for row in rows:
            f.write("\t".join(_clean(row.get(c, "")) for c in cols) + "\n")


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

def kelly(p: float, price: float) -> float:
    """Kelly fraction for buying a binary share at `price` with win prob `p`."""
    if price <= 0.0 or price >= 1.0:
        return 0.0
    b = (1.0 - price) / price
    f = (p * b - (1.0 - p)) / b
    return max(0.0, f)


def side_values(side: str, p_yes: float, price_yes: float) -> tuple[float, float]:
    """Return (p_side, price_side) for YES or NO."""
    if side.upper() == "YES":
        return p_yes, price_yes
    return 1.0 - p_yes, 1.0 - price_yes


def compute_edge(side: str, p_yes: float, price_yes: float, slippage: float) -> float:
    p_side, price_side = side_values(side, p_yes, price_yes)
    return p_side - price_side - slippage


def position_size(p_side: float, price_side: float, bankroll: float, th: dict) -> float:
    raw = th["kelly_fraction"] * kelly(p_side, price_side) * bankroll
    return round(min(raw, th["max_stake_frac"] * bankroll), 2)


# ---------- leaker stats (deterministic accounting) ----------

def update_leaker_stats(row: dict, hit: bool, price_at_call: float | None, th: dict) -> dict:
    """Incrementally fold one resolved call into a (leaker, call_class) row.

    Unpriced calls use the conservative fallback from PROGRAM.md §2:
    hits assume a late-consensus price of 0.85, misses assume 0.50 — never
    flattering the leaker.
    """
    n = int(row.get("n_calls") or 0)
    hits = int(row.get("hits") or 0)
    avg_p = float(row.get("avg_price_at_call") or 0.0)
    if price_at_call is None:
        price_at_call = 0.85 if hit else 0.50
    n2 = n + 1
    hits2 = hits + (1 if hit else 0)
    avg_p2 = (avg_p * n + price_at_call) / n2
    hit_rate = hits2 / n2
    est_edge = hit_rate - avg_p2
    row.update({
        "n_calls": n2, "hits": hits2,
        "hit_rate": f"{hit_rate:.3f}",
        "avg_price_at_call": f"{avg_p2:.3f}",
        "est_edge": f"{est_edge:.3f}",
    })
    prior = row.get("status", "candidate")
    if prior != "retired":
        if n2 >= th["verify_min_calls"] and est_edge >= th["verify_min_edge"]:
            row["status"] = "verified"
        elif n2 >= th["verify_min_calls"]:
            row["status"] = "probation"  # enough calls, not enough edge — track, never bet
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

def config_patch(patch: dict, blocked: list[str]) -> tuple[bool, str]:
    """Apply {dotted.key: value} onto config.json. Only EXISTING keys; top-level
    blocked keys rejected. Returns (ok, message)."""
    cfg = load_config()
    for key in patch:
        if key.split(".")[0] in blocked:
            return False, f"blocked key: {key}"
    for key, val in patch.items():
        node = cfg
        parts = key.split(".")
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                return False, f"unknown path: {key}"
            node = node[part]
        if not isinstance(node, dict) or parts[-1] not in node:
            return False, f"unknown key: {key}"
        node[parts[-1]] = val
    (ROOT / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return True, f"patched {', '.join(patch)}"


def kickstart_active(cfg: dict) -> bool:
    until = (cfg.get("kickstart") or {}).get("active_until", "")
    return bool(until) and now_iso() < until
