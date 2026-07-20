import importlib
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
snapshot_state = importlib.import_module("snapshot_state")

REQUIRED_ENV = (
    "EXA_API_KEY",
    "X_BEARER_TOKEN",
    "DELPHI_COGNEE_URL",
    "DELPHI_COGNEE_TOKEN",
)


def encrypted_env(suffix: str = "A") -> str:
    lines = ['DOTENV_PUBLIC_KEY="' + ("P" * 66) + '"']
    lines.extend(
        f'{name}="encrypted:{suffix + ("A" * 80)}"' for name in REQUIRED_ENV
    )
    return "\n".join(lines) + "\n"


def git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


class SnapshotStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Delphi Test")
        git(self.repo, "config", "user.email", "delphi@example.invalid")
        (self.repo / "delphi/ledger").mkdir(parents=True)
        (self.repo / "delphi/scripts").mkdir(parents=True)
        (self.repo / ".env.delphi").write_text(encrypted_env())
        (self.repo / "delphi/ledger/results.tsv").write_text("header\n")
        (self.repo / "delphi/scripts/code.py").write_text("baseline = True\n")
        git(self.repo, "add", ".env.delphi", "delphi")
        git(self.repo, "commit", "-qm", "baseline")
        self.keys = self.repo / ".shared.keys"
        self.keys.write_text("valid\n")
        self.dotenvx = self.repo / ".fake-dotenvx"
        self.dotenvx.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "args=sys.argv[1:]\n"
            "key=pathlib.Path(args[args.index('-fk')+1])\n"
            "if key.read_text() != 'valid\\n': raise SystemExit(1)\n"
            f"names={REQUIRED_ENV!r}\n"
            "for name in names: os.environ[name]=''\n"
            "mark=args.index('--')\n"
            "os.execv(args[mark+1], args[mark+1:])\n"
        )
        self.dotenvx.chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def enable(self):
        git_dir = pathlib.Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-dir")
            .stdout.strip()
        )
        (git_dir / snapshot_state.SENTINEL).write_bytes(b"enabled\n")

    def snapshot(self):
        return snapshot_state.run_snapshot(
            self.repo, env_keys=self.keys, dotenvx_cmd=self.dotenvx
        )

    def index_bytes(self):
        index = pathlib.Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-path", "index")
            .stdout.strip()
        )
        return index.read_bytes()

    def git_dir(self):
        return pathlib.Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-dir")
            .stdout.strip()
        )

    def assert_transaction_artifacts_absent(self):
        git_dir = self.git_dir()
        self.assertFalse((git_dir / "index.lock").exists())
        self.assertEqual([], list(git_dir.glob(".delphi-index-*")))

    def test_missing_sentinel_fails_without_staging_or_committing(self):
        (self.repo / "delphi/ledger/results.tsv").write_text("header\nrow\n")
        before = git(self.repo, "rev-parse", "HEAD").stdout
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        self.assertEqual(before, git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)

    def test_untracked_env_or_dirty_index_fails_closed(self):
        self.enable()
        git(self.repo, "rm", "--cached", "-q", ".env.delphi")
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        git(self.repo, "reset", "-q", "HEAD", "--", ".env.delphi")
        (self.repo / "delphi/scripts/code.py").write_text("staged = True\n")
        git(self.repo, "add", "delphi/scripts/code.py")
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()

    def test_enabled_snapshot_commits_only_narrow_operational_paths(self):
        self.enable()
        (self.repo / ".env.delphi").write_text(encrypted_env("B"))
        (self.repo / "delphi/ledger/results.tsv").write_text("header\nrow\n")
        (self.repo / "delphi/scripts/code.py").write_text("unreviewed = True\n")
        self.snapshot()
        committed = set(
            git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
            .stdout.splitlines()
        )
        self.assertEqual({".env.delphi", "delphi/ledger/results.tsv"}, committed)
        self.assertIn("delphi/scripts/code.py", git(self.repo, "status", "--short").stdout)
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)

    def test_sentinel_requires_exact_regular_file(self):
        git_dir = pathlib.Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-dir")
            .stdout.strip()
        )
        sentinel = git_dir / snapshot_state.SENTINEL
        sentinel.write_bytes(b"yes\n")
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        sentinel.unlink()
        os.symlink("/dev/null", sentinel)
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()

    def test_plaintext_missing_and_wrong_key_env_fail_before_index_mutation(self):
        self.enable()
        env_path = self.repo / ".env.delphi"
        cases = (
            "EXA_API_KEY=plaintext\n",
            encrypted_env().replace('X_BEARER_TOKEN="encrypted:',
                                    'MISSING_X_BEARER_TOKEN="encrypted:'),
        )
        for payload in cases:
            with self.subTest(payload=payload[:20]):
                env_path.write_text(payload)
                before_index = self.index_bytes()
                before_head = git(self.repo, "rev-parse", "HEAD").stdout
                with self.assertRaises(snapshot_state.SnapshotRefused):
                    self.snapshot()
                self.assertEqual(before_index, self.index_bytes())
                self.assertEqual(before_head, git(self.repo, "rev-parse", "HEAD").stdout)
        env_path.write_text(encrypted_env())
        self.keys.write_text("wrong\n")
        before_index = self.index_bytes()
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        self.assertEqual(before_index, self.index_bytes())

    def test_env_rejects_comments_blank_lines_unknowns_and_reordering(self):
        self.enable()
        canonical = encrypted_env()
        lines = canonical.splitlines()
        cases = (
            "# PLAINTEXT_SENTINEL\n" + canonical,
            canonical + "\n",
            canonical + "UNKNOWN=plaintext\n",
            "\n".join((lines[1], lines[0], *lines[2:])) + "\n",
        )
        for payload in cases:
            with self.subTest(payload=payload[:30]):
                (self.repo / ".env.delphi").write_text(payload)
                index_before = self.index_bytes()
                with self.assertRaises(snapshot_state.SnapshotRefused):
                    self.snapshot()
                self.assertEqual(index_before, self.index_bytes())

    def test_env_and_allowlisted_paths_reject_symlinks_and_special_files(self):
        self.enable()
        env_path = self.repo / ".env.delphi"
        outside_env = self.repo / "outside.env"
        outside_env.write_text(encrypted_env())
        env_path.unlink()
        env_path.symlink_to(outside_env)
        before = self.index_bytes()
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        self.assertEqual(before, self.index_bytes())

        env_path.unlink()
        env_path.write_text(encrypted_env())
        results = self.repo / "delphi/ledger/results.tsv"
        outside_results = self.repo / "outside-results.tsv"
        outside_results.write_text("outside\n")
        results.unlink()
        results.symlink_to(outside_results)
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        results.unlink()
        os.mkfifo(results)
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()

    def test_internal_parent_symlink_is_rejected(self):
        self.enable()
        ledger = self.repo / "delphi/ledger"
        internal = self.repo / "delphi/internal-ledger"
        ledger.rename(internal)
        ledger.symlink_to("internal-ledger", target_is_directory=True)
        before = self.index_bytes()
        with self.assertRaises(snapshot_state.SnapshotRefused):
            self.snapshot()
        self.assertEqual(before, self.index_bytes())

    def test_traversal_and_pathspec_like_candidates_are_rejected(self):
        for path in ("../outside", "-n", "delphi/ledger/../../outside"):
            with self.subTest(path=path), self.assertRaises(
                snapshot_state.SnapshotRefused
            ):
                snapshot_state._validate_candidate(self.repo, path)

    def test_failing_commit_hook_leaves_real_index_and_worktree_identical(self):
        self.enable()
        results = self.repo / "delphi/ledger/results.tsv"
        results.write_text("header\nrow\n")
        worktree_before = results.read_bytes()
        index_before = self.index_bytes()
        head_before = git(self.repo, "rev-parse", "HEAD").stdout
        hooks = self.repo / ".git/hooks"
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaises(subprocess.CalledProcessError):
            self.snapshot()
        self.assertEqual(index_before, self.index_bytes())
        self.assertEqual(worktree_before, results.read_bytes())
        self.assertEqual(head_before, git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)
        self.assert_transaction_artifacts_absent()

    def test_real_index_lock_blocks_concurrent_git_add(self):
        self.enable()
        results = self.repo / "delphi/ledger/results.tsv"
        results.write_text("header\nrow\n")
        code = self.repo / "delphi/scripts/code.py"
        code.write_text("concurrent = True\n")
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            "(unset GIT_INDEX_FILE; git add delphi/scripts/code.py) 2>/dev/null "
            "&& exit 91\n"
            "exit 0\n"
        )
        hook.chmod(0o755)

        self.assertTrue(self.snapshot())

        self.assertIn("delphi/scripts/code.py", git(self.repo, "status", "--short").stdout)
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)
        self.assert_transaction_artifacts_absent()

    def test_atomic_phase_failures_restore_head_and_real_index(self):
        self.enable()
        results = self.repo / "delphi/ledger/results.tsv"
        results.write_text("header\nvalidated\n")
        worktree_before = results.read_bytes()
        index_before = self.index_bytes()
        head_before = git(self.repo, "rev-parse", "HEAD").stdout
        phases = (
            "_write_tree",
            "_create_commit",
            "_update_head",
            "_replace_index_file",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                with mock.patch.object(
                    snapshot_state, phase, side_effect=OSError(f"injected {phase}")
                ):
                    with self.assertRaises(OSError):
                        self.snapshot()
                self.assertEqual(index_before, self.index_bytes())
                self.assertEqual(head_before, git(self.repo, "rev-parse", "HEAD").stdout)
                self.assertEqual(worktree_before, results.read_bytes())
                self.assertEqual(
                    "", git(self.repo, "diff", "--cached", "--name-only").stdout
                )
                self.assert_transaction_artifacts_absent()

    def test_post_install_fsync_failure_rolls_back_atomically(self):
        self.enable()
        results = self.repo / "delphi/ledger/results.tsv"
        results.write_text("header\nvalidated\n")
        worktree_before = results.read_bytes()
        index_before = self.index_bytes()
        head_before = git(self.repo, "rev-parse", "HEAD").stdout

        with mock.patch.object(
            snapshot_state,
            "_fsync_directory",
            side_effect=(OSError("injected fsync"), None),
        ):
            with self.assertRaises(OSError):
                self.snapshot()

        self.assertEqual(index_before, self.index_bytes())
        self.assertEqual(head_before, git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual(worktree_before, results.read_bytes())
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)
        self.assert_transaction_artifacts_absent()

    def test_failed_head_rollback_leaves_explicit_fail_stop_lock(self):
        self.enable()
        (self.repo / "delphi/ledger/results.tsv").write_text(
            "header\nvalidated\n"
        )
        index_before = self.index_bytes()
        head_before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        original_update = snapshot_state._update_head
        updates = 0

        def fail_rollback(repo, new, old, message):
            nonlocal updates
            updates += 1
            if updates == 2:
                raise OSError("injected rollback failure")
            return original_update(repo, new, old, message)

        with mock.patch.object(
            snapshot_state, "_update_head", side_effect=fail_rollback
        ), mock.patch.object(
            snapshot_state,
            "_replace_index_file",
            side_effect=OSError("injected install failure"),
        ):
            with self.assertRaisesRegex(
                snapshot_state.SnapshotRefused,
                "rollback failed; leave index.lock in place",
            ):
                self.snapshot()

        self.assertNotEqual(head_before, git(self.repo, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(index_before, self.index_bytes())
        self.assertTrue((self.git_dir() / "index.lock").is_file())

    def test_race_before_final_compare_fails_with_real_index_untouched(self):
        self.enable()
        env_path = self.repo / ".env.delphi"
        results = self.repo / "delphi/ledger/results.tsv"
        results.write_text("header\nvalidated\n")
        index_before = self.index_bytes()
        head_before = git(self.repo, "rev-parse", "HEAD").stdout
        original = snapshot_state._validate_staged_env

        def race(*args, **kwargs):
            original(*args, **kwargs)
            env_path.write_text("EXA_API_KEY=plaintext-race\n")
            results.unlink()
            results.symlink_to(self.repo / "outside-results.tsv")

        (self.repo / "outside-results.tsv").write_text("race\n")
        with mock.patch.object(snapshot_state, "_validate_staged_env", side_effect=race):
            with self.assertRaises(snapshot_state.SnapshotRefused):
                self.snapshot()
        self.assertEqual(index_before, self.index_bytes())
        self.assertEqual(head_before, git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual("EXA_API_KEY=plaintext-race\n", env_path.read_text())
        self.assertTrue(results.is_symlink())

    def test_race_at_commit_cannot_enter_validated_isolated_index(self):
        self.enable()
        env_path = self.repo / ".env.delphi"
        valid_env = encrypted_env("C")
        env_path.write_text(valid_env)
        results = self.repo / "delphi/ledger/results.tsv"
        valid_results = "header\nvalidated\n"
        results.write_text(valid_results)
        outside = self.repo / "outside-results.tsv"
        outside.write_text("race\n")
        original_create_commit = snapshot_state._create_commit
        raced = False

        def race_create_commit(repo, tree, parent, isolated_env):
            nonlocal raced
            if not raced:
                raced = True
                env_path.write_text("EXA_API_KEY=plaintext-race\n")
                results.unlink()
                results.symlink_to(outside)
                subprocess.run(
                    [
                        "git",
                        "add",
                        "-A",
                        "--",
                        ".env.delphi",
                        "delphi/ledger/results.tsv",
                    ],
                    cwd=repo,
                    env=isolated_env,
                    check=True,
                    capture_output=True,
                )
            return original_create_commit(repo, tree, parent, isolated_env)

        with mock.patch.object(
            snapshot_state, "_create_commit", side_effect=race_create_commit
        ):
            self.assertTrue(self.snapshot())
        self.assertTrue(raced)
        self.assertEqual(valid_env, git(self.repo, "show", "HEAD:.env.delphi").stdout)
        self.assertEqual(
            valid_results,
            git(self.repo, "show", "HEAD:delphi/ledger/results.tsv").stdout,
        )
        self.assertEqual(
            git(self.repo, "rev-parse", "HEAD^{tree}").stdout,
            git(self.repo, "write-tree").stdout,
        )
        self.assertTrue(
            git(
                self.repo,
                "ls-files",
                "--stage",
                "--",
                "delphi/ledger/results.tsv",
            ).stdout.startswith("100644 ")
        )
        self.assertEqual("", git(self.repo, "diff", "--cached", "--name-only").stdout)
        self.assertEqual("EXA_API_KEY=plaintext-race\n", env_path.read_text())
        self.assertTrue(results.is_symlink())


if __name__ == "__main__":
    unittest.main()
