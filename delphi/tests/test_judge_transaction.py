from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DELPHI = Path(__file__).resolve().parents[1]
SCRIPTS = DELPHI / "scripts"
sys.path.insert(0, str(SCRIPTS))

import judge  # noqa: E402
import lib  # noqa: E402


JOURNAL_HEADER = (
    "signal_id\tdomain\tmarket_id\tmarket_question\ttoken_id\tside\tstate\t"
    "ts_decided\tposition_id\tintended_status\tjudge_p\tjudge_conf\tedge\t"
    "quote_price\tslippage\tentry_price\tavailable_usd\ttotal_equity_usd\tkelly_fraction\t"
    "max_stake_frac\tmin_edge\tjudge_min_conf\tsize_usd\tshares\tnote"
)


class InjectedCrash(RuntimeError):
    pass


class JudgeDecisionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".f6-", dir=DELPHI)
        self.addCleanup(self.tmp.cleanup)
        self.ddir = Path(self.tmp.name)
        production = DELPHI / "domains" / "ai-releases"
        for name in ("signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv"):
            header = (production / name).read_text(encoding="utf-8").splitlines()[0]
            (self.ddir / name).write_text(header + "\n", encoding="utf-8")
        (self.ddir / "judge-decisions.tsv").write_text(
            JOURNAL_HEADER + "\n", encoding="utf-8")

        lib.append_tsv(self.ddir / "signals.tsv", {
            "signal_id": "sig-1", "ts_detected": "2026-07-14T08:00:00Z",
            "domain": "test", "leaker_id": "x-source", "platform": "x",
            "post_url": "https://example.test/post/1",
            "post_ts": "2026-07-14T07:00:00Z", "claim": "Release today",
            "call_class": "release-timing", "hedged": "false",
            "market_id": "market-1", "event_id": "event-1",
            "market_question": "Will the release happen today?",
            "token_id": "yes-token", "side": "YES",
            "price_at_signal": "0.350", "liquidity_usd": "2500",
            "status": "pending_judge", "stat_counted": "false",
        })
        lib.append_tsv(self.ddir / "leakers.tsv", {
            "leaker_id": "x-source", "platform": "x", "handle": "source",
            "domain": "test", "call_class": "release-timing",
            "status": "verified", "n_calls": "20", "hits": "16",
            "hit_rate": "0.800", "avg_price_at_call": "0.400",
            "est_edge": "0.400", "edge_lcb": "0.200", "n_unpriced": "0",
            "n_live": "0",
        })
        self.cfg = {
            "bankroll_usd": 1000.0,
            "roles": {"judge": {"model": "gpt-5.6-luna"}},
            "thresholds": {
                "min_liquidity_usd": 1000.0,
                "slippage": 0.01,
                "min_edge": 0.10,
                "judge_min_conf": 0.60,
                "kelly_fraction": 0.25,
                "max_stake_frac": 0.05,
            },
        }
        self.market = {
            "id": "market-1", "question": "Will the release happen today?",
            "description": "Resolves YES on a release today.",
            "end_date": "2026-07-15T00:00:00Z", "closed": False,
            "liquidity": 2500.0, "yes_token": "yes-token",
            "no_token": "no-token",
        }
        self.model_calls = 0

    def call_model(self, *_args, **_kwargs):
        self.model_calls += 1
        return {
            "p_yes": 0.80,
            "confidence": 0.90,
            "rationale": "Strong independently useful leak.",
            "lessons": [],
        }

    def run_judge(self, *, fault: str | None = None,
                  model=None, ask: float = 0.40) -> None:
        fired = False

        def inject(point: str):
            nonlocal fired
            if point == fault and not fired:
                fired = True
                raise InjectedCrash(point)

        with (
            mock.patch.object(sys, "argv", ["judge.py", "--domain", "test"]),
            mock.patch.object(judge, "domain_dir", return_value=self.ddir),
            mock.patch.object(judge, "load_config", return_value=self.cfg),
            mock.patch.object(judge, "agent_context", return_value=""),
            mock.patch.object(judge.pm, "get_market", return_value=self.market),
            mock.patch.object(judge, "executable_ask", return_value=ask),
            mock.patch.object(judge.cognee, "search", return_value=[]),
            mock.patch.object(judge.cognee, "add"),
            mock.patch.object(judge, "call_json",
                              side_effect=(model or self.call_model)),
            mock.patch.object(judge, "append_lessons"),
            mock.patch.object(judge, "write_note"),
            mock.patch.object(judge, "log_result"),
            mock.patch.object(judge, "now_iso",
                              return_value="2026-07-14T09:00:00Z"),
            mock.patch.object(judge, "fault_point", side_effect=inject),
        ):
            judge.main()

    def rows(self, name: str) -> list[dict]:
        return lib.read_tsv(self.ddir / name)

    def assert_materialized_bet(self):
        signal = self.rows("signals.tsv")[0]
        positions = self.rows("positions.tsv")
        journal = self.rows("judge-decisions.tsv")
        self.assertEqual(signal["status"], "bet")
        self.assertEqual(signal["judge_p"], "0.800")
        self.assertEqual(signal["judge_conf"], "0.90")
        self.assertEqual(signal["edge"], "0.390")
        self.assertEqual(signal["note"], "Strong independently useful leak.")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["position_id"],
                         judge.deterministic_position_id("test", "sig-1"))
        self.assertEqual(positions[0]["signal_id"], "sig-1")
        self.assertEqual(positions[0]["quote_price"], "0.400")
        self.assertEqual(positions[0]["entry_price"], "0.410")
        self.assertEqual(positions[0]["size_usd"], "50.00")
        self.assertEqual(positions[0]["shares"], "121.95")
        self.assertEqual(journal[0]["available_usd"], "1000.00")
        self.assertEqual(journal[0]["total_equity_usd"], "1000.00")
        self.assertEqual([row["state"] for row in journal],
                         ["prepared", "final"])
        for field in JOURNAL_HEADER.split("\t"):
            if field != "state":
                self.assertEqual(journal[0][field], journal[1][field])

    def prepared_bet(self, *, state: str = "prepared", **overrides) -> dict:
        row = {
            "signal_id": "sig-1", "domain": "test", "market_id": "market-1",
            "market_question": "Will the release happen today?",
            "token_id": "yes-token", "side": "YES", "state": state,
            "ts_decided": "2026-07-14T09:00:00Z",
            "position_id": judge.deterministic_position_id("test", "sig-1"),
            "intended_status": "bet",
            "judge_p": "0.800",
            "judge_conf": "0.90", "edge": "0.390", "quote_price": "0.400",
            "slippage": "0.010", "entry_price": "0.410",
            "available_usd": "1000.00", "kelly_fraction": "0.250000",
            "total_equity_usd": "1000.00",
            "max_stake_frac": "0.050000", "min_edge": "0.100",
            "judge_min_conf": "0.60", "size_usd": "50.00",
            "shares": "121.95", "note": "Strong independently useful leak.",
        }
        row.update(overrides)
        return row

    def materialized_position(self, *, status: str = "open") -> dict:
        return {
            "position_id": judge.deterministic_position_id("test", "sig-1"),
            "signal_id": "sig-1", "ts_open": "2026-07-14T09:00:00Z",
            "market_id": "market-1",
            "market_question": "Will the release happen today?",
            "token_id": "yes-token", "side": "YES", "quote_price": "0.400",
            "entry_price": "0.410", "size_usd": "50.00", "shares": "121.95",
            "judge_p": "0.800", "status": status,
            "note": "Strong independently useful leak.",
        }

    def test_every_transaction_boundary_replays_idempotently(self):
        boundaries = (
            "before_prepared", "after_prepared", "after_position_append",
            "after_signal_update", "before_final", "after_final",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                self.setUp()
                try:
                    with self.assertRaisesRegex(InjectedCrash, boundary):
                        self.run_judge(fault=boundary)
                    calls_after_crash = self.model_calls
                    self.run_judge()
                    self.run_judge()
                    self.assert_materialized_bet()
                    expected_calls = 2 if boundary == "before_prepared" else 1
                    self.assertEqual(calls_after_crash, 1)
                    self.assertEqual(self.model_calls, expected_calls)
                finally:
                    self.doCleanups()

    def test_kelly_uses_available_while_portfolio_cap_uses_total_equity(self):
        lib.append_tsv(self.ddir / "positions.tsv", {
            "position_id": "existing-position", "signal_id": "existing-signal",
            "ts_open": "2026-07-14T07:00:00Z", "market_id": "other-market",
            "market_question": "An unrelated open paper position?",
            "token_id": "other-token", "side": "YES", "quote_price": "0.500",
            "entry_price": "0.500", "size_usd": "800.00", "shares": "1600.00",
            "judge_p": "0.750", "status": "open", "note": "existing",
        })

        def acceptance_model(*_args, **_kwargs):
            self.model_calls += 1
            return {"p_yes": 0.75, "confidence": 0.90,
                    "rationale": "Acceptance vector.", "lessons": []}

        self.run_judge(model=acceptance_model, ask=0.49)

        new_position = [p for p in self.rows("positions.tsv")
                        if p["signal_id"] == "sig-1"][0]
        prepared = self.rows("judge-decisions.tsv")[0]
        self.assertEqual(new_position["entry_price"], "0.500")
        self.assertEqual(new_position["size_usd"], "25.00")
        self.assertEqual(prepared["available_usd"], "200.00")
        self.assertEqual(prepared["total_equity_usd"], "1000.00")

    def test_malformed_account_ledger_fails_before_recovery_or_model(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        lib.append_tsv(self.ddir / "positions.tsv", {
            "position_id": "bad-position", "signal_id": "bad-signal",
            "ts_open": "2026-07-14T07:00:00Z", "market_id": "other-market",
            "market_question": "Bad ledger row", "token_id": "other-token",
            "side": "YES", "quote_price": "0.500", "entry_price": "0.500",
            "size_usd": "NaN", "shares": "1.00", "judge_p": "0.750",
            "status": "open", "note": "bad",
        })

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.model_calls, 0)
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(len(self.rows("positions.tsv")), 1)
        self.assertEqual(
            [row["state"] for row in self.rows("judge-decisions.tsv")],
            ["prepared"],
        )

    def test_nonfinite_liquidity_stays_retryable_before_model_or_decision(self):
        self.market["liquidity"] = float("nan")

        self.run_judge()

        signal = self.rows("signals.tsv")[0]
        self.assertEqual(self.model_calls, 0)
        self.assertEqual(signal["status"], "pending_judge")
        self.assertIn("retrying", signal["note"])
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.rows("judge-decisions.tsv"), [])

    def test_prepared_position_is_recovered_without_model_or_duplicate(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        lib.append_tsv_atomic(
            self.ddir / "positions.tsv", self.materialized_position())

        def forbidden_model(*_args, **_kwargs):
            raise AssertionError("prepared decisions must not call the model")

        self.run_judge(model=forbidden_model)
        self.assert_materialized_bet()

    def test_resolver_interleaving_recovers_prepared_bet_without_reopening(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        lib.append_tsv_atomic(
            self.ddir / "positions.tsv",
            self.materialized_position(status="closed"))
        lib.append_tsv(self.ddir / "resolved.tsv", {
            "position_id": judge.deterministic_position_id("test", "sig-1"),
            "signal_id": "sig-1", "ts_resolved": "2026-07-14T10:00:00Z",
            "market_id": "market-1", "side": "YES", "entry_price": "0.410",
            "size_usd": "50.00", "exit_value": "121.95", "pnl_usd": "71.95",
            "brier": "0.0400", "leaker_id": "x-source",
            "call_class": "release-timing",
        })
        signals = self.rows("signals.tsv")
        signals[0].update({"status": "expired", "resolved_outcome": "YES"})
        lib.write_tsv(self.ddir / "signals.tsv", signals)

        def forbidden_model(*_args, **_kwargs):
            raise AssertionError("prepared decisions must not call the model")

        self.run_judge(model=forbidden_model)
        signal = self.rows("signals.tsv")[0]
        positions = self.rows("positions.tsv")
        self.assertEqual(signal["status"], "bet")
        self.assertEqual(signal["resolved_outcome"], "YES")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["status"], "closed")
        self.assertEqual(
            [row["state"] for row in self.rows("judge-decisions.tsv")],
            ["prepared", "final"],
        )

    def test_prepared_bet_repairs_terminal_signal_missing_its_position(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        signals = self.rows("signals.tsv")
        signals[0].update({
            "status": "bet", "judge_p": "0.800", "judge_conf": "0.90",
            "edge": "0.390", "note": "Strong independently useful leak.",
        })
        lib.write_tsv(self.ddir / "signals.tsv", signals)

        def forbidden_model(*_args, **_kwargs):
            raise AssertionError("prepared decisions must not call the model")

        self.run_judge(model=forbidden_model)
        self.assert_materialized_bet()

    def test_legitimate_pass_is_prepared_and_replayed_without_position(self):
        def pass_model(*_args, **_kwargs):
            self.model_calls += 1
            return {"p_yes": 0.45, "confidence": 0.90,
                    "rationale": "No executable edge.", "lessons": []}

        with self.assertRaisesRegex(InjectedCrash, "after_prepared"):
            self.run_judge(fault="after_prepared", model=pass_model)
        self.run_judge(model=pass_model)
        self.run_judge(model=pass_model)

        signal = self.rows("signals.tsv")[0]
        journal = self.rows("judge-decisions.tsv")
        self.assertEqual(self.model_calls, 1)
        self.assertEqual(signal["status"], "pass")
        self.assertEqual(signal["judge_p"], "0.450")
        self.assertEqual(signal["edge"], "0.040")
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual([row["state"] for row in journal],
                         ["prepared", "final"])
        self.assertEqual(journal[0]["intended_status"], "pass")
        self.assertEqual(journal[0]["position_id"], "")

    def test_torn_journal_fails_retryably_before_model_or_materialization(self):
        with open(self.ddir / "judge-decisions.tsv", "a", encoding="utf-8") as f:
            f.write("sig-1\tprepared\t2026-07-14T09:00:00Z\tpos-torn")

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.model_calls, 0)
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])

    def test_malformed_prepared_economics_fail_without_deriving_pass(self):
        values = self.prepared_bet(size_usd="not-a-size")
        with open(self.ddir / "judge-decisions.tsv", "a", newline="",
                  encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=JOURNAL_HEADER.split("\t"),
                                    delimiter="\t", lineterminator="\n")
            writer.writerow(values)

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.model_calls, 0)
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])

    def test_contradictory_final_row_fails_before_any_projection(self):
        prepared = self.prepared_bet()
        lib.append_tsv_atomic(self.ddir / "judge-decisions.tsv", prepared)
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv",
            self.prepared_bet(state="final", size_usd="49.00"),
        )

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.model_calls, 0)
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])

    def test_prepared_identity_mismatch_cannot_substitute_signal_trade(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        signals = self.rows("signals.tsv")
        signals[0].update({
            "domain": "changed", "market_id": "market-substitute",
            "market_question": "A substituted market?", "token_id": "other-token",
            "side": "NO",
        })
        lib.write_tsv(self.ddir / "signals.tsv", signals)

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        persisted = self.rows("signals.tsv")[0]
        self.assertEqual(persisted["status"], "pending_judge")
        self.assertEqual(persisted["market_id"], "market-substitute")
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.model_calls, 0)

    def test_quoted_tab_journal_field_is_not_canonical_tsv(self):
        row = self.prepared_bet(note="quoted\ttab")
        with open(self.ddir / "judge-decisions.tsv", "a", newline="",
                  encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=JOURNAL_HEADER.split("\t"), delimiter="\t",
                lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(row)

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.model_calls, 0)

    def test_later_orphan_preflights_before_any_valid_decision_projection(self):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet())
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv",
            self.prepared_bet(
                signal_id="sig-missing",
                position_id=judge.deterministic_position_id(
                    "test", "sig-missing"),
            ),
        )

        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()

        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(
            [row["state"] for row in self.rows("judge-decisions.tsv")],
            ["prepared", "prepared"],
        )
        self.assertEqual(self.model_calls, 0)

    def assert_bad_prepared_evidence_is_nonmutating(self, **overrides):
        lib.append_tsv_atomic(
            self.ddir / "judge-decisions.tsv", self.prepared_bet(**overrides))
        with self.assertRaises(judge.RetryableDecisionError):
            self.run_judge()
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "pending_judge")
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.model_calls, 0)

    def test_shares_must_equal_size_divided_by_entry(self):
        self.assert_bad_prepared_evidence_is_nonmutating(shares="999.99")

    def test_size_must_match_prepared_kelly_and_cap_inputs(self):
        self.assert_bad_prepared_evidence_is_nonmutating(
            size_usd="40.00", shares="97.56")

    def test_total_equity_tamper_cannot_change_portfolio_cap(self):
        self.assert_bad_prepared_evidence_is_nonmutating(
            total_equity_usd="100.00", size_usd="50.00", shares="121.95")

    def test_malformed_total_equity_fails_before_projection(self):
        self.assert_bad_prepared_evidence_is_nonmutating(
            total_equity_usd="NaN")

    def test_available_capital_cannot_exceed_total_equity(self):
        self.assert_bad_prepared_evidence_is_nonmutating(
            available_usd="2000.00", total_equity_usd="1000.00")

    def test_edge_must_exactly_match_side_probability_minus_entry(self):
        self.assert_bad_prepared_evidence_is_nonmutating(edge="0.391")

    def test_fill_must_be_quote_plus_prepared_slippage(self):
        self.assert_bad_prepared_evidence_is_nonmutating(quote_price="0.900")

    def test_timestamp_requires_zero_padded_canonical_utc_shape(self):
        self.assert_bad_prepared_evidence_is_nonmutating(
            ts_decided="2026-7-4T9:2:3Z")


if __name__ == "__main__":
    unittest.main()
