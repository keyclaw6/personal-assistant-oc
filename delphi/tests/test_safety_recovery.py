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
        return tmp, root, agent

    def test_config_before_image_exists_before_patch(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        state = {"sources": {"history_days": 365}}

        def patch_config(patch):
            meta = json.loads((agent / "experiments" / "exp.json").read_text())
            self.assertEqual(meta["patch_before"], {"sources.history_days": 365})
            state["sources"]["history_days"] = patch["sources.history_days"]
            return True, "patched sources.history_days"

        cfg = {"orchestrator": {"editable_files_regex": "^$"}}
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent),
              mock.patch.object(orchestrator, "load_config",
                                side_effect=lambda: copy.deepcopy(state)),
              mock.patch.object(orchestrator, "config_patch", side_effect=patch_config)):
            outcome = orchestrator.apply_amendment(
                cfg, {"id": "exp", "kind": "config",
                      "patch": {"sources.history_days": 180}})
        self.assertIn("patched", outcome)
        self.assertEqual(state["sources"]["history_days"], 180)

    def test_failed_revert_remains_live_and_retryable(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        exp = agent / "EXPERIMENTS.md"
        exp.write_text("| exp | now | change | metric | 24h | live |\n", encoding="utf-8")
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent),
              mock.patch.object(orchestrator, "_restore",
                                return_value=(False, "restore readback failed"))):
            notes = orchestrator.review_experiments(
                [{"id": "exp", "verdict": "revert", "reason": "worse"}])
        self.assertEqual(notes, ["exp:revert-error"])
        self.assertIn("| live |", exp.read_text(encoding="utf-8"))
        self.assertIn("retryable-error",
                      (root / "ledger" / "learnings.md").read_text(encoding="utf-8"))

    def test_restore_requires_readback_and_is_idempotent(self):
        tmp, root, agent = self.harness()
        self.addCleanup(tmp.cleanup)
        experiments = agent / "experiments"

        (experiments / "cfg.json").write_text(json.dumps({
            "kind": "config", "patch_before": {"sources.history_days": 365},
        }), encoding="utf-8")
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent),
              mock.patch.object(orchestrator, "config_patch",
                                return_value=(True, "patched")),
              mock.patch.object(orchestrator, "load_config",
                                return_value={"sources": {"history_days": 180}})):
            ok, reason = orchestrator._restore("cfg")
        self.assertFalse(ok)
        self.assertIn("readback failed", reason)

        target = root / "prompt.md"
        target.write_text("before", encoding="utf-8")
        (experiments / "file.json").write_text(
            json.dumps({"kind": "file", "path": "prompt.md"}), encoding="utf-8")
        (experiments / "file.before").write_text("before", encoding="utf-8")
        (experiments / "file.after").write_text("after", encoding="utf-8")
        with (mock.patch.object(orchestrator, "ROOT", root),
              mock.patch.object(orchestrator, "agent_dir", return_value=agent)):
            ok, reason = orchestrator._restore("file")
        self.assertTrue(ok)
        self.assertIn("already restored", reason)


if __name__ == "__main__":
    unittest.main()
