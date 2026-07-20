from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

DELPHI = Path(__file__).resolve().parents[1]
SCRIPTS = DELPHI / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lib  # noqa: E402
import resolve  # noqa: E402


class AtomicTsvAppendTests(unittest.TestCase):
    def table(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        # Keep the disposable destination on the same mount as Delphi's real
        # ledgers so this exercises the production rename assumption safely.
        tmp = tempfile.TemporaryDirectory(prefix=".f2-", dir=DELPHI)
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "resolved.tsv"
        path.write_text("position_id\tpnl_usd\np0\t1.00\n", encoding="utf-8")
        return tmp, path

    def test_atomic_append_uses_same_directory_and_same_filesystem(self):
        _, path = self.table()
        original_mode = path.stat().st_mode
        real_replace = os.replace
        replacements: list[tuple[Path, Path]] = []

        def checked_replace(src, dst):
            src, dst = Path(src), Path(dst)
            self.assertEqual(src.parent, path.parent)
            self.assertEqual(dst, path)
            self.assertEqual(src.stat().st_dev, path.parent.stat().st_dev)
            replacements.append((src, dst))
            real_replace(src, dst)

        with mock.patch.object(lib.os, "replace", side_effect=checked_replace):
            lib.append_tsv_atomic(path, {"position_id": "p1", "pnl_usd": "2.00"})

        self.assertEqual(len(replacements), 1)
        self.assertEqual(path.stat().st_mode, original_mode)
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "position_id\tpnl_usd\np0\t1.00\np1\t2.00\n",
        )

    def test_failed_replace_leaves_destination_byte_identical(self):
        _, path = self.table()
        before = path.read_bytes()

        with (mock.patch.object(lib.os, "replace", side_effect=OSError("fault")),
              self.assertRaisesRegex(OSError, "fault")):
            lib.append_tsv_atomic(path, {"position_id": "p1", "pnl_usd": "2.00"})

        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class ResolveSettlementReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".f2-", dir=DELPHI)
        self.addCleanup(self.tmp.cleanup)
        self.ddir = Path(self.tmp.name)
        production = DELPHI / "domains" / "ai-releases"
        for name in ("signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv"):
            header = (production / name).read_text(encoding="utf-8").splitlines()[0]
            (self.ddir / name).write_text(header + "\n", encoding="utf-8")

        lib.append_tsv(self.ddir / "signals.tsv", {
            "signal_id": "s1", "ts_detected": "2026-07-14T00:00:00Z",
            "domain": "test", "leaker_id": "x-source", "platform": "x",
            "post_url": "https://example.test/post", "post_ts": "2026-07-13T00:00:00Z",
            "claim": "release ships", "call_class": "timing", "hedged": "false",
            "market_id": "m1", "event_id": "e1", "market_question": "Will it ship?",
            "token_id": "yes-token", "side": "YES", "price_at_signal": "0.40",
            "liquidity_usd": "1000", "status": "bet", "judge_p": "0.800",
            "judge_conf": "0.90", "edge": "0.400",
        })
        lib.append_tsv(self.ddir / "positions.tsv", {
            "position_id": "p1", "signal_id": "s1",
            "ts_open": "2026-07-14T00:00:00Z", "market_id": "m1",
            "market_question": "Will it ship?", "token_id": "yes-token",
            "side": "YES", "quote_price": "0.390", "entry_price": "0.400",
            "size_usd": "40.00", "shares": "100.00", "judge_p": "0.800",
            "status": "open",
        })
        # Exact reachable F2 state: the host died immediately after the ID,
        # before any accounting field or row terminator reached the ledger.
        with open(self.ddir / "resolved.tsv", "a", encoding="utf-8") as f:
            f.write("p1")

        self.config = {
            "bankroll_usd": 1000.0,
            "call_classes": {"test": ["timing"]},
            "thresholds": {
                "verify_min_calls": 10,
                "verify_min_edge": 0.05,
                "verify_z": 1.2816,
            },
        }
        self.summaries: list[str] = []

    @staticmethod
    def settlement(**overrides) -> dict:
        row = {
            "position_id": "p1", "signal_id": "s1",
            "ts_resolved": "2026-07-14T12:00:00Z", "market_id": "m1",
            "side": "YES", "entry_price": "0.400", "size_usd": "40.00",
            "exit_value": "100.00", "pnl_usd": "60.00", "brier": "0.0400",
            "leaker_id": "x-source", "call_class": "timing",
        }
        row.update(overrides)
        return row

    def terminate_torn_row(self):
        with open(self.ddir / "resolved.tsv", "a", encoding="utf-8") as f:
            f.write("\n")

    def contextual_settlements(self, rows: list[dict]) -> list[dict]:
        return resolve.valid_position_settlements(
            rows,
            lib.read_tsv(self.ddir / "positions.tsv"),
            lib.read_tsv(self.ddir / "signals.tsv"),
            lambda _position, _signal: "YES",
        )

    def run_resolve(self, *, crash_before_position_close: bool = False):
        real_write = resolve.write_tsv

        def maybe_crash(path, rows):
            if crash_before_position_close and Path(path).name == "positions.tsv":
                raise RuntimeError("injected crash before position close")
            return real_write(path, rows)

        market = {"closed": True}
        with (mock.patch.object(resolve, "domain_dir", return_value=self.ddir),
              mock.patch.object(resolve, "load_config", return_value=self.config),
              mock.patch.object(resolve, "now_iso", return_value="2026-07-14T12:00:00Z"),
              mock.patch.object(resolve.pm, "get_market", return_value=market),
              mock.patch.object(resolve.pm, "winning_side", return_value="YES"),
              mock.patch.object(resolve.cognee, "add"),
              mock.patch.object(resolve.cognee, "cognify"),
              mock.patch.object(resolve, "write_tsv", side_effect=maybe_crash),
              mock.patch.object(resolve, "log_result",
                                side_effect=lambda _script, _domain, summary:
                                self.summaries.append(summary)),
              mock.patch.object(sys, "argv", ["resolve.py", "--domain", "test"])):
            resolve.main()

    def test_malformed_roster_preflight_precedes_provider_and_all_writes(self):
        lib.append_tsv(self.ddir / "leakers.tsv", {
            "leaker_id": "x-source", "platform": "x", "handle": "source",
            "domain": "test", "call_class": "timing", "status": "verified",
            "n_calls": "10", "hits": "8", "hit_rate": "0.800",
            "avg_price_at_call": "0.400", "est_edge": "0.400",
            "edge_lcb": "0.1", "n_unpriced": "0", "n_live": "0",
            "last_seen_ts": "", "notes": "malformed ranking cell",
        })
        paths = [self.ddir / name for name in (
            "resolved.tsv", "positions.tsv", "signals.tsv", "leakers.tsv")]
        before = {path: path.read_bytes() for path in paths}

        with (mock.patch.object(resolve, "domain_dir", return_value=self.ddir),
              mock.patch.object(resolve, "load_config", return_value=self.config),
              mock.patch.object(resolve.pm, "get_market") as get_market,
              mock.patch.object(resolve.pm, "winning_side") as winning_side,
              mock.patch.object(resolve.cognee, "add"),
              mock.patch.object(resolve.cognee, "cognify"),
              mock.patch.object(resolve, "log_result"),
              mock.patch.object(sys, "argv", ["resolve.py", "--domain", "test"]),
              self.assertRaises(resolve.RosterProjectionError)):
            resolve.main()

        get_market.assert_not_called()
        winning_side.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_rogue_resolved_signal_class_cannot_mutate_any_ledger(self):
        signals = lib.read_tsv(self.ddir / "signals.tsv")
        signals[0]["call_class"] = "rogue-class"
        lib.write_tsv(self.ddir / "signals.tsv", signals)
        paths = [self.ddir / name for name in (
            "resolved.tsv", "positions.tsv", "signals.tsv", "leakers.tsv")]
        before = {path: path.read_bytes() for path in paths}

        with (mock.patch.object(resolve, "domain_dir", return_value=self.ddir),
              mock.patch.object(resolve, "load_config", return_value=self.config),
              mock.patch.object(resolve.pm, "get_market") as get_market,
              mock.patch.object(resolve.pm, "winning_side") as winning_side,
              mock.patch.object(resolve.cognee, "add"),
              mock.patch.object(resolve.cognee, "cognify"),
              mock.patch.object(resolve, "log_result"),
              mock.patch.object(sys, "argv", ["resolve.py", "--domain", "test"]),
              self.assertRaises(resolve.RosterProjectionError)):
            resolve.main()

        get_market.assert_not_called()
        winning_side.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_torn_row_is_recomputed_once_across_crash_and_replay(self):
        with self.assertRaisesRegex(RuntimeError, "injected crash"):
            self.run_resolve(crash_before_position_close=True)

        # The incomplete evidence remains for audit, but only the newly
        # persisted complete row qualifies as a settlement.
        rows = lib.read_tsv(self.ddir / "resolved.tsv")
        settlements = resolve.valid_settlements(rows)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(resolve.is_valid_settlement(row) for row in rows), 1)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements[0]["position_id"], "p1")
        self.assertEqual(settlements[0]["pnl_usd"], "60.00")
        self.assertEqual(lib.read_tsv(self.ddir / "positions.tsv")[0]["status"], "open")

        # Replay sees the valid settlement, closes the still-open position,
        # and never appends a second valid payment.
        self.run_resolve()
        rows = lib.read_tsv(self.ddir / "resolved.tsv")
        settlements = resolve.valid_settlements(rows)
        self.assertEqual(sum(resolve.is_valid_settlement(row) for row in rows), 1)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(lib.read_tsv(self.ddir / "positions.tsv")[0]["status"], "closed")
        self.assertIn("equity 1060.00 (lifetime pnl +60.00)", self.summaries[-1])

    def test_complete_but_invalid_accounting_row_does_not_close_position(self):
        resolved = self.ddir / "resolved.tsv"
        self.terminate_torn_row()
        lib.append_tsv(resolved, self.settlement(pnl_usd="not-a-number"))

        self.run_resolve()
        settlements = resolve.valid_settlements(lib.read_tsv(resolved))
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements[0]["pnl_usd"], "60.00")
        self.assertIn("lifetime pnl +60.00", self.summaries[-1])

    def test_structurally_valid_mismatched_row_is_ignored_and_replaced_once(self):
        resolved = self.ddir / "resolved.tsv"
        self.terminate_torn_row()
        lib.append_tsv(resolved, self.settlement(
            signal_id="stale-signal", market_id="stale-market", side="NO",
            entry_price="0.500", exit_value="0.00", pnl_usd="-40.00",
            brier="0.6400", leaker_id="x-other", call_class="direction",
        ))

        self.run_resolve()
        rows = lib.read_tsv(resolved)
        contextual = self.contextual_settlements(rows)
        self.assertEqual(len(rows), 3)  # torn evidence + forged row + correct row
        self.assertEqual(sum(resolve.is_valid_settlement(row) for row in rows), 2)
        self.assertEqual(len(contextual), 1)
        self.assertEqual(contextual[0]["pnl_usd"], "60.00")
        self.assertEqual(lib.read_tsv(self.ddir / "positions.tsv")[0]["status"], "closed")
        self.assertIn("equity 1060.00 (lifetime pnl +60.00)", self.summaries[-1])

        self.run_resolve()
        rows = lib.read_tsv(resolved)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(self.contextual_settlements(rows)), 1)

    def test_huge_finite_decimal_is_rejected_without_infinite_equity(self):
        resolved = self.ddir / "resolved.tsv"
        self.terminate_torn_row()
        huge = self.settlement(
            size_usd="0", exit_value="1e309", pnl_usd="1e309")
        self.assertFalse(resolve.is_valid_settlement(huge))
        lib.append_tsv(resolved, huge)

        self.run_resolve()
        rows = lib.read_tsv(resolved)
        contextual = self.contextual_settlements(rows)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(resolve.is_valid_settlement(row) for row in rows), 1)
        self.assertEqual(len(contextual), 1)
        self.assertEqual(contextual[0]["pnl_usd"], "60.00")
        self.assertNotIn("inf", self.summaries[-1].lower())
        self.assertIn("equity 1060.00 (lifetime pnl +60.00)", self.summaries[-1])

    def test_provider_winner_overrides_stale_signal_outcome_in_totals(self):
        signals_path = self.ddir / "signals.tsv"
        signals = lib.read_tsv(signals_path)
        signals[0]["resolved_outcome"] = "NO"
        lib.write_tsv(signals_path, signals)

        resolved = self.ddir / "resolved.tsv"
        self.terminate_torn_row()
        lib.append_tsv(resolved, self.settlement(
            exit_value="0.00", pnl_usd="-40.00", brier="0.6400"))

        self.run_resolve()  # provider is definitively YES in the harness
        rows = lib.read_tsv(resolved)
        contextual = self.contextual_settlements(rows)
        self.assertEqual(len(rows), 3)  # torn + stale-NO row + provider-YES row
        self.assertEqual(sum(resolve.is_valid_settlement(row) for row in rows), 2)
        self.assertEqual(len(contextual), 1)
        self.assertEqual(contextual[0]["pnl_usd"], "60.00")
        self.assertIn("equity 1060.00 (lifetime pnl +60.00)", self.summaries[-1])

        self.run_resolve()
        self.assertEqual(len(lib.read_tsv(resolved)), 3)
        self.assertIn("equity 1060.00 (lifetime pnl +60.00)", self.summaries[-1])

    def test_mandatory_fields_require_canonical_text_and_timestamp(self):
        valid = self.settlement()
        self.assertTrue(resolve.is_valid_settlement(valid))
        cases = {
            "date-only timestamp": {"ts_resolved": "2026-07-14"},
            "leading whitespace": {"position_id": " p1"},
            "trailing whitespace": {"signal_id": "s1 "},
            "embedded signal whitespace": {"signal_id": "bad signal id"},
            "embedded market whitespace": {"market_id": "bad market id"},
            "control character": {"market_id": "m1\x00"},
            "blank leaker": {"leaker_id": ""},
            "blank class": {"call_class": ""},
        }
        for label, override in cases.items():
            with self.subTest(label):
                self.assertFalse(resolve.is_valid_settlement(
                    self.settlement(**override)))

    def test_position_share_math_binds_settlement_to_canonical_position(self):
        signal = lib.read_tsv(self.ddir / "signals.tsv")[0]
        position = lib.read_tsv(self.ddir / "positions.tsv")[0]
        impossible = {**position, "entry_price": "0.500", "size_usd": "50.00",
                      "shares": "999.00"}
        impossible_settlement = self.settlement(
            entry_price="0.500", size_usd="50.00", exit_value="999.00",
            pnl_usd="949.00")
        self.assertFalse(resolve.settlement_matches_position(
            impossible_settlement, impossible, signal, "YES"))

        half_even = {**position, "entry_price": "0.320", "size_usd": "1.00",
                     "shares": "3.12"}
        half_even_settlement = self.settlement(
            entry_price="0.320", size_usd="1.00", exit_value="3.12",
            pnl_usd="2.12")
        self.assertTrue(resolve.settlement_matches_position(
            half_even_settlement, half_even, signal, "YES"))
        self.assertFalse(resolve.settlement_matches_position(
            half_even_settlement, {**half_even, "shares": "3.13"},
            signal, "YES"))

    def test_entry_above_canonical_fill_cap_rejects_before_append(self):
        self.assertFalse(resolve.is_valid_settlement(
            self.settlement(entry_price="0.999")))
        positions = lib.read_tsv(self.ddir / "positions.tsv")
        positions[0].update({
            "entry_price": "0.999", "size_usd": "40.00", "shares": "40.04",
        })
        lib.write_tsv(self.ddir / "positions.tsv", positions)

        with self.assertRaisesRegex(ValueError, "refusing invalid settlement"):
            self.run_resolve()

        self.assertEqual(resolve.valid_settlements(
            lib.read_tsv(self.ddir / "resolved.tsv")), [])

    def test_zero_size_rejects_at_shared_and_resolve_boundaries(self):
        with self.assertRaises(ValueError):
            lib.canonical_position_shares(
                Decimal("0.00"), Decimal("0.500"))
        self.assertEqual(
            lib.canonical_position_shares(
                Decimal("1.00"), Decimal("0.500")),
            Decimal("2.00"),
        )
        self.assertEqual(
            lib.canonical_position_shares(
                Decimal("1.00"), Decimal("0.990")),
            Decimal("1.01"),
        )
        self.assertTrue(resolve.is_valid_settlement(self.settlement(
            entry_price="0.990", size_usd="1.00", exit_value="1.01",
            pnl_usd="0.01")))

        zero_settlement = self.settlement(
            entry_price="0.500", size_usd="0.00", exit_value="0.00",
            pnl_usd="0.00")
        self.assertFalse(resolve.is_valid_settlement(zero_settlement))
        signal = lib.read_tsv(self.ddir / "signals.tsv")[0]
        position = lib.read_tsv(self.ddir / "positions.tsv")[0]
        zero_position = {**position, "entry_price": "0.500",
                         "size_usd": "0.00", "shares": "0.00"}
        self.assertFalse(resolve.settlement_matches_position(
            zero_settlement, zero_position, signal, "YES"))

    def test_zero_size_rejects_pre_append_without_mutating_ledgers(self):
        positions = lib.read_tsv(self.ddir / "positions.tsv")
        positions[0].update({
            "entry_price": "0.500", "size_usd": "0.00", "shares": "0.00",
        })
        lib.write_tsv(self.ddir / "positions.tsv", positions)
        position_before = (self.ddir / "positions.tsv").read_bytes()
        resolved_before = (self.ddir / "resolved.tsv").read_bytes()

        with self.assertRaisesRegex(ValueError, "refusing invalid settlement"):
            self.run_resolve()

        self.assertEqual((self.ddir / "positions.tsv").read_bytes(),
                         position_before)
        self.assertEqual((self.ddir / "resolved.tsv").read_bytes(),
                         resolved_before)
        self.assertEqual(
            lib.read_tsv(self.ddir / "positions.tsv")[0]["status"], "open")


if __name__ == "__main__":
    unittest.main()
