import importlib
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
schedule_gate = importlib.import_module("schedule_gate")
lib = importlib.import_module("lib")


class ScheduleGateTests(unittest.TestCase):
    def test_through_july_eighteenth_and_exact_boundary(self):
        cutoff = schedule_gate.parse_cutoff("2026-07-19T00:00:00Z")
        self.assertEqual(
            "kickstart",
            schedule_gate.schedule_mode(
                cutoff, datetime(2026, 7, 18, 23, 59, 59, tzinfo=timezone.utc)),
        )
        self.assertEqual(
            "normal",
            schedule_gate.schedule_mode(
                cutoff, datetime(2026, 7, 19, 0, 0, 0, tzinfo=timezone.utc)),
        )

    def test_cutoff_is_strict_canonical_utc(self):
        invalid = (
            "2026-07-19T00:00:00+00:00",
            "2026-7-19T00:00:00Z",
            " 2026-07-19T00:00:00Z",
            "2026-07-19T00:00:00.000Z",
            "2026-02-30T00:00:00Z",
            "２０２６-07-19T00:00:00Z",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule_gate.parse_cutoff(value)

    def test_config_failure_is_closed_for_both_modes(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "config.json"
            for payload in (
                {},
                {"kickstart": {}},
                {"kickstart": {"active_until": None}},
                {"kickstart": {"active_until": "bad"}},
            ):
                path.write_text(json.dumps(payload), encoding="utf-8")
                for requested in ("kickstart", "normal"):
                    self.assertEqual(
                        2,
                        schedule_gate.cli([requested], config_path=path),
                    )

    def test_repository_config_is_the_only_gate_source(self):
        config = json.loads(
            (SCRIPTS.parent / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "2026-07-19T00:00:00Z", config["kickstart"]["active_until"]
        )

    def test_duplicate_keys_at_any_depth_fail_closed(self):
        duplicate_documents = (
            '{"kickstart":{"active_until":"2026-07-19T00:00:00Z",'
            '"active_until":"2026-07-20T00:00:00Z"}}',
            '{"kickstart":{"active_until":"2026-07-19T00:00:00Z"},'
            '"kickstart":{"active_until":"2026-07-20T00:00:00Z"}}',
            '{"kickstart":{"active_until":"2026-07-19T00:00:00Z"},'
            '"unrelated":{"nested":1,"nested":2}}',
            '{"kickstart":{"active_until":"2026-07-19T00:00:00Z"},'
            '"unrelated":NaN}',
        )
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "config.json"
            for document in duplicate_documents:
                path.write_text(document, encoding="utf-8")
                for requested in ("kickstart", "normal"):
                    self.assertEqual(
                        2, schedule_gate.cli([requested], config_path=path)
                    )

    def test_orchestrator_patch_uses_the_same_cutoff_validator(self):
        valid, _ = lib.validate_config_patch(
            {"kickstart.active_until": "2026-07-19T00:00:00Z"}
        )
        self.assertTrue(valid)
        for value in (
            "2026-07-19T00:00:00+00:00",
            "2026-7-19T00:00:00Z",
            "2026-02-30T00:00:00Z",
            " bad ",
            None,
        ):
            with self.subTest(value=value):
                valid, _ = lib.validate_config_patch(
                    {"kickstart.active_until": value}
                )
                self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
