#!/usr/bin/env python3
"""Run Cognee while redacting configured secrets from both output streams."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading


SENSITIVE_NAME = re.compile(
    r"(?:API_KEY|PASSWORD|TOKEN|SECRET|PRIVATE_KEY)(?:$|_)", re.IGNORECASE
)
PROVIDER_MARKER = re.compile(rb"(?i)(?:sk|pk|token|secret|key)[_-]")
TOKEN_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
REPLACEMENT = b"[REDACTED]"
MIN_FRAGMENT = 8


class AnsiStripper:
    NORMAL = 0
    ESCAPE = 1
    CSI = 2
    OSC = 3
    OSC_ESCAPE = 4

    def __init__(self) -> None:
        self.state = self.NORMAL

    def feed(self, data: bytes) -> bytes:
        output = bytearray()
        for byte in data:
            if self.state == self.NORMAL:
                if byte == 0x1B:
                    self.state = self.ESCAPE
                else:
                    output.append(byte)
            elif self.state == self.ESCAPE:
                if byte == ord("["):
                    self.state = self.CSI
                elif byte == ord("]"):
                    self.state = self.OSC
                else:
                    self.state = self.NORMAL
            elif self.state == self.CSI:
                if 0x40 <= byte <= 0x7E:
                    self.state = self.NORMAL
            elif self.state == self.OSC:
                if byte == 0x07:
                    self.state = self.NORMAL
                elif byte == 0x1B:
                    self.state = self.OSC_ESCAPE
            elif self.state == self.OSC_ESCAPE:
                if byte == ord("\\"):
                    self.state = self.NORMAL
                elif byte != 0x1B:
                    self.state = self.OSC
        return bytes(output)


class ProviderTokenFilter:
    def __init__(self) -> None:
        self.pending = b""
        self.redacting = False
        markers = (b"sk-", b"pk-", b"token-", b"secret-", b"key-")
        self.marker_overlap = max(len(marker) for marker in markers) - 1

    def feed(self, chunk: bytes, *, final: bool = False) -> bytes:
        data = self.pending + chunk
        self.pending = b""
        output = bytearray()
        position = 0

        if self.redacting:
            while position < len(data) and data[position] in TOKEN_BYTES:
                position += 1
            if position == len(data):
                return b""
            self.redacting = False

        while position < len(data):
            match = PROVIDER_MARKER.search(data, position)
            if match is None:
                if final:
                    output.extend(data[position:])
                else:
                    keep = min(self.marker_overlap, len(data) - position)
                    emit_end = len(data) - keep
                    output.extend(data[position:emit_end])
                    self.pending = data[emit_end:]
                break

            output.extend(data[position : match.start()])
            token_end = match.end()
            while token_end < len(data) and data[token_end] in TOKEN_BYTES:
                token_end += 1
            suffix_length = token_end - match.end()

            if token_end == len(data) and not final and suffix_length < MIN_FRAGMENT:
                self.pending = data[match.start():]
                break
            if suffix_length >= MIN_FRAGMENT:
                output.extend(REPLACEMENT)
                if token_end == len(data) and not final:
                    self.redacting = True
                    break
                position = token_end
                continue

            output.extend(data[match.start():token_end])
            position = token_end

        return bytes(output)


class ConfiguredSecretFilter:
    def __init__(self, secrets: tuple[bytes, ...]) -> None:
        patterns: set[bytes] = set()
        for secret in secrets:
            if len(secret) < MIN_FRAGMENT:
                patterns.add(secret)
            else:
                patterns.update(
                    secret[offset : offset + MIN_FRAGMENT]
                    for offset in range(len(secret) - MIN_FRAGMENT + 1)
                )
        self.patterns = tuple(sorted(patterns, key=len, reverse=True))
        self.overlap = max((len(pattern) for pattern in self.patterns), default=1) - 1
        self.pending = b""

    @staticmethod
    def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not intervals:
            return []
        intervals.sort()
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            old_start, old_end = merged[-1]
            if start <= old_end:
                merged[-1] = (old_start, max(old_end, end))
            else:
                merged.append((start, end))
        return merged

    def _intervals(self, data: bytes) -> list[tuple[int, int]]:
        intervals: list[tuple[int, int]] = []
        for pattern in self.patterns:
            start = 0
            while True:
                index = data.find(pattern, start)
                if index < 0:
                    break
                intervals.append((index, index + len(pattern)))
                start = index + 1
        return self._merge(intervals)

    def feed(self, chunk: bytes, *, final: bool = False) -> bytes:
        data = self.pending + chunk
        self.pending = b""
        emit_limit = len(data) if final else max(0, len(data) - self.overlap)
        intervals = self._intervals(data)
        output = bytearray()
        cursor = 0
        consumed_until = emit_limit

        for start, end in intervals:
            if start >= emit_limit:
                break
            if cursor < start:
                output.extend(data[cursor:start])
            output.extend(REPLACEMENT)
            cursor = max(cursor, end)
            consumed_until = max(consumed_until, end)
        if cursor < emit_limit:
            output.extend(data[cursor:emit_limit])
        self.pending = data[consumed_until:]
        return bytes(output)


class StreamRedactor:
    def __init__(self, secrets: tuple[bytes, ...]) -> None:
        self.secrets = secrets
        self.ansi = AnsiStripper()
        self.provider = ProviderTokenFilter()
        self.secret = ConfiguredSecretFilter(secrets)

    def feed(self, raw: bytes) -> bytes:
        plain = self.ansi.feed(raw)
        provider_safe = self.provider.feed(plain)
        return self.secret.feed(provider_safe)

    def finish(self) -> bytes:
        provider_safe = self.provider.feed(b"", final=True)
        return self.secret.feed(provider_safe, final=True)

    def finish_record(self) -> bytes:
        output = self.finish()
        self.provider = ProviderTokenFilter()
        self.secret = ConfiguredSecretFilter(self.secrets)
        return output


def _sensitive_values(environment: dict[str, str]) -> tuple[bytes, ...]:
    values: set[bytes] = set()
    for name, value in environment.items():
        if not value or not SENSITIVE_NAME.search(name):
            continue
        encoded = value.encode("utf-8", errors="surrogateescape")
        if len(encoded) >= 4:
            values.add(encoded)
    return tuple(sorted(values, key=len, reverse=True))


def _write_destination(destination, data: bytes) -> None:
    if not data:
        return
    try:
        destination.write(data)
        destination.flush()
    except (BrokenPipeError, OSError):
        pass


def _pump(stream, destination, secrets: tuple[bytes, ...]) -> None:
    redactor = StreamRedactor(secrets)
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        start = 0
        while start < len(chunk):
            newline = chunk.find(b"\n", start)
            end = len(chunk) if newline < 0 else newline + 1
            sanitized = redactor.feed(chunk[start:end])
            if newline >= 0:
                sanitized += redactor.finish_record()
            _write_destination(destination, sanitized)
            start = end
    _write_destination(destination, redactor.finish())


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("usage: cognee-log-redactor.py -- COMMAND [ARG ...]", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["COGNEE_LOG_FILE"] = "false"
    environment["PYTHONUNBUFFERED"] = "1"
    secrets = _sensitive_values(environment)
    child: subprocess.Popen | None = None
    pending_signal: int | None = None

    def forward(signum, _frame) -> None:
        nonlocal pending_signal
        pending_signal = signum
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    handled_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    previous_handlers = {signum: signal.getsignal(signum) for signum in handled_signals}
    for signum in handled_signals:
        signal.signal(signum, forward)

    result = 126
    try:
        child = subprocess.Popen(
            argv[2:],
            env=environment,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
        )
        if pending_signal is not None and child.poll() is None:
            child.send_signal(pending_signal)
        assert child.stdout is not None
        assert child.stderr is not None
        threads = [
            threading.Thread(
                target=_pump,
                args=(child.stdout, sys.stdout.buffer, secrets),
                daemon=True,
            ),
            threading.Thread(
                target=_pump,
                args=(child.stderr, sys.stderr.buffer, secrets),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()
        return_code = child.wait()
        for thread in threads:
            thread.join()
        child.stdout.close()
        child.stderr.close()
        result = return_code if return_code >= 0 else 128 - return_code
    except OSError as exc:
        print(
            f"Cognee log redactor could not start child ({type(exc).__name__})",
            file=sys.stderr,
        )
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
