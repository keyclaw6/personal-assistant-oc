#!/usr/bin/env python3
"""Orchestrator (hourly): top-level maintainer / goal-direction agent.

Reads the whole machine's state, diagnoses against the goal, applies AT MOST
ONE allowlisted amendment per run (script-enforced), reviews due experiments,
and logs everything: ledger/learnings.md row + dated note in its own workspace
(PROGRAM.md §6). It can change the harness, never the scoreboard.
"""
from __future__ import annotations

import argparse
import calendar
import ctypes
import hashlib
import json
import os
import re
import stat
import time
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import cognee
from lib import (ROOT, agent_context, agent_dir, append_lessons, domain_dir,
                 kickstart_active, load_config, log_result,
                 now_iso, read_tsv, validate_config_patch, write_note)
from llm import call_json

AGENTS = ["explorer", "heartbeat", "judge", "orchestrator"]

APPLY_JOURNAL = "APPLY_JOURNAL.tsv"
_DISPLACED_COLUMNS = (
    "displaced_dev", "displaced_ino", "displaced_mode", "displaced_sha256",
    "displaced_size",
)
JOURNAL_COLUMNS = (
    "schema", "id", "state", "transition_ts", "prepared_ts", "kind",
    "target_rel", "target_canonical", "target_dev", "target_ino",
    "before_path", "before_dev", "before_ino", "before_mode", "before_sha256",
    "before_size", "after_path", "after_dev", "after_ino", "after_mode",
    "after_sha256", "after_size", "meta_path", "meta_dev", "meta_ino",
    "meta_mode", "meta_sha256", "meta_size", "exchange_rel", "exchange_dev",
    "exchange_ino", "exchange_mode", "exchange_sha256", "exchange_size",
    *_DISPLACED_COLUMNS,
    "mode", "review_after_hours", "metric", "rationale", "change",
    "review_result",
)
JOURNAL_HEADER = "\t".join(JOURNAL_COLUMNS) + "\n"
EXPERIMENTS_TEMPLATE = """# Live experiments

Managed by the orchestrator. One row per experiment; keep/revert verdicts are
also logged in ledger/learnings.md.

| id | started | change | metric | review_after | status |
|---|---|---|---|---|---|
"""
_EXP_DIR_PARTS = ("agents", "orchestrator", "experiments")
_ID_RE = re.compile(r"exp-[0-9]{8}-[a-z0-9]{5,64}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_ISO_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_METRIC_PATH_RE = re.compile(
    r"(?:ledger/results\.tsv|domains/[a-z0-9-]+/[a-z0-9-]+\.tsv)\Z")
_METRIC_COMPARATORS = frozenset(("<", "<=", "==", ">=", ">"))
_METRIC_AGGREGATES = frozenset(("count", "sum", "mean"))
_CANONICAL_DECIMAL_RE = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_DECLARED_DECIMAL_MAX_CHARS = 100
# Covers the worst accepted fixed-point sum: 100 integer characters, six
# row-count carry digits, 98 fractional places, sign, and decimal point.
_RESULT_DECIMAL_MAX_CHARS = 220
_MEAN_DECIMAL_PLACES = 100


class ApplySafetyError(RuntimeError):
    """The apply evidence or filesystem cannot be trusted enough to mutate."""


@dataclass
class _RootRef:
    path: Path
    fd: int
    dev: int
    ino: int

    def close(self) -> None:
        os.close(self.fd)


@dataclass
class _DirRef:
    root: _RootRef
    parts: tuple[str, ...]
    fd: int
    dev: int
    ino: int

    def close(self) -> None:
        os.close(self.fd)
        self.root.close()


@dataclass
class _TargetRef:
    directory: _DirRef
    rel: str
    canonical: str
    name: str
    dev: int
    ino: int
    mode: int

    def close(self) -> None:
        self.directory.close()


@dataclass(frozen=True)
class _FileIdentity:
    dev: int
    ino: int
    mode: int


def _open_lexical_root() -> _RootRef:
    raw = os.fspath(ROOT)
    if not os.path.isabs(raw) or raw == "/" or raw.endswith("/") or "\x00" in raw:
        raise ApplySafetyError("DELPHI root must be a strict absolute lexical path")
    parts = raw.split("/")[1:]
    if any(part in ("", ".", "..") or not part.isprintable() for part in parts):
        raise ApplySafetyError("DELPHI root contains an ambiguous lexical component")
    try:
        fd = os.open("/", _dir_flags())
    except OSError as exc:
        raise ApplySafetyError(f"cannot anchor DELPHI root at /: {exc}") from exc
    try:
        for part in parts:
            entry = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                raise ApplySafetyError(
                    f"DELPHI lexical root component is not a real directory: {part}")
            next_fd = os.open(part, _dir_flags(), dir_fd=fd)
            opened = os.fstat(next_fd)
            if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
                os.close(next_fd)
                raise ApplySafetyError(f"DELPHI root component changed while opening: {part}")
            os.close(fd)
            fd = next_fd
        opened = os.fstat(fd)
        return _RootRef(Path(raw), fd, opened.st_dev, opened.st_ino)
    except (OSError, ApplySafetyError) as exc:
        os.close(fd)
        if isinstance(exc, ApplySafetyError):
            raise
        raise ApplySafetyError(f"cannot open DELPHI lexical root safely: {exc}") from exc


def _root() -> Path:
    root = _open_lexical_root()
    try:
        return root.path
    finally:
        root.close()


def _dir_flags() -> int:
    return (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))


def _file_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_controlled_dir(parts: tuple[str, ...], *, create_last: bool = False) -> _DirRef:
    root = _open_lexical_root()
    fd = os.dup(root.fd)
    try:
        for index, part in enumerate(parts):
            if not part or part in (".", "..") or "/" in part:
                raise ApplySafetyError(f"invalid controlled directory component: {part!r}")
            try:
                entry = os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if not (create_last and index == len(parts) - 1):
                    raise ApplySafetyError(
                        f"controlled directory is missing: {'/'.join(parts[:index + 1])}")
                os.mkdir(part, 0o700, dir_fd=fd)
                os.fsync(fd)
                entry = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                raise ApplySafetyError(
                    f"controlled path component is not a real directory: {part}")
            next_fd = os.open(part, _dir_flags(), dir_fd=fd)
            opened = os.fstat(next_fd)
            if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
                os.close(next_fd)
                raise ApplySafetyError(f"controlled directory changed while opening: {part}")
            os.close(fd)
            fd = next_fd
        current = os.fstat(fd)
        return _DirRef(root, parts, fd, current.st_dev, current.st_ino)
    except Exception:
        os.close(fd)
        root.close()
        raise


def _revalidate_dir(ref: _DirRef) -> None:
    held_root = os.fstat(ref.root.fd)
    if (held_root.st_dev, held_root.st_ino) != (ref.root.dev, ref.root.ino):
        raise ApplySafetyError("held DELPHI root descriptor changed identity")
    current = os.fstat(ref.fd)
    if (current.st_dev, current.st_ino) != (ref.dev, ref.ino):
        raise ApplySafetyError("held directory descriptor changed identity")
    fresh = _open_controlled_dir(ref.parts)
    try:
        if ((fresh.root.dev, fresh.root.ino) != (ref.root.dev, ref.root.ino)
                or fresh.root.path != ref.root.path):
            raise ApplySafetyError("DELPHI lexical root changed identity")
        if (fresh.dev, fresh.ino) != (ref.dev, ref.ino):
            raise ApplySafetyError("controlled directory path changed identity")
    finally:
        fresh.close()


def _normalize_relative(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ApplySafetyError("target path must be a non-empty string")
    if value.startswith("/") or value.endswith("/"):
        raise ApplySafetyError(f"target path is not DELPHI-root-relative: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ApplySafetyError(f"target path contains traversal or ambiguity: {value!r}")
    if any("\\" in part or not part.isprintable() for part in parts):
        raise ApplySafetyError(f"target path contains an unsafe component: {value!r}")
    root = _root()
    candidate = root.joinpath(*parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ApplySafetyError(f"target escapes DELPHI root: {value!r}") from exc
    if candidate == root:
        raise ApplySafetyError("target must be strictly below DELPHI root")
    return "/".join(parts)


def _check_target_policy(cfg: dict, rel: str, kind: str) -> None:
    if kind == "config":
        if rel != "config.json":
            raise ApplySafetyError("config amendment target identity is invalid")
        return
    pattern = str((cfg.get("orchestrator") or {}).get("editable_files_regex") or "")
    try:
        allowed = bool(pattern and re.fullmatch(pattern, rel))
    except re.error as exc:
        raise ApplySafetyError(f"orchestrator target allowlist is invalid: {exc}") from exc
    if not allowed:
        raise ApplySafetyError(f"file amendment path is not allowlisted: {rel}")


def _read_fd(fd: int) -> bytes:
    chunks = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_regular_at_held(directory: _DirRef, name: str) -> tuple[bytes, os.stat_result]:
    try:
        entry = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ApplySafetyError(f"required regular file is missing: {name}") from exc
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise ApplySafetyError(f"target is not a regular non-symlink file: {name}")
    try:
        fd = os.open(name, _file_flags(), dir_fd=directory.fd)
    except OSError as exc:
        raise ApplySafetyError(f"cannot safely open regular file {name}: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
            raise ApplySafetyError(f"file changed while opening: {name}")
        return _read_fd(fd), opened
    finally:
        os.close(fd)


def _read_regular_at(directory: _DirRef, name: str) -> tuple[bytes, os.stat_result]:
    _revalidate_dir(directory)
    return _read_regular_at_held(directory, name)


def _open_regular_relative(rel: str) -> tuple[_TargetRef, bytes]:
    rel = _normalize_relative(rel)
    parts = tuple(rel.split("/"))
    directory = _open_controlled_dir(parts[:-1])
    try:
        payload, opened = _read_regular_at(directory, parts[-1])
        canonical = str(directory.root.path.joinpath(*parts))
        return (_TargetRef(directory, rel, canonical, parts[-1], opened.st_dev,
                           opened.st_ino, stat.S_IMODE(opened.st_mode)), payload)
    except Exception:
        directory.close()
        raise


def _open_target(cfg: dict, rel: str, kind: str) -> tuple[_TargetRef, bytes]:
    rel = _normalize_relative(rel)
    _check_target_policy(cfg, rel, kind)
    return _open_regular_relative(rel)


def _revalidate_parent(ref: _TargetRef) -> None:
    _revalidate_dir(ref.directory)


def _read_target_again(ref: _TargetRef, *, same_identity: bool) -> tuple[bytes, os.stat_result]:
    _revalidate_parent(ref)
    payload, opened = _read_regular_at(ref.directory, ref.name)
    if same_identity and (opened.st_dev, opened.st_ino) != (ref.dev, ref.ino):
        raise ApplySafetyError(f"target identity changed before mutation: {ref.rel}")
    return payload, opened


def _write_bytes(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("zero-length filesystem write")
        view = view[written:]


def _write_all(fd: int, payload: bytes) -> None:
    """Target-temp write seam used by fault-injection regressions."""
    _write_bytes(fd, payload)


_RENAME_EXCHANGE = 2


def _rename_exchange_at(source: str, target: str, dir_fd: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ApplySafetyError("Linux renameat2(RENAME_EXCHANGE) is unavailable")
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                          ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    result = renameat2(dir_fd, os.fsencode(source), dir_fd, os.fsencode(target),
                       _RENAME_EXCHANGE)
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), f"{source}<->{target}")


def _replace_at(source: str, target: str, dir_fd: int) -> None:
    """Conditional target-exchange seam used by fault-injection regressions."""
    _rename_exchange_at(source, target, dir_fd)


def _atomic_replace_ref(ref: _TargetRef, expected: bytes, desired: bytes,
                        mode: int, *, expected_identity: tuple[int, int] | None = None) -> None:
    current, opened = _read_target_again(ref, same_identity=True)
    if current != expected:
        raise ApplySafetyError(f"target changed before mutation: {ref.rel}")
    if expected_identity and (opened.st_dev, opened.st_ino) != expected_identity:
        raise ApplySafetyError(f"target identity changed since prepared snapshot: {ref.rel}")

    temp_name = f".{ref.name}.apply-{uuid.uuid4().hex}.tmp"
    temp_created = False
    try:
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        fd = os.open(temp_name, flags, 0o600, dir_fd=ref.directory.fd)
        temp_created = True
        try:
            _write_all(fd, desired)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)

        _revalidate_parent(ref)
        current, opened = _read_target_again(ref, same_identity=True)
        if current != expected:
            raise ApplySafetyError(f"target changed at replace boundary: {ref.rel}")
        if expected_identity and (opened.st_dev, opened.st_ino) != expected_identity:
            raise ApplySafetyError(f"target identity changed at replace boundary: {ref.rel}")
        _replace_control_at(temp_name, ref.name, ref.directory.fd)
        temp_created = False
        os.fsync(ref.directory.fd)

        _revalidate_parent(ref)
        readback, replaced = _read_regular_at(ref.directory, ref.name)
        if readback != desired:
            raise ApplySafetyError(f"target readback does not match after snapshot: {ref.rel}")
        if stat.S_IMODE(replaced.st_mode) != mode:
            raise ApplySafetyError(f"target mode readback failed: {ref.rel}")
    finally:
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=ref.directory.fd)
                os.fsync(ref.directory.fd)
            except FileNotFoundError:
                pass


def _revalidate_record_evidence(cfg: dict, row: dict) -> dict:
    physical = {column: row[column] for column in JOURNAL_COLUMNS}
    return _validate_journal_row(cfg, physical)


def _inspect_exchange(cfg: dict, row: dict) -> tuple[
        _TargetRef, bytes, os.stat_result, bytes, os.stat_result]:
    ref, target_bytes = _open_target(cfg, row["target_rel"], row["kind"])
    try:
        target_stat = os.stat(ref.name, dir_fd=ref.directory.fd, follow_symlinks=False)
        exchange_parent, _, exchange_name = row["exchange_rel"].rpartition("/")
        target_parent = row["target_rel"].rpartition("/")[0]
        if exchange_parent != target_parent:
            raise ApplySafetyError("exchange file is not beside the target")
        exchange_bytes, exchange_stat = _read_regular_at(ref.directory, exchange_name)
        return ref, target_bytes, target_stat, exchange_bytes, exchange_stat
    except Exception:
        ref.close()
        raise


def _layout_is_before(row: dict, target_bytes: bytes, target_stat: os.stat_result,
                      exchange_bytes: bytes, exchange_stat: os.stat_result) -> bool:
    return (
        target_bytes == row["_before"]
        and (target_stat.st_dev, target_stat.st_ino)
        == (int(row["target_dev"]), int(row["target_ino"]))
        and stat.S_IMODE(target_stat.st_mode) == int(row["mode"], 8)
        and exchange_bytes == row["_after"]
        and (exchange_stat.st_dev, exchange_stat.st_ino)
        == (int(row["exchange_dev"]), int(row["exchange_ino"]))
        and stat.S_IMODE(exchange_stat.st_mode) == int(row["exchange_mode"], 8)
    )


def _layout_is_after(row: dict, target_bytes: bytes, target_stat: os.stat_result,
                     exchange_bytes: bytes, exchange_stat: os.stat_result) -> bool:
    return (
        target_bytes == row["_after"]
        and (target_stat.st_dev, target_stat.st_ino)
        == (int(row["exchange_dev"]), int(row["exchange_ino"]))
        and stat.S_IMODE(target_stat.st_mode) == int(row["mode"], 8)
        and exchange_bytes == row["_before"]
        and (exchange_stat.st_dev, exchange_stat.st_ino)
        == (int(row["target_dev"]), int(row["target_ino"]))
        and stat.S_IMODE(exchange_stat.st_mode) == int(row["mode"], 8)
    )


def _recorded_after_at_target(row: dict, payload: bytes,
                              opened: os.stat_result) -> bool:
    return (
        payload == row["_after"]
        and (opened.st_dev, opened.st_ino)
        == (int(row["exchange_dev"]), int(row["exchange_ino"]))
        and stat.S_IMODE(opened.st_mode) == int(row["mode"], 8)
    )


def _recorded_after_at_exchange(row: dict, payload: bytes,
                                opened: os.stat_result) -> bool:
    return (
        payload == row["_after"]
        and (opened.st_dev, opened.st_ino)
        == (int(row["exchange_dev"]), int(row["exchange_ino"]))
        and stat.S_IMODE(opened.st_mode) == int(row["exchange_mode"], 8)
    )


def _displaced_values(payload: bytes, opened: os.stat_result) -> dict[str, str]:
    return {
        "displaced_dev": str(opened.st_dev),
        "displaced_ino": str(opened.st_ino),
        "displaced_mode": f"{stat.S_IMODE(opened.st_mode):04o}",
        "displaced_sha256": _sha(payload),
        "displaced_size": str(len(payload)),
    }


def _matches_displaced(row: dict, payload: bytes, opened: os.stat_result) -> bool:
    return (
        len(payload) == int(row["displaced_size"])
        and _sha(payload) == row["displaced_sha256"]
        and (opened.st_dev, opened.st_ino)
        == (int(row["displaced_dev"]), int(row["displaced_ino"]))
        and stat.S_IMODE(opened.st_mode) == int(row["displaced_mode"], 8)
    )


def _layout_is_unexpected_displaced(
        row: dict, target_bytes: bytes, target_stat: os.stat_result,
        exchange_bytes: bytes, exchange_stat: os.stat_result) -> bool:
    return (
        _recorded_after_at_target(row, target_bytes, target_stat)
        and not _layout_is_after(
            row, target_bytes, target_stat, exchange_bytes, exchange_stat)
    )


def _layout_is_abort_exchanged(
        row: dict, target_bytes: bytes, target_stat: os.stat_result,
        exchange_bytes: bytes, exchange_stat: os.stat_result) -> bool:
    return (
        _recorded_after_at_target(row, target_bytes, target_stat)
        and _matches_displaced(row, exchange_bytes, exchange_stat)
    )


def _layout_is_abort_rolled_back(
        row: dict, target_bytes: bytes, target_stat: os.stat_result,
        exchange_bytes: bytes, exchange_stat: os.stat_result) -> bool:
    return (
        _matches_displaced(row, target_bytes, target_stat)
        and _recorded_after_at_exchange(row, exchange_bytes, exchange_stat)
    )


def _atomic_replace_bytes(cfg: dict, rel: str, expected: bytes, desired: bytes,
                          mode: int, *, kind: str = "file",
                          expected_identity: tuple[int, int] | None = None,
                          record: dict | None = None) -> None:
    if record is None:
        raise ApplySafetyError("journal-bound exchange record is required")
    row = _revalidate_record_evidence(cfg, record)
    if (row["target_rel"] != rel or row["kind"] != kind
            or row["_before"] != expected or row["_after"] != desired
            or int(row["mode"], 8) != mode):
        raise ApplySafetyError("mutation request contradicts prepared journal evidence")
    recorded_identity = (int(row["target_dev"]), int(row["target_ino"]))
    if expected_identity is not None and expected_identity != recorded_identity:
        raise ApplySafetyError("mutation identity contradicts prepared journal evidence")

    ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(cfg, row)
    exchange_name = row["exchange_rel"].rpartition("/")[2]
    try:
        if not _layout_is_before(row, target_bytes, target_stat,
                                 exchange_bytes, exchange_stat):
            raise ApplySafetyError("prepared target/exchange identity is not the before layout")
        _revalidate_record_evidence(cfg, row)
        _revalidate_parent(ref)
        target_bytes, target_stat = _read_regular_at(ref.directory, ref.name)
        exchange_bytes, exchange_stat = _read_regular_at(ref.directory, exchange_name)
        if not _layout_is_before(row, target_bytes, target_stat,
                                 exchange_bytes, exchange_stat):
            raise ApplySafetyError("target/exchange changed at conditional exchange boundary")
        _replace_at(exchange_name, ref.name, ref.directory.fd)
        os.fsync(ref.directory.fd)
        try:
            _revalidate_record_evidence(cfg, row)
            _revalidate_parent(ref)
            target_bytes, target_stat = _read_regular_at(ref.directory, ref.name)
            exchange_bytes, exchange_stat = _read_regular_at(ref.directory, exchange_name)
            if not _layout_is_after(row, target_bytes, target_stat,
                                    exchange_bytes, exchange_stat):
                raise ApplySafetyError("conditional exchange displaced unexpected evidence")
        except Exception as exc:
            observed_target, observed_target_stat = _read_regular_at_held(
                ref.directory, ref.name)
            observed_exchange, observed_exchange_stat = _read_regular_at_held(
                ref.directory, exchange_name)
            abort_row = None
            abort_record_error = None
            if _layout_is_unexpected_displaced(
                    row, observed_target, observed_target_stat,
                    observed_exchange, observed_exchange_stat):
                # Bind the concurrent file before rolling the exchange back.
                # If the process dies after rollback, abort_prepared makes the
                # restored layout independently recoverable.
                displaced = _displaced_values(
                    observed_exchange, observed_exchange_stat)
                abort_row = dict(row)
                abort_row.update(displaced)
                try:
                    abort_row = _append_abort_prepared_transition(
                        cfg, row, observed_exchange, observed_exchange_stat)
                except Exception as record_exc:
                    # The concurrent target still has priority over the
                    # journal error: restore it before surfacing the failure.
                    abort_record_error = record_exc
            _rename_exchange_at(exchange_name, ref.name, ref.directory.fd)
            os.fsync(ref.directory.fd)
            restored_target, restored_stat = _read_regular_at_held(ref.directory, ref.name)
            restored_exchange, restored_exchange_stat = _read_regular_at_held(
                ref.directory, exchange_name)
            if abort_row is not None:
                if not _layout_is_abort_rolled_back(
                        abort_row, restored_target, restored_stat,
                        restored_exchange, restored_exchange_stat):
                    raise ApplySafetyError(
                        "conditional exchange abort rollback validation failed") from exc
                if abort_record_error is not None:
                    raise ApplySafetyError(
                        "conditional exchange rolled back but abort intent was not durable"
                    ) from abort_record_error
                final = _append_state_transition(cfg, abort_row, "aborted")
                _cleanup_final_exchange(cfg, final, "aborted")
            elif not _layout_is_before(row, restored_target, restored_stat,
                                       restored_exchange, restored_exchange_stat):
                raise ApplySafetyError(
                    "conditional exchange mismatch and rollback validation failed") from exc
            raise
    finally:
        ref.close()


def _atomic_revert_exchange(cfg: dict, row: dict) -> None:
    row = _revalidate_record_evidence(cfg, row)
    ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(cfg, row)
    exchange_name = row["exchange_rel"].rpartition("/")[2]
    try:
        if not _layout_is_after(row, target_bytes, target_stat,
                                exchange_bytes, exchange_stat):
            raise ApplySafetyError("revert target/exchange identity is not the live layout")
        _revalidate_record_evidence(cfg, row)
        _revalidate_parent(ref)
        target_bytes, target_stat = _read_regular_at(ref.directory, ref.name)
        exchange_bytes, exchange_stat = _read_regular_at(ref.directory, exchange_name)
        if not _layout_is_after(row, target_bytes, target_stat,
                                exchange_bytes, exchange_stat):
            raise ApplySafetyError("revert layout changed at conditional exchange boundary")
        _replace_at(exchange_name, ref.name, ref.directory.fd)
        os.fsync(ref.directory.fd)
        try:
            _revalidate_record_evidence(cfg, row)
            target_bytes, target_stat = _read_regular_at(ref.directory, ref.name)
            exchange_bytes, exchange_stat = _read_regular_at(ref.directory, exchange_name)
            if not _layout_is_before(row, target_bytes, target_stat,
                                     exchange_bytes, exchange_stat):
                raise ApplySafetyError("revert exchange displaced unexpected evidence")
        except Exception as exc:
            _rename_exchange_at(exchange_name, ref.name, ref.directory.fd)
            os.fsync(ref.directory.fd)
            restored_target, restored_stat = _read_regular_at_held(ref.directory, ref.name)
            restored_exchange, restored_exchange_stat = _read_regular_at_held(
                ref.directory, exchange_name)
            if not _layout_is_after(row, restored_target, restored_stat,
                                    restored_exchange, restored_exchange_stat):
                raise ApplySafetyError(
                    "revert exchange mismatch and rollback validation failed") from exc
            raise
    finally:
        ref.close()


def _atomic_abort_exchange(cfg: dict, row: dict) -> None:
    """Reverse an exchange that displaced an unrecorded concurrent target."""
    row = _revalidate_record_evidence(cfg, row)
    ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(
        cfg, row)
    exchange_name = row["exchange_rel"].rpartition("/")[2]
    try:
        if not _layout_is_abort_exchanged(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat):
            raise ApplySafetyError(
                "abort target/exchange identity is not the displaced layout")
        _revalidate_record_evidence(cfg, row)
        _revalidate_parent(ref)
        target_bytes, target_stat = _read_regular_at(ref.directory, ref.name)
        exchange_bytes, exchange_stat = _read_regular_at(
            ref.directory, exchange_name)
        if not _layout_is_abort_exchanged(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat):
            raise ApplySafetyError(
                "abort layout changed at conditional exchange boundary")
        _replace_at(exchange_name, ref.name, ref.directory.fd)
        os.fsync(ref.directory.fd)
        _revalidate_record_evidence(cfg, row)
        target_bytes, target_stat = _read_regular_at_held(ref.directory, ref.name)
        exchange_bytes, exchange_stat = _read_regular_at_held(
            ref.directory, exchange_name)
        if not _layout_is_abort_rolled_back(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat):
            raise ApplySafetyError(
                "abort rollback did not restore displaced target evidence")
    finally:
        ref.close()


def _cleanup_final_exchange(cfg: dict, row: dict, state: str) -> None:
    if state not in ("keep", "revert", "aborted"):
        return
    exchange_name = row["exchange_rel"].rpartition("/")[2]
    try:
        ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(
            cfg, row)
    except ApplySafetyError as exc:
        # Missing exchange evidence is valid only after a prior successful
        # final cleanup; prove the surviving target identity directly.
        ref, target_bytes = _open_target(cfg, row["target_rel"], row["kind"])
        try:
            try:
                os.stat(exchange_name, dir_fd=ref.directory.fd,
                        follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise exc
            target_stat = os.stat(ref.name, dir_fd=ref.directory.fd,
                                  follow_symlinks=False)
            target_ok = (
                state == "keep" and target_bytes == row["_after"]
                and (target_stat.st_dev, target_stat.st_ino)
                == (int(row["exchange_dev"]), int(row["exchange_ino"]))
                or state == "revert" and target_bytes == row["_before"]
                and (target_stat.st_dev, target_stat.st_ino)
                == (int(row["target_dev"]), int(row["target_ino"]))
                or state == "aborted"
                and _matches_displaced(row, target_bytes, target_stat)
            )
            if (not target_ok or state != "aborted"
                    and stat.S_IMODE(target_stat.st_mode) != int(row["mode"], 8)):
                raise ApplySafetyError("final target identity is invalid after cleanup") from exc
            return
        finally:
            ref.close()
    try:
        if state == "keep":
            expected_layout = _layout_is_after(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat)
        elif state == "revert":
            expected_layout = _layout_is_before(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat)
        else:
            expected_layout = _layout_is_abort_rolled_back(
                row, target_bytes, target_stat, exchange_bytes, exchange_stat)
        if not expected_layout:
            raise ApplySafetyError("cannot clean contradictory final exchange evidence")
        _revalidate_parent(ref)
        os.unlink(exchange_name, dir_fd=ref.directory.fd)
        os.fsync(ref.directory.fd)
    finally:
        ref.close()


def _atomic_replace_controlled(rel: str, expected: bytes, desired: bytes, mode: int) -> None:
    ref, current = _open_regular_relative(rel)
    try:
        if current != expected:
            raise ApplySafetyError(f"controlled file changed before replace: {rel}")
        _atomic_replace_ref(ref, expected, desired, mode)
    finally:
        ref.close()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _new_experiment_id() -> str:
    return f"exp-{time.strftime('%Y%m%d', time.gmtime())}-{uuid.uuid4().hex}"


def _exclusive_evidence_write(directory_fd: int, name: str,
                              payload: bytes) -> os.stat_result:
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        _write_bytes(fd, payload)
        os.fsync(fd)
        return os.fstat(fd)
    finally:
        os.close(fd)


def _json_cell(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=True, separators=(",", ":"))


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ApplySafetyError("value is not canonical JSON") from exc


def _decimal_text(value: object, field: str, *,
                  max_chars: int = _DECLARED_DECIMAL_MAX_CHARS) -> str:
    if isinstance(value, bool) or type(value) not in (int, float, str):
        raise ApplySafetyError(f"{field} must be a finite decimal")
    raw = str(value)
    if (not raw or len(raw) > max_chars or not _CANONICAL_DECIMAL_RE.fullmatch(raw)
            or raw == "-0"):
        raise ApplySafetyError(f"{field} must use bounded canonical decimal text")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ApplySafetyError(f"{field} must be a finite decimal") from exc
    if not number.is_finite():
        raise ApplySafetyError(f"{field} must be finite")
    return raw


def _render_decimal(value: Decimal, field: str) -> str:
    if not value.is_finite():
        raise ApplySafetyError(f"{field} must be finite")
    rendered = "0" if value == 0 else format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return _decimal_text(rendered, field, max_chars=_RESULT_DECIMAL_MAX_CHARS)


def _scaled_integer(value: Decimal) -> tuple[int, int]:
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in digits)) if digits else 0
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return coefficient * (10 ** exponent), 0
    return coefficient, -exponent


def _exact_scaled_sum(values: list[Decimal]) -> tuple[int, int]:
    if not values:
        return 0, 0
    parts = [_scaled_integer(value) for value in values]
    scale = max(part_scale for _, part_scale in parts)
    total = sum(coefficient * (10 ** (scale - part_scale))
                for coefficient, part_scale in parts)
    return total, scale


def _decimal_from_scaled_integer(value: int, scale: int) -> Decimal:
    if value == 0:
        return Decimal(0)
    digits = tuple(int(digit) for digit in str(abs(value)))
    return Decimal((1 if value < 0 else 0, digits, -scale))


def _mean_half_even(total: int, scale: int, count: int) -> Decimal:
    """Round the exact rational mean half-even to 100 decimal places."""
    if count <= 0:
        raise ApplySafetyError("metric mean selection is empty")
    if _MEAN_DECIMAL_PLACES >= scale:
        numerator = total * (10 ** (_MEAN_DECIMAL_PLACES - scale))
        denominator = count
    else:
        numerator = total
        denominator = count * (10 ** (scale - _MEAN_DECIMAL_PLACES))
    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    twice_remainder = remainder * 2
    if twice_remainder > denominator or (
            twice_remainder == denominator and quotient % 2 == 1):
        quotient += 1
    return _decimal_from_scaled_integer(sign * quotient, _MEAN_DECIMAL_PLACES)


def _normalize_metric(value: object) -> dict:
    if type(value) is not dict:
        raise ApplySafetyError("metric must be an object")
    if any(type(key) is not str for key in value):
        raise ApplySafetyError("metric field names must be strings")
    if type(value.get("schema")) is not int or value.get("schema") != 1:
        raise ApplySafetyError("unknown metric schema")
    if type(value.get("type")) is not str or value.get("type") != "tsv_aggregate":
        raise ApplySafetyError("unknown metric type")
    aggregate = value.get("aggregate")
    if type(aggregate) is not str:
        raise ApplySafetyError("metric aggregate must be a string")
    expected = {
        "schema", "type", "path", "where", "aggregate", "comparator", "threshold",
    }
    if aggregate in ("sum", "mean"):
        expected.add("column")
    if set(value) != expected:
        raise ApplySafetyError("metric fields do not match the TSV aggregate contract")
    if aggregate not in _METRIC_AGGREGATES:
        raise ApplySafetyError("unknown metric aggregate")
    comparator = value.get("comparator")
    if type(comparator) is not str:
        raise ApplySafetyError("metric comparator must be a string")
    if comparator not in _METRIC_COMPARATORS:
        raise ApplySafetyError("unknown metric comparator")
    path = value.get("path")
    if type(path) is not str:
        raise ApplySafetyError("metric evidence path must be a string")
    rel = _normalize_relative(path)
    if not _METRIC_PATH_RE.fullmatch(rel):
        raise ApplySafetyError("metric evidence path is not allowlisted")
    where = value.get("where")
    if type(where) is not dict or len(where) > 16:
        raise ApplySafetyError("metric where must be a small exact-match object")
    normalized_where = {}
    for key, child in where.items():
        if type(key) is not str or not key or type(child) is not str:
            raise ApplySafetyError("metric where keys and values must be strings")
        _validate_metadata_string(key, "metric.where.key", allow_empty=False)
        _validate_metadata_string(child, f"metric.where.{key}")
        normalized_where[key] = child
    normalized = {
        "schema": 1,
        "type": "tsv_aggregate",
        "path": rel,
        "where": dict(sorted(normalized_where.items())),
        "aggregate": aggregate,
        "comparator": comparator,
        "threshold": _decimal_text(value.get("threshold"), "metric.threshold"),
    }
    if aggregate in ("sum", "mean"):
        column = value.get("column")
        if type(column) is not str or not column:
            raise ApplySafetyError("numeric aggregate requires a column")
        _validate_metadata_string(column, "metric.column", allow_empty=False)
        normalized["column"] = column
    return normalized


def _metric_cell(metric: dict) -> str:
    return _canonical_json(_normalize_metric(metric))


def _decode_metric_cell(row: dict) -> dict:
    try:
        value = json.loads(row["metric"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApplySafetyError("invalid JSON journal metric") from exc
    normalized = _normalize_metric(value)
    if row["metric"] != _canonical_json(normalized):
        raise ApplySafetyError("journal metric is not canonical JSON")
    return normalized


def _validate_metadata_string(value: str, field: str, *, allow_empty: bool = True) -> None:
    if not allow_empty and not value:
        raise ApplySafetyError(f"metadata string {field} must not be empty")
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("C") or category in ("Zl", "Zp"):
            raise ApplySafetyError(f"metadata string {field} contains control/format data")


def _validate_semantic_metadata(value: object, field: str = "metadata") -> None:
    if isinstance(value, str):
        _validate_metadata_string(value, field)
    elif isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise ApplySafetyError(f"{field} contains a non-string key")
            _validate_metadata_string(key, f"{field}.key", allow_empty=False)
            _validate_semantic_metadata(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_semantic_metadata(child, f"{field}[{index}]")
    elif value is not None and type(value) not in (bool, int, float):
        raise ApplySafetyError(f"{field} contains a non-canonical value type")


def _decode_cell(row: dict, field: str) -> str:
    try:
        value = json.loads(row[field])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApplySafetyError(f"invalid JSON journal cell {field}") from exc
    if type(value) is not str:
        raise ApplySafetyError(f"journal cell {field} must encode a string")
    _validate_metadata_string(value, field)
    if row[field] != _json_cell(value):
        raise ApplySafetyError(f"journal cell {field} is not canonical JSON")
    return value


def _validate_evidence_cell(value: str, field: str) -> None:
    for char in value:
        category = unicodedata.category(char)
        if (char != " " and not char.isprintable()) or category.startswith("C") or (
                category.startswith("Z") and char != " "):
            raise ApplySafetyError(
                f"metric evidence {field} contains non-printable or format data")


def _read_metric_tsv(metric: dict) -> tuple[bytes, list[str], list[tuple[int, bytes, dict]]]:
    ref, raw = _open_regular_relative(metric["path"])
    ref.close()
    if len(raw) > 64 * 1024 * 1024:
        raise ApplySafetyError("metric evidence TSV is too large")
    if not raw or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw:
        raise ApplySafetyError("metric evidence TSV has malformed physical framing")
    physical = raw[:-1].split(b"\n")
    if not physical or not physical[0] or any(line == b"" for line in physical):
        raise ApplySafetyError("metric evidence TSV contains an empty physical row")
    if len(physical) > 1_000_001:
        raise ApplySafetyError("metric evidence TSV has too many rows")
    try:
        decoded = [line.decode("utf-8") for line in physical]
    except UnicodeDecodeError as exc:
        raise ApplySafetyError("metric evidence TSV is not UTF-8") from exc
    columns = decoded[0].split("\t")
    if (not columns or any(not column for column in columns)
            or len(columns) != len(set(columns))):
        raise ApplySafetyError("metric evidence TSV header is missing or ambiguous")
    for column in columns:
        _validate_evidence_cell(column, "header")
    required = set(metric["where"])
    if metric["aggregate"] != "count":
        required.add(metric["column"])
    missing = required - set(columns)
    if missing:
        raise ApplySafetyError(
            f"metric evidence TSV lacks declared columns: {sorted(missing)}")
    rows = []
    for line_number, (raw_line, line) in enumerate(
            zip(physical[1:], decoded[1:], strict=True), 2):
        fields = line.split("\t")
        if len(fields) != len(columns):
            raise ApplySafetyError(
                f"metric evidence TSV row {line_number} has the wrong field count")
        row = dict(zip(columns, fields, strict=True))
        for column, cell in row.items():
            _validate_evidence_cell(cell, f"row {line_number} column {column}")
        if metric["aggregate"] != "count":
            _decimal_text(
                row[metric["column"]],
                f"metric evidence row {line_number} column {metric['column']}",
            )
        rows.append((line_number, raw_line, row))
    return raw, columns, rows


def _metric_comparison(value: Decimal, comparator: str, threshold: Decimal) -> bool:
    if comparator == "<":
        return value < threshold
    if comparator == "<=":
        return value <= threshold
    if comparator == "==":
        return value == threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == ">":
        return value > threshold
    raise ApplySafetyError("unknown metric comparator")


def _evaluate_metric(metric_value: object) -> dict:
    metric = _normalize_metric(metric_value)
    raw, _, rows = _read_metric_tsv(metric)
    selected = []
    selection_hash = hashlib.sha256()
    for line_number, raw_line, row in rows:
        if all(row[column] == expected
               for column, expected in metric["where"].items()):
            selected.append(row)
            selection_hash.update(str(line_number).encode("ascii"))
            selection_hash.update(b"\x00")
            selection_hash.update(hashlib.sha256(raw_line).digest())
            selection_hash.update(b"\n")

    aggregate = metric["aggregate"]
    if aggregate == "count":
        value_text = str(len(selected))
    else:
        values = []
        for row in selected:
            raw_value = row[metric["column"]]
            try:
                number = Decimal(_decimal_text(
                    raw_value, f"metric evidence {metric['column']}"))
            except InvalidOperation as exc:
                raise ApplySafetyError(
                    f"metric evidence contains a non-decimal {metric['column']}") from exc
            values.append(number)
        total, scale = _exact_scaled_sum(values)
        if aggregate == "mean":
            value = _mean_half_even(total, scale, len(values))
        else:
            value = _decimal_from_scaled_integer(total, scale)
        value_text = _render_decimal(value, "metric result")
    threshold = Decimal(metric["threshold"])
    canonical_metric = _canonical_json(metric).encode("ascii")
    return {
        "schema": 1,
        "metric_sha256": _sha(canonical_metric),
        "evidence": {
            "path": metric["path"],
            "sha256": _sha(raw),
            "rows": len(rows),
        },
        "selection": {
            "where": metric["where"],
            "matched_rows": len(selected),
            "rows_sha256": selection_hash.hexdigest(),
        },
        "operation": aggregate,
        "column": metric.get("column"),
        "value": value_text,
        "comparator": metric["comparator"],
        "threshold": metric["threshold"],
        "satisfied": _metric_comparison(Decimal(value_text), metric["comparator"],
                                         threshold),
    }


def _validate_metric_result(value: object, metric_value: object) -> dict:
    metric = _normalize_metric(metric_value)
    if type(value) is not dict or set(value) != {
            "schema", "metric_sha256", "evidence", "selection", "operation",
            "column", "value", "comparator", "threshold", "satisfied"}:
        raise ApplySafetyError("metric result fields do not match the contract")
    evidence = value.get("evidence")
    selection = value.get("selection")
    if type(evidence) is not dict or set(evidence) != {"path", "sha256", "rows"}:
        raise ApplySafetyError("metric result evidence identity is malformed")
    if type(selection) is not dict or set(selection) != {
            "where", "matched_rows", "rows_sha256"}:
        raise ApplySafetyError("metric result row selection is malformed")
    if type(value.get("schema")) is not int or value.get("schema") != 1:
        raise ApplySafetyError("unknown metric result schema")
    metric_sha = _sha(_canonical_json(metric).encode("ascii"))
    if type(value.get("metric_sha256")) is not str or value.get(
            "metric_sha256") != metric_sha:
        raise ApplySafetyError("metric result declaration identity mismatch")
    if (type(evidence.get("path")) is not str
            or evidence.get("path") != metric["path"]
            or type(evidence.get("sha256")) is not str
            or not _SHA_RE.fullmatch(evidence.get("sha256", ""))
            or type(evidence.get("rows")) is not int
            or isinstance(evidence.get("rows"), bool) or evidence["rows"] < 0):
        raise ApplySafetyError("metric result evidence identity is invalid")
    if (type(selection.get("where")) is not dict
            or selection.get("where") != metric["where"]
            or type(selection.get("rows_sha256")) is not str
            or not _SHA_RE.fullmatch(selection.get("rows_sha256", ""))
            or type(selection.get("matched_rows")) is not int
            or isinstance(selection.get("matched_rows"), bool)
            or not 0 <= selection["matched_rows"] <= evidence["rows"]):
        raise ApplySafetyError("metric result row selection is invalid")
    expected_column = metric.get("column")
    if (type(value.get("operation")) is not str
            or value.get("operation") != metric["aggregate"]
            or (value.get("column") is not None
                and type(value.get("column")) is not str)
            or value.get("column") != expected_column
            or type(value.get("comparator")) is not str
            or value.get("comparator") != metric["comparator"]
            or type(value.get("threshold")) is not str
            or value.get("threshold") != metric["threshold"]):
        raise ApplySafetyError("metric result operation contradicts its declaration")
    if type(value.get("value")) is not str:
        raise ApplySafetyError("metric result value is not canonical")
    value_text = _decimal_text(
        value["value"], "metric result value", max_chars=_RESULT_DECIMAL_MAX_CHARS)
    if value_text != value["value"]:
        raise ApplySafetyError("metric result value is not canonical")
    if type(value.get("satisfied")) is not bool:
        raise ApplySafetyError("metric result satisfaction must be boolean")
    expected_satisfaction = _metric_comparison(
        Decimal(value_text), metric["comparator"], Decimal(metric["threshold"]))
    if value["satisfied"] != expected_satisfaction:
        raise ApplySafetyError("metric result satisfaction is contradictory")
    if metric["aggregate"] == "count" and value_text != str(
            selection["matched_rows"]):
        raise ApplySafetyError("count result contradicts selected rows")
    normalized = {
        "schema": 1,
        "metric_sha256": metric_sha,
        "evidence": {
            "path": evidence["path"], "sha256": evidence["sha256"],
            "rows": evidence["rows"],
        },
        "selection": {
            "where": metric["where"],
            "matched_rows": selection["matched_rows"],
            "rows_sha256": selection["rows_sha256"],
        },
        "operation": metric["aggregate"],
        "column": metric.get("column"),
        "value": value_text,
        "comparator": metric["comparator"],
        "threshold": metric["threshold"],
        "satisfied": value["satisfied"],
    }
    if _canonical_json(value) != _canonical_json(normalized):
        raise ApplySafetyError("metric result is not canonical")
    return normalized


def _review_result_cell(result: dict) -> str:
    return _canonical_json(result)


def _decode_review_result_cell(row: dict, metric: dict) -> dict:
    try:
        value = json.loads(row["review_result"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApplySafetyError("invalid JSON journal review result") from exc
    result = _validate_metric_result(value, metric)
    if row["review_result"] != _review_result_cell(result):
        raise ApplySafetyError("journal review result is not canonical JSON")
    return result


def _build_config_after(before: bytes, patch: dict) -> tuple[bytes, dict, str]:
    ok, message = validate_config_patch(patch)
    if not ok:
        raise ApplySafetyError(message)
    try:
        cfg = json.loads(before.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplySafetyError("config.json is not valid UTF-8 JSON") from exc
    if type(cfg) is not dict:
        raise ApplySafetyError("config.json root must be an object")
    patch_before = {}
    for key, value in patch.items():
        node = cfg
        parts = key.split(".")
        try:
            for part in parts[:-1]:
                node = node[part]
            patch_before[key] = node[parts[-1]]
            node[parts[-1]] = value
        except (KeyError, TypeError) as exc:
            raise ApplySafetyError(f"config patch target is missing: {key}") from exc
    after = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
    return after, patch_before, message


def _reserve_evidence(*, kind: str, target: _TargetRef, before: bytes, after: bytes,
                      review_after: int, metric: dict, rationale: str, change: str,
                      amendment_meta: dict) -> dict:
    metric = _normalize_metric(metric)
    _validate_metadata_string(rationale, "rationale")
    _validate_metadata_string(change, "change", allow_empty=False)
    _validate_semantic_metadata(amendment_meta, "amendment")
    exp_dir = _open_controlled_dir(_EXP_DIR_PARTS, create_last=True)
    try:
        for _ in range(64):
            exp_id = _new_experiment_id()
            if not _ID_RE.fullmatch(exp_id):
                raise ApplySafetyError("program-generated experiment id is malformed")
            try:
                os.mkdir(exp_id, 0o700, dir_fd=exp_dir.fd)
            except FileExistsError:
                continue
            os.fsync(exp_dir.fd)
            reserved_dir = os.stat(exp_id, dir_fd=exp_dir.fd, follow_symlinks=False)
            if not stat.S_ISDIR(reserved_dir.st_mode):
                raise ApplySafetyError("reserved experiment evidence path is not a directory")
            evidence_dir = os.open(exp_id, _dir_flags(), dir_fd=exp_dir.fd)
            opened_dir = os.fstat(evidence_dir)
            if (opened_dir.st_dev, opened_dir.st_ino) != (
                    reserved_dir.st_dev, reserved_dir.st_ino):
                os.close(evidence_dir)
                raise ApplySafetyError("reserved experiment directory changed while opening")
            exchange_name = f".{target.name}.delphi-{exp_id}.exchange"
            parent_rel = target.rel.rpartition("/")[0]
            exchange_rel = f"{parent_rel}/{exchange_name}" if parent_rel else exchange_name
            exchange_created = False
            try:
                prepared_ts = now_iso()
                before_path = f"agents/orchestrator/experiments/{exp_id}/before.bin"
                after_path = f"agents/orchestrator/experiments/{exp_id}/after.bin"
                meta_path = f"agents/orchestrator/experiments/{exp_id}/meta.json"
                before_stat = _exclusive_evidence_write(evidence_dir, "before.bin", before)
                after_stat = _exclusive_evidence_write(evidence_dir, "after.bin", after)
                _revalidate_parent(target)
                exchange_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                  | getattr(os, "O_CLOEXEC", 0)
                                  | getattr(os, "O_NOFOLLOW", 0))
                exchange_fd = os.open(exchange_name, exchange_flags, 0o600,
                                      dir_fd=target.directory.fd)
                exchange_created = True
                try:
                    _write_all(exchange_fd, after)
                    os.fchmod(exchange_fd, target.mode)
                    os.fsync(exchange_fd)
                    exchange_stat = os.fstat(exchange_fd)
                finally:
                    os.close(exchange_fd)
                os.fsync(target.directory.fd)
                metadata = {
                    "schema": 3,
                    "id": exp_id,
                    "prepared_ts": prepared_ts,
                    "kind": kind,
                    "target_rel": target.rel,
                    "target_canonical": target.canonical,
                    "target_dev": target.dev,
                    "target_ino": target.ino,
                    "before_path": before_path,
                    "before_dev": before_stat.st_dev,
                    "before_ino": before_stat.st_ino,
                    "before_mode": stat.S_IMODE(before_stat.st_mode),
                    "before_sha256": _sha(before),
                    "before_size": len(before),
                    "after_path": after_path,
                    "after_dev": after_stat.st_dev,
                    "after_ino": after_stat.st_ino,
                    "after_mode": stat.S_IMODE(after_stat.st_mode),
                    "after_sha256": _sha(after),
                    "after_size": len(after),
                    "exchange_rel": exchange_rel,
                    "exchange_dev": exchange_stat.st_dev,
                    "exchange_ino": exchange_stat.st_ino,
                    "exchange_mode": stat.S_IMODE(exchange_stat.st_mode),
                    "exchange_sha256": _sha(after),
                    "exchange_size": len(after),
                    "mode": target.mode,
                    "review_after_hours": review_after,
                    "metric": metric,
                    "rationale": rationale,
                    "change": change,
                    "amendment": amendment_meta,
                }
                meta = (json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True) + "\n").encode("utf-8")
                meta_stat = _exclusive_evidence_write(evidence_dir, "meta.json", meta)
                os.fsync(evidence_dir)
            except Exception:
                if exchange_created:
                    try:
                        os.unlink(exchange_name, dir_fd=target.directory.fd)
                        os.fsync(target.directory.fd)
                    except FileNotFoundError:
                        pass
                raise
            finally:
                os.close(evidence_dir)
            return {
                "schema": "3", "id": exp_id, "state": "prepared",
                "transition_ts": prepared_ts, "prepared_ts": prepared_ts,
                "kind": kind, "target_rel": target.rel,
                "target_canonical": target.canonical,
                "target_dev": str(target.dev), "target_ino": str(target.ino),
                "before_path": before_path, "before_dev": str(before_stat.st_dev),
                "before_ino": str(before_stat.st_ino),
                "before_mode": f"{stat.S_IMODE(before_stat.st_mode):04o}",
                "before_sha256": _sha(before), "before_size": str(len(before)),
                "after_path": after_path, "after_dev": str(after_stat.st_dev),
                "after_ino": str(after_stat.st_ino),
                "after_mode": f"{stat.S_IMODE(after_stat.st_mode):04o}",
                "after_sha256": _sha(after), "after_size": str(len(after)),
                "meta_path": meta_path, "meta_dev": str(meta_stat.st_dev),
                "meta_ino": str(meta_stat.st_ino),
                "meta_mode": f"{stat.S_IMODE(meta_stat.st_mode):04o}",
                "meta_sha256": _sha(meta), "meta_size": str(len(meta)),
                "exchange_rel": exchange_rel, "exchange_dev": str(exchange_stat.st_dev),
                "exchange_ino": str(exchange_stat.st_ino),
                "exchange_mode": f"{stat.S_IMODE(exchange_stat.st_mode):04o}",
                "exchange_sha256": _sha(after), "exchange_size": str(len(after)),
                **{column: "" for column in _DISPLACED_COLUMNS},
                "mode": f"{target.mode:04o}",
                "review_after_hours": str(review_after), "metric": _metric_cell(metric),
                "rationale": _json_cell(rationale), "change": _json_cell(change),
                "review_result": "",
            }
        raise ApplySafetyError("could not reserve a unique experiment id")
    finally:
        exp_dir.close()


def _journal_raw(exp_dir: _DirRef) -> bytes:
    try:
        raw, _ = _read_regular_at(exp_dir, APPLY_JOURNAL)
        return raw
    except ApplySafetyError as exc:
        try:
            os.stat(APPLY_JOURNAL, dir_fd=exp_dir.fd, follow_symlinks=False)
        except FileNotFoundError:
            temp_name = f".{APPLY_JOURNAL}.init-{uuid.uuid4().hex}.tmp"
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            fd = os.open(temp_name, flags, 0o600, dir_fd=exp_dir.fd)
            try:
                _write_bytes(fd, JOURNAL_HEADER.encode("ascii"))
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                try:
                    # A hard link is an atomic no-overwrite install. A crash
                    # before it leaves only an ignorable temp; after it, the
                    # journal name always contains the complete durable header.
                    os.link(temp_name, APPLY_JOURNAL, src_dir_fd=exp_dir.fd,
                            dst_dir_fd=exp_dir.fd, follow_symlinks=False)
                    os.fsync(exp_dir.fd)
                except FileExistsError:
                    pass
                raw, _ = _read_regular_at(exp_dir, APPLY_JOURNAL)
                return raw
            finally:
                try:
                    os.unlink(temp_name, dir_fd=exp_dir.fd)
                except FileNotFoundError:
                    pass
        raise exc


def _replace_control_at(source: str, target: str, dir_fd: int) -> None:
    os.replace(source, target, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)


def _rewrite_journal(cfg: dict, expected: bytes, desired: bytes) -> None:
    # Validate the complete candidate before creating or writing any temp file.
    # Callers also do this before invoking this function so a mocked or replaced
    # rewrite seam can never receive invalid journal bytes.
    _parse_journal_raw(cfg, desired)
    exp_dir = _open_controlled_dir(_EXP_DIR_PARTS, create_last=True)
    temp_name = f".{APPLY_JOURNAL}.{uuid.uuid4().hex}.tmp"
    temp_created = False
    try:
        raw, opened = _read_regular_at(exp_dir, APPLY_JOURNAL)
        if raw != expected:
            raise ApplySafetyError("apply journal changed concurrently")
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        fd = os.open(temp_name, flags, 0o600, dir_fd=exp_dir.fd)
        temp_created = True
        try:
            _write_bytes(fd, desired)
            os.fchmod(fd, stat.S_IMODE(opened.st_mode))
            os.fsync(fd)
        finally:
            os.close(fd)
        _revalidate_dir(exp_dir)
        current, current_stat = _read_regular_at(exp_dir, APPLY_JOURNAL)
        if current != expected or (current_stat.st_dev, current_stat.st_ino) != (
                opened.st_dev, opened.st_ino):
            raise ApplySafetyError("apply journal changed at replace boundary")
        _replace_control_at(temp_name, APPLY_JOURNAL, exp_dir.fd)
        temp_created = False
        os.fsync(exp_dir.fd)
        readback, _ = _read_regular_at(exp_dir, APPLY_JOURNAL)
        if readback != desired:
            raise ApplySafetyError("apply journal durable readback failed")
    finally:
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=exp_dir.fd)
            except FileNotFoundError:
                pass
        exp_dir.close()


def _read_snapshot_evidence(rel: str) -> tuple[bytes, _FileIdentity]:
    ref, payload = _open_regular_relative(rel)
    try:
        return payload, _FileIdentity(ref.dev, ref.ino, ref.mode)
    finally:
        ref.close()


def _read_snapshot(rel: str) -> bytes:
    return _read_snapshot_evidence(rel)[0]


def _validate_journal_row(cfg: dict, row: dict) -> dict:
    states = (
        "prepared", "exchanged", "live", "keep", "revert_prepared", "revert",
        "abort_prepared", "aborted",
    )
    if row["schema"] != "3" or row["state"] not in states:
        raise ApplySafetyError("unknown apply journal schema or state")
    if not _ID_RE.fullmatch(row["id"]):
        raise ApplySafetyError("malformed experiment id in apply journal")
    if not _ISO_RE.fullmatch(row["transition_ts"]) or not _ISO_RE.fullmatch(
            row["prepared_ts"]):
        raise ApplySafetyError("malformed apply journal timestamp")
    try:
        time.strptime(row["transition_ts"], "%Y-%m-%dT%H:%M:%SZ")
        time.strptime(row["prepared_ts"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ApplySafetyError("invalid apply journal calendar timestamp") from exc
    if row["transition_ts"] < row["prepared_ts"]:
        raise ApplySafetyError("apply transition predates preparation")
    if row["kind"] not in ("file", "config"):
        raise ApplySafetyError("unknown amendment kind in apply journal")
    rel = _normalize_relative(row["target_rel"])
    _check_target_policy(cfg, rel, row["kind"])
    canonical = str(_root().joinpath(*rel.split("/")))
    if row["target_canonical"] != canonical:
        raise ApplySafetyError("journal target canonical identity mismatch")
    numeric_fields = (
        "target_dev", "target_ino", "before_dev", "before_ino", "before_size",
        "after_dev", "after_ino", "after_size", "meta_dev", "meta_ino",
        "meta_size", "exchange_dev", "exchange_ino", "exchange_size",
    )
    for field in numeric_fields:
        if (not row[field].isdigit() or str(int(row[field])) != row[field]
                or (field.endswith(("_dev", "_ino")) and int(row[field]) <= 0)):
            raise ApplySafetyError(f"invalid numeric journal field: {field}")
    for field in ("before_sha256", "after_sha256", "meta_sha256", "exchange_sha256"):
        if not _SHA_RE.fullmatch(row[field]):
            raise ApplySafetyError(f"invalid journal digest: {field}")
    for field in ("mode", "before_mode", "after_mode", "meta_mode", "exchange_mode"):
        if not re.fullmatch(r"[0-7]{4}", row[field]):
            raise ApplySafetyError(f"invalid mode in journal: {field}")
    if row["state"] in ("abort_prepared", "aborted"):
        for field in ("displaced_dev", "displaced_ino", "displaced_size"):
            if (not row[field].isdigit() or str(int(row[field])) != row[field]
                    or (field.endswith(("_dev", "_ino")) and int(row[field]) <= 0)):
                raise ApplySafetyError(f"invalid displaced journal field: {field}")
        if not re.fullmatch(r"[0-7]{4}", row["displaced_mode"]):
            raise ApplySafetyError("invalid displaced journal mode")
        if not _SHA_RE.fullmatch(row["displaced_sha256"]):
            raise ApplySafetyError("invalid displaced journal digest")
    elif any(row[field] for field in _DISPLACED_COLUMNS):
        raise ApplySafetyError("non-abort transition contains displaced evidence")
    if (not row["review_after_hours"].isdigit()
            or str(int(row["review_after_hours"])) != row["review_after_hours"]
            or not 1 <= int(row["review_after_hours"]) <= 8760):
        raise ApplySafetyError("invalid review metadata in journal")
    metric = _decode_metric_cell(row)
    rationale = _decode_cell(row, "rationale")
    change = _decode_cell(row, "change")
    review_result = None
    if row["state"] in ("keep", "revert_prepared", "revert"):
        review_result = _decode_review_result_cell(row, metric)
        if row["state"] == "keep" and not review_result["satisfied"]:
            raise ApplySafetyError("keep transition has an unsatisfied metric")
    elif row["review_result"]:
        raise ApplySafetyError("pre-review transition contains a metric result")
    base = f"agents/orchestrator/experiments/{row['id']}"
    expected_paths = {
        "before_path": f"{base}/before.bin",
        "after_path": f"{base}/after.bin",
        "meta_path": f"{base}/meta.json",
    }
    for field, expected in expected_paths.items():
        if row[field] != expected:
            raise ApplySafetyError(f"snapshot identity mismatch: {field}")
    target_parent, _, target_name = rel.rpartition("/")
    expected_exchange_name = f".{target_name}.delphi-{row['id']}.exchange"
    expected_exchange_rel = (f"{target_parent}/{expected_exchange_name}"
                             if target_parent else expected_exchange_name)
    if row["exchange_rel"] != expected_exchange_rel:
        raise ApplySafetyError("exchange evidence path is not deterministic")
    before, before_stat = _read_snapshot_evidence(row["before_path"])
    after, after_stat = _read_snapshot_evidence(row["after_path"])
    meta_raw, meta_stat = _read_snapshot_evidence(row["meta_path"])
    for payload, opened, prefix in ((before, before_stat, "before"),
                                    (after, after_stat, "after"),
                                    (meta_raw, meta_stat, "meta")):
        if len(payload) != int(row[f"{prefix}_size"]):
            raise ApplySafetyError(f"{prefix} snapshot size mismatch")
        if _sha(payload) != row[f"{prefix}_sha256"]:
            raise ApplySafetyError(f"{prefix} snapshot digest mismatch")
        if (opened.dev != int(row[f"{prefix}_dev"])
                or opened.ino != int(row[f"{prefix}_ino"])
                or opened.mode != int(row[f"{prefix}_mode"], 8)):
            raise ApplySafetyError(f"{prefix} snapshot physical identity mismatch")
    if (row["exchange_sha256"] != row["after_sha256"]
            or row["exchange_size"] != row["after_size"]
            or row["exchange_mode"] != row["mode"]):
        raise ApplySafetyError("exchange evidence contradicts intended target bytes/mode")
    try:
        metadata = json.loads(meta_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplySafetyError("experiment metadata is malformed") from exc
    canonical_meta = (json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True) + "\n").encode("utf-8")
    if meta_raw != canonical_meta:
        raise ApplySafetyError("experiment metadata serialization is not canonical")
    _validate_semantic_metadata(metadata)
    common = {
        "schema": 3, "id": row["id"], "prepared_ts": row["prepared_ts"],
        "kind": row["kind"], "target_rel": rel, "target_canonical": canonical,
        "target_dev": int(row["target_dev"]), "target_ino": int(row["target_ino"]),
        "before_path": row["before_path"], "before_dev": int(row["before_dev"]),
        "before_ino": int(row["before_ino"]),
        "before_mode": int(row["before_mode"], 8),
        "before_sha256": row["before_sha256"], "before_size": len(before),
        "after_path": row["after_path"], "after_dev": int(row["after_dev"]),
        "after_ino": int(row["after_ino"]), "after_mode": int(row["after_mode"], 8),
        "after_sha256": row["after_sha256"], "after_size": len(after),
        "exchange_rel": row["exchange_rel"],
        "exchange_dev": int(row["exchange_dev"]),
        "exchange_ino": int(row["exchange_ino"]),
        "exchange_mode": int(row["exchange_mode"], 8),
        "exchange_sha256": row["exchange_sha256"],
        "exchange_size": int(row["exchange_size"]),
        "mode": int(row["mode"], 8),
        "review_after_hours": int(row["review_after_hours"]), "metric": metric,
        "rationale": rationale, "change": change,
    }
    if (type(metadata) is not dict or set(metadata) != set(common) | {"amendment"}
            or any(metadata.get(key) != value for key, value in common.items())):
        raise ApplySafetyError("experiment metadata contradicts journal evidence")
    amendment = metadata.get("amendment")
    if type(amendment) is not dict:
        raise ApplySafetyError("experiment amendment metadata is malformed")
    if row["kind"] == "file":
        if amendment != {"content_encoding": "utf-8"}:
            raise ApplySafetyError("file amendment metadata is contradictory")
        try:
            decoded_after = after.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApplySafetyError("file after snapshot is not UTF-8 LLM content") from exc
        if not decoded_after.strip():
            raise ApplySafetyError("file after snapshot is empty")
    else:
        patch = amendment.get("patch")
        patch_before = amendment.get("patch_before")
        if (set(amendment) != {"patch", "patch_before"} or type(patch) is not dict
                or type(patch_before) is not dict):
            raise ApplySafetyError("config amendment metadata is malformed")
        rebuilt, expected_before, _ = _build_config_after(before, patch)
        if rebuilt != after or patch_before != expected_before:
            raise ApplySafetyError("config snapshots contradict the recorded patch")
    validated = dict(row)
    validated.update({"_before": before, "_after": after, "_metadata": metadata,
                      "_metric": metric, "_review_result": review_result})
    return validated


def _parse_journal_raw(cfg: dict, raw: bytes) -> list[dict]:
    """Strictly validate complete physical journal bytes without writing."""
    if not raw.endswith(b"\n"):
        raise ApplySafetyError("apply journal is torn (missing final newline)")
    if b"\r" in raw or b"\x00" in raw:
        raise ApplySafetyError("apply journal requires physical LF framing only")
    physical_lines = raw.split(b"\n")
    if physical_lines[-1] != b"" or any(line == b"" for line in physical_lines[:-1]):
        raise ApplySafetyError("apply journal has missing or extra physical lines")
    try:
        lines = [line.decode("utf-8") for line in physical_lines[:-1]]
    except UnicodeDecodeError as exc:
        raise ApplySafetyError("apply journal is not UTF-8") from exc
    if not lines or lines[0] != JOURNAL_HEADER.rstrip("\n"):
        raise ApplySafetyError("apply journal header does not match exact schema")
    rows = []
    for line_number, line in enumerate(lines[1:], 2):
        if not line:
            raise ApplySafetyError(f"blank apply journal row at line {line_number}")
        fields = line.split("\t")
        if len(fields) != len(JOURNAL_COLUMNS):
            raise ApplySafetyError(f"malformed apply journal row at line {line_number}")
        for column, value in zip(JOURNAL_COLUMNS, fields, strict=True):
            _validate_metadata_string(value, f"journal.{column}")
        rows.append(_validate_journal_row(
            cfg, dict(zip(JOURNAL_COLUMNS, fields, strict=True))))

    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        exp_id = row["id"]
        if exp_id not in groups:
            groups[exp_id] = []
            order.append(exp_id)
        groups[exp_id].append(row)
    unresolved_targets = set()
    valid_sequences = (
        ["prepared"],
        ["prepared", "exchanged"],
        ["prepared", "exchanged", "live"],
        ["prepared", "exchanged", "live", "keep"],
        ["prepared", "exchanged", "live", "revert_prepared"],
        ["prepared", "exchanged", "live", "revert_prepared", "revert"],
        ["prepared", "abort_prepared"],
        ["prepared", "abort_prepared", "aborted"],
    )
    for exp_id in order:
        transitions = groups[exp_id]
        if [row["state"] for row in transitions] not in valid_sequences:
            raise ApplySafetyError(f"invalid state transition sequence for {exp_id}")
        if len(transitions) >= 2:
            first = transitions[0]
            for second in transitions[1:]:
                for field in JOURNAL_COLUMNS:
                    if (field not in ("state", "transition_ts", "review_result",
                                      *_DISPLACED_COLUMNS)
                            and first[field] != second[field]):
                        raise ApplySafetyError(
                            f"state transition evidence changed for {exp_id}")
            for earlier, later in zip(transitions, transitions[1:], strict=False):
                if later["transition_ts"] < earlier["transition_ts"]:
                    raise ApplySafetyError(
                        f"state transition timestamp regressed for {exp_id}")
        review_rows = [row for row in transitions
                       if row["state"] in ("keep", "revert_prepared", "revert")]
        non_review_rows = transitions[:-len(review_rows)] if review_rows else transitions
        if any(row["review_result"] for row in non_review_rows):
            raise ApplySafetyError(f"review evidence predates verdict for {exp_id}")
        if review_rows:
            result_cell = review_rows[0]["review_result"]
            if not result_cell or any(row["review_result"] != result_cell
                                      for row in review_rows[1:]):
                raise ApplySafetyError(
                    f"review evidence changed during transition for {exp_id}")
        abort_rows = [row for row in transitions
                      if row["state"] in ("abort_prepared", "aborted")]
        if abort_rows:
            evidence = {field: abort_rows[0][field] for field in _DISPLACED_COLUMNS}
            if any(any(row[field] for field in _DISPLACED_COLUMNS)
                   for row in transitions[:-len(abort_rows)]):
                raise ApplySafetyError(
                    f"displaced evidence predates abort intent for {exp_id}")
            if any(any(row[field] != evidence[field] for field in _DISPLACED_COLUMNS)
                   for row in abort_rows[1:]):
                raise ApplySafetyError(
                    f"abort evidence changed during transition for {exp_id}")
        if transitions[-1]["state"] in ("prepared", "exchanged", "abort_prepared"):
            target = transitions[0]["target_rel"]
            if target in unresolved_targets:
                raise ApplySafetyError("multiple unresolved applies target the same file")
            unresolved_targets.add(target)
    return rows


def _load_journal(cfg: dict) -> tuple[bytes, list[dict]]:
    exp_dir = _open_controlled_dir(_EXP_DIR_PARTS, create_last=True)
    try:
        raw = _journal_raw(exp_dir)
    finally:
        exp_dir.close()
    return raw, _parse_journal_raw(cfg, raw)


def _row_bytes(row: dict) -> bytes:
    values = []
    for column in JOURNAL_COLUMNS:
        value = row[column]
        if type(value) is not str or "\t" in value or "\r" in value or "\n" in value:
            raise ApplySafetyError(f"unsafe journal field: {column}")
        _validate_metadata_string(value, f"journal.{column}")
        values.append(value)
    return ("\t".join(values) + "\n").encode("utf-8")


def _append_prepared_transition(cfg: dict, row: dict) -> None:
    raw, rows = _load_journal(cfg)
    if row["state"] != "prepared" or any(existing["id"] == row["id"] for existing in rows):
        raise ApplySafetyError("prepared transition reuses an experiment id")
    desired = raw + _row_bytes(row)
    _parse_journal_raw(cfg, desired)
    _rewrite_journal(cfg, raw, desired)
    _load_journal(cfg)


def _append_abort_prepared_transition(
        cfg: dict, prepared: dict, displaced: bytes,
        displaced_stat: os.stat_result) -> dict:
    raw, rows = _load_journal(cfg)
    matching = [row for row in rows if row["id"] == prepared["id"]]
    evidence = _displaced_values(displaced, displaced_stat)
    if matching and matching[-1]["state"] == "abort_prepared":
        if any(matching[-1][field] != value for field, value in evidence.items()):
            raise ApplySafetyError("durable abort intent contradicts displaced evidence")
        return matching[-1]
    if not matching or matching[-1]["state"] != "prepared":
        raise ApplySafetyError("cannot append abort intent after current primary state")
    abort_row = {column: matching[-1][column] for column in JOURNAL_COLUMNS}
    abort_row.update(evidence)
    abort_row["state"] = "abort_prepared"
    abort_row["transition_ts"] = now_iso()
    desired = raw + _row_bytes(abort_row)
    _parse_journal_raw(cfg, desired)
    _rewrite_journal(cfg, raw, desired)
    _, validated = _load_journal(cfg)
    return [row for row in validated if row["id"] == abort_row["id"]][-1]


def _append_state_transition(cfg: dict, prepared: dict, state: str,
                             review_result: dict | None = None) -> dict:
    raw, rows = _load_journal(cfg)
    matching = [row for row in rows if row["id"] == prepared["id"]]
    if matching and matching[-1]["state"] == state:
        if review_result is not None:
            expected = _review_result_cell(
                _validate_metric_result(review_result, matching[-1]["_metric"]))
            if matching[-1]["review_result"] != expected:
                raise ApplySafetyError("replayed verdict contradicts durable metric result")
        return matching[-1]
    prior = {
        "exchanged": "prepared",
        "live": "exchanged",
        "keep": "live",
        "revert_prepared": "live",
        "revert": "revert_prepared",
        "aborted": "abort_prepared",
    }.get(state)
    if prior is None or not matching or matching[-1]["state"] != prior:
        raise ApplySafetyError(f"cannot append {state} after current primary state")
    live = {column: matching[-1][column] for column in JOURNAL_COLUMNS}
    if state in ("keep", "revert_prepared"):
        if review_result is None:
            raise ApplySafetyError(f"{state} requires evaluated metric evidence")
        result = _validate_metric_result(review_result, matching[-1]["_metric"])
        if state == "keep" and not result["satisfied"]:
            raise ApplySafetyError("cannot keep an experiment with an unsatisfied metric")
        live["review_result"] = _review_result_cell(result)
    elif review_result is not None:
        raise ApplySafetyError(f"{state} cannot introduce metric review evidence")
    live["state"] = state
    live["transition_ts"] = now_iso()
    desired = raw + _row_bytes(live)
    _parse_journal_raw(cfg, desired)
    _rewrite_journal(cfg, raw, desired)
    _, validated = _load_journal(cfg)
    return [row for row in validated if row["id"] == live["id"]][-1]


def _append_exchanged_transition(cfg: dict, prepared: dict) -> dict:
    return _append_state_transition(cfg, prepared, "exchanged")


def _append_live_transition(cfg: dict, prepared: dict) -> dict:
    return _append_state_transition(cfg, prepared, "live")


def _markdown_cell(value: str) -> str:
    return " ".join(value.replace("|", "/").split())[:300] or "?"


def _metric_summary(metric: dict) -> str:
    where = ",".join(f"{key}={value}" for key, value in metric["where"].items())
    aggregate = metric["aggregate"]
    if metric.get("column"):
        aggregate += f"({metric['column']})"
    selection = f" where {where}" if where else ""
    return (f"{aggregate} {metric['path']}{selection} "
            f"{metric['comparator']} {metric['threshold']}")


def _read_display() -> tuple[bytes, int]:
    ref, raw = _open_regular_relative("agents/orchestrator/EXPERIMENTS.md")
    mode = ref.mode
    ref.close()
    return raw, mode


def _reconcile_display(cfg: dict, rows: list[dict] | None = None) -> None:
    if rows is None:
        _, rows = _load_journal(cfg)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    lines = [EXPERIMENTS_TEMPLATE]
    display_states = {
        "live": "live", "keep": "keep", "revert_prepared": "revert-pending",
        "revert": "revert", "abort_prepared": "abort-pending",
        "aborted": "aborted",
    }
    for transitions in groups.values():
        latest = transitions[-1]["state"]
        if latest not in display_states:
            continue
        row = transitions[0]
        lines.append(
            f"| {row['id']} | {row['prepared_ts']} | "
            f"{_markdown_cell(_decode_cell(row, 'change'))} | "
            f"{_markdown_cell(_metric_summary(_decode_metric_cell(row)))} | "
            f"{row['review_after_hours']}h | {display_states[latest]} |\n")
    desired = "".join(lines).encode("utf-8")
    raw, mode = _read_display()
    if raw != desired:
        _atomic_replace_controlled(
            "agents/orchestrator/EXPERIMENTS.md", raw, desired, mode)


def _ensure_learning_row(row: dict) -> None:
    rel = "ledger/learnings.md"
    ref, raw = _open_regular_relative(rel)
    mode = ref.mode
    ref.close()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApplySafetyError("learnings journal is not UTF-8") from exc
    if f"({row['id']})" in text:
        return
    line = (f"| {time.strftime('%Y-%m-%d')} | {_markdown_cell(_decode_cell(row, 'change'))} "
            f"({row['id']}) | {_markdown_cell(_decode_cell(row, 'rationale'))[:160]} | "
            f"{_markdown_cell(_metric_summary(_decode_metric_cell(row)))} | "
            "pending |\n").encode("utf-8")
    _atomic_replace_controlled(rel, raw, raw + line, mode)


def recover_prepared_amendments(cfg: dict) -> int:
    """Recover all valid prepared-only applies before starting another run."""
    _, rows = _load_journal(cfg)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    pending = [(transitions[-1], transitions[-1]["state"])
               for transitions in groups.values()
               if transitions[-1]["state"] in (
                   "prepared", "exchanged", "abort_prepared")]

    plans = []
    for row, primary_state in pending:
        checked = _revalidate_record_evidence(cfg, row)
        ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(
            cfg, checked)
        try:
            before_layout = _layout_is_before(
                checked, target_bytes, target_stat, exchange_bytes, exchange_stat)
            after_layout = _layout_is_after(
                checked, target_bytes, target_stat, exchange_bytes, exchange_stat)
            unexpected_displaced = _layout_is_unexpected_displaced(
                checked, target_bytes, target_stat, exchange_bytes, exchange_stat)
            abort_exchanged = (
                primary_state == "abort_prepared"
                and _layout_is_abort_exchanged(
                    checked, target_bytes, target_stat,
                    exchange_bytes, exchange_stat)
            )
            abort_rolled_back = (
                primary_state == "abort_prepared"
                and _layout_is_abort_rolled_back(
                    checked, target_bytes, target_stat,
                    exchange_bytes, exchange_stat)
            )
        finally:
            ref.close()
        if primary_state == "prepared" and before_layout:
            plans.append((checked, "apply", None))
        elif primary_state == "prepared" and after_layout:
            plans.append((checked, "record-exchanged", None))
        elif primary_state == "prepared" and unexpected_displaced:
            plans.append((checked, "prepare-abort", (exchange_bytes, exchange_stat)))
        elif primary_state == "exchanged" and after_layout:
            plans.append((checked, "finalize", None))
        elif primary_state == "abort_prepared" and abort_exchanged:
            plans.append((checked, "rollback-abort", None))
        elif primary_state == "abort_prepared" and abort_rolled_back:
            plans.append((checked, "finalize-abort", None))
        else:
            raise ApplySafetyError(
                f"prepared target/exchange identity matches no recoverable layout: "
                f"{row['target_rel']}")

    recovered = 0
    for row, action, displaced_evidence in plans:
        if action == "prepare-abort":
            displaced, displaced_stat = displaced_evidence
            row = _append_abort_prepared_transition(
                cfg, row, displaced, displaced_stat)
            _atomic_abort_exchange(cfg, row)
            final = _append_state_transition(cfg, row, "aborted")
            _cleanup_final_exchange(cfg, final, "aborted")
            recovered += 1
            continue
        if action == "rollback-abort":
            _atomic_abort_exchange(cfg, row)
            action = "finalize-abort"
        if action == "finalize-abort":
            final = _append_state_transition(cfg, row, "aborted")
            _cleanup_final_exchange(cfg, final, "aborted")
            recovered += 1
            continue
        if action == "apply":
            _atomic_replace_bytes(
                cfg, row["target_rel"], row["_before"], row["_after"],
                int(row["mode"], 8), kind=row["kind"],
                expected_identity=(int(row["target_dev"]), int(row["target_ino"])),
                record=row)
        if action in ("apply", "record-exchanged"):
            row = _append_exchanged_transition(cfg, row)
        live = _append_live_transition(cfg, row)
        _ensure_learning_row(live)
        recovered += 1

    # Revert intent is durable primary state. A crash either side of the
    # reverse exchange is resolved by the two inode-bound layouts.
    _, current_rows = _load_journal(cfg)
    current_groups: dict[str, list[dict]] = {}
    for row in current_rows:
        current_groups.setdefault(row["id"], []).append(row)
    pending_reverts = [transitions for transitions in current_groups.values()
                       if transitions[-1]["state"] == "revert_prepared"]
    for transitions in pending_reverts:
        row = transitions[0]
        ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(
            cfg, row)
        try:
            if not (_layout_is_after(row, target_bytes, target_stat,
                                     exchange_bytes, exchange_stat)
                    or _layout_is_before(row, target_bytes, target_stat,
                                         exchange_bytes, exchange_stat)):
                raise ApplySafetyError("pending revert matches no recoverable layout")
        finally:
            ref.close()
    for transitions in pending_reverts:
        ok, message = _restore(transitions[0]["id"])
        if not ok:
            raise ApplySafetyError(message)
        final = _append_state_transition(cfg, transitions[0], "revert")
        _cleanup_final_exchange(cfg, final, "revert")
        recovered += 1

    # A crash after the durable live transition may have omitted secondary logs.
    _, current_rows = _load_journal(cfg)
    live_rows = [row for row in current_rows if row["state"] == "live"]
    for row in live_rows:
        _ensure_learning_row(row)
    current_groups = {}
    for row in current_rows:
        current_groups.setdefault(row["id"], []).append(row)
    for transitions in current_groups.values():
        if transitions[-1]["state"] in ("keep", "revert", "aborted"):
            _cleanup_final_exchange(cfg, transitions[-1], transitions[-1]["state"])
    _reconcile_display(cfg, current_rows)
    return recovered


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
    """Prepare evidence durably, atomically apply once, then mark it live."""
    recover_prepared_amendments(cfg)
    kind = amd.get("kind")
    if kind == "file":
        rel = _normalize_relative(amd.get("path"))
        _check_target_policy(cfg, rel, "file")
        content = str(amd.get("content", ""))
        if not content.strip():
            return "REJECTED file amendment: empty content"
        after = content.encode("utf-8")
        outcome = f"wrote {rel}"
        amendment_meta = {"content_encoding": "utf-8"}
    elif kind == "config":
        patch = dict(amd.get("patch") or {})
        ok, msg = validate_config_patch(patch)
        if not ok:
            return f"REJECTED config amendment: {msg}"
        rel = "config.json"
        outcome = f"config {msg}"
        after = None
        amendment_meta = {"patch": patch}
    else:
        return f"REJECTED amendment: unknown kind {kind!r}"

    review_after = amd.get("review_after_hours", 24)
    if (type(review_after) is not int or isinstance(review_after, bool)
            or not 1 <= review_after <= 8760):
        return "REJECTED amendment: invalid review_after_hours"
    try:
        metric = _normalize_metric(amd.get("metric"))
    except ApplySafetyError as exc:
        return f"REJECTED amendment: invalid metric — {exc}"
    rationale = str(amd.get("rationale", ""))
    ref, before = _open_target(cfg, rel, kind)
    try:
        if kind == "config":
            after, patch_before, _ = _build_config_after(before, patch)
            amendment_meta["patch_before"] = patch_before
        if before == after:
            raise ApplySafetyError("amendment produces no byte change")
        prepared = _reserve_evidence(
            kind=kind, target=ref, before=before, after=after,
            review_after=review_after, metric=metric,
            rationale=rationale, change=outcome, amendment_meta=amendment_meta)
    finally:
        ref.close()

    _append_prepared_transition(cfg, prepared)
    _atomic_replace_bytes(
        cfg, rel, before, after, int(prepared["mode"], 8), kind=kind,
        expected_identity=(int(prepared["target_dev"]), int(prepared["target_ino"])),
        record=prepared)
    exchanged = _append_exchanged_transition(cfg, prepared)
    live = _append_live_transition(cfg, exchanged)
    _reconcile_display(cfg)
    _ensure_learning_row(live)
    return outcome


def _restore(exp_id: str) -> tuple[bool, str]:
    """Restore a live experiment through its validated, contained evidence."""
    try:
        cfg = load_config()
        _, rows = _load_journal(cfg)
        matching = [row for row in rows if row["id"] == exp_id]
        if matching:
            if matching[-1]["state"] not in ("live", "revert_prepared"):
                return False, f"{exp_id}: experiment is not revertible"
            row = matching[0]
            ref, target_bytes, target_stat, exchange_bytes, exchange_stat = _inspect_exchange(
                cfg, row)
            try:
                already = _layout_is_before(
                    row, target_bytes, target_stat, exchange_bytes, exchange_stat)
                live = _layout_is_after(
                    row, target_bytes, target_stat, exchange_bytes, exchange_stat)
            finally:
                ref.close()
            if already:
                return True, f"{exp_id}: {row['target_rel']} already restored"
            if not live:
                return False, (f"{exp_id}: {row['target_rel']} changed since experiment"
                               " — restore SKIPPED")
            _atomic_revert_exchange(cfg, row)
            return True, f"{exp_id}: restored {row['target_rel']}"

        # Compatibility for pre-journal snapshots. All reads still use the
        # controlled no-follow path; new applies never create this format.
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", exp_id):
            return False, f"{exp_id}: invalid legacy snapshot id"
        base = "agents/orchestrator/experiments"
        try:
            meta_raw = _read_snapshot(f"{base}/{exp_id}.json")
        except ApplySafetyError:
            return False, f"{exp_id}: no snapshot found — cannot restore"
        meta = json.loads(meta_raw.decode("utf-8"))
        if meta.get("kind") == "file":
            rel = _normalize_relative(meta.get("path"))
            _check_target_policy(cfg, rel, "file")
            before = _read_snapshot(f"{base}/{exp_id}.before")
            try:
                after = _read_snapshot(f"{base}/{exp_id}.after")
            except ApplySafetyError:
                after = None
            ref, current = _open_target(cfg, rel, "file")
            mode = ref.mode
            ref.close()
            if current == before:
                return True, f"{exp_id}: {rel} already restored"
            if after is None or current != after:
                return False, f"{exp_id}: {rel} changed since experiment — restore SKIPPED"
            _atomic_replace_controlled(rel, after, before, mode)
            return True, f"{exp_id}: restored {rel}"
        if meta.get("kind") != "config":
            return False, f"{exp_id}: unknown snapshot kind"
        patch_before = meta.get("patch_before") or {}
        if not patch_before:
            return False, f"{exp_id}: empty config snapshot — nothing restored"
        ref, current = _open_target(cfg, "config.json", "config")
        mode = ref.mode
        ref.close()
        desired, current_values, msg = _build_config_after(current, patch_before)
        if current_values == patch_before:
            return True, f"{exp_id}: config already restored"
        _atomic_replace_controlled("config.json", current, desired, mode)
        check_ref, readback = _open_target(cfg, "config.json", "config")
        check_ref.close()
        _, restored_values, _ = _build_config_after(readback, patch_before)
        if restored_values != patch_before:
            return False, f"{exp_id}: config restore readback failed"
        return True, f"{exp_id}: config restore ok ({msg})"
    except (ApplySafetyError, OSError, KeyError, TypeError, ValueError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"{exp_id}: restore error — {exc}"


def _append_review_learning(line: str) -> None:
    rel = "ledger/learnings.md"
    ref, raw = _open_regular_relative(rel)
    mode = ref.mode
    ref.close()
    payload = line.encode("utf-8")
    _atomic_replace_controlled(rel, raw, raw + payload, mode)


def _review_due_epoch(row: dict) -> int:
    return (calendar.timegm(time.strptime(row["prepared_ts"], "%Y-%m-%dT%H:%M:%SZ"))
            + int(row["review_after_hours"]) * 3600)


def _review_now(now_epoch: int | float | None) -> int:
    if now_epoch is None:
        return int(time.time())
    if isinstance(now_epoch, bool) or type(now_epoch) not in (int, float):
        raise ApplySafetyError("review time must be a Unix timestamp")
    try:
        value = Decimal(str(now_epoch))
    except InvalidOperation as exc:
        raise ApplySafetyError("review time must be finite") from exc
    if not value.is_finite():
        raise ApplySafetyError("review time must be finite")
    return int(value)


def review_candidates(cfg: dict, *, now_epoch: int | float | None = None) -> list[dict]:
    """Return only due, primary-live experiments with evaluated file evidence."""
    now = _review_now(now_epoch)
    _, rows = _load_journal(cfg)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    candidates = []
    for transitions in groups.values():
        latest = transitions[-1]
        if latest["state"] != "live" or now < _review_due_epoch(transitions[0]):
            continue
        try:
            result = _evaluate_metric(transitions[0]["_metric"])
        except (ApplySafetyError, OSError, ValueError):
            # Missing or untrustworthy evidence is not a review candidate. It
            # remains live so the exact same experiment can be retried later.
            continue
        due = _review_due_epoch(transitions[0])
        candidates.append({
            "id": transitions[0]["id"],
            "due_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(due)),
            "metric": transitions[0]["_metric"],
            "metric_result": result,
        })
    return candidates


def _metric_result_summary(result: dict) -> str:
    evidence = result["evidence"]
    selection = result["selection"]
    return (f"{evidence['path']} sha256={evidence['sha256']} "
            f"selected={selection['matched_rows']} "
            f"selection_sha256={selection['rows_sha256']} value={result['value']} "
            f"{result['comparator']} {result['threshold']} "
            f"satisfied={str(result['satisfied']).lower()}")


def _validate_review_batch(reviews: object) -> tuple[list[dict], list[str]]:
    if type(reviews) is not list:
        return [], ["reviews:retryable-invalid-batch"]
    id_counts: dict[str, int] = {}
    for review in reviews:
        if type(review) is dict and type(review.get("id")) is str:
            experiment_id = review["id"]
            if _ID_RE.fullmatch(experiment_id):
                id_counts[experiment_id] = id_counts.get(experiment_id, 0) + 1

    valid = []
    notes = []
    expected_fields = {"id", "verdict", "reason", "metric_result"}
    duplicate_notes = set()
    for index, review in enumerate(reviews):
        if (type(review) is dict
                and set(review) in (expected_fields, expected_fields - {"metric_result"})
                and type(review.get("id")) is str
                and _ID_RE.fullmatch(review["id"])
                and type(review.get("verdict")) is str
                and type(review.get("reason")) is str
                and type(review.get("metric_result")) is not dict):
            notes.append(f"{review['id']}:retryable-metric-result")
            continue
        if (type(review) is not dict or set(review) != expected_fields
                or type(review.get("id")) is not str
                or type(review.get("verdict")) is not str
                or type(review.get("reason")) is not str
                or type(review.get("metric_result")) is not dict):
            notes.append(f"review[{index}]:retryable-invalid-shape")
            continue
        try:
            _validate_metadata_string(review["reason"], f"review[{index}].reason")
        except ApplySafetyError:
            notes.append(f"review[{index}]:retryable-invalid-shape")
            continue
        experiment_id = review["id"]
        if not _ID_RE.fullmatch(experiment_id):
            notes.append(f"review[{index}]:retryable-invalid-id")
            continue
        if id_counts.get(experiment_id, 0) > 1:
            if experiment_id not in duplicate_notes:
                notes.append(f"{experiment_id}:retryable-duplicate-review")
                duplicate_notes.add(experiment_id)
            continue
        if review["verdict"] not in ("keep", "revert"):
            notes.append(f"{experiment_id}:retryable-invalid-verdict")
            continue
        valid.append(review)
    return valid, notes


def review_experiments(reviews: object, *,
                       now_epoch: int | float | None = None) -> list[str]:
    validated_reviews, notes = _validate_review_batch(reviews)
    if type(reviews) is not list:
        return notes
    cfg = load_config()
    now = _review_now(now_epoch)
    mutated = False
    for rv in validated_reviews:
        eid = rv["id"]
        verdict = rv["verdict"]
        _, rows = _load_journal(cfg)
        matching = [row for row in rows if row["id"] == eid]
        if not matching or matching[-1]["state"] != "live":
            notes.append(f"{eid}:ignored-not-live")
            continue
        if now < _review_due_epoch(matching[0]):
            notes.append(f"{eid}:ignored-not-due")
            continue
        try:
            expected_result = _evaluate_metric(matching[0]["_metric"])
        except (ApplySafetyError, OSError, ValueError):
            notes.append(f"{eid}:retryable-metric-error")
            continue
        try:
            supplied_result = _validate_metric_result(
                rv.get("metric_result"), matching[0]["_metric"])
        except ApplySafetyError:
            notes.append(f"{eid}:retryable-metric-result")
            continue
        if _review_result_cell(supplied_result) != _review_result_cell(expected_result):
            notes.append(f"{eid}:retryable-metric-result")
            continue
        if verdict == "keep" and not expected_result["satisfied"]:
            notes.append(f"{eid}:retryable-unsatisfied-keep")
            continue
        restore_msg = ""
        if verdict == "keep":
            final = _append_state_transition(
                cfg, matching[0], "keep", expected_result)
            mutated = True
            _cleanup_final_exchange(cfg, final, "keep")
        else:
            prepared_revert = _append_state_transition(
                cfg, matching[0], "revert_prepared", expected_result)
            mutated = True
            restored, restore_msg = _restore(eid)
            if not restored:
                notes.append(f"{eid}:revert-error")
                _append_review_learning(
                    f"| {time.strftime('%Y-%m-%d')} | experiment {eid} revert failed"
                    f" — {_markdown_cell(restore_msg)} | "
                    f"{_markdown_cell(str(rv.get('reason', '')))[:160]} | "
                    f"{_markdown_cell(_metric_result_summary(expected_result))} | "
                    "retryable-error |\n")
                _reconcile_display(cfg)
                continue
            final = _append_state_transition(cfg, prepared_revert, "revert")
            _cleanup_final_exchange(cfg, final, "revert")
        _append_review_learning(
            f"| {time.strftime('%Y-%m-%d')} | experiment {eid} verdict: {verdict}"
            f"{' — ' + _markdown_cell(restore_msg) if restore_msg else ''} | "
            f"{_markdown_cell(str(rv.get('reason', '')))[:160]} | "
            f"{_markdown_cell(_metric_result_summary(expected_result))} | {verdict} |\n")
        notes.append(f"{eid}:{verdict}")
    if mutated:
        _reconcile_display(cfg)
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="diagnose only, apply nothing")
    args = ap.parse_args()
    cfg = load_config()
    recover_prepared_amendments(cfg)
    cfg = load_config()  # a recovered config apply changes the source of truth
    due_reviews = review_candidates(cfg)

    state = ["## RUN LOG (tail)", tail("ledger/results.tsv", 40),
             "## STUCK-STATE HEURISTICS", stuck_heuristics(cfg),
             "## LEARNINGS (tail)", tail("ledger/learnings.md", 12),
             "## EXPERIMENTS DUE FOR REVIEW (primary journal, exact result required)",
             json.dumps(due_reviews, sort_keys=True, ensure_ascii=True)]
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
    reviews = review_experiments(j.get("experiments_review"))
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
