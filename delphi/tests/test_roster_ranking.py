from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lib  # noqa: E402
import resolve  # noqa: E402


HEADER = ("leaker_id\tplatform\thandle\tdomain\tcall_class\tstatus\tn_calls\thits\t"
          "hit_rate\tavg_price_at_call\test_edge\tedge_lcb\tn_unpriced\tn_live\t"
          "last_seen_ts\tnotes\n")


class RosterRankingTests(unittest.TestCase):
    @staticmethod
    def row(leaker_id: str, *, call_class: str = "timing",
            status: str = "verified", edge_lcb: str = "0.100",
            n_calls: str = "10") -> dict:
        return {
            "leaker_id": leaker_id, "platform": "x",
            "handle": leaker_id.removeprefix("x-"), "domain": "d",
            "call_class": call_class, "status": status,
            "n_calls": n_calls, "hits": "0", "hit_rate": "",
            "avg_price_at_call": "", "est_edge": "",
            "edge_lcb": edge_lcb, "n_unpriced": "0", "n_live": "0",
            "last_seen_ts": "", "notes": "",
        }

    def test_status_edge_sample_and_id_rank_best_to_worst(self):
        rows = [
            self.row("x-retired", status="retired", edge_lcb="0.990", n_calls="999"),
            self.row("x-negative", edge_lcb="-0.050", n_calls="100"),
            self.row("x-probation", status="probation", edge_lcb="0.900", n_calls="999"),
            self.row("x-nine", edge_lcb="0.200", n_calls="9"),
            self.row("x-twelve_z", edge_lcb="0.200", n_calls="12"),
            self.row("x-twelve_a", edge_lcb="0.200", n_calls="12"),
            self.row("x-candidate", status="candidate", edge_lcb="", n_calls="0"),
        ]

        ranked = resolve.rank_roster(rows)

        self.assertEqual([
            "x-twelve_a", "x-twelve_z", "x-nine", "x-negative",
            "x-probation", "x-candidate", "x-retired",
        ], [row["leaker_id"] for row in ranked])

    def test_exact_tie_uses_leaker_id_then_call_class(self):
        rows = [
            self.row("x-b", call_class="timing"),
            self.row("x-a", call_class="timing"),
            self.row("x-a", call_class="existence"),
        ]

        ranked = resolve.rank_roster(rows)

        self.assertEqual([
            ("x-a", "existence"), ("x-a", "timing"), ("x-b", "timing"),
        ], [(row["leaker_id"], row["call_class"]) for row in ranked])

    def test_input_reordering_and_rerun_are_byte_stable(self):
        original = [
            self.row("x-z", status="probation", edge_lcb="-0.100", n_calls="20"),
            self.row("x-a", edge_lcb="0.050", n_calls="10"),
            self.row("x-b", edge_lcb="0.050", n_calls="10"),
        ]
        payloads = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leakers.tsv"
            for source in (original, list(reversed(copy.deepcopy(original)))):
                path.write_text(HEADER, encoding="utf-8")
                lib.write_tsv(path, resolve.rank_roster(source))
                first = path.read_bytes()
                lib.write_tsv(path, resolve.rank_roster(lib.read_tsv(path)))
                self.assertEqual(first, path.read_bytes())
                payloads.append(first)

        self.assertEqual(payloads[0], payloads[1])

    def test_duplicate_composite_id_is_rejected(self):
        duplicate = self.row("x-a")
        with self.assertRaises(resolve.RosterProjectionError):
            resolve.rank_roster([duplicate, copy.deepcopy(duplicate)])

    def test_malformed_rows_are_rejected_not_coerced(self):
        valid = self.row("x-a")
        malformed = [
            {**valid, "status": "VERIFIED"},
            {**valid, "status": "unknown"},
            {**valid, "edge_lcb": "NaN"},
            {**valid, "edge_lcb": "-0.000"},
            {**valid, "edge_lcb": "0.1"},
            {**valid, "edge_lcb": " 0.100"},
            {**valid, "edge_lcb": "1.001"},
            {**valid, "edge_lcb": "", "n_calls": "1"},
            {**valid, "edge_lcb": "0.100", "n_calls": "0"},
            {**valid, "edge_lcb": "", "n_calls": "0"},
            {**valid, "status": "probation", "edge_lcb": "", "n_calls": "0"},
            {**valid, "n_calls": "02"},
            {**valid, "n_calls": "-1"},
            {**valid, "leaker_id": " x-a"},
            {**valid, "leaker_id": "x-A"},
            {**valid, "leaker_id": "other-a"},
            {**valid, "leaker_id": "x-b"},
            {**valid, "leaker_id": "x-\x00a"},
            {**valid, "call_class": ""},
            {key: value for key, value in valid.items() if key != "notes"},
            {**valid, "unexpected": "value"},
        ]
        for row in malformed:
            with self.subTest(row=row):
                with self.assertRaises(resolve.RosterProjectionError):
                    resolve.rank_roster([row])

    def test_persisted_header_and_row_shape_must_be_exact(self):
        valid_line = ("x-a\tx\ta\td\ttiming\tverified\t10\t0\t\t\t\t0.100\t0\t0\t\t\n")
        malformed_payloads = [
            HEADER.replace("\tnotes\n", "\n") + valid_line.rsplit("\t", 1)[0] + "\n",
            HEADER.rstrip("\n") + "\textra\n" + valid_line.rstrip("\n") + "\tx\n",
            HEADER + valid_line.rstrip("\n").rsplit("\t", 1)[0] + "\n",
            HEADER + valid_line.rstrip("\n") + "\textra\n",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leakers.tsv"
            for payload in malformed_payloads:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaises(resolve.RosterProjectionError):
                        resolve.validate_persisted_roster(path, lib.read_tsv(path))

    def test_lowercase_id_can_bind_original_case_handle(self):
        row = self.row("x-source")
        row["handle"] = "Source"
        self.assertEqual([row], resolve.rank_roster([row]))

    def test_scorecard_producer_never_emits_signed_zero_edge(self):
        row = self.row(
            "x-a", status="candidate", edge_lcb="0.100", n_calls="2")
        row.update({"hits": 1, "avg_price_at_call": "0.106"})

        lib.update_leaker_stats(row, False, 0.106, {
            "verify_min_calls": 10, "verify_min_edge": 0.05,
            "verify_z": 1.2816,
        })

        self.assertEqual("0.000", row["edge_lcb"])
        self.assertEqual([row], resolve.rank_roster([row]))

    def test_call_class_requires_canonical_lowercase_hyphenated_tokens(self):
        invalid = [
            "Timing", "TIMING", "timing_alias", "release/timing", "tímíng",
            "-timing", "timing-", "timing--release", "",
        ]
        for call_class in invalid:
            with self.subTest(call_class=call_class):
                with self.assertRaises(resolve.RosterProjectionError):
                    resolve.rank_roster([
                        self.row("x-a", call_class=call_class),
                    ])

        valid = [
            "-", "release-timing", "model-existence", "feature-sighting",
            "benchmark-position", "org-event", "unclassified", "timing",
        ]
        for call_class in valid:
            with self.subTest(call_class=call_class):
                row = self.row("x-a", call_class=call_class)
                self.assertEqual([row], resolve.rank_roster([row]))

    def test_persisted_call_class_must_belong_to_domain_taxonomy_when_available(self):
        row = self.row("x-a", call_class="timing")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leakers.tsv"
            path.write_text(HEADER, encoding="utf-8")
            lib.write_tsv(path, [row])

            with self.assertRaises(resolve.RosterProjectionError):
                resolve.validate_persisted_roster(
                    path, lib.read_tsv(path),
                    allowed_call_classes=["release-timing", "unclassified"],
                )

            resolve.validate_persisted_roster(
                path, lib.read_tsv(path), allowed_call_classes=["timing"])

    def test_domain_taxonomy_is_strict_frozen_config(self):
        self.assertEqual(
            ["release-timing", "model-existence", "unclassified"],
            resolve.validate_domain_taxonomy({
                "call_classes": {
                    "d": ["release-timing", "model-existence", "unclassified"],
                },
            }, "d"),
        )

        malformed = [
            {},
            {"call_classes": []},
            {"call_classes": {}},
            {"call_classes": {"d": []}},
            {"call_classes": {"d": "timing"}},
            {"call_classes": {"d": ("timing",)}},
            {"call_classes": {"d": ["timing", "timing"]}},
            {"call_classes": {"d": ["Timing"]}},
            {"call_classes": {"d": ["timing_alias"]}},
            {"call_classes": {"d": ["release/timing"]}},
            {"call_classes": {"d": ["tímíng"]}},
            {"call_classes": {"d": ["-"]}},
            {"call_classes": {"d": [1]}},
        ]
        for cfg in malformed:
            with self.subTest(cfg=cfg):
                with self.assertRaises(resolve.RosterProjectionError):
                    resolve.validate_domain_taxonomy(cfg, "d")

    def test_final_rank_rejects_grammar_valid_class_outside_taxonomy(self):
        with self.assertRaises(resolve.RosterProjectionError):
            resolve.rank_roster(
                [self.row("x-a", call_class="rogue-class")],
                allowed_call_classes=["timing"],
            )


if __name__ == "__main__":
    unittest.main()
