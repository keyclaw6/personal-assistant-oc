from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

DELPHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DELPHI / "scripts"))

import judge  # noqa: E402


THRESHOLDS = {
    "kelly_fraction": Decimal("0.250000"),
    "max_stake_frac": Decimal("0.050000"),
}


class JudgeCapitalSizingTests(unittest.TestCase):
    @staticmethod
    def position(position_id: str = "p1", signal_id: str = "s1",
                 market_id: str = "m1", status: str = "closed",
                 **overrides) -> dict:
        row = {
            "position_id": position_id, "signal_id": signal_id,
            "market_id": market_id, "side": "YES", "entry_price": "0.500",
            "size_usd": "1.00", "shares": "2.00", "judge_p": "0.800",
            "status": status,
        }
        row.update(overrides)
        return row

    @staticmethod
    def settlement(position_id: str = "p1", signal_id: str = "s1",
                   market_id: str = "m1", **overrides) -> dict:
        row = {
            "position_id": position_id, "signal_id": signal_id,
            "ts_resolved": "2026-07-14T12:00:00Z", "market_id": market_id,
            "side": "YES", "entry_price": "0.500", "size_usd": "1.00",
            "exit_value": "2.00", "pnl_usd": "1.00", "brier": "0.0400",
            "leaker_id": "x-source", "call_class": "timing",
        }
        row.update(overrides)
        return row

    def size(self, *, available: str, equity: str,
             p: str = "0.750", entry: str = "0.500") -> Decimal:
        return judge.canonical_position_size(
            "YES", Decimal(p), Decimal(entry),
            available_capital=Decimal(available),
            total_equity=Decimal(equity), thresholds=THRESHOLDS)

    def test_fractional_kelly_uses_available_but_cap_uses_total_equity(self):
        # Kelly: .25 * ((.75-.50)/(1-.50)) * 200 = 25.
        # Portfolio cap: .05 * 1000 = 50. The result is $25, not the
        # old, incorrectly available-capital-capped $10.
        self.assertEqual(self.size(available="200.00", equity="1000.00"),
                         Decimal("25.00"))

    def test_low_available_high_equity_is_kelly_limited(self):
        self.assertEqual(self.size(available="40.00", equity="1000.00"),
                         Decimal("5.00"))

    def test_high_available_low_equity_is_portfolio_cap_limited(self):
        self.assertEqual(self.size(available="900.00", equity="100.00"),
                         Decimal("5.00"))

    def test_zero_available_or_equity_never_sizes_a_position(self):
        self.assertEqual(self.size(available="0.00", equity="1000.00"),
                         Decimal("0.00"))
        self.assertEqual(self.size(available="200.00", equity="0.00"),
                         Decimal("0.00"))

    def test_decimal_half_even_rounding_is_exact(self):
        # Raw Kelly stake is 1.005 and must use Decimal half-even cents.
        self.assertEqual(self.size(
            available="8.04", equity="1000.00"), Decimal("1.00"))

    def test_account_capital_is_exact_and_rejects_unsafe_ledgers(self):
        equity, available = judge.account_capital(
            Decimal("1000.00"),
            [self.settlement()],
            [self.position(), self.position(
                position_id="p2", signal_id="s2", market_id="m2",
                status="open", entry_price="0.500", size_usd="200.10",
                shares="400.20")],
        )
        self.assertEqual(equity, Decimal("1001.00"))
        self.assertEqual(available, Decimal("800.90"))

        bad_values = ("nan", "inf", "-1.00", "not-money", "1.001",
                      "1.000", "1e2", " 1.00", "+1.00", "01.00")
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(
                    judge.RetryableDecisionError):
                judge.account_capital(
                    Decimal("1000.00"), [],
                    [self.position(status="open", size_usd=bad)],
                )

    def test_account_capital_rejects_duplicate_or_unbound_rows(self):
        valid_position = self.position()
        valid_settlement = self.settlement()
        bad_ledgers = (
            ([valid_position, dict(valid_position)], [valid_settlement]),
            ([self.position(position_id="")], [valid_settlement]),
            ([self.position(status="OPEN")], []),
            ([valid_position], [valid_settlement, dict(valid_settlement)]),
            ([valid_position], [self.settlement(signal_id="other")]),
            ([valid_position], []),
            ([self.position(status="open")], [valid_settlement]),
            ([self.position(status="open"), self.position(
                position_id="p2", signal_id="s2", status="open")], []),
        )
        for positions, resolved in bad_ledgers:
            with self.subTest(positions=positions, resolved=resolved), \
                    self.assertRaises(judge.RetryableDecisionError):
                judge.account_capital(Decimal("1000.00"), resolved, positions)

    def test_account_capital_rejects_impossible_open_and_closed_shares(self):
        impossible_open = self.position(
            status="open", shares="999.00")
        with self.assertRaises(judge.RetryableDecisionError):
            judge.account_capital(Decimal("1000.00"), [], [impossible_open])

        impossible_closed = self.position(shares="999.00")
        matching_bad_payout = self.settlement(
            exit_value="999.00", pnl_usd="998.00")
        with self.assertRaises(judge.RetryableDecisionError):
            judge.account_capital(
                Decimal("1000.00"), [matching_bad_payout],
                [impossible_closed])

    def test_account_capital_uses_half_even_share_rounding(self):
        half_even = self.position(
            status="open", entry_price="0.320", shares="3.12")
        equity, available = judge.account_capital(
            Decimal("1000.00"), [], [half_even])
        self.assertEqual((equity, available),
                         (Decimal("1000.00"), Decimal("999.00")))
        with self.assertRaises(judge.RetryableDecisionError):
            judge.account_capital(
                Decimal("1000.00"), [],
                [self.position(
                    status="open", entry_price="0.320", shares="3.13")])

    def test_entry_above_canonical_fill_cap_rejects_every_sizing_path(self):
        with self.assertRaises(judge.RetryableDecisionError):
            judge.account_capital(
                Decimal("1000.00"), [], [self.position(
                    status="open", entry_price="0.999", shares="1.00")])
        with self.assertRaises(judge.RetryableDecisionError):
            judge.canonical_position_size(
                "YES", Decimal("0.999"), Decimal("0.999"),
                available_capital=Decimal("200.00"),
                total_equity=Decimal("1000.00"), thresholds=THRESHOLDS)

    def test_duplicate_settlement_credit_cannot_double_count_pnl(self):
        positions = [
            self.position(),
            self.position(position_id="p2", signal_id="s2", status="closed"),
        ]
        settlements = [
            self.settlement(),
            self.settlement(position_id="p2", signal_id="s2"),
        ]
        with self.assertRaises(judge.RetryableDecisionError):
            judge.account_capital(Decimal("1000.00"), settlements, positions)

    def test_negative_or_nonfinite_direct_sizing_inputs_fail(self):
        for available, equity in (("-1", "1000"), ("1", "-1"),
                                  ("NaN", "1000"), ("1", "Infinity")):
            with self.subTest(available=available, equity=equity), \
                    self.assertRaises(judge.RetryableDecisionError):
                self.size(available=available, equity=equity)

    def test_exact_sizing_contract_rejects_coercive_numeric_types(self):
        exact = {
            "p_yes": Decimal("0.750"), "entry": Decimal("0.500"),
            "available_capital": Decimal("200.00"),
            "total_equity": Decimal("1000.00"), "thresholds": THRESHOLDS,
        }
        for field, value in (("p_yes", 0.75), ("entry", 0.5),
                             ("available_capital", 200.0),
                             ("total_equity", 1000),
                             ("p_yes", True)):
            args = {**exact, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(
                    judge.RetryableDecisionError):
                judge.canonical_position_size("YES", **args)

    def test_exact_sizing_contract_rejects_coercive_threshold_types(self):
        exact = {
            "kelly_fraction": Decimal("0.250000"),
            "max_stake_frac": Decimal("0.050000"),
        }
        for field, value in (("kelly_fraction", 0.25),
                             ("max_stake_frac", 0.05),
                             ("kelly_fraction", 1),
                             ("max_stake_frac", True),
                             ("kelly_fraction", Decimal("NaN"))):
            thresholds = {**exact, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(
                    judge.RetryableDecisionError):
                judge.canonical_position_size(
                    "YES", Decimal("0.750"), Decimal("0.500"),
                    available_capital=Decimal("200.00"),
                    total_equity=Decimal("1000.00"), thresholds=thresholds)

    def test_config_sizing_thresholds_are_canonicalized_once(self):
        converted = judge.canonical_sizing_thresholds({
            "kelly_fraction": 0.25, "max_stake_frac": 0.05,
        })
        self.assertEqual(converted, {
            "kelly_fraction": Decimal("0.250000"),
            "max_stake_frac": Decimal("0.050000"),
        })
        for value in (True, "0.25", float("nan"), float("inf"),
                      0.1234567, 0, -0.1, 1.1):
            with self.subTest(value=value), self.assertRaises(
                    judge.RetryableDecisionError):
                judge.canonical_sizing_thresholds({
                    "kelly_fraction": value, "max_stake_frac": 0.05,
                })


if __name__ == "__main__":
    unittest.main()
