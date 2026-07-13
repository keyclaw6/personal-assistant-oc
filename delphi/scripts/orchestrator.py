#!/usr/bin/env python3
"""Orchestrator (hourly): top-level maintainer / goal-direction agent.

Reads the whole machine's state, diagnoses against the goal, applies AT MOST
ONE allowlisted amendment per run (script-enforced), reviews due experiments,
and logs everything: ledger/learnings.md row + dated note in its own workspace
(PROGRAM.md §6). It can change the harness, never the scoreboard.
"""
from __future__ import annotations

import argparse
import re
import time

import cognee
from lib import (ROOT, agent_context, agent_dir, append_lessons, config_patch,
                 domain_dir, kickstart_active, load_config, log_result,
                 now_iso, read_tsv, write_note)
from llm import call_json

AGENTS = ["explorer", "heartbeat", "judge", "orchestrator"]


def tail(path, n):
    p = ROOT / path
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-n:])


def domain_summary(domain: str) -> str:
    ddir = domain_dir(domain)
    leakers = read_tsv(ddir / "leakers.tsv")
    signals = read_tsv(ddir / "signals.tsv")
    positions = read_tsv(ddir / "positions.tsv")
    resolved = read_tsv(ddir / "resolved.tsv")
    by = {}
    for r in leakers:
        by[r["status"]] = by.get(r["status"], 0) + 1
    cutoff = time.strftime("%Y-%m-%dT", time.gmtime(time.time() - 48 * 3600))
    recent = [s for s in signals if s["ts_detected"] >= cutoff]
    sby = {}
    for s in recent:
        sby[s["status"]] = sby.get(s["status"], 0) + 1
    hist = sum(1 for s in signals if s["status"] == "historical")
    nomkt = sum(1 for s in signals if s["status"] == "no_market")
    open_pos = [p for p in positions if p["status"] == "open"]
    exposure = sum(float(p.get("size_usd") or 0) for p in open_pos)
    pnl = sum(float(r.get("pnl_usd") or 0) for r in resolved)
    return (f"### domain {domain}\n"
            f"- leaker rows by status: {by or 'none'}\n"
            f"- signals last 48h by status: {sby or 'none'} | lifetime historical rows: {hist}, no_market: {nomkt}\n"
            f"- open positions: {len(open_pos)} (exposure {exposure:.2f}) | lifetime paper pnl: {pnl:+.2f}\n"
            f"- last 5 historical rows (FP audit sample):\n"
            + "\n".join(f"  {s['leaker_id']} | {s['call_class']} | {s['claim'][:70]} | "
                        f"side {s['side']} | outcome {s['resolved_outcome']} | price {s['price_at_signal']}"
                        for s in [x for x in signals if x["status"] == "historical"][-5:]))


def stuck_heuristics(cfg) -> str:
    res = read_tsv(ROOT / "ledger" / "results.tsv")
    lines = []
    if not any(r["script"] == "explorer" for r in res[-60:]):
        lines.append("explorer has no recent runs in results tail")
    hb = [r for r in res if r["script"] == "heartbeat"][-12:]
    if hb and all("0 new posts" in r["summary"] or "roster empty" in r["summary"] for r in hb):
        lines.append("heartbeat: no new posts in last ~12 runs (sources or roster problem?)")
    jf = sum(1 for r in res[-40:] if "unparseable" in r["summary"] or "FAILED" in r["summary"])
    if jf:
        lines.append(f"{jf} failure mentions in recent results tail")
    lines.append(f"kickstart active: {kickstart_active(cfg)}")
    return "\n".join(f"- {x}" for x in lines) or "- none detected"


def apply_amendment(cfg, amd: dict) -> str:
    """Validate against the allowlist and apply. Returns outcome message."""
    oc = cfg["orchestrator"]
    kind = amd.get("kind")
    exp_id = amd.get("id") or f"exp-{time.strftime('%Y%m%d-%H%M')}"
    if kind == "file":
        rel = str(amd.get("path", "")).lstrip("/").removeprefix("delphi/")
        if not re.match(oc["editable_files_regex"], rel):
            return f"REJECTED file amendment (path not in allowlist): {rel}"
        content = str(amd.get("content", ""))
        if not content.strip():
            return "REJECTED file amendment: empty content"
        (ROOT / rel).write_text(content, encoding="utf-8")
        outcome = f"wrote {rel}"
    elif kind == "config":
        ok, msg = config_patch(dict(amd.get("patch") or {}), oc["config_blocked_keys"])
        if not ok:
            return f"REJECTED config amendment: {msg}"
        outcome = f"config {msg}"
    else:
        return f"REJECTED amendment: unknown kind {kind!r}"
    with open(agent_dir("orchestrator") / "EXPERIMENTS.md", "a", encoding="utf-8") as f:
        f.write(f"| {exp_id} | {now_iso()} | {outcome} | {amd.get('metric', '?')} | "
                f"{amd.get('review_after_hours', 24)}h | live |\n")
    with open(ROOT / "ledger" / "learnings.md", "a", encoding="utf-8") as f:
        f.write(f"| {time.strftime('%Y-%m-%d')} | {outcome} | "
                f"{str(amd.get('rationale', ''))[:160]} | {amd.get('metric', '?')} | pending |\n")
    return outcome


def review_experiments(reviews: list) -> list[str]:
    notes = []
    exp_path = agent_dir("orchestrator") / "EXPERIMENTS.md"
    text = exp_path.read_text(encoding="utf-8") if exp_path.exists() else ""
    for rv in reviews or []:
        eid, verdict = str(rv.get("id", "")), str(rv.get("verdict", ""))
        if not eid or verdict not in ("keep", "revert"):
            continue
        lines = []
        for line in text.splitlines():
            if line.startswith(f"| {eid} ") and "| live |" in line:
                line = line.replace("| live |", f"| {verdict} |")
            lines.append(line)
        text = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")
        with open(ROOT / "ledger" / "learnings.md", "a", encoding="utf-8") as f:
            f.write(f"| {time.strftime('%Y-%m-%d')} | experiment {eid} verdict: {verdict} | "
                    f"{str(rv.get('reason', ''))[:160]} | - | {verdict} |\n")
        notes.append(f"{eid}:{verdict}")
    if notes:
        exp_path.write_text(text, encoding="utf-8")
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="diagnose only, apply nothing")
    args = ap.parse_args()
    cfg = load_config()

    state = ["## RUN LOG (tail)", tail("ledger/results.tsv", 40),
             "## STUCK-STATE HEURISTICS", stuck_heuristics(cfg),
             "## LEARNINGS (tail)", tail("ledger/learnings.md", 12),
             "## EXPERIMENTS", tail("agents/orchestrator/EXPERIMENTS.md", 20)]
    for d in cfg["domains"]:
        state.append(domain_summary(d))
    for a in AGENTS:
        if a == "orchestrator":
            continue
        state.append(f"## AGENT {a} MEMORY.md\n" + tail(f"agents/{a}/MEMORY.md", 40))
        mem = agent_dir(a) / "memory"
        latest = sorted(mem.glob("*.md"), reverse=True)[:1] if mem.exists() else []
        if latest:
            state.append(f"## AGENT {a} latest note ({latest[0].name})\n"
                         + latest[0].read_text(encoding="utf-8")[:1200])
    ctx = cognee.search("orchestrator open problems experiments delphi", 2)
    if ctx:
        state.append("## RETRIEVED (cognee)\n" + "\n".join(ctx))

    prompt = (agent_context("orchestrator")
              + "\n\n" + (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
              + "\n\n# CURRENT STATE\n" + "\n\n".join(state)
              + "\n\n## REQUEST\nRun your hourly maintenance pass now. JSON only.")
    j = call_json("orchestrator", prompt, cfg)
    if not j:
        log_result("orchestrator", "all", "LLM output unparseable — no action taken")
        return

    actions = []
    reviews = review_experiments(j.get("experiments_review") or [])
    if reviews:
        actions.append("reviews " + ",".join(reviews))
    amd = j.get("amendment")
    if amd and not args.dry_run:
        actions.append(apply_amendment(cfg, amd))
    elif amd:
        actions.append("dry-run: amendment skipped")
    note = str(j.get("note") or j.get("observations") or "no note produced")
    write_note("orchestrator", f"run-{time.strftime('%H%M')}", note)
    cognee.add(note[:1500], meta="orchestrator note")
    append_lessons("orchestrator", j.get("lessons"))
    log_result("orchestrator", "all",
               ("; ".join(actions) or "observation only") + " | "
               + str(j.get("observations", ""))[:200])


if __name__ == "__main__":
    main()
