#!/usr/bin/env python3
"""Judge (after each heartbeat): strong-model probability estimate for pending
signals from verified leakers; scripts compute edge and size and open PAPER
positions.

Review fixes baked in:
- Shares/entry/P&L use the slippage-adjusted FILL price on a side-specific
  quote (NO-side book via its own token when available); the paper account is
  self-financing: equity = bankroll + realized P&L − nothing imaginary.
- Deterministic eligibility is checked immediately before judgment and again
  before a position append. Transient lookup/quote failures remain retryable.
- Exposure-stacking guard: one open position per market.
- A per-domain append-only decision journal makes a judged bet/pass recoverable
  across process death.  Its prepared row is the source of truth for terminal
  status and economics; immutable signal fields supply market/order identity;
  positions.tsv and terminal signal fields are idempotent projections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import cognee
import polymarket as pm
from lib import (CANONICAL_MAX_ENTRY_PRICE, ROOT, agent_context,
                 aggregate_market_signals, append_lessons, append_tsv_atomic,
                 canonical_position_shares, domain_dir, format_aggregate,
                 leaker_row, load_config, log_result, now_iso, read_tsv,
                 side_values, write_note, write_tsv)
from llm import call_json

MAX_PER_RUN = 10
JOURNAL_FILE = "judge-decisions.tsv"
MAX_JUDGE_RESPONSE_CHARS = 8_192
MAX_JUDGE_NUMBER_CHARS = 32
JUDGE_RESPONSE_FIELDS = frozenset(
    {"p_yes", "confidence", "rationale", "lessons"})
JUDGE_RETRY_NOTE_PREFIX = "[[judge-retry:"
JUDGE_RETRY_NOTE = JUDGE_RETRY_NOTE_PREFIX + "model-or-output-failure]]"
JUDGE_RETRY_NOTE_RE = re.compile(
    re.escape(JUDGE_RETRY_NOTE_PREFIX) + r"[a-z-]{1,40}\]\]")
MAX_RATIONALE_CHARS = 2_000
MAX_LESSON_CHARS = 500
JSON_DECIMAL_TOKEN = re.compile(r"(?:0|[1-9]\d*)\.\d+")
JOURNAL_COLUMNS = (
    "signal_id", "domain", "market_id", "market_question", "token_id", "side",
    "state", "ts_decided", "position_id", "intended_status",
    "judge_p", "judge_conf", "edge", "quote_price", "slippage", "entry_price",
    "available_usd", "total_equity_usd", "kelly_fraction", "max_stake_frac", "min_edge",
    "judge_min_conf", "size_usd", "shares", "note",
)
JOURNAL_HEADER = "\t".join(JOURNAL_COLUMNS) + "\n"
TERMINAL_STATUSES = {"bet", "pass", "expired"}
DECISION_EVIDENCE_FIELDS = tuple(c for c in JOURNAL_COLUMNS if c != "state")
TRADE_IDENTITY_FIELDS = (
    "domain", "market_id", "market_question", "token_id", "side",
)
ECONOMIC_FIELDS = (
    "judge_p", "judge_conf", "edge", "quote_price", "slippage",
    "entry_price", "available_usd", "total_equity_usd", "kelly_fraction", "max_stake_frac",
    "min_edge", "judge_min_conf", "size_usd", "shares",
)
DECIMAL_FORMATS = {
    "judge_p": r"0\.\d{3}",
    "judge_conf": r"[01]\.\d{2}",
    "edge": r"-?0\.\d{3}",
    "quote_price": r"0\.\d{3}",
    "slippage": r"0\.\d{3}",
    "entry_price": r"0\.\d{3}",
    "available_usd": r"(?:0|[1-9]\d*)\.\d{2}",
    "total_equity_usd": r"(?:0|[1-9]\d*)\.\d{2}",
    "kelly_fraction": r"0\.\d{6}",
    "max_stake_frac": r"0\.\d{6}",
    "min_edge": r"0\.\d{3}",
    "judge_min_conf": r"[01]\.\d{2}",
    "size_usd": r"(?:0|[1-9]\d*)\.\d{2}",
    "shares": r"(?:0|[1-9]\d*)\.\d{2}",
}
POSITION_MONEY_FORMATS = {
    "entry_price": r"(?:0|[1-9]\d*)\.\d{3}",
    "size_usd": r"(?:0|[1-9]\d*)\.\d{2}",
    "shares": r"(?:0|[1-9]\d*)\.\d{2}",
    "judge_p": r"0\.\d{3}",
}
SETTLEMENT_MONEY_FORMATS = {
    "entry_price": r"(?:0|[1-9]\d*)\.\d{3}",
    "size_usd": r"(?:0|[1-9]\d*)\.\d{2}",
    "exit_value": r"(?:0|[1-9]\d*)\.\d{2}",
    "pnl_usd": r"-?(?:0|[1-9]\d*)\.\d{2}",
    "brier": r"(?:0|[1-9]\d*)\.\d{4}",
}


class RetryableDecisionError(RuntimeError):
    """Journal/materialization evidence is unsafe; leave the signal retryable."""


class JudgeOutputError(ValueError):
    """The Judge model response is not one exact, safe response object."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise JudgeOutputError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str):
    raise JudgeOutputError(f"nonstandard JSON number: {value}")


def _reject_json_integer(value: str):
    raise JudgeOutputError(f"Judge numbers must use decimal notation: {value}")


def _parse_json_decimal(value: str) -> Decimal:
    if (len(value) > MAX_JUDGE_NUMBER_CHARS
            or not JSON_DECIMAL_TOKEN.fullmatch(value)):
        raise JudgeOutputError("noncanonical or oversized Judge number")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise JudgeOutputError("invalid Judge number") from exc
    if not number.is_finite() or number.is_zero() and number.is_signed():
        raise JudgeOutputError("non-finite or negative-zero Judge number")
    return number


def _plain_text(value, field: str, limit: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise JudgeOutputError(f"invalid Judge {field}")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise JudgeOutputError(f"unsafe Unicode in Judge {field}")
    return value.strip()


def _validated_judge_number(value, field: str, *, lower: Decimal,
                            upper: Decimal, lower_inclusive: bool,
                            upper_inclusive: bool,
                            quantum: Decimal, max_scale: int) -> float:
    if type(value) is Decimal:
        number = value
    elif type(value) is float and math.isfinite(value):
        number = Decimal(str(value))
    else:
        raise JudgeOutputError(f"Judge {field} must be a finite decimal")
    if (not number.is_finite()
            or number.is_zero() and number.is_signed()
            or number < lower
            or not lower_inclusive and number == lower
            or number > upper
            or not upper_inclusive and number == upper):
        raise JudgeOutputError(f"Judge {field} is outside its domain")
    scale = max(0, -number.as_tuple().exponent)
    if scale > max_scale:
        raise JudgeOutputError(f"Judge {field} exceeds journal scale")
    try:
        if number.quantize(quantum) != number:
            raise JudgeOutputError(
                f"Judge {field} exceeds journal precision")
    except InvalidOperation as exc:
        raise JudgeOutputError(f"invalid Judge {field}") from exc
    converted = float(number)
    if not math.isfinite(converted) or Decimal(str(converted)) != number:
        raise JudgeOutputError(f"lossy Judge {field} conversion")
    return converted


def validate_judge_response(value) -> dict:
    """Validate the exact response contract before any trading state changes."""
    if type(value) is not dict or set(value) != JUDGE_RESPONSE_FIELDS:
        raise JudgeOutputError("Judge response fields do not match the schema")

    p_yes = _validated_judge_number(
        value["p_yes"], "p_yes", lower=Decimal("0"), upper=Decimal("1"),
        lower_inclusive=False, upper_inclusive=False,
        quantum=Decimal("0.001"), max_scale=3)
    confidence = _validated_judge_number(
        value["confidence"], "confidence", lower=Decimal("0"),
        upper=Decimal("1"), lower_inclusive=True, upper_inclusive=True,
        quantum=Decimal("0.01"), max_scale=2)

    rationale = _plain_text(
        value["rationale"], "rationale", MAX_RATIONALE_CHARS)
    lessons = value["lessons"]
    if type(lessons) is not list or len(lessons) > 3:
        raise JudgeOutputError("Judge lessons must be a list of at most 3 items")
    normalized_lessons = [
        _plain_text(lesson, "lesson", MAX_LESSON_CHARS) for lesson in lessons
    ]
    return {
        "p_yes": p_yes,
        "confidence": confidence,
        "rationale": rationale,
        "lessons": normalized_lessons,
    }


def parse_judge_output(text: str) -> dict:
    """Decode one complete Judge JSON object without lossy extraction."""
    if type(text) is not str or not text:
        raise JudgeOutputError("empty Judge response")
    if len(text) > MAX_JUDGE_RESPONSE_CHARS:
        raise JudgeOutputError("Judge response exceeds the raw size limit")
    try:
        if len(text.encode("utf-8")) > MAX_JUDGE_RESPONSE_CHARS:
            raise JudgeOutputError("Judge response exceeds the raw size limit")
    except UnicodeEncodeError as exc:
        raise JudgeOutputError("invalid Unicode in raw Judge response") from exc
    payload = text
    fence_open = "```json\n"
    fence_close = "\n```"
    if payload.startswith(fence_open) and payload.endswith(fence_close):
        payload = payload[len(fence_open):-len(fence_close)]
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
            parse_float=_parse_json_decimal,
            parse_int=_reject_json_integer,
        )
    except JudgeOutputError:
        raise
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise JudgeOutputError("malformed Judge JSON") from exc
    return validate_judge_response(value)


def fault_point(_point: str) -> None:
    """No-op production seam used by crash-boundary regression tests."""


def deterministic_position_id(domain: str, signal_id: str) -> str:
    """Stable ID prevents a replayed prepared bet from duplicating a position."""
    digest = hashlib.sha256(f"{domain}\0{signal_id}".encode()).hexdigest()[:16]
    return f"pos-{digest}"


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_decision_journal(path: Path) -> None:
    """Create a durable empty journal without ever exposing a partial header."""
    path = Path(path)
    if path.exists():
        return
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            f.write(JOURNAL_HEADER)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _number(row: dict, field: str) -> Decimal:
    value = row.get(field, "")
    if not re.fullmatch(DECIMAL_FORMATS[field], value):
        raise RetryableDecisionError(
            f"noncanonical decision journal {field} for {row.get('signal_id')}")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise RetryableDecisionError(
            f"invalid decision journal {field} for {row.get('signal_id')}") from exc
    if not number.is_finite():
        raise RetryableDecisionError(
            f"non-finite decision journal {field} for {row.get('signal_id')}")
    return number


def _sized_stake(p_side: Decimal, entry: Decimal, available_capital: Decimal,
                 total_equity: Decimal, kelly_fraction: Decimal,
                 max_stake_frac: Decimal) -> Decimal:
    if (any(not value.is_finite() for value in (
            p_side, entry, available_capital, total_equity, kelly_fraction,
            max_stake_frac))
            or not Decimal("0") <= p_side <= Decimal("1")
            or not Decimal("0") < entry <= CANONICAL_MAX_ENTRY_PRICE
            or available_capital < 0 or total_equity < 0
            or not Decimal("0") < kelly_fraction <= Decimal("1")
            or not Decimal("0") < max_stake_frac <= Decimal("1")):
        raise RetryableDecisionError("invalid position sizing inputs")
    kelly = max(Decimal("0"), (p_side - entry) / (Decimal("1") - entry))
    try:
        return min(
            kelly_fraction * kelly * available_capital,
            max_stake_frac * total_equity,
        ).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise RetryableDecisionError("position size is outside safe range") from exc


def _position_shares(size: Decimal, entry: Decimal) -> Decimal:
    try:
        return canonical_position_shares(size, entry)
    except ValueError as exc:
        raise RetryableDecisionError("invalid position share inputs") from exc


def canonical_sizing_thresholds(thresholds: dict) -> dict[str, Decimal]:
    """Canonicalize the two JSON sizing thresholds at the config boundary."""
    if type(thresholds) is not dict:
        raise RetryableDecisionError("invalid sizing threshold config")
    canonical: dict[str, Decimal] = {}
    for field in ("kelly_fraction", "max_stake_frac"):
        value = thresholds.get(field)
        if type(value) not in (int, float):
            raise RetryableDecisionError(f"invalid config {field}")
        number = _input_decimal(
            value, f"config {field}", quantum=Decimal("0.000001"))
        if not Decimal("0") < number <= Decimal("1"):
            raise RetryableDecisionError(f"config {field} is outside its range")
        canonical[field] = number
    return canonical


def _input_decimal(value, field: str, *, quantum: Decimal,
                   negative: bool = False) -> Decimal:
    if type(value) is bool or type(value) not in (Decimal, int, float, str):
        raise RetryableDecisionError(f"invalid {field}")
    text = str(value)
    if (not text or len(text) > MAX_JUDGE_NUMBER_CHARS
            or type(value) is str
            and not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", text)):
        raise RetryableDecisionError(f"invalid {field}")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise RetryableDecisionError(f"invalid {field}") from exc
    if (not number.is_finite() or number.is_zero() and number.is_signed()
            or not negative and number < 0):
        raise RetryableDecisionError(f"invalid {field}")
    scale = max(0, -number.as_tuple().exponent)
    target_scale = max(0, -quantum.as_tuple().exponent)
    if scale > target_scale:
        raise RetryableDecisionError(f"over-precise {field}")
    try:
        canonical = number.quantize(quantum)
    except InvalidOperation as exc:
        raise RetryableDecisionError(f"invalid {field}") from exc
    if canonical != number:
        raise RetryableDecisionError(f"over-precise {field}")
    return canonical


def account_capital(bankroll, resolved: list[dict],
                    positions: list[dict]) -> tuple[Decimal, Decimal]:
    """Return exact equity/availability after validating both account ledgers."""
    bankroll_d = _input_decimal(
        bankroll, "bankroll", quantum=Decimal("0.01"))

    positions_by_id: dict[str, tuple[dict, dict[str, Decimal]]] = {}
    position_signal_ids: set[str] = set()
    open_market_ids: set[str] = set()
    open_sizes: list[Decimal] = []
    for row in positions:
        identity = {
            field: _ledger_identifier(row.get(field), f"position {field}")
            for field in ("position_id", "signal_id", "market_id")
        }
        position_id = identity["position_id"]
        signal_id = identity["signal_id"]
        if position_id in positions_by_id or signal_id in position_signal_ids:
            raise RetryableDecisionError("duplicate position identity")
        if row.get("status") not in ("open", "closed"):
            raise RetryableDecisionError(
                f"invalid position status for {position_id}")
        if row.get("side") not in ("YES", "NO"):
            raise RetryableDecisionError(f"invalid position side for {position_id}")
        numbers = {
            field: _ledger_number(
                row.get(field), f"position {field}", pattern)
            for field, pattern in POSITION_MONEY_FORMATS.items()
        }
        if (not Decimal("0") < numbers["entry_price"] <= CANONICAL_MAX_ENTRY_PRICE
                or numbers["size_usd"] < Decimal("1.00")
                or numbers["shares"] <= 0
                or not Decimal("0") < numbers["judge_p"] < Decimal("1")):
            raise RetryableDecisionError(
                f"invalid position economics for {position_id}")
        if numbers["shares"] != _position_shares(
                numbers["size_usd"], numbers["entry_price"]):
            raise RetryableDecisionError(
                f"position shares conflict with size and fill for {position_id}")
        positions_by_id[position_id] = (row, numbers)
        position_signal_ids.add(signal_id)
        if row["status"] == "open":
            if identity["market_id"] in open_market_ids:
                raise RetryableDecisionError("duplicate open market exposure")
            open_market_ids.add(identity["market_id"])
            open_sizes.append(numbers["size_usd"])

    realized_pnls: list[Decimal] = []
    settlement_position_ids: set[str] = set()
    settlement_signal_ids: set[str] = set()
    settlement_credits: set[tuple[str, str]] = set()
    for row in resolved:
        identity = {
            field: _ledger_identifier(row.get(field), f"settlement {field}")
            for field in ("position_id", "signal_id", "market_id",
                          "leaker_id", "call_class")
        }
        position_id = identity["position_id"]
        signal_id = identity["signal_id"]
        credit = (identity["leaker_id"], identity["market_id"])
        if (position_id in settlement_position_ids
                or signal_id in settlement_signal_ids
                or credit in settlement_credits):
            raise RetryableDecisionError("duplicate settlement identity or credit")
        bound = positions_by_id.get(position_id)
        if bound is None or bound[0]["status"] != "closed":
            raise RetryableDecisionError(
                f"settlement is not bound to a closed position: {position_id}")
        position, position_numbers = bound
        if (position.get("signal_id") != signal_id
                or position.get("market_id") != identity["market_id"]
                or row.get("side") not in ("YES", "NO")
                or position.get("side") != row.get("side")
                or not _canonical_utc_timestamp(row.get("ts_resolved"))):
            raise RetryableDecisionError(
                f"settlement identity conflicts with position {position_id}")
        numbers = {
            field: _ledger_number(
                row.get(field), f"settlement {field}", pattern,
                negative=field == "pnl_usd")
            for field, pattern in SETTLEMENT_MONEY_FORMATS.items()
        }
        if (numbers["entry_price"] != position_numbers["entry_price"]
                or numbers["size_usd"] != position_numbers["size_usd"]
                or numbers["exit_value"] not in (
                    Decimal("0.00"), position_numbers["shares"])
                or numbers["pnl_usd"]
                != numbers["exit_value"] - numbers["size_usd"]
                or not Decimal("0") <= numbers["brier"] <= Decimal("1")):
            raise RetryableDecisionError(
                f"invalid settlement economics for {position_id}")
        p_side = (position_numbers["judge_p"] if row["side"] == "YES"
                  else Decimal("1") - position_numbers["judge_p"])
        outcome = (Decimal("1") if numbers["exit_value"]
                   == position_numbers["shares"] else Decimal("0"))
        expected_brier = ((p_side - outcome) ** 2).quantize(
            Decimal("0.0001"))
        if numbers["brier"] != expected_brier:
            raise RetryableDecisionError(
                f"settlement score conflicts with position {position_id}")
        settlement_position_ids.add(position_id)
        settlement_signal_ids.add(signal_id)
        settlement_credits.add(credit)
        realized_pnls.append(numbers["pnl_usd"])

    closed_ids = {
        position_id for position_id, (row, _) in positions_by_id.items()
        if row["status"] == "closed"
    }
    if closed_ids != settlement_position_ids:
        raise RetryableDecisionError(
            "closed positions and validated settlements do not match")
    open_cost = _exact_money_sum(open_sizes)
    realized = _exact_money_sum(realized_pnls)
    try:
        with localcontext() as context:
            context.prec = MAX_JUDGE_NUMBER_CHARS + 4
            total_equity = (bankroll_d + realized).quantize(Decimal("0.01"))
            available_capital = max(
                Decimal("0.00"), total_equity - open_cost).quantize(
                    Decimal("0.01"))
    except InvalidOperation as exc:
        raise RetryableDecisionError("account capital is outside safe range") from exc
    if total_equity < 0:
        raise RetryableDecisionError("total equity is negative")
    return total_equity, available_capital


def _exact_money_sum(values: list[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = (MAX_JUDGE_NUMBER_CHARS
                        + len(str(max(1, len(values)))) + 2)
        try:
            return sum(values, Decimal("0.00")).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise RetryableDecisionError(
                "account ledger total is outside safe range") from exc


def _ledger_identifier(value, field: str) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > 200 or any(
                char.isspace() or unicodedata.category(char).startswith("C")
                for char in value)):
        raise RetryableDecisionError(f"invalid {field}")
    return value


def _ledger_number(value, field: str, pattern: str, *,
                   negative: bool = False) -> Decimal:
    if (type(value) is not str or len(value) > MAX_JUDGE_NUMBER_CHARS
            or not re.fullmatch(pattern, value)):
        raise RetryableDecisionError(f"noncanonical {field}")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise RetryableDecisionError(f"invalid {field}") from exc
    if (not number.is_finite() or number.is_zero() and number.is_signed()
            or not negative and number < 0):
        raise RetryableDecisionError(f"invalid {field}")
    return number


def _canonical_utc_timestamp(value) -> bool:
    if (type(value) is not str
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def canonical_position_size(side: str, p_yes, entry, *, available_capital,
                            total_equity, thresholds: dict) -> Decimal:
    """Size from the exact canonical inputs stored in prepared evidence."""
    if side not in ("YES", "NO"):
        raise RetryableDecisionError("invalid sizing side")
    if any(type(value) is not Decimal for value in (
            p_yes, entry, available_capital, total_equity)):
        raise RetryableDecisionError("sizing economics must be exact Decimal values")
    p = _input_decimal(p_yes, "judge probability", quantum=Decimal("0.001"))
    entry_d = _input_decimal(entry, "entry price", quantum=Decimal("0.001"))
    available_d = _input_decimal(
        available_capital, "available capital", quantum=Decimal("0.01"))
    equity_d = _input_decimal(
        total_equity, "total equity", quantum=Decimal("0.01"))
    try:
        kelly_value = thresholds["kelly_fraction"]
        max_stake_value = thresholds["max_stake_frac"]
    except (KeyError, TypeError) as exc:
        raise RetryableDecisionError("incomplete sizing thresholds") from exc
    if type(kelly_value) is not Decimal or type(max_stake_value) is not Decimal:
        raise RetryableDecisionError(
            "sizing thresholds must be exact Decimal values")
    kelly_fraction = _input_decimal(
        kelly_value, "Kelly fraction", quantum=Decimal("0.000001"))
    max_stake_frac = _input_decimal(
        max_stake_value, "stake cap", quantum=Decimal("0.000001"))
    p_side = p if side == "YES" else Decimal("1") - p
    return _sized_stake(
        p_side,
        entry_d,
        available_d,
        equity_d,
        kelly_fraction,
        max_stake_frac,
    )


def _canonical_row_line(row: dict) -> str:
    """Return the one physical TSV line allowed for a journal transition."""
    if set(row) != set(JOURNAL_COLUMNS):
        raise RetryableDecisionError("decision journal row fields mismatch")
    values = []
    for field in JOURNAL_COLUMNS:
        value = row[field]
        if not isinstance(value, str):
            raise RetryableDecisionError(
                f"non-string decision journal {field} for {row.get('signal_id')}")
        if value != value.strip() or any(
                unicodedata.category(ch) == "Cc" for ch in value):
            raise RetryableDecisionError(
                f"noncanonical decision journal {field} for {row.get('signal_id')}")
        values.append(value)
    return "\t".join(values) + "\n"


def _validate_decision_row(row: dict, domain: str, line: int) -> None:
    _canonical_row_line(row)
    signal_id = row["signal_id"]
    if not signal_id or any(ch.isspace() for ch in signal_id):
        raise RetryableDecisionError(f"invalid decision signal_id on line {line}")
    if row["domain"] != domain:
        raise RetryableDecisionError(f"invalid decision domain for {signal_id}")
    if any(not row[field] for field in TRADE_IDENTITY_FIELDS):
        raise RetryableDecisionError(f"incomplete trade identity for {signal_id}")
    if row["side"] not in ("YES", "NO"):
        raise RetryableDecisionError(f"invalid decision side for {signal_id}")
    if row["state"] not in ("prepared", "final"):
        raise RetryableDecisionError(f"invalid decision state on line {line}")
    if row["intended_status"] not in TERMINAL_STATUSES:
        raise RetryableDecisionError(f"invalid intended status on line {line}")
    timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
    try:
        parsed = datetime.strptime(row["ts_decided"], timestamp_format)
    except ValueError as exc:
        raise RetryableDecisionError(
            f"invalid decision timestamp on line {line}") from exc
    if (not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                         row["ts_decided"])
            or parsed.strftime(timestamp_format) != row["ts_decided"]):
        raise RetryableDecisionError(
            f"noncanonical decision timestamp on line {line}")

    economic = tuple(row[field] for field in ECONOMIC_FIELDS)
    if row["intended_status"] == "bet":
        if row["position_id"] != deterministic_position_id(domain, signal_id):
            raise RetryableDecisionError(
                f"invalid deterministic position ID for {signal_id}")
        if any(value == "" for value in economic):
            raise RetryableDecisionError(f"incomplete prepared bet for {signal_id}")
    else:
        if row["position_id"]:
            raise RetryableDecisionError(
                f"non-bet decision has position ID for {signal_id}")
        if any(economic) and not all(economic):
            raise RetryableDecisionError(
                f"partial decision economics for {signal_id}")
        if row["intended_status"] == "expired" and any(economic):
            raise RetryableDecisionError(
                f"expired decision has economics for {signal_id}")

    if not any(economic):
        return
    p = _number(row, "judge_p")
    conf = _number(row, "judge_conf")
    edge = _number(row, "edge")
    quote = _number(row, "quote_price")
    slippage = _number(row, "slippage")
    entry = _number(row, "entry_price")
    available = _number(row, "available_usd")
    total_equity = _number(row, "total_equity_usd")
    kelly_fraction = _number(row, "kelly_fraction")
    max_stake_frac = _number(row, "max_stake_frac")
    min_edge = _number(row, "min_edge")
    judge_min_conf = _number(row, "judge_min_conf")
    size = _number(row, "size_usd")
    shares = _number(row, "shares")
    if not (Decimal("0") < p < Decimal("1")):
        raise RetryableDecisionError(f"invalid judge probability for {signal_id}")
    if not (Decimal("0") <= conf <= Decimal("1")):
        raise RetryableDecisionError(f"invalid judge confidence for {signal_id}")
    if not (Decimal("-1") < edge < Decimal("1")):
        raise RetryableDecisionError(f"invalid edge for {signal_id}")
    if not (Decimal("0") < quote < Decimal("1")):
        raise RetryableDecisionError(f"invalid quote for {signal_id}")
    if not (Decimal("0") <= slippage < Decimal("1")):
        raise RetryableDecisionError(f"invalid slippage for {signal_id}")
    if not (Decimal("0") < entry <= CANONICAL_MAX_ENTRY_PRICE):
        raise RetryableDecisionError(f"invalid fill for {signal_id}")
    if available < 0 or total_equity < 0:
        raise RetryableDecisionError(f"negative account capital for {signal_id}")
    if available > total_equity:
        raise RetryableDecisionError(
            f"available capital exceeds total equity for {signal_id}")
    if not (Decimal("0") < kelly_fraction <= Decimal("1")):
        raise RetryableDecisionError(f"invalid Kelly fraction for {signal_id}")
    if not (Decimal("0") < max_stake_frac <= Decimal("1")):
        raise RetryableDecisionError(f"invalid stake cap for {signal_id}")
    if not (Decimal("0") <= min_edge < Decimal("1")):
        raise RetryableDecisionError(f"invalid edge gate for {signal_id}")
    if not (Decimal("0") <= judge_min_conf <= Decimal("1")):
        raise RetryableDecisionError(f"invalid confidence gate for {signal_id}")
    if size < 0 or shares < 0:
        raise RetryableDecisionError(f"negative economics for {signal_id}")
    if row["intended_status"] == "bet" and (size < 1 or shares <= 0):
        raise RetryableDecisionError(f"invalid bet size for {signal_id}")
    if row["intended_status"] != "bet" and (size != 0 or shares != 0):
        raise RetryableDecisionError(f"nonzero pass size for {signal_id}")

    expected_entry = min(Decimal("0.990"), quote + slippage)
    if entry != expected_entry:
        raise RetryableDecisionError(
            f"fill conflicts with quote and slippage for {signal_id}")
    p_side = p if row["side"] == "YES" else Decimal("1") - p
    if edge != p_side - entry:
        raise RetryableDecisionError(
            f"edge conflicts with side probability and fill for {signal_id}")
    expected_size = _sized_stake(
        p_side, entry, available, total_equity, kelly_fraction,
        max_stake_frac)
    clears_gate = edge >= min_edge and conf >= judge_min_conf
    if row["intended_status"] == "bet":
        if not clears_gate or expected_size < 1 or size != expected_size:
            raise RetryableDecisionError(
                f"bet size or gate conflicts with prepared inputs for {signal_id}")
        expected_shares = _position_shares(size, entry)
        if shares != expected_shares:
            raise RetryableDecisionError(
                f"shares conflict with size and fill for {signal_id}")
    elif clears_gate and expected_size >= 1:
        raise RetryableDecisionError(
            f"pass conflicts with deterministic bet gate for {signal_id}")


def load_decision_journal(path: Path, domain: str) -> dict[str, tuple[dict, bool]]:
    """Strictly validate the complete append-only state machine.

    Exactly one prepared row may start a signal decision and at most one final
    row may follow it.  The final transition must repeat every evidence byte;
    it changes only ``state``.  Any torn, duplicate, reordered, or contradictory
    row stops replay before signals or positions are touched.
    """
    ensure_decision_journal(path)
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeDecodeError) as exc:
        raise RetryableDecisionError("decision journal is unreadable") from exc
    if not raw.endswith(b"\n"):
        raise RetryableDecisionError("decision journal has a torn final row")
    header = JOURNAL_HEADER.encode("utf-8")
    if not raw.startswith(header):
        raise RetryableDecisionError("decision journal header mismatch")

    grouped: dict[str, list[dict]] = {}
    for line, physical in enumerate(raw[len(header):].splitlines(keepends=True),
                                    start=2):
        if not physical.endswith(b"\n"):
            raise RetryableDecisionError(
                f"torn decision journal row on line {line}")
        try:
            text = physical.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RetryableDecisionError(
                f"invalid UTF-8 in decision journal line {line}") from exc
        values = text[:-1].split("\t")
        if len(values) != len(JOURNAL_COLUMNS):
            raise RetryableDecisionError(
                f"malformed decision journal row on line {line}")
        row = dict(zip(JOURNAL_COLUMNS, values, strict=True))
        if _canonical_row_line(row).encode("utf-8") != physical:
            raise RetryableDecisionError(
                f"noncanonical decision journal row on line {line}")
        _validate_decision_row(row, domain, line)
        grouped.setdefault(row["signal_id"], []).append(row)

    decisions: dict[str, tuple[dict, bool]] = {}
    for signal_id, history in grouped.items():
        if history[0]["state"] != "prepared" or len(history) > 2:
            raise RetryableDecisionError(
                f"invalid decision transition history for {signal_id}")
        if len(history) == 2:
            if history[1]["state"] != "final":
                raise RetryableDecisionError(
                    f"invalid decision transition for {signal_id}")
            if any(history[0][field] != history[1][field]
                   for field in DECISION_EVIDENCE_FIELDS):
                raise RetryableDecisionError(
                    f"contradictory decision rows for {signal_id}")
        decisions[signal_id] = (history[0], len(history) == 2)
    return decisions


def _signal_for_decision(signals: list[dict], decision: dict,
                         finalized: bool = False) -> dict:
    matches = [s for s in signals if s.get("signal_id") == decision["signal_id"]]
    if len(matches) != 1:
        raise RetryableDecisionError(
            f"decision signal is missing or duplicated: {decision['signal_id']}")
    signal = matches[0]
    if any(signal.get(field, "") != decision[field]
           for field in TRADE_IDENTITY_FIELDS):
        raise RetryableDecisionError(
            f"decision trade identity conflicts with signal {decision['signal_id']}")

    status = signal.get("status")
    resolver_interleaving = (
        not finalized and status == "expired"
        and signal.get("resolved_outcome") in ("YES", "NO")
    )
    if (status not in ("pending_judge", decision["intended_status"])
            and not resolver_interleaving):
        raise RetryableDecisionError(
            f"decision conflicts with signal status for {decision['signal_id']}")

    if finalized and status == decision["intended_status"]:
        projection = {
            "judge_p": decision["judge_p"],
            "judge_conf": decision["judge_conf"],
            "edge": decision["edge"],
            "note": decision["note"],
        }
        if any(signal.get(field, "") != value
               for field, value in projection.items()):
            raise RetryableDecisionError(
                f"terminal signal conflicts with decision {decision['signal_id']}")
    return signal


def _expected_position(decision: dict) -> dict:
    """Build the position only from immutable prepared evidence."""
    return {
        "position_id": decision["position_id"],
        "signal_id": decision["signal_id"],
        "ts_open": decision["ts_decided"],
        "market_id": decision["market_id"],
        "market_question": decision["market_question"],
        "token_id": decision["token_id"],
        "side": decision["side"],
        "quote_price": decision["quote_price"],
        "entry_price": decision["entry_price"],
        "size_usd": decision["size_usd"],
        "shares": decision["shares"],
        "judge_p": decision["judge_p"],
        "status": "open",
        "note": decision["note"],
    }


def _related_positions(positions: list[dict], decision: dict) -> list[dict]:
    deterministic_id = deterministic_position_id(
        decision["domain"], decision["signal_id"])
    return [p for p in positions
            if p.get("position_id") == deterministic_id
            or p.get("signal_id") == decision["signal_id"]]


def _validate_position_projection(positions: list[dict], decision: dict) -> dict | None:
    related = _related_positions(positions, decision)
    if len(related) > 1:
        raise RetryableDecisionError(
            f"duplicate position materialization for {decision['signal_id']}")
    if decision["intended_status"] != "bet":
        if related:
            raise RetryableDecisionError(
                f"non-bet decision conflicts with a position for {decision['signal_id']}")
        return None

    expected = _expected_position(decision)
    if not related:
        return None
    immutable = {field: value for field, value in expected.items()
                 if field != "status"}
    if (related[0].get("status") not in ("open", "closed")
            or any(related[0].get(field, "") != value
                   for field, value in immutable.items())):
        raise RetryableDecisionError(
            f"position conflicts with prepared decision for {decision['signal_id']}")
    return related[0]


def preflight_decisions(decisions: dict[str, tuple[dict, bool]],
                        signals: list[dict], positions: list[dict]) -> None:
    """Validate the complete recovery set against one read-only snapshot."""
    planned_markets: dict[str, str] = {}
    for decision, finalized in decisions.values():
        _signal_for_decision(signals, decision, finalized)
        existing = _validate_position_projection(positions, decision)
        if decision["intended_status"] != "bet":
            continue
        needs_open_position = existing is None or existing.get("status") == "open"
        if not needs_open_position:
            continue
        other = planned_markets.get(decision["market_id"])
        if other and other != decision["signal_id"]:
            raise RetryableDecisionError(
                f"prepared bets conflict on market {decision['market_id']}")
        planned_markets[decision["market_id"]] = decision["signal_id"]
        if any(p.get("status") == "open"
               and p.get("market_id") == decision["market_id"]
               and p.get("signal_id") != decision["signal_id"]
               for p in positions):
            raise RetryableDecisionError(
                f"prepared bet conflicts with open market position for "
                f"{decision['signal_id']}")


def _materialize_position(ddir: Path, decision: dict) -> None:
    expected = _expected_position(decision)
    positions = read_tsv(ddir / "positions.tsv")
    if _validate_position_projection(positions, decision) is not None:
        return
    append_tsv_atomic(ddir / "positions.tsv", expected)
    fault_point("after_position_append")


def _materialize_signal(ddir: Path, decision: dict, finalized: bool) -> None:
    path = ddir / "signals.tsv"
    signals = read_tsv(path)
    signal = _signal_for_decision(signals, decision, finalized)
    expected = {
        "status": decision["intended_status"],
        "judge_p": decision["judge_p"],
        "judge_conf": decision["judge_conf"],
        "edge": decision["edge"],
        "note": decision["note"],
    }
    if all(signal.get(field, "") == value for field, value in expected.items()):
        return
    signal.update(expected)
    write_tsv(path, signals)
    fault_point("after_signal_update")


def materialize_decision(ddir: Path, domain: str, decision: dict,
                         finalized: bool) -> None:
    """Replay one validated decision in the only safe write order."""
    signals = read_tsv(ddir / "signals.tsv")
    _signal_for_decision(signals, decision, finalized)
    if decision["intended_status"] == "bet":
        _materialize_position(ddir, decision)
    else:
        positions = read_tsv(ddir / "positions.tsv")
        _validate_position_projection(positions, decision)
    _materialize_signal(ddir, decision, finalized)
    if finalized:
        return
    fault_point("before_final")
    append_tsv_atomic(ddir / JOURNAL_FILE, {**decision, "state": "final"})
    fault_point("after_final")


def recover_decisions(ddir: Path, domain: str) -> None:
    decisions = load_decision_journal(ddir / JOURNAL_FILE, domain)
    signals = read_tsv(ddir / "signals.tsv")
    positions = read_tsv(ddir / "positions.tsv")
    preflight_decisions(decisions, signals, positions)
    for decision, finalized in decisions.values():
        materialize_decision(ddir, domain, decision, finalized)


def commit_decision(ddir: Path, domain: str, decision: dict) -> None:
    """Durably prepare, then idempotently project, one terminal decision."""
    existing = load_decision_journal(ddir / JOURNAL_FILE, domain)
    if decision["signal_id"] in existing:
        prepared, finalized = existing[decision["signal_id"]]
        if any(prepared[field] != decision[field]
               for field in DECISION_EVIDENCE_FIELDS):
            raise RetryableDecisionError(
                f"refusing contradictory decision for {decision['signal_id']}")
        preflight_decisions(
            existing, read_tsv(ddir / "signals.tsv"),
            read_tsv(ddir / "positions.tsv"))
        materialize_decision(ddir, domain, prepared, finalized)
        return
    _validate_decision_row(decision, domain, 0)
    signals = read_tsv(ddir / "signals.tsv")
    positions = read_tsv(ddir / "positions.tsv")
    candidate = {**existing, decision["signal_id"]: (decision, False)}
    preflight_decisions(candidate, signals, positions)
    fault_point("before_prepared")
    append_tsv_atomic(ddir / JOURNAL_FILE, decision)
    fault_point("after_prepared")
    # Replay only the canonical bytes that actually reached durable storage.
    all_decisions = load_decision_journal(ddir / JOURNAL_FILE, domain)
    prepared, finalized = all_decisions[decision["signal_id"]]
    preflight_decisions(
        all_decisions, read_tsv(ddir / "signals.tsv"),
        read_tsv(ddir / "positions.tsv"))
    materialize_decision(ddir, domain, prepared, finalized)


def make_decision(signal: dict, status: str, note: str, *,
                  domain: str, p_yes: float | None = None,
                  conf: float | None = None, quote: float | None = None,
                  slippage: float | None = None,
                  available_capital: Decimal | None = None,
                  total_equity: Decimal | None = None,
                  thresholds: dict | None = None,
                  size: Decimal = Decimal("0.00")) -> dict:
    """Build the canonical evidence row that replay trusts byte-for-byte."""
    economic = p_yes is not None
    if economic and (any(value is None for value in (
            conf, quote, slippage, available_capital, total_equity))
            or thresholds is None):
        raise RetryableDecisionError(
            f"incomplete new decision economics for {signal['signal_id']}")
    p = Decimal(f"{p_yes:.3f}") if economic else None
    quote_d = Decimal(f"{quote:.3f}") if economic else None
    slippage_d = Decimal(f"{slippage:.3f}") if economic else None
    entry = (min(Decimal("0.990"), quote_d + slippage_d)
             if quote_d is not None and slippage_d is not None else None)
    p_side = (p if signal["side"] == "YES" else Decimal("1") - p
              if p is not None else None)
    edge = p_side - entry if p_side is not None and entry is not None else None
    available_d = (_input_decimal(
        available_capital, "available capital", quantum=Decimal("0.01"))
        if economic else None)
    total_equity_d = (_input_decimal(
        total_equity, "total equity", quantum=Decimal("0.01"))
        if economic else None)
    kelly_fraction = (Decimal(f"{thresholds['kelly_fraction']:.6f}")
                      if economic and thresholds is not None else None)
    max_stake_frac = (Decimal(f"{thresholds['max_stake_frac']:.6f}")
                      if economic and thresholds is not None else None)
    min_edge = (Decimal(f"{thresholds['min_edge']:.3f}")
                if economic and thresholds is not None else None)
    judge_min_conf = (Decimal(f"{thresholds['judge_min_conf']:.2f}")
                      if economic and thresholds is not None else None)
    size_d = (_input_decimal(size, "position size", quantum=Decimal("0.01"))
              if economic else None)
    shares = (_position_shares(size_d, entry)
              if status == "bet" and size_d is not None and entry else None)
    note = compose_terminal_note(signal.get("note", ""), note)
    return {
        "signal_id": signal["signal_id"],
        "domain": domain,
        "market_id": signal["market_id"],
        "market_question": signal["market_question"],
        "token_id": signal["token_id"],
        "side": signal["side"],
        "state": "prepared",
        "ts_decided": now_iso(),
        "position_id": (deterministic_position_id(domain, signal["signal_id"])
                        if status == "bet" else ""),
        "intended_status": status,
        "judge_p": f"{p:.3f}" if p is not None else "",
        "judge_conf": f"{conf:.2f}" if economic and conf is not None else "",
        "edge": f"{edge:.3f}" if edge is not None else "",
        "quote_price": f"{quote_d:.3f}" if quote_d is not None else "",
        "slippage": f"{slippage_d:.3f}" if slippage_d is not None else "",
        "entry_price": f"{entry:.3f}" if entry is not None else "",
        "available_usd": (f"{available_d:.2f}"
                          if available_d is not None else ""),
        "total_equity_usd": (f"{total_equity_d:.2f}"
                             if total_equity_d is not None else ""),
        "kelly_fraction": (f"{kelly_fraction:.6f}"
                           if kelly_fraction is not None else ""),
        "max_stake_frac": (f"{max_stake_frac:.6f}"
                           if max_stake_frac is not None else ""),
        "min_edge": f"{min_edge:.3f}" if min_edge is not None else "",
        "judge_min_conf": (f"{judge_min_conf:.2f}"
                           if judge_min_conf is not None else ""),
        "size_usd": f"{size_d:.2f}" if size_d is not None else "",
        "shares": (f"{shares:.2f}" if shares is not None else
                   ("0.00" if economic else "")),
        "note": note,
    }


def persist_pending_note(ddir: Path, signal_id: str, note: str) -> None:
    """Persist retry context atomically without terminalizing the signal."""
    path = ddir / "signals.tsv"
    signals = read_tsv(path)
    matches = [s for s in signals if s.get("signal_id") == signal_id]
    if len(matches) != 1 or matches[0].get("status") != "pending_judge":
        raise RetryableDecisionError(f"cannot update pending signal {signal_id}")
    if matches[0].get("note", "") == note:
        return
    matches[0]["note"] = note
    write_tsv(path, signals)


def persist_judge_retry_note(ddir: Path, signal_id: str) -> None:
    """Atomically replace Judge's one bounded marker, preserving other notes."""
    path = ddir / "signals.tsv"
    signals = read_tsv(path)
    matches = [s for s in signals if s.get("signal_id") == signal_id]
    if len(matches) != 1 or matches[0].get("status") != "pending_judge":
        raise RetryableDecisionError(f"cannot update pending signal {signal_id}")
    prior = matches[0].get("note", "")
    unrelated = unmanaged_judge_note(prior)
    note = f"{unrelated} {JUDGE_RETRY_NOTE}".strip()
    if prior == note:
        return
    matches[0]["note"] = note
    write_tsv(path, signals)


def unmanaged_judge_note(note: str) -> str:
    """Remove only Judge's managed retry marker and normalize TSV whitespace."""
    return " ".join(JUDGE_RETRY_NOTE_RE.sub("", str(note or "")).split())


def compose_terminal_note(existing: str, decision: str) -> str:
    """Keep unrelated signal context while clearing Judge's retry marker."""
    unrelated = unmanaged_judge_note(existing)
    decision = " ".join(str(decision or "").split())
    if not unrelated or unrelated == decision:
        return decision or unrelated
    if not decision:
        return unrelated
    return f"{unrelated} | {decision}"


def calibration_record(signals: list[dict]) -> str:
    agg: dict[str, list[float]] = {}
    for s in signals:
        if not s.get("judge_p") or s.get("resolved_outcome") not in ("YES", "NO"):
            continue
        try:
            p_yes = float(s["judge_p"])
        except ValueError:
            continue
        outcome = 1.0 if s["resolved_outcome"] == "YES" else 0.0
        agg.setdefault(s["call_class"], []).append((p_yes - outcome) ** 2)
    if not agg:
        return "no resolved judged signals yet"
    return "; ".join(f"{cls}: mean Brier {sum(v)/len(v):.3f} over {len(v)}"
                     for cls, v in sorted(agg.items()))


def executable_ask(market: dict, side: str) -> float | None:
    """Current executable ask for the side Delphi would buy."""
    token = market["yes_token"] if side == "YES" else market.get("no_token", "")
    ask = pm.best_ask(token) if token else None
    if ask is None and side == "NO":
        bid_yes = pm.best_bid(market["yes_token"])
        ask = 1.0 - bid_yes if bid_yes is not None else None
    return ask if ask is not None and 0.0 < ask < 1.0 else None


def _liquidity_decimal(value) -> Decimal | None:
    if type(value) is bool or type(value) not in (Decimal, int, float, str):
        return None
    text = str(value)
    if (not text or len(text) > MAX_JUDGE_NUMBER_CHARS
            or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", text)):
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    scale = max(0, -number.as_tuple().exponent)
    if not number.is_finite() or number < 0 or scale > 6:
        return None
    return number


def eligibility(signal: dict, leakers: list[dict], positions: list[dict],
                thresholds: dict) -> tuple[dict | None, float | None, str | None, str]:
    """Return market/ask when eligible, otherwise terminal status (or None
    for a transient retry) and an explicit reason."""
    row = leaker_row(leakers, signal["leaker_id"], signal["call_class"])
    if not row or row.get("status") != "verified":
        return None, None, "pass", "leaker class is no longer verified"
    if any(p.get("status") == "open" and p.get("market_id") == signal["market_id"]
           for p in positions):
        return None, None, "pass", "already positioned on this market — stacking guard"
    market = pm.get_market(signal["market_id"])
    if market is None:
        return None, None, None, "market lookup failed — retrying next run"
    if market["closed"]:
        return None, None, "expired", "market closed before trade"
    liquidity = _liquidity_decimal(market.get("liquidity"))
    minimum_liquidity = _liquidity_decimal(
        thresholds.get("min_liquidity_usd"))
    if liquidity is None or minimum_liquidity is None:
        return None, None, None, "market liquidity unusable — retrying next run"
    if liquidity < minimum_liquidity:
        return None, None, "pass", "market liquidity fell below minimum"
    ask = executable_ask(market, signal["side"])
    if ask is None:
        return None, None, None, "no fresh executable quote — retrying next run"
    return market, ask, None, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="ai-releases")
    args = ap.parse_args()
    cfg = load_config()
    th = cfg["thresholds"]
    decision_thresholds = {**th, **canonical_sizing_thresholds(th)}
    ddir = domain_dir(args.domain)
    ctx = agent_context("judge")
    prompt_t = (ROOT / "prompts" / "judge.md").read_text(encoding="utf-8")

    # Refuse malformed account ledgers before recovery can project a position
    # or terminal signal. A valid prepared decision then wins over fresh
    # eligibility/model work.
    initial_positions = read_tsv(ddir / "positions.tsv")
    initial_resolved = read_tsv(ddir / "resolved.tsv")
    account_capital(cfg["bankroll_usd"], initial_resolved, initial_positions)
    # Recover the journal before selecting pending signals so the exact crash
    # state (position exists, signal still pending) cannot hit stacking guard.
    recover_decisions(ddir, args.domain)
    signals = read_tsv(ddir / "signals.tsv")
    leakers = read_tsv(ddir / "leakers.tsv")
    positions = read_tsv(ddir / "positions.tsv")
    resolved = read_tsv(ddir / "resolved.tsv")

    pending = [s for s in signals if s["status"] == "pending_judge"][:MAX_PER_RUN]
    if not pending:
        return  # quiet — heartbeat already logged the sweep

    # F13: self-financing paper account with separate sizing bases.
    total_equity, available_capital = account_capital(
        cfg["bankroll_usd"], resolved, positions)
    realized = total_equity - _input_decimal(
        cfg["bankroll_usd"], "bankroll", quantum=Decimal("0.01"))
    calib = calibration_record(signals)
    slippage = float(f"{th['slippage']:.3f}")
    n_bet = n_pass = 0
    lessons_all: list[str] = []
    events: list[str] = []

    for s in pending:
        market, quote_side, terminal, reason = eligibility(s, leakers, positions, th)
        if market is None:
            if terminal:
                decision = make_decision(
                    s, terminal, reason, domain=args.domain)
                commit_decision(ddir, args.domain, decision)
                s.update({"status": terminal, "note": reason})
                n_pass += terminal == "pass"
            else:
                persist_pending_note(ddir, s["signal_id"], reason)
            continue
        quote_yes_disp = quote_side if s["side"] == "YES" else 1.0 - quote_side

        lk = leaker_row(leakers, s["leaker_id"], s["call_class"]) or {}
        scorecard = (f"n_calls={lk.get('n_calls')}, hit_rate={lk.get('hit_rate')}, "
                     f"avg_price_at_call={lk.get('avg_price_at_call')}, "
                     f"edge_lcb={lk.get('edge_lcb')}, n_unpriced={lk.get('n_unpriced')}, "
                     f"n_live={lk.get('n_live')}")
        # VISION: deterministic weighted aggregate across ALL roster leakers
        # with live calls on this market — input to the judge, never a gate.
        agg_block = format_aggregate(
            aggregate_market_signals(signals, leakers, s["market_id"]))
        past = cognee.search(f"{s['call_class']} {market['question'][:80]}", 3)

        prompt = (ctx + "\n\n" + prompt_t
                  + f"\n\n## MARKET\nquestion: {market['question']}"
                  + f"\nresolution criteria: {market['description']}"
                  + f"\nend date: {market['end_date']}"
                  + f"\ncurrent YES price: {quote_yes_disp:.3f}"
                  + f" | liquidity: {_liquidity_decimal(market['liquidity']):.0f} USD"
                  + f"\n\n## LEAKER POST\nleaker: {s['leaker_id']} (hedged: {s['hedged']})"
                  + f"\nposted: {s['post_ts']} | detected: {s['ts_detected']}"
                  + f"\nclaim: {s['claim']}"
                  + f"\nimplied side: {s['side']}"
                  + f"\n\n## LEAKER SCORECARD ({s['call_class']})\n{scorecard}"
                  + f"\n\n## YOUR CALIBRATION RECORD\n{calib}"
                  + "\n\n## WEIGHTED CROSS-LEAKER AGGREGATE (this market)\n"
                  + agg_block
                  + "\n\n## RETRIEVED PAST CASES\n" + ("\n".join(past) or "none")
                  + "\n\n## REQUEST\nEstimate now. JSON only.")
        try:
            j = call_json("judge", prompt, cfg, decoder=parse_judge_output)
            j = validate_judge_response(j)
        except Exception:
            # The note is deliberately fixed: no raw output, exception text,
            # secrets, or attacker-controlled control characters reach state.
            persist_judge_retry_note(ddir, s["signal_id"])
            continue
        p_yes = j["p_yes"]
        conf = j["confidence"]
        lessons_all += j.get("lessons") or []

        # Re-read script-owned state and re-fetch both market and ask after the
        # slow judgment. No predicate from the pre-judgment check is trusted.
        current_leakers = read_tsv(ddir / "leakers.tsv")
        current_positions = read_tsv(ddir / "positions.tsv")
        market, ask, terminal, reason = eligibility(
            s, current_leakers, current_positions, th)
        if market is None:
            if terminal:
                decision = make_decision(
                    s, terminal, reason, domain=args.domain)
                commit_decision(ddir, args.domain, decision)
                s.update({"status": terminal, "note": reason})
                n_pass += terminal == "pass"
            else:
                persist_pending_note(ddir, s["signal_id"], reason)
            continue

        ask = float(f"{ask:.3f}")
        p_side, _ = side_values(s["side"], p_yes, 0.5)
        fill = float(f"{min(0.99, ask + slippage):.3f}")
        edge = p_side - fill
        quote_side = ask  # recorded quote = the executable ask, not a midpoint
        rationale = " ".join(str(j.get("rationale", "")).split())[:180]

        if edge >= th["min_edge"] and conf >= th["judge_min_conf"]:
            p_yes_exact = Decimal(f"{p_yes:.3f}")
            fill_exact = Decimal(f"{fill:.3f}")
            size = canonical_position_size(
                s["side"], p_yes_exact, fill_exact,
                available_capital=available_capital,
                total_equity=total_equity,
                thresholds=decision_thresholds)  # Kelly on the FILL; cap on equity
            if size >= Decimal("1.00"):
                decision = make_decision(
                    s, "bet", rationale, domain=args.domain, p_yes=p_yes,
                    conf=conf, quote=quote_side, slippage=slippage,
                    available_capital=available_capital,
                    total_equity=total_equity,
                    thresholds=decision_thresholds, size=size)
                commit_decision(ddir, args.domain, decision)
                positions = read_tsv(ddir / "positions.tsv")
                available_capital -= Decimal(decision["size_usd"])
                s.update({
                    "status": "bet", "judge_p": decision["judge_p"],
                    "judge_conf": decision["judge_conf"],
                    "edge": decision["edge"], "note": decision["note"],
                })
                n_bet += 1
                events.append(f"BET {s['side']} {decision['size_usd']} @ fill "
                              f"{decision['entry_price']} (quote "
                              f"{decision['quote_price']}) — {s['market_question'][:65]} "
                              f"(p={p_yes:.2f}, edge={edge:.2f})")
            else:
                note = "size below minimum after caps/equity"
                decision = make_decision(
                    s, "pass", note, domain=args.domain, p_yes=p_yes,
                    conf=conf, quote=quote_side, slippage=slippage,
                    available_capital=available_capital,
                    total_equity=total_equity, thresholds=decision_thresholds)
                commit_decision(ddir, args.domain, decision)
                s.update({
                    "status": "pass", "judge_p": decision["judge_p"],
                    "judge_conf": decision["judge_conf"],
                    "edge": decision["edge"], "note": decision["note"],
                })
                n_pass += 1
        else:
            decision = make_decision(
                s, "pass", rationale, domain=args.domain, p_yes=p_yes,
                conf=conf, quote=quote_side, slippage=slippage,
                available_capital=available_capital,
                total_equity=total_equity, thresholds=decision_thresholds)
            commit_decision(ddir, args.domain, decision)
            s.update({
                "status": "pass", "judge_p": decision["judge_p"],
                "judge_conf": decision["judge_conf"],
                "edge": decision["edge"], "note": decision["note"],
            })
            n_pass += 1
            events.append(f"PASS — {s['market_question'][:70]} (p={p_yes:.2f}, "
                          f"edge={edge:.2f}, conf={conf:.2f})")

    append_lessons("judge", lessons_all)
    if events:
        note = "Decisions this run:\n- " + "\n- ".join(events)
        write_note("judge", "decisions", note)
        cognee.add(note, meta=f"judge {args.domain}")
    log_result("judge", args.domain,
               f"{len(pending)} pending → {n_bet} paper bets, {n_pass} passes; "
               f"equity {total_equity:.2f} (realized {realized:+.2f}), "
               f"available {available_capital:.2f}")


if __name__ == "__main__":
    main()
