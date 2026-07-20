#!/usr/bin/env python3
"""Canonical source-post timestamp validation shared by DELPHI ingestion."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


UTC = timezone.utc
SOURCE_CLOCK_TOLERANCE = timedelta(minutes=5)
CANONICAL_SOURCE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_CANONICAL_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_PROVIDER_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|(?P<offset_sign>[+-])"
    r"(?P<offset_hour>\d{2}):(?P<offset_minute>\d{2}))"
)


class SourceTimestampError(ValueError):
    """A source post timestamp is unsafe for ordering or historical pricing."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceTimestampError("comparison clock must be timezone-aware")
    return value.astimezone(UTC)


def validate_source_timestamp(
        value: object, *, now: datetime | None = None,
        normalize_provider: bool = False) -> str:
    """Return canonical UTC seconds or reject an unsafe source timestamp.

    Durable state and consumers accept only ``YYYY-MM-DDTHH:MM:SSZ``. Source
    adapters may opt into aware RFC3339 normalization for offsets/fractions.
    Naive timestamps and values beyond the explicit clock-skew tolerance are
    rejected in both modes.
    """
    if not isinstance(value, str) or value != value.strip():
        raise SourceTimestampError("source timestamp must be canonical text")

    try:
        if normalize_provider:
            provider_match = _PROVIDER_RFC3339_RE.fullmatch(value)
            if provider_match is None:
                raise SourceTimestampError(
                    "provider timestamp must be timezone-aware RFC3339")
            offset_hour = provider_match.group("offset_hour")
            offset_minute = provider_match.group("offset_minute")
            if (offset_hour is not None
                    and (int(offset_hour) > 23 or int(offset_minute) > 59)):
                raise SourceTimestampError(
                    "provider timestamp has an invalid UTC offset")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed = _aware_utc(parsed)
        else:
            if _CANONICAL_RE.fullmatch(value) is None:
                raise SourceTimestampError(
                    "source timestamp must use canonical UTC seconds")
            parsed = datetime.strptime(value, CANONICAL_SOURCE_FORMAT).replace(
                tzinfo=UTC)
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, SourceTimestampError):
            raise
        raise SourceTimestampError("invalid source timestamp") from exc

    reference = _aware_utc(now if now is not None else utc_now())
    if parsed > reference + SOURCE_CLOCK_TOLERANCE:
        raise SourceTimestampError("source timestamp exceeds clock tolerance")
    return parsed.strftime(CANONICAL_SOURCE_FORMAT)


def validate_source_posts(
        posts: list[dict], *, now: datetime | None = None) -> tuple[list[dict], int]:
    """Copy valid canonical posts and count rows rejected before any ordering."""
    reference = now if now is not None else utc_now()
    valid: list[dict] = []
    rejected = 0
    for post in posts:
        if not isinstance(post, dict):
            rejected += 1
            continue
        try:
            timestamp = validate_source_timestamp(post.get("ts"), now=reference)
        except SourceTimestampError:
            rejected += 1
            continue
        normalized = dict(post)
        normalized["ts"] = timestamp
        valid.append(normalized)
    return valid, rejected
