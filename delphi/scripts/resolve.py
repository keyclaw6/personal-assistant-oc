#!/usr/bin/env python3
"""Resolve (every 6 h): close paper positions on resolved markets (P&L, Brier)
and fold resolved signals into per-leaker per-call-class stats.

Review fixes baked in:
- A position with a complete, validated settlement in resolved.tsv is never
  paid again, even after a crash between settlement and status persistence.
- `expired` (and stale pending_judge on closed markets) signals ARE folded
  — fast-resolving calls are not selectively omitted.
- At most ONE fold per (leaker, market) pair, earliest post wins; the
  chosen row is marked stat_counted=true, duplicates false.
- Scorecards are deterministic projections of the signal ledger and are
  rebuilt every run, so a crash between signal and leaker persistence heals.
- P&L uses recorded shares bought at the slippage-adjusted fill.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

import cognee
import polymarket as pm
from lib import (CANONICAL_MAX_ENTRY_PRICE, append_tsv_atomic,
                 canonical_position_shares, domain_dir, ensure_leaker_row,
                 load_config, log_result, now_iso, read_tsv, score_credit_key,
                 score_credit_order_key, score_credit_price, side_values,
                 tsv_columns, update_leaker_stats, write_tsv)


ROSTER_COLUMNS = (
    "leaker_id", "platform", "handle", "domain", "call_class", "status",
    "n_calls", "hits", "hit_rate", "avg_price_at_call", "est_edge",
    "edge_lcb", "n_unpriced", "n_live", "last_seen_ts", "notes",
)
STAT_FIELDS = ("n_calls", "hits", "hit_rate", "avg_price_at_call", "est_edge",
               "edge_lcb", "n_unpriced", "n_live")
ROSTER_STATUS_RANK = {
    "verified": 0,
    "probation": 1,
    "candidate": 2,
    "retired": 3,
}
CANONICAL_ROSTER_EDGE = re.compile(r"-?(?:0|[1-9]\d*)\.\d{3}\Z")
CANONICAL_ROSTER_COUNT = re.compile(r"(?:0|[1-9]\d*)\Z")
CANONICAL_X_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}\Z")
CANONICAL_REDDIT_HANDLE = re.compile(r"[A-Za-z0-9_-]{3,20}\Z")
CANONICAL_CALL_CLASS = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SETTLEMENT_ID_FIELDS = ("position_id", "signal_id", "market_id")
SETTLEMENT_PROVENANCE_FIELDS = ("leaker_id", "call_class")
SETTLEMENT_NUMBER_FIELDS = ("entry_price", "size_usd", "exit_value", "pnl_usd",
                            "brier")
MAX_FLOAT_DECIMAL = Decimal("1.7976931348623157e308")
LEGACY_DUPLICATE_MARKER = "duplicate call on event — not scored"
MARKET_DUPLICATE_MARKER = "duplicate call on market — not scored"


class RosterProjectionError(ValueError):
    """The scorecard ledger cannot produce a canonical ranked projection."""


def _roster_identifier(value, field: str) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or any(char.isspace() or not char.isprintable() for char in value)):
        raise RosterProjectionError(f"invalid roster {field}")
    return value


def _roster_identity(row: dict) -> tuple[str, str]:
    leaker_id = _roster_identifier(row.get("leaker_id"), "leaker_id")
    platform = row.get("platform")
    handle = row.get("handle")
    handle_pattern = (CANONICAL_X_HANDLE if platform == "x"
                      else CANONICAL_REDDIT_HANDLE if platform == "reddit"
                      else None)
    if (handle_pattern is None or type(handle) is not str
            or handle_pattern.fullmatch(handle) is None
            or leaker_id != f"{platform}-{handle}".lower()):
        raise RosterProjectionError("invalid roster leaker_id")
    call_class = _roster_call_class(row.get("call_class"))
    return leaker_id, call_class


def _roster_call_class(value) -> str:
    if (type(value) is not str or value != "-"
            and CANONICAL_CALL_CLASS.fullmatch(value) is None):
        raise RosterProjectionError("invalid roster call_class")
    return value


def _roster_sample_count(value) -> int:
    if type(value) is int:
        if value < 0:
            raise RosterProjectionError("invalid roster n_calls")
        return value
    if (type(value) is not str
            or CANONICAL_ROSTER_COUNT.fullmatch(value) is None):
        raise RosterProjectionError("invalid roster n_calls")
    return int(value)


def _roster_edge(value, n_calls: int) -> Decimal:
    if n_calls == 0:
        if value != "":
            raise RosterProjectionError("invalid roster edge_lcb")
        return Decimal("-Infinity")
    if (type(value) is not str
            or CANONICAL_ROSTER_EDGE.fullmatch(value) is None):
        raise RosterProjectionError("invalid roster edge_lcb")
    try:
        edge = Decimal(value)
    except InvalidOperation as exc:
        raise RosterProjectionError("invalid roster edge_lcb") from exc
    if (not edge.is_finite() or not Decimal("-1") <= edge <= Decimal("1")
            or edge.is_zero() and edge.is_signed()):
        raise RosterProjectionError("invalid roster edge_lcb")
    return edge


def _validate_taxonomy_list(value) -> list[str]:
    if type(value) is not list or not value:
        raise RosterProjectionError("invalid roster call-class taxonomy")
    try:
        classes = [_roster_call_class(item) for item in value]
    except RosterProjectionError as exc:
        raise RosterProjectionError(
            "invalid roster call-class taxonomy") from exc
    if "-" in classes or len(set(classes)) != len(classes):
        raise RosterProjectionError("invalid roster call-class taxonomy")
    return classes


def validate_domain_taxonomy(cfg: dict, domain: str) -> list[str]:
    """Return one requested domain's exact frozen producer taxonomy."""
    if type(cfg) is not dict:
        raise RosterProjectionError("invalid call_classes config")
    configured = cfg.get("call_classes")
    if type(configured) is not dict or domain not in configured:
        raise RosterProjectionError("missing domain call-class taxonomy")
    return _validate_taxonomy_list(configured[domain])


def rank_roster(leakers: list[dict], *,
                allowed_call_classes: list[str] | None = None) -> list[dict]:
    """Return the canonical best-to-worst scorecard projection.

    Status dominates performance because only verified rows are bet-eligible;
    within a status, proven lower-bound edge and then priced sample size rank
    descending. The scorecard identity is the final ascending total tie-break.
    """
    allowed = (set(_validate_taxonomy_list(allowed_call_classes))
               if allowed_call_classes is not None else None)
    ranked: list[tuple[tuple, dict]] = []
    seen: set[tuple[str, str]] = set()
    for row in leakers:
        if type(row) is not dict or set(row) != set(ROSTER_COLUMNS):
            raise RosterProjectionError("invalid roster row shape")
        leaker_id, call_class = _roster_identity(row)
        if (allowed is not None and call_class != "-"
                and call_class not in allowed):
            raise RosterProjectionError(
                "roster call_class outside domain taxonomy")
        identity = (leaker_id, call_class)
        if identity in seen:
            raise RosterProjectionError(
                f"duplicate roster identity {leaker_id}/{call_class}")
        seen.add(identity)
        status = row.get("status")
        if type(status) is not str or status not in ROSTER_STATUS_RANK:
            raise RosterProjectionError("invalid roster status")
        n_calls = _roster_sample_count(row.get("n_calls"))
        if status in ("verified", "probation") and n_calls == 0:
            raise RosterProjectionError("invalid roster status/sample count")
        edge = _roster_edge(row.get("edge_lcb"), n_calls)
        ranked.append(((ROSTER_STATUS_RANK[status], -edge, -n_calls,
                        leaker_id, call_class), row))
    ranked.sort(key=lambda item: item[0])
    return [row for _, row in ranked]


def validate_persisted_roster(path, leakers: list[dict], *,
                              allowed_call_classes: list[str] | None = None) -> None:
    """Fail closed on a noncanonical persisted roster before Resolve acts."""
    try:
        columns = tuple(tsv_columns(path))
    except (OSError, UnicodeError) as exc:
        raise RosterProjectionError("invalid roster header") from exc
    if columns != ROSTER_COLUMNS:
        raise RosterProjectionError("invalid roster header")
    if any(type(row) is not dict
           or set(row) != set(ROSTER_COLUMNS)
           or any(type(row.get(column)) is not str for column in ROSTER_COLUMNS)
           for row in leakers):
        raise RosterProjectionError("invalid roster row shape")
    rank_roster(leakers, allowed_call_classes=allowed_call_classes)


def validate_signal_call_classes(signals: list[dict],
                                 allowed_call_classes: list[str]) -> None:
    """Reject signal classes that could create an off-taxonomy scorecard."""
    allowed = set(_validate_taxonomy_list(allowed_call_classes))
    for row in signals:
        call_class = _roster_call_class(row.get("call_class"))
        if call_class != "-" and call_class not in allowed:
            raise RosterProjectionError(
                "signal call_class outside domain taxonomy")


def _complete_generated_roster_row(row: dict) -> dict:
    """Give an internally-created scorecard the persisted roster shape."""
    if type(row) is not dict or not set(row).issubset(ROSTER_COLUMNS):
        raise RosterProjectionError("invalid generated roster row shape")
    count_fields = {"n_calls", "hits", "n_unpriced", "n_live"}
    for column in ROSTER_COLUMNS:
        row.setdefault(column, 0 if column in count_fields else "")
    return row


def _canonical_text(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text or text != text.strip():
        return None
    if any(unicodedata.category(char) == "Cc" for char in text):
        return None
    return text


def _canonical_identifier(value) -> str | None:
    text = _canonical_text(value)
    if text is None or any(char.isspace() for char in text):
        return None
    return text


def _canonical_timestamp(value) -> bool:
    text = _canonical_text(value)
    if text is None:
        return False
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == text


def _managed_duplicate_note(value, *, duplicate: bool) -> str:
    """Rebuild only the score projection's duplicate marker."""
    note = str(value or "")
    for marker in (LEGACY_DUPLICATE_MARKER, MARKET_DUPLICATE_MARKER):
        note = note.replace(marker, "")
    note = re.sub(r"\s{2,}", " ", note).strip()
    if duplicate:
        note = f"{note} {MARKET_DUPLICATE_MARKER}".strip()
    return note


def _settlement_numbers(row: dict) -> dict[str, Decimal] | None:
    numbers: dict[str, Decimal] = {}
    try:
        for field in SETTLEMENT_NUMBER_FIELDS:
            text = _canonical_text(row.get(field))
            if text is None:
                return None
            value = Decimal(text)
            if not value.is_finite() or abs(value) > MAX_FLOAT_DECIMAL:
                return None
            numbers[field] = value
    except InvalidOperation:
        return None
    return numbers


def is_valid_settlement(row: dict) -> bool:
    """Return whether a ledger row is complete and internally accountable."""
    identifiers = SETTLEMENT_ID_FIELDS + SETTLEMENT_PROVENANCE_FIELDS
    if any(_canonical_identifier(row.get(field)) is None for field in identifiers):
        return False
    if _canonical_text(row.get("side")) is None:
        return False
    if row.get("side") not in ("YES", "NO") or not _canonical_timestamp(
            row.get("ts_resolved")):
        return False
    numbers = _settlement_numbers(row)
    if numbers is None:
        return False
    entry = numbers["entry_price"]
    size = numbers["size_usd"]
    exit_value = numbers["exit_value"]
    pnl = numbers["pnl_usd"]
    brier = numbers["brier"]
    return (bool(re.fullmatch(
                r"(?:0|[1-9]\d*)\.\d{3}", str(row.get("entry_price", ""))))
            and Decimal("0") < entry <= CANONICAL_MAX_ENTRY_PRICE
            and size >= Decimal("1.00") and exit_value >= 0
            and Decimal("0") <= brier <= Decimal("1")
            and pnl == exit_value - size)


def settlement_matches_position(row: dict, position: dict, signal: dict,
                                winner: str) -> bool:
    """Validate one settlement against its durable position and outcome."""
    if not is_valid_settlement(row) or winner not in ("YES", "NO") or not signal:
        return False
    if any(row.get(field) != position.get(field)
           for field in ("position_id", "signal_id", "market_id", "side")):
        return False
    if signal.get("signal_id") != position.get("signal_id"):
        return False
    if signal.get("market_id") != position.get("market_id"):
        return False
    if signal.get("side") != position.get("side"):
        return False
    if row.get("leaker_id") != signal.get("leaker_id"):
        return False
    if row.get("call_class") != signal.get("call_class"):
        return False

    numbers = _settlement_numbers(row)
    try:
        position_entry = Decimal(_canonical_text(position.get("entry_price")) or "")
        position_size = Decimal(_canonical_text(position.get("size_usd")) or "")
        position_shares = Decimal(_canonical_text(position.get("shares")) or "")
        judge_p = Decimal(_canonical_text(position.get("judge_p")) or "0.5")
    except InvalidOperation:
        return False
    position_numbers = (position_entry, position_size, position_shares, judge_p)
    if not all(value.is_finite() and abs(value) <= MAX_FLOAT_DECIMAL
               for value in position_numbers):
        return False
    if not (Decimal("0") < position_entry <= CANONICAL_MAX_ENTRY_PRICE
            and position_size >= 0 and position_shares >= 0
            and Decimal("0") <= judge_p <= Decimal("1")):
        return False
    try:
        if position_shares != canonical_position_shares(
                position_size, position_entry):
            return False
    except ValueError:
        return False

    try:
        size = position_size
        exit_value = (position_shares
                      if position["side"] == winner else Decimal("0"))
        pnl = exit_value - size
        p_side = judge_p if position["side"] == "YES" else Decimal("1") - judge_p
        outcome = Decimal("1") if position["side"] == winner else Decimal("0")
        brier = ((p_side - outcome) ** 2).quantize(Decimal("0.0001"))
    except InvalidOperation:
        return False
    return (numbers is not None
            and numbers["entry_price"] == position_entry
            and numbers["size_usd"] == size
            and numbers["exit_value"] == exit_value
            and numbers["pnl_usd"] == pnl
            and numbers["brier"] == brier)


def valid_settlements(rows: list[dict]) -> list[dict]:
    """Select at most one valid settlement per position in ledger order."""
    selected: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        position_id = row.get("position_id")
        if position_id in seen or not is_valid_settlement(row):
            continue
        seen.add(position_id)
        selected.append(row)
    return selected


def valid_position_settlements(rows: list[dict], positions: list[dict],
                               signals: list[dict], winner_for) -> list[dict]:
    """Select one context-matched settlement per durable position."""
    positions_by_id = {p.get("position_id"): p for p in positions}
    signals_by_id = {s.get("signal_id"): s for s in signals}
    selected: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        position_id = row.get("position_id")
        position = positions_by_id.get(position_id)
        if position_id in seen or position is None or not is_valid_settlement(row):
            continue
        signal = signals_by_id.get(position.get("signal_id"), {})
        winner = winner_for(position, signal)
        if not settlement_matches_position(row, position, signal, winner):
            continue
        seen.add(position_id)
        selected.append(row)
    return selected


def rebuild_leaker_stats(signals: list[dict], leakers: list[dict], thresholds: dict,
                         domain: str) -> tuple[bool, list[str]]:
    """Reconcile scorecards from resolved signal rows, deterministically.

    Signals are the durable source of truth. Persisting them before this
    projection means an interrupted run is repaired by the next resolve pass,
    without a second journal or an ambiguous "fold applied" marker.
    """
    # Validate the source projection before mutating it. In particular, a
    # duplicate scorecard identity must not be hidden by dictionary projection.
    leakers[:] = rank_roster(leakers)
    before = {(r.get("leaker_id"), r.get("call_class")):
              tuple(str(r.get(k, "")) for k in ("status",) + STAT_FIELDS)
              for r in leakers}
    prior_status = {key: values[0] for key, values in before.items()}

    for row in leakers:
        if row.get("call_class") == "-":
            continue
        retired = row.get("status") == "retired"
        row.update({"n_calls": 0, "hits": 0, "hit_rate": "",
                    "avg_price_at_call": "", "est_edge": "", "edge_lcb": "",
                    "n_unpriced": 0, "n_live": 0,
                    "status": "retired" if retired else "candidate"})

    resolved = [s for s in signals
                if s.get("resolved_outcome") in ("YES", "NO")
                and s.get("side") in ("YES", "NO")]
    ordered: list[tuple[tuple[str, str, str], dict]] = []
    for signal in resolved:
        signal["note"] = _managed_duplicate_note(
            signal.get("note"), duplicate=False)
        order = score_credit_order_key(signal)
        if order is None:
            signal["stat_counted"] = "false"
            marker = "invalid score credit identity — not scored"
            if marker not in signal["note"]:
                signal["note"] = f"{signal['note']} {marker}".strip()
            continue
        ordered.append((order, signal))
    ordered.sort(key=lambda item: item[0])

    counted_pairs: set[tuple[str, str]] = set()
    for _order, s in ordered:
        pair = score_credit_key(s.get("leaker_id"), s.get("market_id"))
        if pair is None:
            s["stat_counted"] = "false"
            marker = "invalid score credit identity — not scored"
            if marker not in s.get("note", ""):
                s["note"] = (s.get("note", "") + " " + marker).strip()
            continue
        price_yes = score_credit_price(s.get("price_at_signal"))
        base = {"leaker_id": s["leaker_id"], "platform": s.get("platform", ""),
                "handle": s["leaker_id"].split("-", 1)[-1], "domain": domain,
                "call_class": s["call_class"], "status": "candidate",
                "n_calls": 0, "hits": 0, "notes": ""}
        if price_yes is None:
            row = _complete_generated_roster_row(
                ensure_leaker_row(leakers, base, s["call_class"]))
            update_leaker_stats(row, s["side"] == s["resolved_outcome"], None,
                                thresholds, live=s.get("status") != "historical")
            s["stat_counted"] = "false"
            continue
        if pair in counted_pairs:
            s["stat_counted"] = "false"
            s["note"] = _managed_duplicate_note(s.get("note"), duplicate=True)
            continue
        counted_pairs.add(pair)
        _, price_side = side_values(s["side"], 0.5, price_yes)
        row = _complete_generated_roster_row(
            ensure_leaker_row(leakers, base, s["call_class"]))
        update_leaker_stats(row, s["side"] == s["resolved_outcome"], price_side,
                            thresholds, live=s.get("status") != "historical")
        s["stat_counted"] = "true"

    after = {(r.get("leaker_id"), r.get("call_class")):
             tuple(str(r.get(k, "")) for k in ("status",) + STAT_FIELDS)
             for r in leakers}
    promotions = [f"{lid}/{cls}" for (lid, cls), values in after.items()
                  if values[0] == "verified"
                  and prior_status.get((lid, cls)) != "verified"]
    leakers[:] = rank_roster(leakers)
    return before != after, promotions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    call_class_taxonomy = validate_domain_taxonomy(cfg, args.domain)
    th = cfg["thresholds"]
    ddir = domain_dir(args.domain)
    roster_path = ddir / "leakers.tsv"
    leakers = read_tsv(roster_path)
    validate_persisted_roster(
        roster_path, leakers, allowed_call_classes=call_class_taxonomy)
    signals = read_tsv(ddir / "signals.tsv")
    validate_signal_call_classes(signals, call_class_taxonomy)
    positions = read_tsv(ddir / "positions.tsv")
    resolved_rows = read_tsv(ddir / "resolved.tsv")

    market_cache: dict[str, dict | None] = {}

    def market(mid: str):
        if mid not in market_cache:
            market_cache[mid] = pm.get_market(mid)
        return market_cache[mid]

    def winner_for(position: dict, signal: dict) -> str | None:
        current = market(position["market_id"])
        if current is not None:
            if not current["closed"]:
                return None
            provider_winner = pm.winning_side(current)
            return provider_winner if provider_winner in ("YES", "NO") else None
        if (signal.get("market_id") == position.get("market_id")
                and signal.get("resolved_outcome") in ("YES", "NO")):
            return signal["resolved_outcome"]
        return None

    # 1) close positions (idempotent, F4)
    n_closed, pnl_total = 0, Decimal("0")
    sig_by_id = {s["signal_id"]: s for s in signals}
    for p in positions:
        if p.get("status") != "open":
            continue
        m = market(p["market_id"])
        if not m or not m["closed"]:
            continue
        winner = pm.winning_side(m)
        if winner is None:
            p["note"] = (p.get("note", "") + " closed but ambiguous — held (§7)").strip()
            continue
        sig = sig_by_id.get(p["signal_id"], {})
        if any(settlement_matches_position(row, p, sig, winner)
               for row in resolved_rows
               if row.get("position_id") == p["position_id"]):
            p["status"] = "closed"
            continue
        win = (p["side"] == winner)
        try:
            shares = Decimal(_canonical_text(p.get("shares")) or "")
            size = Decimal(_canonical_text(p.get("size_usd")) or "")
            p_yes = Decimal(_canonical_text(p.get("judge_p")) or "0.5")
            exit_value = shares if win else Decimal("0")
            pnl = exit_value - size
            p_side = p_yes if p["side"] == "YES" else Decimal("1") - p_yes
            brier = ((p_side - (Decimal("1") if win else Decimal("0"))) ** 2)
            brier = brier.quantize(Decimal("0.0001"))
        except InvalidOperation as exc:
            raise ValueError(
                f"refusing invalid position economics for {p['position_id']}") from exc
        settlement = {
            "position_id": p["position_id"], "signal_id": p["signal_id"],
            "ts_resolved": now_iso(), "market_id": p["market_id"],
            "side": p["side"], "entry_price": p["entry_price"],
            "size_usd": f"{size:.2f}", "exit_value": f"{exit_value:.2f}",
            "pnl_usd": f"{pnl:.2f}", "brier": f"{brier:.4f}",
            "leaker_id": sig.get("leaker_id", ""), "call_class": sig.get("call_class", ""),
        }
        if not settlement_matches_position(settlement, p, sig, winner):
            raise ValueError(f"refusing invalid settlement for {p['position_id']}")
        append_tsv_atomic(ddir / "resolved.tsv", settlement)
        resolved_rows.append(settlement)
        p["status"] = "closed"
        n_closed += 1
        pnl_total += pnl
        cognee.add(f"Resolved paper bet: {p['side']} on '{p['market_question'][:100]}' "
                   f"entry {p['entry_price']}, judged p={p.get('judge_p')}, outcome {winner}, "
                   f"pnl {pnl:+.2f}, leaker {sig.get('leaker_id')} class {sig.get('call_class')}",
                   meta="resolved bet")
    write_tsv(ddir / "positions.tsv", positions)  # persist closes before anything else

    # 2) fill outcomes on resolved signals (incl. expired / stale pending, F6)
    foldable_statuses = ("bet", "pass", "tracked_probation", "expired", "pending_judge")
    newly_resolved: list[dict] = []
    for s in signals:
        if not s.get("market_id") or s.get("resolved_outcome"):
            continue
        if s["status"] not in foldable_statuses:
            continue
        m = market(s["market_id"])
        if not m or not m["closed"]:
            continue
        winner = pm.winning_side(m)
        if winner is None:
            continue
        s["resolved_outcome"] = winner
        if s["status"] == "pending_judge":
            s["status"] = "expired"
        if s["side"] in ("YES", "NO"):
            newly_resolved.append(s)

    # 3) Every run reconciles the complete projection. Signals persist first:
    # if the following leaker write is interrupted, the next run replays it.
    aggregates_changed, promotions = rebuild_leaker_stats(
        signals, leakers, th, args.domain)
    leakers[:] = rank_roster(
        leakers, allowed_call_classes=call_class_taxonomy)
    write_tsv(ddir / "signals.tsv", signals)
    write_tsv(ddir / "leakers.tsv", leakers)
    for promoted in promotions:
        lid, cls = promoted.rsplit("/", 1)
        row = next(r for r in leakers
                   if r["leaker_id"] == lid and r["call_class"] == cls)
        cognee.add(f"Leaker promoted to verified: {lid} on {cls} "
                   f"(hit_rate {row['hit_rate']}, edge_lcb {row['edge_lcb']}, "
                   f"n={row['n_calls']})", meta="promotion")

    n_scored = len(newly_resolved)
    if n_closed or n_scored or aggregates_changed:
        cognee.cognify()  # refresh the delphi dataset graph — never per-heartbeat

    resolved_all = valid_position_settlements(
        resolved_rows, positions, signals, winner_for)
    lifetime_pnl = sum((Decimal(r["pnl_usd"]) for r in resolved_all), Decimal("0"))
    equity = Decimal(str(cfg["bankroll_usd"])) + lifetime_pnl
    log_result("resolve", args.domain,
               f"closed {n_closed} positions (pnl {pnl_total:+.2f}); scored {n_scored} signals; "
               f"promotions: {', '.join(promotions) or 'none'}; "
               f"equity {equity:.2f} "
               f"(lifetime pnl {lifetime_pnl:+.2f})")


if __name__ == "__main__":
    main()
