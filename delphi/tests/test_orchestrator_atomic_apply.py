from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import orchestrator  # noqa: E402


EXPERIMENTS = """# Live experiments

Managed by the orchestrator. One row per experiment; keep/revert verdicts are
also logged in ledger/learnings.md.

| id | started | change | metric | review_after | status |
|---|---|---|---|---|---|
"""


def metric_decl():
    return {
        "schema": 1,
        "type": "tsv_aggregate",
        "path": "ledger/results.tsv",
        "where": {},
        "aggregate": "count",
        "comparator": ">=",
        "threshold": 0,
    }


class OrchestratorAtomicApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "delphi"
        (self.root / "prompts").mkdir(parents=True)
        (self.root / "agents" / "orchestrator" / "experiments").mkdir(
            parents=True)
        (self.root / "ledger").mkdir()
        (self.root / "ledger" / "results.tsv").write_text(
            "ts\tscript\tdomain\tsummary\n", encoding="utf-8")
        (self.root / "agents" / "orchestrator" / "EXPERIMENTS.md").write_text(
            EXPERIMENTS, encoding="utf-8")
        (self.root / "ledger" / "learnings.md").write_text("", encoding="utf-8")
        self.target = self.root / "prompts" / "heartbeat.md"
        self.target.write_bytes(b"before\r\n")
        (self.root / "config.json").write_bytes(
            b'{"sources":{"history_days":365}}\r\n')
        self.cfg = {
            "orchestrator": {
                "editable_files_regex": (
                    r"^(prompts/(explorer|heartbeat|judge)\.md|"
                    r"agents/(explorer|heartbeat|judge)/(AGENT|MEMORY)\.md|"
                    r"agents/orchestrator/MEMORY\.md|"
                    r"domains/[a-z0-9-]+/domain\.md)$"
                )
            }
        }
        self.root_patch = mock.patch.object(orchestrator, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def amendment(self, **changes):
        amendment = {
            "id": "llm-controlled-id",
            "kind": "file",
            "path": "prompts/heartbeat.md",
            "content": "after\r\n",
            "rationale": "test",
            "metric": metric_decl(),
            "review_after_hours": 24,
        }
        amendment.update(changes)
        return amendment

    def journal_rows(self):
        path = (self.root / "agents" / "orchestrator" / "experiments"
                / orchestrator.APPLY_JOURNAL)
        lines = path.read_text(encoding="utf-8").splitlines()
        return [dict(zip(orchestrator.JOURNAL_COLUMNS, line.split("\t"), strict=True))
                for line in lines[1:]]

    def review_payload(self, exp_id, verdict, reason):
        first = next(row for row in self.journal_rows() if row["id"] == exp_id)
        due = orchestrator._review_due_epoch(first)
        candidate = next(row for row in orchestrator.review_candidates(
            self.cfg, now_epoch=due) if row["id"] == exp_id)
        return ({"id": exp_id, "verdict": verdict, "reason": reason,
                 "metric_result": candidate["metric_result"]}, due)

    def experiment_dir(self):
        rows = self.journal_rows()
        exp_id = rows[0]["id"]
        return self.root / "agents" / "orchestrator" / "experiments" / exp_id

    def apply_second_experiment(self):
        target = self.root / "prompts" / "judge.md"
        target.write_bytes(b"judge-before\n")
        orchestrator.apply_amendment(
            self.cfg,
            self.amendment(path="prompts/judge.md", content="judge-after\n"),
        )
        return target

    def test_code_id_and_byte_exact_snapshots_preserve_non_utf8_before(self):
        self.target.write_bytes(b"\xffbefore\r\n")
        outcome = orchestrator.apply_amendment(self.cfg, self.amendment())

        self.assertIn("wrote prompts/heartbeat.md", outcome)
        rows = self.journal_rows()
        self.assertEqual([row["state"] for row in rows],
                         ["prepared", "exchanged", "live"])
        self.assertNotEqual(rows[0]["id"], "llm-controlled-id")
        self.assertEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual(self.target.read_bytes(), b"after\r\n")
        exp_dir = self.experiment_dir()
        self.assertEqual((exp_dir / "before.bin").read_bytes(), b"\xffbefore\r\n")
        self.assertEqual((exp_dir / "after.bin").read_bytes(), b"after\r\n")
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o644)

    def test_crash_after_prepared_recovers_by_completing_apply_once(self):
        original = orchestrator._atomic_replace_bytes
        with mock.patch.object(orchestrator, "_atomic_replace_bytes",
                               side_effect=RuntimeError("crash after prepared")):
            with self.assertRaisesRegex(RuntimeError, "crash after prepared"):
                orchestrator.apply_amendment(self.cfg, self.amendment())

        self.assertEqual(self.target.read_bytes(), b"before\r\n")
        self.assertEqual([row["state"] for row in self.journal_rows()], ["prepared"])
        with mock.patch.object(orchestrator, "_atomic_replace_bytes", wraps=original):
            recovered = orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(recovered, 1)
        self.assertEqual(self.target.read_bytes(), b"after\r\n")
        self.assertEqual([row["state"] for row in self.journal_rows()],
                         ["prepared", "exchanged", "live"])
        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 0)
        display = (self.root / "agents" / "orchestrator" / "EXPERIMENTS.md").read_text()
        self.assertEqual(display.count(f"| {self.journal_rows()[0]['id']} |"), 1)

    def test_crash_after_replace_before_live_finalizes_without_rewriting(self):
        with mock.patch.object(orchestrator, "_append_live_transition",
                               side_effect=RuntimeError("crash before live")):
            with self.assertRaisesRegex(RuntimeError, "crash before live"):
                orchestrator.apply_amendment(self.cfg, self.amendment())

        after_stat = self.target.stat()
        self.assertEqual(self.target.read_bytes(), b"after\r\n")
        self.assertEqual([row["state"] for row in self.journal_rows()],
                         ["prepared", "exchanged"])
        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 1)
        self.assertEqual(self.target.stat().st_ino, after_stat.st_ino)
        self.assertEqual([row["state"] for row in self.journal_rows()],
                         ["prepared", "exchanged", "live"])

    def test_config_prepared_recovery_uses_the_same_raw_transaction(self):
        amendment = {
            "id": "not-trusted",
            "kind": "config",
            "patch": {"sources.history_days": 180},
            "metric": metric_decl(),
            "review_after_hours": 24,
        }
        with mock.patch.object(orchestrator, "_atomic_replace_bytes",
                               side_effect=RuntimeError("stop config")):
            with self.assertRaisesRegex(RuntimeError, "stop config"):
                orchestrator.apply_amendment(self.cfg, amendment)
        self.assertEqual(json.loads((self.root / "config.json").read_text())
                         ["sources"]["history_days"], 365)

        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 1)
        self.assertEqual(json.loads((self.root / "config.json").read_text())
                         ["sources"]["history_days"], 180)
        exp_dir = self.experiment_dir()
        self.assertEqual((exp_dir / "before.bin").read_bytes(),
                         b'{"sources":{"history_days":365}}\r\n')

    def test_prepared_journal_failure_never_mutates_target(self):
        before = self.target.read_bytes()
        with mock.patch.object(orchestrator, "_rewrite_journal",
                               side_effect=OSError("journal replace failed")):
            with self.assertRaisesRegex(OSError, "journal replace failed"):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.journal_rows(), [])

    def test_live_journal_crash_reconciles_secondary_logs_without_reapply(self):
        original = orchestrator._reconcile_display
        calls = 0

        def crash_after_live(cfg, rows=None):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("display crash")
            return original(cfg, rows)

        with mock.patch.object(orchestrator, "_reconcile_display",
                               side_effect=crash_after_live):
            with self.assertRaisesRegex(RuntimeError, "display crash"):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        after_stat = self.target.stat()
        self.assertEqual([row["state"] for row in self.journal_rows()],
                         ["prepared", "exchanged", "live"])

        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 0)
        self.assertEqual(self.target.stat().st_ino, after_stat.st_ino)
        display = (self.root / "agents" / "orchestrator" / "EXPERIMENTS.md").read_text()
        self.assertEqual(display.count(f"| {self.journal_rows()[0]['id']} |"), 1)

    def test_snapshot_collision_retries_without_overwriting_evidence(self):
        collision = (self.root / "agents" / "orchestrator" / "experiments"
                     / "exp-20260714-collision")
        collision.mkdir()
        evidence = collision / "before.bin"
        evidence.write_bytes(b"do-not-overwrite")
        ids = iter(("exp-20260714-collision", "exp-20260714-fresh"))
        with mock.patch.object(orchestrator, "_new_experiment_id",
                               side_effect=lambda: next(ids)):
            orchestrator.apply_amendment(self.cfg, self.amendment())

        self.assertEqual(evidence.read_bytes(), b"do-not-overwrite")
        self.assertEqual(self.journal_rows()[0]["id"], "exp-20260714-fresh")

    def test_replace_failure_leaves_target_identical_and_cleans_temp(self):
        before = self.target.read_bytes()
        with mock.patch.object(orchestrator, "_replace_at",
                               side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                orchestrator.apply_amendment(self.cfg, self.amendment())

        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse(list(self.target.parent.glob(".*.apply-*.tmp")))
        self.assertEqual([row["state"] for row in self.journal_rows()], ["prepared"])

    def test_partial_temp_write_leaves_target_identical_and_cleans_temp(self):
        before = self.target.read_bytes()
        original = orchestrator._write_all

        def partial_then_fail(fd, payload):
            if payload == b"after\r\n":
                os.write(fd, payload[:2])
                raise OSError("partial write")
            return original(fd, payload)

        with mock.patch.object(orchestrator, "_write_all", side_effect=partial_then_fail):
            with self.assertRaisesRegex(OSError, "partial write"):
                orchestrator.apply_amendment(self.cfg, self.amendment())

        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse(list(self.target.parent.glob(".*.apply-*.tmp")))

    def test_prepared_target_mismatch_fails_closed_without_overwrite(self):
        with mock.patch.object(orchestrator, "_atomic_replace_bytes",
                               side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.target.write_bytes(b"founder change")

        with self.assertRaisesRegex(orchestrator.ApplySafetyError,
                                    "no recoverable layout"):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.read_bytes(), b"founder change")
        self.assertEqual([row["state"] for row in self.journal_rows()], ["prepared"])

    def test_malformed_torn_or_contradictory_journal_fails_before_write(self):
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        journal.write_bytes(b"torn")
        before = self.target.read_bytes()
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.read_bytes(), before)

    def test_duplicate_transition_and_tampered_snapshot_fail_closed(self):
        with mock.patch.object(orchestrator, "_atomic_replace_bytes",
                               side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        raw = journal.read_bytes()
        prepared_line = raw.splitlines(keepends=True)[1]
        journal.write_bytes(raw + prepared_line)
        before = self.target.read_bytes()
        with self.assertRaisesRegex(orchestrator.ApplySafetyError,
                                    "state transition"):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.read_bytes(), before)

        journal.write_bytes(raw)
        (self.experiment_dir() / "after.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(orchestrator.ApplySafetyError,
                                    "snapshot (size|digest) mismatch"):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.read_bytes(), before)

    def test_symlink_journal_is_rejected_without_touching_referent(self):
        orchestrator.recover_prepared_amendments(self.cfg)
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        outside = Path(self.tmp.name) / "outside-journal"
        outside.write_bytes(b"outside evidence")
        journal.unlink()
        journal.symlink_to(outside)
        before = self.target.read_bytes()
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(outside.read_bytes(), b"outside evidence")
        self.assertEqual(self.target.read_bytes(), before)

    def test_symlink_target_and_parent_escape_are_rejected(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        outside_file = outside / "heartbeat.md"
        outside_file.write_bytes(b"outside")
        self.target.unlink()
        self.target.symlink_to(outside_file)
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(outside_file.read_bytes(), b"outside")

        self.target.unlink()
        (self.root / "prompts").rmdir()
        (self.root / "prompts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(outside_file.read_bytes(), b"outside")

    def test_traversal_absolute_and_non_regular_targets_are_rejected(self):
        attempts = [
            "prompts/../agents/orchestrator/MEMORY.md",
            "/prompts/heartbeat.md",
            "delphi/prompts/heartbeat.md",
        ]
        for path in attempts:
            with self.subTest(path=path):
                with self.assertRaises(orchestrator.ApplySafetyError):
                    orchestrator.apply_amendment(self.cfg, self.amendment(path=path))

        self.target.unlink()
        self.target.mkdir()
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.apply_amendment(self.cfg, self.amendment())

    def test_parent_revalidation_detects_race_before_replace(self):
        outside = Path(self.tmp.name) / "outside-race"
        outside.mkdir()
        outside_file = outside / "heartbeat.md"
        outside_file.write_bytes(b"outside")
        original = orchestrator._revalidate_parent
        raced = False

        def race(ref):
            nonlocal raced
            if not raced:
                raced = True
                moved = self.root / "prompts-original"
                self.target.parent.rename(moved)
                (self.root / "prompts").symlink_to(outside, target_is_directory=True)
            return original(ref)

        with mock.patch.object(orchestrator, "_revalidate_parent", side_effect=race):
            with self.assertRaises(orchestrator.ApplySafetyError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(outside_file.read_bytes(), b"outside")

    def test_lexical_root_symlink_is_rejected_even_when_outside_tree_is_valid(self):
        real_root = self.root
        lexical_root = Path(self.tmp.name) / "delphi-link"
        lexical_root.symlink_to(real_root, target_is_directory=True)
        with mock.patch.object(orchestrator, "ROOT", lexical_root):
            with self.assertRaises(orchestrator.ApplySafetyError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(self.target.read_bytes(), b"before\r\n")

    def test_recovery_rejects_same_bytes_and_mode_on_a_new_target_inode(self):
        with mock.patch.object(orchestrator, "_atomic_replace_bytes",
                               side_effect=RuntimeError("prepared")):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        replacement = self.target.with_suffix(".replacement")
        replacement.write_bytes(b"before\r\n")
        replacement.chmod(stat.S_IMODE(self.target.stat().st_mode))
        replacement.replace(self.target)
        replaced_ino = self.target.stat().st_ino

        with self.assertRaisesRegex(orchestrator.ApplySafetyError,
                                    "identity|inode"):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.stat().st_ino, replaced_ino)
        self.assertEqual(self.target.read_bytes(), b"before\r\n")

    def test_injected_target_swap_at_replace_boundary_rolls_back(self):
        original_replace = orchestrator._replace_at
        attacker_name = ".heartbeat.md.attacker"
        attacker = self.target.parent / attacker_name
        attacker.write_bytes(b"attacker")
        attacker_inode = attacker.stat().st_ino

        def swap_then_replace(source, target, dir_fd):
            os.replace(attacker_name, target, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            return original_replace(source, target, dir_fd)

        with mock.patch.object(orchestrator, "_replace_at",
                               side_effect=swap_then_replace):
            with self.assertRaises(orchestrator.ApplySafetyError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(self.target.stat().st_ino, attacker_inode)
        self.assertEqual(self.target.read_bytes(), b"attacker")
        self.assertEqual(
            [row["state"] for row in self.journal_rows()],
            ["prepared", "abort_prepared", "aborted"],
        )
        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 0)
        self.assertEqual(self.target.stat().st_ino, attacker_inode)

    def test_after_snapshot_overwrite_at_mutation_entry_causes_zero_mutation(self):
        original_append = orchestrator._append_prepared_transition

        def append_then_tamper(cfg, row):
            original_append(cfg, row)
            exp_dir = (self.root / "agents" / "orchestrator" / "experiments"
                       / row["id"])
            (exp_dir / "after.bin").write_bytes(b"tampered")

        before = self.target.read_bytes()
        with mock.patch.object(orchestrator, "_append_prepared_transition",
                               side_effect=append_then_tamper):
            with self.assertRaises(orchestrator.ApplySafetyError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(self.target.read_bytes(), before)

    def test_journal_requires_physical_lf_and_metadata_rejects_controls(self):
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        journal.write_bytes(orchestrator.JOURNAL_HEADER.replace("\n", "\r\n").encode())
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.recover_prepared_amendments(self.cfg)

        journal.write_bytes(orchestrator.JOURNAL_HEADER.encode())
        before = self.target.read_bytes()
        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.apply_amendment(
                self.cfg, self.amendment(metric=metric_decl(), rationale="bad\u200bformat"))
        self.assertEqual(self.target.read_bytes(), before)

    def test_primary_journal_rebuilds_secondary_and_records_keep(self):
        orchestrator.apply_amendment(self.cfg, self.amendment())
        rows = self.journal_rows()
        exp_id = rows[0]["id"]
        display_path = self.root / "agents" / "orchestrator" / "EXPERIMENTS.md"
        display_path.write_text(
            display_path.read_text().replace("| live |", "| keep |"), encoding="utf-8")

        orchestrator.recover_prepared_amendments(self.cfg)
        self.assertIn(f"| {exp_id} |", display_path.read_text())
        self.assertIn("| live |", display_path.read_text())
        payload, due = self.review_payload(exp_id, "keep", "better")
        with mock.patch.object(orchestrator, "load_config", return_value=self.cfg):
            self.assertEqual(
                orchestrator.review_experiments([payload], now_epoch=due),
                [f"{exp_id}:keep"],
            )
        self.assertEqual(self.journal_rows()[-1]["state"], "keep")
        self.assertIn("| keep |", display_path.read_text())

    def test_interleaved_older_experiment_keep_is_append_only_and_valid(self):
        orchestrator.apply_amendment(self.cfg, self.amendment())
        first_id = self.journal_rows()[0]["id"]
        self.apply_second_experiment()
        payload, due = self.review_payload(first_id, "keep", "better")

        with mock.patch.object(orchestrator, "load_config", return_value=self.cfg):
            self.assertEqual(
                orchestrator.review_experiments([payload], now_epoch=due),
                [f"{first_id}:keep"],
            )

        rows = self.journal_rows()
        first_states = [row["state"] for row in rows if row["id"] == first_id]
        self.assertEqual(first_states, ["prepared", "exchanged", "live", "keep"])
        self.assertEqual(rows[-1]["id"], first_id)
        orchestrator._load_journal(self.cfg)

    def test_interleaved_older_experiment_revert_is_append_only_and_valid(self):
        orchestrator.apply_amendment(self.cfg, self.amendment())
        first_id = self.journal_rows()[0]["id"]
        self.apply_second_experiment()
        payload, due = self.review_payload(first_id, "revert", "worse")

        with mock.patch.object(orchestrator, "load_config", return_value=self.cfg):
            self.assertEqual(
                orchestrator.review_experiments([payload], now_epoch=due),
                [f"{first_id}:revert"],
            )

        rows = self.journal_rows()
        first_states = [row["state"] for row in rows if row["id"] == first_id]
        self.assertEqual(
            first_states,
            ["prepared", "exchanged", "live", "revert_prepared", "revert"],
        )
        self.assertEqual(rows[-1]["id"], first_id)
        self.assertEqual(self.target.read_bytes(), b"before\r\n")
        orchestrator._load_journal(self.cfg)

    def test_malformed_interleaved_transition_is_rejected_before_rewrite(self):
        orchestrator.apply_amendment(self.cfg, self.amendment())
        first = self.journal_rows()[0]
        self.apply_second_experiment()
        raw_before = (self.root / "agents" / "orchestrator" / "experiments"
                      / orchestrator.APPLY_JOURNAL).read_bytes()
        malformed = dict(first)
        malformed["state"] = "exchanged"
        payload, _ = self.review_payload(first["id"], "keep", "better")

        with (mock.patch.object(orchestrator, "_row_bytes",
                                return_value=orchestrator._row_bytes(malformed)),
              mock.patch.object(orchestrator, "_rewrite_journal") as rewrite):
            with self.assertRaisesRegex(orchestrator.ApplySafetyError,
                                        "state transition"):
                orchestrator._append_state_transition(
                    self.cfg, first, "keep", payload["metric_result"])
        rewrite.assert_not_called()
        self.assertEqual(
            (self.root / "agents" / "orchestrator" / "experiments"
             / orchestrator.APPLY_JOURNAL).read_bytes(),
            raw_before,
        )

    def test_renamed_root_to_outside_symlink_rolls_exchange_back(self):
        outside = Path(self.tmp.name) / "outside-root"
        (outside / "prompts").mkdir(parents=True)
        outside_target = outside / "prompts" / "heartbeat.md"
        outside_target.write_bytes(b"outside")
        moved_root = Path(self.tmp.name) / "delphi-moved"
        original = orchestrator._replace_at
        injected = False

        def rename_root_then_exchange(source, target, dir_fd):
            nonlocal injected
            if not injected:
                injected = True
                self.root.rename(moved_root)
                self.root.symlink_to(outside, target_is_directory=True)
            return original(source, target, dir_fd)

        with mock.patch.object(orchestrator, "_replace_at",
                               side_effect=rename_root_then_exchange):
            with self.assertRaises(orchestrator.ApplySafetyError):
                orchestrator.apply_amendment(self.cfg, self.amendment())
        self.assertEqual(outside_target.read_bytes(), b"outside")
        self.assertEqual((moved_root / "prompts" / "heartbeat.md").read_bytes(),
                         b"before\r\n")

    def test_multiple_prepared_preflight_has_no_partial_target_write(self):
        second = self.root / "prompts" / "judge.md"
        second.write_bytes(b"judge-before")

        def prepare(rel, after):
            ref, before = orchestrator._open_target(self.cfg, rel, "file")
            try:
                row = orchestrator._reserve_evidence(
                    kind="file", target=ref, before=before, after=after,
                    review_after=24, metric=metric_decl(), rationale="test",
                    change=f"wrote {rel}",
                    amendment_meta={"content_encoding": "utf-8"})
            finally:
                ref.close()
            orchestrator._append_prepared_transition(self.cfg, row)
            return row

        prepare("prompts/heartbeat.md", b"heartbeat-after")
        prepare("prompts/judge.md", b"judge-after")
        replacement = second.with_suffix(".replacement")
        replacement.write_bytes(b"judge-before")
        replacement.chmod(stat.S_IMODE(second.stat().st_mode))
        replacement.replace(second)

        with self.assertRaises(orchestrator.ApplySafetyError):
            orchestrator.recover_prepared_amendments(self.cfg)
        self.assertEqual(self.target.read_bytes(), b"before\r\n")
        self.assertEqual(second.read_bytes(), b"judge-before")

    def test_revert_exchange_crash_is_finalized_from_primary_intent(self):
        orchestrator.apply_amendment(self.cfg, self.amendment())
        exp_id = self.journal_rows()[0]["id"]
        payload, due = self.review_payload(exp_id, "revert", "worse")
        original = orchestrator._atomic_revert_exchange

        def revert_then_crash(cfg, row):
            original(cfg, row)
            raise RuntimeError("crash after revert exchange")

        with (mock.patch.object(orchestrator, "load_config", return_value=self.cfg),
              mock.patch.object(orchestrator, "_atomic_revert_exchange",
                                side_effect=revert_then_crash)):
            with self.assertRaisesRegex(RuntimeError, "crash after revert exchange"):
                orchestrator.review_experiments([payload], now_epoch=due)
        self.assertEqual(self.target.read_bytes(), b"before\r\n")
        self.assertEqual(self.journal_rows()[-1]["state"], "revert_prepared")

        with mock.patch.object(orchestrator, "load_config", return_value=self.cfg):
            self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 1)
        self.assertEqual(self.journal_rows()[-1]["state"], "revert")
        self.assertEqual(self.target.read_bytes(), b"before\r\n")

    def test_unexpected_displaced_hard_crash_rolls_back_and_aborts_idempotently(self):
        class HardCrash(BaseException):
            pass

        attacker_name = ".heartbeat.md.attacker"
        attacker = self.target.parent / attacker_name
        attacker.write_bytes(b"attacker-concurrent-write")
        attacker.chmod(0o640)
        attacker_stat = attacker.stat()

        def displace_exchange_then_crash(source, target, dir_fd):
            os.replace(attacker_name, target, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            orchestrator._rename_exchange_at(source, target, dir_fd)
            os.fsync(dir_fd)
            raise HardCrash("power loss after exchange")

        with mock.patch.object(orchestrator, "_replace_at",
                               side_effect=displace_exchange_then_crash):
            with self.assertRaisesRegex(HardCrash, "power loss"):
                orchestrator.apply_amendment(self.cfg, self.amendment())

        prepared = self.journal_rows()[0]
        exchange = self.root / prepared["exchange_rel"]
        self.assertEqual([row["state"] for row in self.journal_rows()], ["prepared"])
        self.assertEqual(self.target.stat().st_ino, int(prepared["exchange_ino"]))
        self.assertEqual(self.target.read_bytes(), b"after\r\n")
        self.assertEqual(exchange.stat().st_ino, attacker_stat.st_ino)
        self.assertEqual(exchange.read_bytes(), b"attacker-concurrent-write")

        original_append = orchestrator._append_state_transition

        def crash_before_terminal_abort(cfg, row, state):
            if state == "aborted":
                raise HardCrash("power loss after rollback")
            return original_append(cfg, row, state)

        with mock.patch.object(orchestrator, "_append_state_transition",
                               side_effect=crash_before_terminal_abort):
            with self.assertRaisesRegex(HardCrash, "after rollback"):
                orchestrator.recover_prepared_amendments(self.cfg)

        self.assertEqual(self.journal_rows()[-1]["state"], "abort_prepared")
        restored_stat = self.target.stat()
        self.assertEqual(
            (restored_stat.st_dev, restored_stat.st_ino,
             stat.S_IMODE(restored_stat.st_mode)),
            (attacker_stat.st_dev, attacker_stat.st_ino,
             stat.S_IMODE(attacker_stat.st_mode)),
        )
        self.assertEqual(self.target.read_bytes(), b"attacker-concurrent-write")
        self.assertEqual(exchange.stat().st_ino, int(prepared["exchange_ino"]))

        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 1)
        self.assertEqual(self.journal_rows()[-1]["state"], "aborted")
        self.assertEqual(self.target.stat().st_ino, attacker_stat.st_ino)
        self.assertEqual(self.target.read_bytes(), b"attacker-concurrent-write")
        self.assertFalse(exchange.exists())
        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 0)
        self.assertEqual(self.target.stat().st_ino, attacker_stat.st_ino)


if __name__ == "__main__":
    unittest.main()
