from __future__ import annotations

import calendar
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import orchestrator  # noqa: E402


START = "2026-07-14T00:00:00Z"
START_EPOCH = calendar.timegm((2026, 7, 14, 0, 0, 0))


class OrchestratorExperimentMetricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "delphi"
        (self.root / "prompts").mkdir(parents=True)
        (self.root / "agents" / "orchestrator" / "experiments").mkdir(
            parents=True)
        (self.root / "ledger").mkdir()
        (self.root / "domains" / "test").mkdir(parents=True)
        (self.root / "agents" / "orchestrator" / "EXPERIMENTS.md").write_text(
            orchestrator.EXPERIMENTS_TEMPLATE, encoding="utf-8")
        (self.root / "ledger" / "learnings.md").write_text("", encoding="utf-8")
        self.target = self.root / "prompts" / "heartbeat.md"
        self.target.write_text("before\n", encoding="utf-8")
        (self.root / "prompts" / "judge.md").write_text("judge-before\n",
                                                           encoding="utf-8")
        (self.root / "config.json").write_text(
            '{"sources":{"history_days":365}}\n', encoding="utf-8")
        self.evidence = self.root / "domains" / "test" / "evidence.tsv"
        self.evidence.write_bytes(
            b"id\tstatus\tvalue\n1\tok\t1.25\n2\tbad\t2.5\n3\tok\t3.75\n")
        self.cfg = {
            "orchestrator": {
                "editable_files_regex": r"^prompts/(heartbeat|judge)\.md$",
            }
        }
        patches = (
            mock.patch.object(orchestrator, "ROOT", self.root),
            mock.patch.object(orchestrator, "now_iso", return_value=START),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def metric(self, **changes):
        metric = {
            "schema": 1,
            "type": "tsv_aggregate",
            "path": "domains/test/evidence.tsv",
            "where": {"status": "ok"},
            "aggregate": "count",
            "comparator": ">=",
            "threshold": 2,
        }
        metric.update(changes)
        return metric

    def amendment(self, **changes):
        amendment = {
            "kind": "file",
            "path": "prompts/heartbeat.md",
            "content": "after\n",
            "rationale": "focused metric test",
            "metric": self.metric(),
            "review_after_hours": 168,
        }
        amendment.update(changes)
        return amendment

    def apply(self, **changes):
        orchestrator.apply_amendment(self.cfg, self.amendment(**changes))
        return self.rows()[0]["id"]

    def rows(self):
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        lines = journal.read_text(encoding="utf-8").splitlines()
        return [dict(zip(orchestrator.JOURNAL_COLUMNS, line.split("\t"), strict=True))
                for line in lines[1:]]

    def states(self, experiment_id):
        return [row["state"] for row in self.rows() if row["id"] == experiment_id]

    def candidate(self, experiment_id, now_epoch=START_EPOCH + 168 * 3600):
        candidates = orchestrator.review_candidates(self.cfg, now_epoch=now_epoch)
        return next(row for row in candidates if row["id"] == experiment_id)

    def review(self, payload, now_epoch=START_EPOCH + 168 * 3600):
        with mock.patch.object(orchestrator, "load_config", return_value=self.cfg):
            return orchestrator.review_experiments(payload, now_epoch=now_epoch)

    def test_seven_day_defer_exact_boundary_and_secondary_never_controls(self):
        experiment_id = self.apply()
        display = self.root / "agents" / "orchestrator" / "EXPERIMENTS.md"
        display.write_text(display.read_text().replace("| live |", "| keep |"),
                           encoding="utf-8")
        journal_before = self.rows()
        display_before = display.read_bytes()

        self.assertEqual(
            orchestrator.review_candidates(self.cfg, now_epoch=START_EPOCH + 3600), [])
        due_candidate = self.candidate(experiment_id)
        self.assertEqual(due_candidate["id"], experiment_id)

        early = self.review([{
            "id": experiment_id,
            "verdict": "keep",
            "reason": "narrative cannot make it due",
            "metric_result": due_candidate["metric_result"],
        }], now_epoch=START_EPOCH + 167 * 3600 + 3599)
        self.assertEqual(early, [f"{experiment_id}:ignored-not-due"])
        self.assertEqual(self.rows(), journal_before)
        self.assertEqual(display.read_bytes(), display_before)

    def test_non_live_experiments_are_never_candidates(self):
        experiment_id = self.apply()
        result = self.candidate(experiment_id)["metric_result"]
        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "keep", "reason": "met",
            "metric_result": result,
        }]), [f"{experiment_id}:keep"])
        self.assertEqual(orchestrator.review_candidates(
            self.cfg, now_epoch=START_EPOCH + 169 * 3600), [])

    def test_file_evaluation_binds_digest_selection_and_value(self):
        experiment_id = self.apply()
        first = self.candidate(experiment_id)["metric_result"]
        second = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(first, second)
        self.assertEqual(first["evidence"], {
            "path": "domains/test/evidence.tsv",
            "sha256": hashlib.sha256(self.evidence.read_bytes()).hexdigest(),
            "rows": 3,
        })
        self.assertEqual(first["selection"]["where"], {"status": "ok"})
        self.assertEqual(first["selection"]["matched_rows"], 2)
        self.assertRegex(first["selection"]["rows_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["metric_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["operation"], "count")
        self.assertEqual(first["value"], "2")
        self.assertEqual(first["threshold"], "2")
        self.assertTrue(first["satisfied"])

    def test_numeric_mean_is_computed_from_selected_file_values(self):
        experiment_id = self.apply(metric=self.metric(
            aggregate="mean", column="value", comparator=">", threshold=2))
        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(result["operation"], "mean")
        self.assertEqual(result["column"], "value")
        self.assertEqual(result["selection"]["matched_rows"], 2)
        self.assertEqual(result["value"], "2.5")
        self.assertTrue(result["satisfied"])

    def test_sixty_digit_sum_and_equality_are_exact(self):
        operand = "123456789012345678901234567890123456789012345678901234567890"
        expected = str(int(operand) * 2)
        self.evidence.write_text(
            f"id\tstatus\tvalue\n1\tok\t{operand}\n2\tok\t{operand}\n",
            encoding="utf-8",
        )
        experiment_id = self.apply(metric=self.metric(
            where={}, aggregate="sum", column="value", comparator="==",
            threshold=expected))

        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(result["value"], expected)
        self.assertTrue(result["satisfied"])

    def test_carry_heavy_sum_is_exact(self):
        operand = "9" * 60
        expected = str(int(operand) * 10)
        rows = "".join(f"{index}\tok\t{operand}\n" for index in range(10))
        self.evidence.write_text(
            "id\tstatus\tvalue\n" + rows, encoding="utf-8")
        experiment_id = self.apply(metric=self.metric(
            where={}, aggregate="sum", column="value", comparator="==",
            threshold=expected))

        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(result["value"], expected)
        self.assertTrue(result["satisfied"])

    def test_mixed_fractional_scale_sum_is_exact(self):
        integer = "123456789012345678901234567890123456789012345678901234567890"
        fraction = "0.12345678901234567890123456789"
        expected = f"{integer}.12345678901234567890123456789"
        self.evidence.write_text(
            f"id\tstatus\tvalue\n1\tok\t{integer}\n2\tok\t{fraction}\n",
            encoding="utf-8",
        )
        experiment_id = self.apply(metric=self.metric(
            where={}, aggregate="sum", column="value", comparator="==",
            threshold=expected))

        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(result["value"], expected)
        self.assertTrue(result["satisfied"])

    def test_mean_uses_explicit_half_even_at_one_hundred_decimal_places(self):
        tiny_even = "0." + "0" * 97 + "1"
        rows = [tiny_even, *("0" for _ in range(7))]
        self.evidence.write_text(
            "id\tstatus\tvalue\n" + "".join(
                f"{index}\tok\t{value}\n" for index, value in enumerate(rows)),
            encoding="utf-8",
        )
        experiment_id = self.apply(metric=self.metric(
            where={}, aggregate="mean", column="value", comparator=">",
            threshold="0"))

        even = self.candidate(experiment_id)["metric_result"]
        self.assertEqual(even["value"], "0." + "0" * 98 + "12")
        self.assertTrue(even["satisfied"])

        tiny_odd = "0." + "0" * 97 + "3"
        rows[0] = tiny_odd
        self.evidence.write_text(
            "id\tstatus\tvalue\n" + "".join(
                f"{index}\tok\t{value}\n" for index, value in enumerate(rows)),
            encoding="utf-8",
        )
        odd = self.candidate(experiment_id)["metric_result"]
        self.assertEqual(odd["value"], "0." + "0" * 98 + "38")
        self.assertTrue(odd["satisfied"])

    def test_satisfied_keep_requires_exact_result_and_is_durable(self):
        experiment_id = self.apply()
        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "keep", "reason": "met",
            "metric_result": result,
        }]), [f"{experiment_id}:keep"])
        terminal = self.rows()[-1]
        self.assertEqual(terminal["state"], "keep")
        self.assertEqual(json.loads(terminal["review_result"]), result)

    def test_missing_narrative_stale_and_invented_results_are_retryable(self):
        experiment_id = self.apply()
        result = self.candidate(experiment_id)["metric_result"]
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        display = self.root / "agents" / "orchestrator" / "EXPERIMENTS.md"

        attempts = [
            {"id": experiment_id, "verdict": "keep", "reason": "looks better"},
            {"id": experiment_id, "verdict": "keep", "reason": "narrative",
             "metric_result": "count is two"},
            {"id": experiment_id, "verdict": "keep", "reason": "invented",
             "metric_result": {**result, "value": "999"}},
        ]
        for payload in attempts:
            with self.subTest(payload=payload):
                primary_before = journal.read_bytes()
                secondary_before = display.read_bytes()
                self.assertEqual(self.review([payload]),
                                 [f"{experiment_id}:retryable-metric-result"])
                self.assertEqual(journal.read_bytes(), primary_before)
                self.assertEqual(display.read_bytes(), secondary_before)
                self.assertEqual(self.states(experiment_id),
                                 ["prepared", "exchanged", "live"])

        self.evidence.write_bytes(self.evidence.read_bytes() + b"4\tok\t1.00\n")
        primary_before = journal.read_bytes()
        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "keep", "reason": "stale",
            "metric_result": result,
        }]), [f"{experiment_id}:retryable-metric-result"])
        self.assertEqual(journal.read_bytes(), primary_before)

    def test_unsatisfied_metric_cannot_be_kept_but_can_be_reverted(self):
        experiment_id = self.apply(
            metric=self.metric(comparator=">=", threshold=3))
        result = self.candidate(experiment_id)["metric_result"]
        self.assertFalse(result["satisfied"])

        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "keep", "reason": "wishful",
            "metric_result": result,
        }]), [f"{experiment_id}:retryable-unsatisfied-keep"])
        self.assertEqual(self.states(experiment_id), ["prepared", "exchanged", "live"])
        self.assertEqual(self.target.read_text(), "after\n")

        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "revert", "reason": "missed target",
            "metric_result": result,
        }]), [f"{experiment_id}:revert"])
        self.assertEqual(self.target.read_text(), "before\n")
        self.assertEqual(json.loads(self.rows()[-1]["review_result"]), result)

    def assert_evidence_failure(self, mutate):
        experiment_id = self.apply(metric=self.metric(
            aggregate="mean", column="value", threshold=1))
        mutate()
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        display = self.root / "agents" / "orchestrator" / "EXPERIMENTS.md"
        primary_before = journal.read_bytes()
        secondary_before = display.read_bytes()

        self.assertEqual(orchestrator.review_candidates(
            self.cfg, now_epoch=START_EPOCH + 168 * 3600), [])
        self.assertEqual(self.review([{
            "id": experiment_id, "verdict": "revert", "reason": "guess",
            "metric_result": {},
        }]), [f"{experiment_id}:retryable-metric-error"])
        self.assertEqual(journal.read_bytes(), primary_before)
        self.assertEqual(display.read_bytes(), secondary_before)
        self.assertEqual(self.target.read_text(), "after\n")

    def test_missing_evidence_fails_closed(self):
        self.assert_evidence_failure(self.evidence.unlink)

    def test_malformed_evidence_fails_closed(self):
        self.assert_evidence_failure(lambda: self.evidence.write_bytes(
            b"id\tstatus\tvalue\n1\tok\n"))

    def test_nonfinite_evidence_fails_closed(self):
        self.assert_evidence_failure(lambda: self.evidence.write_bytes(
            b"id\tstatus\tvalue\n1\tok\tNaN\n"))

    def test_symlink_evidence_fails_closed(self):
        self.assert_evidence_failure(self._replace_evidence_with_symlink)

    def _replace_evidence_with_symlink(self):
        outside = Path(self.tmp.name) / "outside.tsv"
        outside.write_bytes(b"id\tstatus\tvalue\n1\tok\t1\n")
        self.evidence.unlink()
        self.evidence.symlink_to(outside)

    def test_multiple_live_metrics_are_independent_and_deterministic(self):
        first_id = self.apply()
        second_metric = self.root / "domains" / "test" / "second.tsv"
        second_metric.write_bytes(b"status\nready\n")
        orchestrator.apply_amendment(self.cfg, self.amendment(
            path="prompts/judge.md", content="judge-after\n",
            review_after_hours=24,
            metric=self.metric(path="domains/test/second.tsv", threshold=1),
        ))
        second_id = next(row["id"] for row in self.rows() if row["id"] != first_id)

        after_one_day = orchestrator.review_candidates(
            self.cfg, now_epoch=START_EPOCH + 24 * 3600)
        self.assertEqual([row["id"] for row in after_one_day], [second_id])
        after_week = orchestrator.review_candidates(
            self.cfg, now_epoch=START_EPOCH + 168 * 3600)
        self.assertEqual([row["id"] for row in after_week], [first_id, second_id])

    def test_revert_crash_replays_with_the_same_durable_metric_result(self):
        experiment_id = self.apply()
        result = self.candidate(experiment_id)["metric_result"]
        original = orchestrator._atomic_revert_exchange

        def revert_then_crash(cfg, row):
            original(cfg, row)
            raise RuntimeError("crash after revert")

        with mock.patch.object(orchestrator, "_atomic_revert_exchange",
                               side_effect=revert_then_crash):
            with self.assertRaisesRegex(RuntimeError, "crash after revert"):
                self.review([{
                    "id": experiment_id, "verdict": "revert", "reason": "reviewed",
                    "metric_result": result,
                }])
        self.assertEqual(self.states(experiment_id),
                         ["prepared", "exchanged", "live", "revert_prepared"])
        self.assertEqual(json.loads(self.rows()[-1]["review_result"]), result)
        self.assertEqual(self.target.read_text(), "before\n")

        self.assertEqual(orchestrator.recover_prepared_amendments(self.cfg), 1)
        self.assertEqual(self.states(experiment_id), [
            "prepared", "exchanged", "live", "revert_prepared", "revert"])
        self.assertEqual(json.loads(self.rows()[-1]["review_result"]), result)

    def test_unstructured_or_unknown_metric_is_rejected_before_mutation(self):
        for metric in ("flow", {}, self.metric(aggregate="eval"),
                       self.metric(path="../outside.tsv"),
                       self.metric(threshold=float("inf"))):
            with self.subTest(metric=metric):
                before = self.target.read_bytes()
                outcome = orchestrator.apply_amendment(
                    self.cfg, self.amendment(metric=metric))
                self.assertIn("REJECTED amendment: invalid metric", outcome)
                self.assertEqual(self.target.read_bytes(), before)

    def test_metric_fields_require_exact_types_and_canonical_decimals(self):
        invalid = [
            self.metric(schema=True),
            self.metric(type=[]),
            self.metric(aggregate=[]),
            self.metric(comparator={}),
            self.metric(path=[]),
            self.metric(where=[]),
            self.metric(where={"status": []}),
            self.metric(aggregate="mean", column=[]),
            self.metric(threshold=" 1 "),
            self.metric(threshold="+1"),
            self.metric(threshold="01"),
            self.metric(threshold="1.0"),
            self.metric(threshold="1e0"),
            self.metric(threshold=-0.0),
        ]
        for metric in invalid:
            with self.subTest(metric=metric):
                before = self.target.read_bytes()
                outcome = orchestrator.apply_amendment(
                    self.cfg, self.amendment(metric=metric))
                self.assertIn("REJECTED amendment: invalid metric", outcome)
                self.assertEqual(self.target.read_bytes(), before)

    def test_every_cell_and_every_numeric_column_value_is_strict(self):
        experiment_id = self.apply(metric=self.metric(
            aggregate="mean", column="value", threshold=1))
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        display = self.root / "agents" / "orchestrator" / "EXPERIMENTS.md"
        primary_before = journal.read_bytes()
        secondary_before = display.read_bytes()
        malformed = [
            "id\tstatus\tvalue\n1\tok\t1.25\n2\tba\u200bd\t2.5\n",
            "id\tstatus\tvalue\n1\tok\t 1.25 \n2\tbad\t2.5\n",
            "id\tstatus\tvalue\n1\tok\t1.25\n2\tbad\t02.5\n",
            "id\tstatus\tvalue\n1\tok\t1e0\n2\tbad\t2.5\n",
            f"id\tstatus\tvalue\n1\tok\t{'1' * 101}\n2\tbad\t2.5\n",
        ]
        for evidence in malformed:
            with self.subTest(evidence=evidence):
                self.evidence.write_text(evidence, encoding="utf-8")
                self.assertEqual(orchestrator.review_candidates(
                    self.cfg, now_epoch=START_EPOCH + 168 * 3600), [])
                self.assertEqual(self.review([{
                    "id": experiment_id, "verdict": "revert", "reason": "bad data",
                    "metric_result": {},
                }]), [f"{experiment_id}:retryable-metric-error"])
                self.assertEqual(journal.read_bytes(), primary_before)
                self.assertEqual(display.read_bytes(), secondary_before)
                self.assertEqual(self.states(experiment_id),
                                 ["prepared", "exchanged", "live"])

    def test_ordinary_spaces_in_text_cells_remain_valid(self):
        self.evidence.write_text(
            "id\tstatus\tvalue\n1\tnot ready\t1.25\n2\tbad row\t2.5\n",
            encoding="utf-8",
        )
        experiment_id = self.apply(metric=self.metric(
            where={"status": "not ready"}, aggregate="mean", column="value",
            threshold="1"))

        result = self.candidate(experiment_id)["metric_result"]

        self.assertEqual(result["selection"]["matched_rows"], 1)
        self.assertEqual(result["value"], "1.25")

    def apply_pair(self):
        first_id = self.apply()
        orchestrator.apply_amendment(self.cfg, self.amendment(
            path="prompts/judge.md", content="judge-after\n"))
        second_id = next(row["id"] for row in self.rows() if row["id"] != first_id)
        candidates = {row["id"]: row for row in orchestrator.review_candidates(
            self.cfg, now_epoch=START_EPOCH + 168 * 3600)}
        return first_id, second_id, candidates

    @staticmethod
    def verdict(experiment_id, result, **extra):
        payload = {
            "id": experiment_id,
            "verdict": "keep",
            "reason": "metric met",
            "metric_result": result,
        }
        payload.update(extra)
        return payload

    def test_nonlist_and_extra_field_batches_are_retryable_and_nonmutating(self):
        experiment_id = self.apply()
        result = self.candidate(experiment_id)["metric_result"]
        journal = (self.root / "agents" / "orchestrator" / "experiments"
                   / orchestrator.APPLY_JOURNAL)
        primary_before = journal.read_bytes()
        for reviews in (None, {}, "review", (self.verdict(experiment_id, result),)):
            with self.subTest(reviews=reviews):
                self.assertEqual(self.review(reviews),
                                 ["reviews:retryable-invalid-batch"])
                self.assertEqual(journal.read_bytes(), primary_before)
        self.assertEqual(self.review([
            self.verdict(experiment_id, result, extra="not allowed"),
        ]), ["review[0]:retryable-invalid-shape"])
        self.assertEqual(journal.read_bytes(), primary_before)

    def test_none_or_malformed_known_review_does_not_poison_later_valid_review(self):
        first_id, second_id, candidates = self.apply_pair()
        reviews = [
            None,
            self.verdict(first_id, {}),
            self.verdict(second_id, candidates[second_id]["metric_result"]),
        ]

        notes = self.review(reviews)

        self.assertIn("review[0]:retryable-invalid-shape", notes)
        self.assertIn(f"{first_id}:retryable-metric-result", notes)
        self.assertIn(f"{second_id}:keep", notes)
        self.assertEqual(self.states(first_id), ["prepared", "exchanged", "live"])
        self.assertEqual(self.states(second_id),
                         ["prepared", "exchanged", "live", "keep"])

    def test_duplicate_and_unknown_ids_do_not_poison_independent_valid_review(self):
        first_id, second_id, candidates = self.apply_pair()
        first = self.verdict(first_id, candidates[first_id]["metric_result"])
        unknown = self.verdict(
            "exp-20260714-unknown", candidates[first_id]["metric_result"])
        second = self.verdict(second_id, candidates[second_id]["metric_result"])

        notes = self.review([first, unknown, dict(first), second])

        self.assertIn(f"{first_id}:retryable-duplicate-review", notes)
        self.assertIn("exp-20260714-unknown:ignored-not-live", notes)
        self.assertIn(f"{second_id}:keep", notes)
        self.assertEqual(self.states(first_id), ["prepared", "exchanged", "live"])
        self.assertEqual(self.states(second_id),
                         ["prepared", "exchanged", "live", "keep"])


if __name__ == "__main__":
    unittest.main()
