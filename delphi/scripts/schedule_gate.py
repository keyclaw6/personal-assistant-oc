#!/usr/bin/env python3
"""Fail-closed cron gate for Delphi's kickstart-to-normal transition."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib import validate_kickstart_cutoff


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"


def parse_cutoff(value: object) -> datetime:
    return validate_kickstart_cutoff(value)


def schedule_mode(cutoff: datetime, now: datetime | None = None) -> str:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return "kickstart" if current.astimezone(timezone.utc) < cutoff else "normal"


def _configured_cutoff(path: Path) -> datetime:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"nonstandard JSON constant: {value}")

    try:
        raw = path.read_text(encoding="utf-8")
        config = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("config.json is unreadable or invalid") from exc
    if type(config) is not dict or type(config.get("kickstart")) is not dict:
        raise ValueError("config.json has no canonical kickstart object")
    return parse_cutoff(config["kickstart"].get("active_until"))


def cli(argv: list[str] | None = None, *, config_path: Path = CONFIG,
        now: datetime | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("kickstart", "normal"):
        print("usage: schedule_gate.py kickstart|normal", file=sys.stderr)
        return 2
    try:
        selected = schedule_mode(_configured_cutoff(config_path), now)
    except ValueError as exc:
        print(f"schedule gate refused: {exc}", file=sys.stderr)
        return 2
    return 0 if args[0] == selected else 1


if __name__ == "__main__":
    raise SystemExit(cli())
