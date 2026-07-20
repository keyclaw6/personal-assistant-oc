from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import judge  # noqa: E402
import orchestrator  # noqa: E402
import resolve  # noqa: E402


def orchestrator_metric():
    return {
        "schema": 1,
        "type": "tsv_aggregate",
        "path": "ledger/results.tsv",
        "where": {},
        "aggregate": "count",
        "comparator": ">=",
        "threshold": 0,
    }


class JudgeEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.signal = {"leaker_id": "x-a", "call_class": "timing",
                       "market_id": "m1", "side": "YES"}
        self.leakers = [{"leaker_id": "x-a", "call_class": "timing",
                         "status": "verified"}]
        self.thresholds = {"min_liquidity_usd": 1000}
        self.market = {"closed": False, "liquidity": 1500,
                       "yes_token": "yes", "no_token": "no"}

    def check(self, leakers=None, positions=None, market=None, ask=0.42):
        with (mock.patch.object(judge.pm, "get_market",
                               return_value=self.market if market is None else market),
              mock.patch.object(judge, "executable_ask", return_value=ask)):
            return judge.eligibility(self.signal, leakers or self.leakers,
                                     positions or [], self.thresholds)

    def test_checks_every_deterministic_predicate(self):
        market, ask, status, _ = self.check()
        self.assertIs(market, self.market)
        self.assertEqual(ask, 0.42)
        self.assertIsNone(status)

        _, _, status, reason = self.check(
            leakers=[{**self.leakers[0], "status": "probation"}])
        self.assertEqual((status, reason),
                         ("pass", "leaker class is no longer verified"))

        _, _, status, reason = self.check(
            positions=[{"market_id": "m1", "status": "open"}])
        self.assertEqual((status, reason),
                         ("pass", "already positioned on this market — stacking guard"))

        _, _, status, _ = self.check(market={**self.market, "closed": True})
        self.assertEqual(status, "expired")
        _, _, status, _ = self.check(market={**self.market, "liquidity": 999})
        self.assertEqual(status, "pass")

    def test_transient_lookup_and_quote_failures_stay_pending(self):
        with mock.patch.object(judge.pm, "get_market", return_value=None):
            _, _, status, reason = judge.eligibility(
                self.signal, self.leakers, [], self.thresholds)
        self.assertIsNone(status)
        self.assertIn("retrying", reason)

    def test_noncanonical_liquidity_is_retryable_before_quote(self):
        for liquidity in (float("nan"), float("inf"), "bad", -1, True,
                          "1e3", "1000.0000001"):
            market = {**self.market, "liquidity": liquidity}
            with self.subTest(liquidity=liquidity), \
                    mock.patch.object(judge.pm, "get_market",
                                      return_value=market), \
                    mock.patch.object(judge, "executable_ask") as ask:
                _, _, status, reason = judge.eligibility(
                    self.signal, self.leakers, [], self.thresholds)
                self.assertIsNone(status)
                self.assertIn("retrying", reason)
                ask.assert_not_called()

        _, _, status, reason = self.check(ask=None)
        self.assertIsNone(status)
        self.assertIn("retrying", reason)

    def test_second_check_can_terminalize_changed_state(self):
        self.assertIsNone(self.check()[2])
        demoted = [{**self.leakers[0], "status": "probation"}]
        self.assertEqual(self.check(leakers=demoted)[2], "pass")


class ResolveReconciliationTests(unittest.TestCase):
    def test_rebuilds_from_signals_idempotently_and_preserves_metadata(self):
        leakers = [{
            "leaker_id": "x-a", "platform": "x", "handle": "a",
            "domain": "d", "call_class": "timing", "status": "verified",
            "n_calls": "99", "hits": "99", "hit_rate": "1.000",
            "avg_price_at_call": "0.100", "est_edge": "0.900",
            "edge_lcb": "0.800", "n_unpriced": "4", "n_live": "8",
            "last_seen_ts": "keep-me", "notes": "keep-note",
        }]
        base = {"leaker_id": "x-a", "platform": "x", "call_class": "timing",
                "market_id": "m1", "event_id": "e1", "side": "YES",
                "resolved_outcome": "YES", "status": "historical",
                "ts_detected": "2026-01-01T00:00:00Z", "note": ""}
        signals = [
            {**base, "signal_id": "later", "post_ts": "2026-01-02T00:00:00Z",
             "price_at_signal": "0.80", "status": "pass"},
            {**base, "signal_id": "earlier", "post_ts": "2026-01-01T00:00:00Z",
             "price_at_signal": "0.40"},
            {**base, "signal_id": "live", "market_id": "m2", "event_id": "e2",
             "post_ts": "2026-01-03T00:00:00Z", "side": "NO",
             "price_at_signal": "0.60", "status": "pass"},
            {**base, "signal_id": "unpriced", "market_id": "m3", "event_id": "e3",
             "post_ts": "2026-01-04T00:00:00Z", "price_at_signal": "",
             "status": "expired"},
        ]
        thresholds = {"verify_min_calls": 10, "verify_min_edge": 0.05,
                      "verify_z": 1.2816}

        changed, promotions = resolve.rebuild_leaker_stats(
            signals, leakers, thresholds, "d")
        self.assertTrue(changed)
        self.assertEqual(promotions, [])
        row = leakers[0]
        self.assertEqual((row["n_calls"], row["hits"], row["n_unpriced"], row["n_live"]),
                         (2, 1, 1, 1))
        self.assertEqual(row["avg_price_at_call"], "0.400")
        self.assertEqual((row["last_seen_ts"], row["notes"]),
                         ("keep-me", "keep-note"))
        self.assertEqual(signals[0]["stat_counted"], "false")
        self.assertEqual(signals[1]["stat_counted"], "true")
        self.assertEqual(signals[3]["stat_counted"], "false")

        snapshot = copy.deepcopy((signals, leakers))
        changed, _ = resolve.rebuild_leaker_stats(signals, leakers, thresholds, "d")
        self.assertFalse(changed)
        self.assertEqual((signals, leakers), snapshot)

        # TSV reads return strings; reconciliation must still recognize that
        # the persisted projection is already current.
        for field in resolve.STAT_FIELDS:
            leakers[0][field] = str(leakers[0][field])
        changed, _ = resolve.rebuild_leaker_stats(signals, leakers, thresholds, "d")
        self.assertFalse(changed)


class OrchestratorRecoveryTests(unittest.TestCase):
    def harness(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        agent = root / "agents" / "orchestrator"
        (agent / "experiments").mkdir(parents=True)
        (root / "ledger").mkdir()
        (agent / "EXPERIMENTS.md").write_text("", encoding="utf-8")
        (root / "ledger" / "learnings.md").write_text("", encoding="utf-8")
        (root / "ledger" / "results.tsv").write_text(
            "ts\tscript\tdomain\tsummary\n", encoding="utf-8")
        return tmp, root, agent

    def test_config_before_image_exists_before_patch(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        state = {"sources": {"history_days": 365}}
        (root / "config.json").write_text(json.dumps(state), encoding="utf-8")

        cfg = {"orchestrator": {"editable_files_regex": "^$"}}
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent)):
            outcome = orchestrator.apply_amendment(
                cfg, {"id": "exp", "kind": "config",
                      "patch": {"sources.history_days": 180},
                      "metric": orchestrator_metric()})
        self.assertIn("patched", outcome)
        self.assertEqual(json.loads((root / "config.json").read_text())
                         ["sources"]["history_days"], 180)
        evidence_dirs = [path for path in (agent / "experiments").iterdir()
                         if path.is_dir()]
        self.assertEqual(len(evidence_dirs), 1)
        meta = json.loads((evidence_dirs[0] / "meta.json").read_text())
        self.assertEqual(meta["amendment"]["patch_before"],
                         {"sources.history_days": 365})

    def test_failed_revert_remains_primary_pending_and_retryable(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        exp = agent / "EXPERIMENTS.md"
        exp.write_text(orchestrator.EXPERIMENTS_TEMPLATE, encoding="utf-8")
        (root / "prompts").mkdir()
        (root / "prompts" / "heartbeat.md").write_text("before", encoding="utf-8")
        cfg = {"orchestrator": {"editable_files_regex":
               r"^prompts/(explorer|heartbeat|judge)\.md$"}}
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent)):
            orchestrator.apply_amendment(
                cfg, {"kind": "file", "path": "prompts/heartbeat.md",
                      "content": "after", "metric": orchestrator_metric()})
            journal = agent / "experiments" / orchestrator.APPLY_JOURNAL
            exp_id = journal.read_text().splitlines()[1].split("\t")[1]
            row = orchestrator._load_journal(cfg)[1][0]
            due = orchestrator._review_due_epoch(row)
            result = orchestrator.review_candidates(
                cfg, now_epoch=due)[0]["metric_result"]
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent),
              mock.patch.object(orchestrator, "load_config", return_value=cfg),
              mock.patch.object(orchestrator, "_restore",
                                return_value=(False, "restore readback failed"))):
            notes = orchestrator.review_experiments(
                [{"id": exp_id, "verdict": "revert", "reason": "worse",
                  "metric_result": result}], now_epoch=due)
        self.assertEqual(notes, [f"{exp_id}:revert-error"])
        self.assertIn("| revert-pending |", exp.read_text(encoding="utf-8"))
        self.assertEqual(journal.read_text().splitlines()[-1].split("\t")[2],
                         "revert_prepared")
        self.assertIn("retryable-error",
                      (root / "ledger" / "learnings.md").read_text(encoding="utf-8"))

    def test_restore_requires_readback_and_is_idempotent(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        experiments = agent / "experiments"

        (experiments / "cfg.json").write_text(json.dumps({
            "kind": "config", "patch_before": {"sources.history_days": 365},
        }), encoding="utf-8")
        (root / "config.json").write_text(
            json.dumps({"sources": {"history_days": 180}}), encoding="utf-8")
        cfg = {"orchestrator": {"editable_files_regex": "^$"},
               "sources": {"history_days": 180}}
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent),
              mock.patch.object(orchestrator, "load_config", return_value=cfg),
              mock.patch.object(orchestrator, "_atomic_replace_controlled")):
            ok, reason = orchestrator._restore("cfg")
        self.assertFalse(ok)
        self.assertIn("readback failed", reason)

        (root / "prompts").mkdir()
        target = root / "prompts" / "heartbeat.md"
        target.write_text("before", encoding="utf-8")
        (experiments / "file.json").write_text(
            json.dumps({"kind": "file", "path": "prompts/heartbeat.md"}),
            encoding="utf-8")
        (experiments / "file.before").write_text("before", encoding="utf-8")
        (experiments / "file.after").write_text("after", encoding="utf-8")
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent)):
            ok, reason = orchestrator._restore("file")
        self.assertTrue(ok)
        self.assertIn("already restored", reason)


if __name__ == "__main__":
    unittest.main()
