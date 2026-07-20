#!/usr/bin/env python3
"""Guarded daily commit of Delphi operational state and T3-editable files."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "delphi-snapshot-ready"
REQUIRED_ENV = (
    "EXA_API_KEY",
    "X_BEARER_TOKEN",
    "DELPHI_COGNEE_URL",
    "DELPHI_COGNEE_TOKEN",
)
_PATH_ROOTS = (
    ".env.delphi",
    "delphi/config.json",
    "delphi/prompts",
    "delphi/agents",
    "delphi/domains",
    "delphi/ledger",
)
_ALLOWED = tuple(
    re.compile(pattern)
    for pattern in (
        r"\.env\.delphi",
        r"delphi/config\.json",
        r"delphi/prompts/(?:explorer|heartbeat|judge)\.md",
        r"delphi/agents/(?:explorer|heartbeat|judge)/(?:AGENT|MEMORY)\.md",
        r"delphi/agents/orchestrator/(?:MEMORY|EXPERIMENTS)\.md",
        r"delphi/agents/(?:explorer|heartbeat|judge|orchestrator)/memory/"
        r"[A-Za-z0-9._-]+\.md",
        r"delphi/agents/orchestrator/experiments/APPLY_JOURNAL\.tsv",
        r"delphi/agents/orchestrator/experiments/[A-Za-z0-9_-]{1,128}/"
        r"(?:before|after)\.bin",
        r"delphi/agents/orchestrator/experiments/[A-Za-z0-9_-]{1,128}/meta\.json",
        r"delphi/agents/orchestrator/experiments/[A-Za-z0-9_-]{1,128}"
        r"\.(?:json|before|after)",
        r"delphi/domains/[a-z0-9-]+/(?:domain\.md|[a-z0-9-]+\.tsv)",
        r"delphi/ledger/(?:results\.tsv|learnings\.md)",
    )
)


class SnapshotRefused(RuntimeError):
    pass


class _FailStop(SnapshotRefused):
    """An inconsistent transaction was locked for explicit recovery."""


def _run(repo: Path, *args: str, check: bool = True,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, capture_output=True, env=env
    )


def _text(output: bytes) -> str:
    try:
        return output.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise SnapshotRefused("git returned a non-UTF-8 path") from exc


def _paths(output: bytes) -> list[str]:
    if not output:
        return []
    try:
        decoded = output.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SnapshotRefused("git returned a non-UTF-8 path") from exc
    parts = decoded.split("\0")
    if parts[-1] != "":
        raise SnapshotRefused("git returned a torn path list")
    paths = parts[:-1]
    if any(not path or path != path.strip() or "\n" in path or "\r" in path
           for path in paths):
        raise SnapshotRefused("git returned a noncanonical path")
    return paths


def _allowed(path: str) -> bool:
    return any(pattern.fullmatch(path) for pattern in _ALLOWED)


def _validate_candidate(repo: Path, rel: str) -> None:
    pure = PurePosixPath(rel)
    if (not rel or rel.startswith("-") or pure.is_absolute()
            or str(pure) != rel or any(part in ("", ".", "..") for part in pure.parts)
            or "\\" in rel or any(ord(char) < 32 or ord(char) == 127 for char in rel)
            or not _allowed(rel)):
        raise SnapshotRefused(f"unsafe snapshot path: {rel!r}")
    root = repo.resolve(strict=True)
    current = root
    for position, part in enumerate(pure.parts):
        current /= part
        try:
            opened = current.lstat()
        except FileNotFoundError:
            return  # a missing component is a valid tracked deletion
        except OSError as exc:
            raise SnapshotRefused(
                f"snapshot path component is not inspectable: {rel}") from exc
        final = position == len(pure.parts) - 1
        if not final and not stat.S_ISDIR(opened.st_mode):
            raise SnapshotRefused(
                f"snapshot parent is not a real directory: {rel}")
        if final and not stat.S_ISREG(opened.st_mode):
            raise SnapshotRefused(f"snapshot path is not a regular file: {rel}")


def _read_candidate_nofollow(
    repo: Path, rel: str
) -> tuple[bytes, os.stat_result] | None:
    """Read a candidate through non-symlink directory descriptors."""
    pure = PurePosixPath(rel)
    descriptors: list[int] = []
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        current = os.open(
            repo, flags | getattr(os, "O_DIRECTORY", 0)
        )
        descriptors.append(current)
        for part in pure.parts[:-1]:
            try:
                current = os.open(
                    part,
                    flags | getattr(os, "O_DIRECTORY", 0),
                    dir_fd=current,
                )
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise SnapshotRefused(
                    f"snapshot parent is absent or unsafe: {rel}") from exc
            descriptors.append(current)
        try:
            target = os.open(pure.parts[-1], flags, dir_fd=current)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SnapshotRefused(
                f"snapshot path is absent or unsafe: {rel}") from exc
        descriptors.append(target)
        opened = os.fstat(target)
        if not stat.S_ISREG(opened.st_mode):
            raise SnapshotRefused(f"snapshot path is not a regular file: {rel}")
        chunks = []
        while True:
            chunk = os.read(target, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), opened
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_regular_nofollow(path: Path, label: str) -> tuple[bytes, os.stat_result]:
    try:
        fd = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise SnapshotRefused(f"{label} is absent or unsafe") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SnapshotRefused(f"{label} is not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), opened
    finally:
        os.close(fd)


def _validate_env_payload(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SnapshotRefused(".env.delphi is not UTF-8") from exc
    if not text.endswith("\n") or "\r" in text or "\0" in text:
        raise SnapshotRefused(".env.delphi has noncanonical physical lines")
    physical = text.split("\n")
    expected_names = ("DOTENV_PUBLIC_KEY", *REQUIRED_ENV)
    if len(physical) != len(expected_names) + 1 or physical[-1] != "":
        raise SnapshotRefused(".env.delphi must contain exactly five assignments")
    values: dict[str, str] = {}
    for expected, line in zip(expected_names, physical[:-1]):
        match = re.fullmatch(rf"{re.escape(expected)}=(.+)", line)
        if not match:
            raise SnapshotRefused(
                ".env.delphi assignments are malformed or out of order")
        values[expected] = match.group(1)
    public = values["DOTENV_PUBLIC_KEY"]
    if not re.fullmatch(r'"[A-Za-z0-9+/=_-]{32,}"', public):
        raise SnapshotRefused(".env.delphi has no canonical public key marker")
    for name in REQUIRED_ENV:
        if not re.fullmatch(r'"encrypted:[A-Za-z0-9+/=_-]{32,}"', values[name]):
            raise SnapshotRefused(f".env.delphi entry is not encrypted: {name}")


def _validate_env_structure(repo: Path) -> Path:
    path = repo / ".env.delphi"
    _validate_candidate(repo, ".env.delphi")
    opened = _read_candidate_nofollow(repo, ".env.delphi")
    if opened is None:
        raise SnapshotRefused(".env.delphi is absent or unsafe")
    payload, _ = opened
    _validate_env_payload(payload)
    return path


def _validate_decryption(repo: Path, env_file: Path, env_keys: Path,
                         dotenvx_cmd: str | os.PathLike[str]) -> None:
    _, key_stat = _read_regular_nofollow(env_keys, "shared dotenvx key file")
    if key_stat.st_size == 0:
        raise SnapshotRefused("shared dotenvx key file is empty")
    status_code = (
        "import os,sys;"
        f"names={REQUIRED_ENV!r};"
        "missing=[n for n in names if n not in os.environ];"
        "sys.exit(3) if missing else None;"
        "[print(n+'=' + ('nonempty' if os.environ[n] else 'empty')) for n in names]"
    )
    clean_env = os.environ.copy()
    for name in tuple(clean_env):
        if name in REQUIRED_ENV or name.startswith("DOTENV_PRIVATE_KEY") \
                or name == "DOTENV_PUBLIC_KEY":
            clean_env.pop(name, None)
    try:
        result = subprocess.run(
            [str(dotenvx_cmd), "-q", "run", "--strict", "-f", str(env_file),
             "-fk", str(env_keys), "--", sys.executable, "-c", status_code],
            cwd=repo, env=clean_env, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotRefused("dotenvx validation could not run") from exc
    try:
        statuses = result.stdout.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise SnapshotRefused("dotenvx status output was invalid") from exc
    expected_names = [f"{name}=" for name in REQUIRED_ENV]
    if (result.returncode != 0 or len(statuses) != len(REQUIRED_ENV)
            or any(not line.startswith(prefix)
                   or line.removeprefix(prefix) not in ("empty", "nonempty")
                   for line, prefix in zip(statuses, expected_names))):
        raise SnapshotRefused(
            ".env.delphi is not decryptable with every required entry")


def _guard(repo: Path) -> tuple[Path, Path]:
    try:
        top = Path(_text(_run(repo, "rev-parse", "--show-toplevel").stdout)).resolve()
    except (subprocess.CalledProcessError, OSError) as exc:
        raise SnapshotRefused("snapshot root is not a git worktree") from exc
    if top != repo.resolve():
        raise SnapshotRefused("snapshot root does not match the git worktree")

    git_dir = Path(_text(
        _run(repo, "rev-parse", "--path-format=absolute", "--git-dir").stdout
    ))
    payload, _ = _read_regular_nofollow(
        git_dir / SENTINEL, "daily snapshot sentinel")
    if payload != b"enabled\n":
        raise SnapshotRefused("daily snapshot sentinel is not the exact regular file")

    index = Path(_text(
        _run(repo, "rev-parse", "--path-format=absolute", "--git-path", "index")
        .stdout))
    return git_dir, index


def _acquire_index_lock(index: Path) -> tuple[Path, int]:
    lock = Path(str(index) + ".lock")
    try:
        descriptor = os.open(
            lock,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise SnapshotRefused("real git index is busy") from exc
    except OSError as exc:
        raise SnapshotRefused("real git index lock could not be acquired") from exc
    return lock, descriptor


def _validate_locked_index(repo: Path) -> None:
    tracked = _run(
        repo, "ls-files", "--error-unmatch", "--", ".env.delphi", check=False
    )
    if tracked.returncode != 0:
        raise SnapshotRefused(".env.delphi must be tracked before snapshots are enabled")
    staged = _run(repo, "diff", "--cached", "--quiet", "--exit-code", check=False)
    if staged.returncode != 0:
        raise SnapshotRefused("git index must be clean before a daily snapshot")


def _temporary_index(index: Path, git_dir: Path) -> tuple[Path, bytes, os.stat_result]:
    original, opened = _read_regular_nofollow(index, "git index")
    fd, name = tempfile.mkstemp(prefix=".delphi-index-", suffix=".tmp", dir=git_dir)
    temp = Path(name)
    try:
        os.fchmod(fd, stat.S_IMODE(opened.st_mode))
        view = memoryview(original)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return temp, original, opened


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]


def _write_index_file(path: Path, payload: bytes, mode: int) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        os.fchmod(descriptor, mode)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze_index(
    source: Path, git_dir: Path
) -> tuple[Path, Path, bytes]:
    payload, opened = _read_regular_nofollow(source, "validated isolated git index")
    directory = Path(tempfile.mkdtemp(prefix=".delphi-index-frozen-", dir=git_dir))
    frozen = directory / "index"
    try:
        _write_index_file(frozen, payload, stat.S_IMODE(opened.st_mode))
        frozen.chmod(0o600)
        directory.chmod(0o700)
    except BaseException:
        directory.chmod(0o700)
        frozen.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return directory, frozen, payload


def _remove_frozen_index(directory: Path, frozen: Path) -> None:
    directory.chmod(0o700)
    frozen.chmod(0o600)
    frozen.unlink(missing_ok=True)
    Path(str(frozen) + ".lock").unlink(missing_ok=True)
    directory.rmdir()


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(
        directory, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_index_file(source: Path, index: Path) -> None:
    os.replace(source, index)


def _update_head(repo: Path, new: str, old: str, message: str) -> None:
    _run(repo, "update-ref", "-m", message, "HEAD", new, old)


def _restore_index(
    index: Path, original: bytes, mode: int, directory: Path
) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=".delphi-index-rollback-", suffix=".tmp", dir=directory
    )
    restore = Path(name)
    try:
        os.fchmod(descriptor, mode)
        _write_all(descriptor, original)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _replace_index_file(restore, index)
        _fsync_directory(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        restore.unlink(missing_ok=True)


def _install_transaction(
    repo: Path,
    final_index: bytes,
    index: Path,
    index_lock_descriptor: int,
    original: bytes,
    original_mode: int,
    old_head: str,
    new_head: str,
) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=".delphi-index-install-", suffix=".tmp", dir=index.parent
    )
    install = Path(name)
    try:
        os.fchmod(descriptor, original_mode)
        _write_all(descriptor, final_index)
        os.fsync(descriptor)
    except BaseException:
        install.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)

    head_updated = False
    index_installed = False
    try:
        os.fchmod(index_lock_descriptor, original_mode)
        os.ftruncate(index_lock_descriptor, 0)
        os.lseek(index_lock_descriptor, 0, os.SEEK_SET)
        _write_all(index_lock_descriptor, final_index)
        os.fsync(index_lock_descriptor)
        _update_head(
            repo,
            new_head,
            old_head,
            "commit: delphi: daily state snapshot",
        )
        head_updated = True
        _replace_index_file(install, index)
        index_installed = True
        _fsync_directory(index.parent)
    except BaseException as exc:
        if not head_updated:
            raise
        try:
            _update_head(
                repo,
                old_head,
                new_head,
                "rollback: failed Delphi daily state snapshot",
            )
        except BaseException as rollback_exc:
            raise _FailStop(
                "snapshot rollback failed; leave index.lock in place and restore "
                f"HEAD from {new_head} to {old_head} before removing it"
            ) from rollback_exc
        if index_installed:
            try:
                _restore_index(
                    index, original, original_mode, index.parent
                )
            except BaseException as rollback_exc:
                raise _FailStop(
                    "snapshot index rollback failed; leave index.lock in place and "
                    "restore the real index before removing it"
                ) from rollback_exc
        raise exc
    finally:
        install.unlink(missing_ok=True)


def _staged_entries(
    repo: Path, candidates: list[str], isolated_env: dict[str, str]
) -> dict[str, str]:
    raw = _run(
        repo, "ls-files", "--stage", "-z", "--", *candidates,
        env=isolated_env).stdout
    entries: dict[str, str] = {}
    for record in _paths(raw):
        try:
            metadata, path = record.split("\t", 1)
            mode, _digest, stage_number = metadata.split(" ", 2)
        except ValueError as exc:
            raise SnapshotRefused("isolated index returned malformed metadata") from exc
        if (path not in candidates or mode not in ("100644", "100755")
                or stage_number != "0"):
            raise SnapshotRefused(
                f"isolated index contains a non-regular path: {path}")
        if path in entries:
            raise SnapshotRefused(
                f"isolated index contains a duplicate path: {path}")
        entries[path] = mode
    return entries


def _validate_staged_regular(repo: Path, candidates: list[str],
                             isolated_env: dict[str, str]) -> None:
    _staged_entries(repo, candidates, isolated_env)


def _validate_staged_env(repo: Path, git_dir: Path, env_keys: Path,
                         dotenvx_cmd: str | os.PathLike[str],
                         isolated_env: dict[str, str]) -> None:
    payload = _run(
        repo, "show", ":.env.delphi", env=isolated_env).stdout
    _validate_env_payload(payload)
    fd, name = tempfile.mkstemp(
        prefix=".delphi-env-", suffix=".tmp", dir=git_dir)
    staged_env = Path(name)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        _validate_decryption(
            repo, staged_env, env_keys, dotenvx_cmd)
    finally:
        if fd >= 0:
            os.close(fd)
        staged_env.unlink(missing_ok=True)


def _validate_worktree_matches_index(
    repo: Path, candidates: list[str], isolated_env: dict[str, str]
) -> None:
    entries = _staged_entries(repo, candidates, isolated_env)
    for path in candidates:
        _validate_candidate(repo, path)
        worktree = _read_candidate_nofollow(repo, path)
        mode = entries.get(path)
        if mode is None:
            if worktree is not None:
                raise SnapshotRefused(
                    f"snapshot path changed after isolated staging: {path}")
            continue
        if worktree is None:
            raise SnapshotRefused(
                f"snapshot path disappeared after isolated staging: {path}")
        payload, opened = worktree
        staged_payload = _run(
            repo, "show", f":{path}", env=isolated_env
        ).stdout
        executable = bool(opened.st_mode & 0o111)
        if payload != staged_payload or executable != (mode == "100755"):
            raise SnapshotRefused(
                f"snapshot path changed after isolated staging: {path}")


def _staged_paths(repo: Path, isolated_env: dict[str, str]) -> list[str]:
    return _paths(
        _run(
            repo,
            "diff",
            "--cached",
            "--name-only",
            "-z",
            env=isolated_env,
        ).stdout
    )


def _validate_isolated_snapshot(
    repo: Path,
    git_dir: Path,
    candidates: list[str],
    env_keys: Path,
    dotenvx_cmd: str | os.PathLike[str],
    isolated_env: dict[str, str],
) -> list[str]:
    staged = _staged_paths(repo, isolated_env)
    if any(not _allowed(path) for path in staged):
        raise SnapshotRefused(
            "staged path escaped the Delphi snapshot allowlist")
    if any(path not in candidates for path in staged):
        raise SnapshotRefused(
            "isolated staging added a path outside the validated candidate set")
    _validate_staged_regular(repo, candidates, isolated_env)
    _validate_staged_env(
        repo, git_dir, env_keys, dotenvx_cmd, isolated_env)
    _validate_worktree_matches_index(repo, candidates, isolated_env)
    return staged


def _require_index_bytes(
    frozen: Path, expected: bytes
) -> None:
    payload, _ = _read_regular_nofollow(frozen, "frozen validated git index")
    if payload != expected:
        raise SnapshotRefused("frozen validated git index changed")


def _validate_frozen_snapshot(
    repo: Path,
    git_dir: Path,
    frozen: Path,
    expected_bytes: bytes,
    expected_staged: list[str],
    expected_tree: str,
    candidates: list[str],
    env_keys: Path,
    dotenvx_cmd: str | os.PathLike[str],
    frozen_env: dict[str, str],
) -> None:
    _require_index_bytes(frozen, expected_bytes)
    staged = _staged_paths(repo, frozen_env)
    if staged != expected_staged:
        raise SnapshotRefused("frozen index staged paths changed")
    if any(not _allowed(path) or path not in candidates for path in staged):
        raise SnapshotRefused("frozen index escaped the validated snapshot scope")
    _validate_staged_regular(repo, candidates, frozen_env)
    _validate_staged_env(
        repo, git_dir, env_keys, dotenvx_cmd, frozen_env)
    if _write_tree(repo, frozen_env) != expected_tree:
        raise SnapshotRefused("frozen index tree differs from the commit tree")
    _require_index_bytes(frozen, expected_bytes)


def _run_pre_commit_hook(
    repo: Path, isolated_env: dict[str, str]
) -> None:
    hook = Path(
        _text(
            _run(
                repo,
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                "hooks/pre-commit",
            ).stdout
        )
    )
    try:
        opened = hook.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SnapshotRefused("pre-commit hook is not inspectable") from exc
    if not stat.S_ISREG(opened.st_mode):
        raise SnapshotRefused("pre-commit hook is not a regular file")
    if not opened.st_mode & 0o111:
        return
    subprocess.run(
        [str(hook)], cwd=repo, env=isolated_env, check=True, capture_output=True
    )


def _write_tree(repo: Path, isolated_env: dict[str, str]) -> str:
    return _text(_run(repo, "write-tree", env=isolated_env).stdout)


def _create_commit(
    repo: Path,
    tree: str,
    parent: str,
    isolated_env: dict[str, str],
) -> str:
    return _text(
        _run(
            repo,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            "delphi: daily state snapshot",
            env=isolated_env,
        ).stdout
    )


def run_snapshot(repo: Path = ROOT, *, env_keys: Path | None = None,
                 dotenvx_cmd: str | os.PathLike[str] = "dotenvx") -> bool:
    repo = repo.resolve()
    git_dir, index = _guard(repo)
    index_lock, index_lock_descriptor = _acquire_index_lock(index)
    temp_index: Path | None = None
    frozen_directory: Path | None = None
    frozen_index: Path | None = None
    keep_index_lock = False
    try:
        _validate_locked_index(repo)
        env_file = _validate_env_structure(repo)
        key_file = Path(env_keys or os.environ.get(
            "ENVKEYS", "/home/kab/.config/dotenvx/.env.keys"))
        _validate_decryption(repo, env_file, key_file, dotenvx_cmd)
        listed = _run(
            repo,
            "ls-files", "-z", "--cached", "--others", "--deleted",
            "--exclude-standard", "--", *_PATH_ROOTS,
        ).stdout
        candidates = sorted({
            path for path in _paths(listed) if _allowed(path)
        })
        if ".env.delphi" not in candidates:
            raise SnapshotRefused(
                "tracked .env.delphi is missing from snapshot scope")
        for path in candidates:
            _validate_candidate(repo, path)

        temp_index, original_index, original_stat = _temporary_index(
            index, git_dir)
        isolated_env = os.environ.copy()
        isolated_env["GIT_INDEX_FILE"] = str(temp_index)
        _run(repo, "add", "-A", "--", *candidates, env=isolated_env)
        staged = _staged_paths(repo, isolated_env)
        if not staged:
            return False

        _validate_env_structure(repo)
        _validate_decryption(repo, env_file, key_file, dotenvx_cmd)
        _validate_isolated_snapshot(
            repo,
            git_dir,
            candidates,
            key_file,
            dotenvx_cmd,
            isolated_env,
        )

        _run_pre_commit_hook(repo, isolated_env)
        _write_tree(repo, isolated_env)  # populate cache-tree before freezing
        staged = _validate_isolated_snapshot(
            repo,
            git_dir,
            candidates,
            key_file,
            dotenvx_cmd,
            isolated_env,
        )
        if not staged:
            raise SnapshotRefused("pre-commit hook removed every snapshot change")

        frozen_directory, frozen_index, frozen_bytes = _freeze_index(
            temp_index, git_dir)
        frozen_env = isolated_env.copy()
        frozen_env["GIT_INDEX_FILE"] = str(frozen_index)
        frozen_env["GIT_OPTIONAL_LOCKS"] = "0"
        frozen_staged = _validate_isolated_snapshot(
            repo,
            git_dir,
            candidates,
            key_file,
            dotenvx_cmd,
            frozen_env,
        )
        if frozen_staged != staged:
            raise SnapshotRefused("frozen index differs from validated staging")

        old_head = _text(
            _run(repo, "rev-parse", "--verify", "HEAD").stdout)
        tree = _write_tree(repo, frozen_env)
        _require_index_bytes(frozen_index, frozen_bytes)
        old_tree = _text(
            _run(repo, "rev-parse", "--verify", "HEAD^{tree}").stdout)
        if tree == old_tree:
            return False
        new_head = _create_commit(repo, tree, old_head, isolated_env)
        if _text(
            _run(repo, "rev-parse", "--verify", f"{new_head}^{{tree}}").stdout
        ) != tree:
            raise SnapshotRefused("created commit does not contain the frozen tree")
        _validate_frozen_snapshot(
            repo,
            git_dir,
            frozen_index,
            frozen_bytes,
            staged,
            tree,
            candidates,
            key_file,
            dotenvx_cmd,
            frozen_env,
        )
        _install_transaction(
            repo,
            frozen_bytes,
            index,
            index_lock_descriptor,
            original_index,
            stat.S_IMODE(original_stat.st_mode),
            old_head,
            new_head,
        )
        return True
    except _FailStop:
        keep_index_lock = True
        raise
    finally:
        if frozen_directory is not None and frozen_index is not None:
            _remove_frozen_index(frozen_directory, frozen_index)
        if temp_index is not None:
            temp_index.unlink(missing_ok=True)
            Path(str(temp_index) + ".lock").unlink(missing_ok=True)
        os.close(index_lock_descriptor)
        if not keep_index_lock:
            index_lock.unlink(missing_ok=True)


def main() -> int:
    try:
        changed = run_snapshot(ROOT)
    except (SnapshotRefused, subprocess.CalledProcessError) as exc:
        print(f"daily snapshot refused: {exc}", file=sys.stderr)
        return 1
    print("daily snapshot committed" if changed else "daily snapshot: no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
