from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from unittest import mock

DELPHI = Path(__file__).resolve().parents[1]
SCRIPTS = DELPHI / "scripts"
sys.path.insert(0, str(SCRIPTS))

import judge  # noqa: E402
import lib  # noqa: E402
import llm  # noqa: E402


VALID_RESPONSE = {
    "p_yes": 0.80,
    "confidence": 0.90,
    "rationale": "The leak is specific. The resolution wording matches it.",
    "lessons": [],
}
JUDGE_MODEL = "gpt-5.6-luna"


class JudgeOutputContractTests(unittest.TestCase):
    def test_exact_duplicate_p_yes_is_rejected(self):
        raw = (
            '{"p_yes":0.10,"confidence":0.8,'
            '"rationale":"Specific evidence.","lessons":[],"p_yes":0.91}'
        )
        with self.assertRaises(judge.JudgeOutputError):
            judge.parse_judge_output(raw)

    def test_nested_and_escaped_equivalent_duplicates_are_rejected(self):
        cases = (
            '{"p_yes":0.8,"confidence":0.8,"rationale":"Specific.",'
            '"lessons":[{"pattern":"one","pattern":"two"}]}',
            '{"p_yes":0.8,"confidence":0.8,"rationale":"Specific.",'
            '"lessons":[],"\\u0070_yes":0.9}',
            '{"p_yes":0.8,"confidence":0.8,"rationale":"Specific.",'
            '"lessons":[{"x":"one","\\u0078":"two"}]}',
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_nonstandard_and_nonfinite_numbers_are_rejected(self):
        for token in (
                "NaN", "Infinity", "-Infinity", "1e999", "1" + "0" * 5_000):
            raw = (
                f'{{"p_yes":{token},"confidence":0.8,'
                '"rationale":"Specific.","lessons":[]}'
            )
            with self.subTest(token=token), self.assertRaises(
                    judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_trailing_prose_multiple_documents_and_wrong_top_level_fail(self):
        valid = json.dumps(VALID_RESPONSE)
        cases = (
            valid + " trailing prose",
            valid + "\n" + valid,
            "[" + valid + "]",
            '"' + valid.replace('"', '\\"') + '"',
            "",
            "not json",
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_only_one_exact_json_fence_is_supported(self):
        valid = json.dumps(VALID_RESPONSE, separators=(",", ":"))
        self.assertEqual(
            judge.parse_judge_output(f"```json\n{valid}\n```"),
            VALID_RESPONSE,
        )
        for raw in (
            f"prose\n```json\n{valid}\n```",
            f"```JSON\n{valid}\n```",
            f"```json {valid}```",
            f"```json\n```json\n{valid}\n```\n```",
            f"```json\n{valid}\n```\nprose",
            f" ```json\n{valid}\n```",
            f"```json\n{valid}\n```\n",
            f"\t```json\n{valid}\n```",
        ):
            with self.subTest(raw=raw), self.assertRaises(judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_plain_json_accepts_only_decoder_defined_outer_whitespace(self):
        valid = json.dumps(VALID_RESPONSE, separators=(",", ":"))
        self.assertEqual(
            judge.parse_judge_output(f" \t\r\n{valid}\n\t "),
            VALID_RESPONSE,
        )
        for wrapper in ("\v", "\f", "\u00a0"):
            with self.subTest(wrapper=wrapper), self.assertRaises(
                    judge.JudgeOutputError):
                judge.parse_judge_output(f"{wrapper}{valid}{wrapper}")

    def test_raw_response_bound_precedes_any_parse_or_trimming(self):
        valid = json.dumps(VALID_RESPONSE, separators=(",", ":"))
        limit = getattr(judge, "MAX_JUDGE_RESPONSE_CHARS", 8_192)
        for raw in (valid + " " * (limit + 1), " " * 1_000_000):
            with self.subTest(size=len(raw)), self.assertRaises(
                    judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_numeric_tokens_are_decimal_lossless_and_bounded(self):
        invalid_tokens = (
            "1e-1", "1E-1", "1e-9999", "-1e-9999", "-0.0", "0",
            "0." + "8" + "0" * 40,
        )
        for token in invalid_tokens:
            raw = (
                f'{{"p_yes":{token},"confidence":0.90,'
                '"rationale":"Specific.","lessons":[]}'
            )
            with self.subTest(token=token), self.assertRaises(
                    judge.JudgeOutputError):
                judge.parse_judge_output(raw)

    def test_numeric_scale_includes_trailing_zeroes(self):
        raw_cases = (
            ('"p_yes":0.8000', '"confidence":0.90'),
            ('"p_yes":0.80', '"confidence":0.900'),
        )
        for probability, confidence in raw_cases:
            raw = (
                f'{{{probability},{confidence},'
                '"rationale":"Specific.","lessons":[]}'
            )
            with self.subTest(raw=raw), self.assertRaises(
                    judge.JudgeOutputError):
                judge.parse_judge_output(raw)

        direct_cases = (
            {**VALID_RESPONSE, "p_yes": Decimal("0.8000")},
            {**VALID_RESPONSE, "confidence": Decimal("0.900")},
        )
        for value in direct_cases:
            with self.subTest(value=value), self.assertRaises(
                    judge.JudgeOutputError):
                judge.validate_judge_response(value)

    def test_exact_schema_missing_extra_wrong_bool_and_ranges_fail(self):
        cases = {
            "missing": {k: v for k, v in VALID_RESPONSE.items()
                        if k != "confidence"},
            "extra": {**VALID_RESPONSE, "edge": 0.4},
            "model-side": {**VALID_RESPONSE, "side": "YES"},
            "model-reasoning": {**VALID_RESPONSE, "reasoning": "ignored"},
            "bool-p": {**VALID_RESPONSE, "p_yes": True},
            "bool-confidence": {**VALID_RESPONSE, "confidence": False},
            "string-p": {**VALID_RESPONSE, "p_yes": "0.8"},
            "null-confidence": {**VALID_RESPONSE, "confidence": None},
            "zero-p": {**VALID_RESPONSE, "p_yes": 0.0},
            "one-p": {**VALID_RESPONSE, "p_yes": 1.0},
            "negative-confidence": {**VALID_RESPONSE, "confidence": -0.01},
            "high-confidence": {**VALID_RESPONSE, "confidence": 1.01},
            "nan-p": {**VALID_RESPONSE, "p_yes": math.nan},
            "inf-confidence": {**VALID_RESPONSE, "confidence": math.inf},
            "negative-zero-p": {**VALID_RESPONSE, "p_yes": -0.0},
            "negative-zero-confidence": {**VALID_RESPONSE, "confidence": -0.0},
            "integer-confidence": {**VALID_RESPONSE, "confidence": 1},
            "lossy-p-precision": {**VALID_RESPONSE, "p_yes": 0.1234},
            "lossy-confidence-precision": {**VALID_RESPONSE,
                                           "confidence": 0.901},
            "wrong-rationale": {**VALID_RESPONSE, "rationale": ["reason"]},
            "empty-rationale": {**VALID_RESPONSE, "rationale": "  "},
            "control-rationale": {**VALID_RESPONSE, "rationale": "bad\x00text"},
            "format-rationale": {**VALID_RESPONSE,
                                 "rationale": "bad\u202etext"},
            "zero-width-rationale": {**VALID_RESPONSE,
                                     "rationale": "bad\u200btext"},
            "surrogate-rationale": {**VALID_RESPONSE,
                                    "rationale": "bad\ud800text"},
            "wrong-lessons": {**VALID_RESPONSE, "lessons": "none"},
            "too-many-lessons": {**VALID_RESPONSE,
                                 "lessons": ["a", "b", "c", "d"]},
            "wrong-lesson": {**VALID_RESPONSE, "lessons": [1]},
            "empty-lesson": {**VALID_RESPONSE, "lessons": [" "]},
            "control-lesson": {**VALID_RESPONSE, "lessons": ["bad\x1ftext"]},
            "format-lesson": {**VALID_RESPONSE, "lessons": ["bad\u202etext"]},
            "surrogate-lesson": {**VALID_RESPONSE,
                                 "lessons": ["bad\ud800text"]},
        }
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaises(
                    judge.JudgeOutputError):
                judge.validate_judge_response(value)

    def test_valid_exact_schema_is_normalized_without_derived_fields(self):
        parsed = judge.validate_judge_response(VALID_RESPONSE)
        self.assertEqual(parsed, VALID_RESPONSE)
        self.assertEqual(set(parsed), {"p_yes", "confidence", "rationale", "lessons"})


class JudgeStrictRetryContractTests(unittest.TestCase):
    def test_invalid_codex_output_retries_once_then_strictly_decodes(self):
        valid = json.dumps(VALID_RESPONSE, separators=(",", ":"))
        cfg = {"llm": {"max_json_retries": 1}}
        with mock.patch.object(
                llm, "call", side_effect=["not json", valid]) as model:
            parsed = llm.call_json(
                "judge", "prompt", cfg, decoder=judge.parse_judge_output)

        self.assertEqual(parsed, VALID_RESPONSE)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(model.call_args_list[0].args[1], "prompt")
        self.assertTrue(model.call_args_list[1].args[1].endswith(
            "REPLY WITH THE JSON OBJECT ONLY. NO PROSE."))

    def test_two_missing_outputs_raise_without_semantic_fallback(self):
        cfg = {"llm": {"max_json_retries": 1}}
        with (mock.patch.object(llm, "call", side_effect=["", ""]),
              self.assertRaises(judge.JudgeOutputError)):
            llm.call_json(
                "judge", "prompt", cfg, decoder=judge.parse_judge_output)


class JudgeRetryStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".f12-", dir=DELPHI)
        self.addCleanup(self.tmp.cleanup)
        self.ddir = Path(self.tmp.name)
        production = DELPHI / "domains" / "ai-releases"
        for name in ("signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv"):
            header = (production / name).read_text(encoding="utf-8").splitlines()[0]
            (self.ddir / name).write_text(header + "\n", encoding="utf-8")
        (self.ddir / "judge-decisions.tsv").write_text(
            judge.JOURNAL_HEADER, encoding="utf-8")
        self.cfg = {
            "bankroll_usd": 1000.0,
            "roles": {"judge": {
                "backend": "codex-cli",
                "model": JUDGE_MODEL,
                "output_schema": "schemas/judge-output.json",
            }},
            "thresholds": {
                "min_liquidity_usd": 1000.0,
                "slippage": 0.01,
                "min_edge": 0.10,
                "judge_min_conf": 0.60,
                "kelly_fraction": 0.25,
                "max_stake_frac": 0.05,
            },
            "codex_cmd": json.loads(
                (DELPHI / "config.json").read_text(encoding="utf-8"))[
                    "codex_cmd"],
            "llm": {"max_json_retries": 0},
        }
        self.add_signal("sig-1", "market-1", note="keep this unrelated note")

    def add_signal(self, signal_id: str, market_id: str, note: str = "") -> None:
        lib.append_tsv(self.ddir / "signals.tsv", {
            "signal_id": signal_id, "ts_detected": "2026-07-14T08:00:00Z",
            "domain": "test", "leaker_id": "x-source", "platform": "x",
            "post_url": f"https://example.test/post/{signal_id}",
            "post_ts": "2026-07-14T07:00:00Z", "source_post_id": signal_id,
            "claim": "Release today", "call_class": "release-timing",
            "hedged": "false", "market_id": market_id,
            "event_id": f"event-{market_id}",
            "market_question": f"Will {market_id} release today?",
            "token_id": f"yes-{market_id}", "side": "YES",
            "price_at_signal": "0.350", "liquidity_usd": "2500",
            "status": "pending_judge", "stat_counted": "false", "note": note,
        })
        if not lib.read_tsv(self.ddir / "leakers.tsv"):
            lib.append_tsv(self.ddir / "leakers.tsv", {
                "leaker_id": "x-source", "platform": "x", "handle": "source",
                "domain": "test", "call_class": "release-timing",
                "status": "verified", "n_calls": "20", "hits": "16",
                "hit_rate": "0.800", "avg_price_at_call": "0.400",
                "est_edge": "0.400", "edge_lcb": "0.200",
                "n_unpriced": "0", "n_live": "0",
            })

    @staticmethod
    def market(market_id: str) -> dict:
        return {
            "id": market_id, "question": f"Will {market_id} release today?",
            "description": "Resolves YES on a release today.",
            "end_date": "2026-07-15T00:00:00Z", "closed": False,
            "liquidity": 2500.0, "yes_token": f"yes-{market_id}",
            "no_token": f"no-{market_id}",
        }

    def run_judge(self, model=None, *,
                  codex_run=None,
                  note_write_error: Exception | None = None) -> None:
        patches = [
            mock.patch.object(sys, "argv", ["judge.py", "--domain", "test"]),
            mock.patch.object(judge, "domain_dir", return_value=self.ddir),
            mock.patch.object(judge, "load_config", return_value=self.cfg),
            mock.patch.object(judge, "agent_context", return_value=""),
            mock.patch.object(judge.pm, "get_market",
                              side_effect=lambda market_id: self.market(market_id)),
            mock.patch.object(judge, "executable_ask", return_value=0.40),
            mock.patch.object(judge.cognee, "search", return_value=[]),
            mock.patch.object(judge.cognee, "add"),
            mock.patch.object(judge, "append_lessons"),
            mock.patch.object(judge, "write_note"),
            mock.patch.object(judge, "log_result"),
            mock.patch.object(judge, "now_iso",
                              return_value="2026-07-14T09:00:00Z"),
        ]
        if codex_run is None:
            patches.append(mock.patch.object(llm, "call", side_effect=model))
        else:
            output_dir = self.ddir / "tmp"
            output_dir.mkdir(exist_ok=True)
            patches.extend((
                mock.patch.object(llm, "tmp_dir", return_value=output_dir),
                mock.patch.object(llm.subprocess, "run", side_effect=codex_run),
            ))
        if note_write_error is not None:
            patches.append(mock.patch.object(
                lib.os, "replace", side_effect=note_write_error))
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            judge.main()

    def rows(self, name: str) -> list[dict]:
        return lib.read_tsv(self.ddir / name)

    def assert_no_decision_side_effects(self):
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.rows("judge-decisions.tsv"), [])
        signal = self.rows("signals.tsv")[0]
        self.assertEqual(signal["status"], "pending_judge")
        self.assertEqual(signal["judge_p"], "")
        self.assertEqual(signal["judge_conf"], "")
        self.assertEqual(signal["edge"], "")

    def test_duplicate_output_stays_pending_without_journal_or_position(self):
        duplicate = (
            '{"p_yes":0.10,"confidence":0.9,"rationale":"Bad duplicate.",'
            '"lessons":[],"p_yes":0.91}'
        )
        self.run_judge(mock.Mock(return_value=duplicate))

        self.assert_no_decision_side_effects()
        note = self.rows("signals.tsv")[0]["note"]
        self.assertIn("keep this unrelated note", note)
        self.assertEqual(note.count(judge.JUDGE_RETRY_NOTE_PREFIX), 1)
        self.assertNotIn("0.91", note)

    def test_each_invalid_output_class_is_nonterminal_and_nontransactional(self):
        valid = json.dumps(VALID_RESPONSE)
        fence = f"```json\n{valid}\n```"
        limit = getattr(judge, "MAX_JUDGE_RESPONSE_CHARS", 8_192)
        invalid = {
            "empty": "",
            "missing": json.dumps({
                "p_yes": 0.8, "confidence": 0.9,
                "rationale": "Missing lessons.",
            }),
            "extra-derived": json.dumps({**VALID_RESPONSE, "edge": 0.39}),
            "bool-number": json.dumps({**VALID_RESPONSE, "p_yes": True}),
            "wrong-type": json.dumps({**VALID_RESPONSE, "confidence": "0.9"}),
            "out-of-range": json.dumps({**VALID_RESPONSE, "p_yes": 87}),
            "nonfinite": json.dumps({**VALID_RESPONSE, "confidence": math.nan}),
            "wrong-rationale": json.dumps({**VALID_RESPONSE, "rationale": []}),
            "wrong-lessons": json.dumps({**VALID_RESPONSE, "lessons": [1]}),
            "trailing": json.dumps(VALID_RESPONSE) + " trailing",
            "multiple": json.dumps(VALID_RESPONSE) * 2,
            "vertical-tab-wrapped": f"\v{valid}\v",
            "form-feed-wrapped": f"\f{valid}\f",
            "nbsp-wrapped": f"\u00a0{valid}\u00a0",
            "padded-fence": " " + fence,
            "oversized-padded": valid + " " * (limit + 1),
            "million-spaces": " " * 1_000_000,
            "positive-underflow": valid.replace("0.8", "1e-9999", 1),
            "negative-underflow": valid.replace("0.8", "-1e-9999", 1),
            "negative-zero-confidence": valid.replace("0.9", "-0.0", 1),
            "lossy-p-precision": valid.replace("0.8", "0.1234", 1),
            "lossy-conf-precision": valid.replace("0.9", "0.901", 1),
        }
        files = (
            "signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv",
            "judge-decisions.tsv",
        )
        original = {name: (self.ddir / name).read_bytes() for name in files}
        for name, raw in invalid.items():
            with self.subTest(name=name):
                for filename, content in original.items():
                    (self.ddir / filename).write_bytes(content)
                self.run_judge(mock.Mock(return_value=raw))
                self.assert_no_decision_side_effects()
                signal = self.rows("signals.tsv")[0]
                self.assertEqual(
                    signal["note"].count(judge.JUDGE_RETRY_NOTE_PREFIX), 1)

    def test_model_exception_is_bounded_and_next_run_can_succeed(self):
        dangerous = RuntimeError("raw output\x00 secret\n" + "x" * 10_000)
        self.run_judge(mock.Mock(side_effect=dangerous))
        self.assert_no_decision_side_effects()
        failed_note = self.rows("signals.tsv")[0]["note"]
        self.assertIn("keep this unrelated note", failed_note)
        self.assertEqual(failed_note.count(judge.JUDGE_RETRY_NOTE_PREFIX), 1)
        self.assertNotIn("secret", failed_note)
        self.assertLess(len(failed_note), 250)

        self.run_judge(mock.Mock(return_value=json.dumps(VALID_RESPONSE)))
        signal = self.rows("signals.tsv")[0]
        self.assertEqual(signal["status"], "bet")
        expected_note = (
            "keep this unrelated note | "
            "The leak is specific. The resolution wording matches it."
        )
        self.assertEqual(signal["note"], expected_note)
        self.assertNotIn(judge.JUDGE_RETRY_NOTE_PREFIX, signal["note"])
        self.assertNotIn("secret", signal["note"])
        self.assertEqual(len(self.rows("positions.tsv")), 1)
        self.assertEqual(self.rows("positions.tsv")[0]["note"], expected_note)
        self.assertTrue(all(
            row["note"] == expected_note
            for row in self.rows("judge-decisions.tsv")))
        self.assertEqual(
            [row["state"] for row in self.rows("judge-decisions.tsv")],
            ["prepared", "final"],
        )

    def test_nonzero_codex_with_valid_file_retries_then_success_commits_once(self):
        self.cfg["llm"]["max_json_retries"] = 1
        valid = json.dumps(VALID_RESPONSE, separators=(",", ":"))
        attempts = 0

        def codex_run(cmd, **_kwargs):
            nonlocal attempts
            attempts += 1
            outfile = Path(cmd[cmd.index("--output-last-message") + 1])
            outfile.write_text(valid, encoding="utf-8")
            return llm.subprocess.CompletedProcess(
                cmd, 9 if attempts == 1 else 0,
                b"raw stdout must not be semantic", b"private diagnostic")

        self.run_judge(codex_run=codex_run)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.rows("signals.tsv")[0]["status"], "bet")
        self.assertEqual(len(self.rows("positions.tsv")), 1)
        self.assertEqual(
            [row["state"] for row in self.rows("judge-decisions.tsv")],
            ["prepared", "final"],
        )
        self.assertEqual(list((self.ddir / "tmp").iterdir()), [])

    def test_missing_codex_file_with_valid_stdout_exhausts_pending_safely(self):
        self.cfg["llm"]["max_json_retries"] = 1
        stdout = json.dumps(VALID_RESPONSE).encode("utf-8")
        attempts = 0

        def codex_run(cmd, **_kwargs):
            nonlocal attempts
            attempts += 1
            return llm.subprocess.CompletedProcess(
                cmd, 0, stdout, b"private diagnostic secret")

        self.run_judge(codex_run=codex_run)

        self.assertEqual(attempts, 2)
        self.assert_no_decision_side_effects()
        signal = self.rows("signals.tsv")[0]
        self.assertEqual(
            signal["note"].count(judge.JUDGE_RETRY_NOTE_PREFIX), 1)
        self.assertNotIn("private", signal["note"])
        self.assertNotIn("diagnostic", signal["note"])
        self.assertEqual(list((self.ddir / "tmp").iterdir()), [])

    def test_repeated_failures_replace_one_managed_marker(self):
        for _ in range(3):
            self.run_judge(mock.Mock(return_value="not json"))
        self.assert_no_decision_side_effects()
        note = self.rows("signals.tsv")[0]["note"]
        self.assertIn("keep this unrelated note", note)
        self.assertEqual(note.count(judge.JUDGE_RETRY_NOTE_PREFIX), 1)
        self.assertLess(len(note), 250)

    def test_bad_signal_does_not_block_unrelated_valid_signal(self):
        self.add_signal("sig-2", "market-2")
        model = mock.Mock(side_effect=[
            RuntimeError("first signal failed"), json.dumps(VALID_RESPONSE),
        ])

        self.run_judge(model)

        signals = {row["signal_id"]: row for row in self.rows("signals.tsv")}
        self.assertEqual(signals["sig-1"]["status"], "pending_judge")
        self.assertEqual(signals["sig-2"]["status"], "bet")
        self.assertEqual([row["signal_id"] for row in self.rows("positions.tsv")],
                         ["sig-2"])
        self.assertEqual(
            {row["signal_id"] for row in self.rows("judge-decisions.tsv")},
            {"sig-2"},
        )

    def test_positive_and_negative_underflow_do_not_block_valid_signal(self):
        self.add_signal("sig-2", "market-2")
        self.add_signal("sig-3", "market-3")
        invalid = json.dumps(VALID_RESPONSE)
        model = mock.Mock(side_effect=[
            invalid.replace("0.8", "1e-9999", 1),
            invalid.replace("0.8", "-1e-9999", 1),
            json.dumps(VALID_RESPONSE),
        ])

        self.run_judge(model)

        signals = {row["signal_id"]: row for row in self.rows("signals.tsv")}
        for signal_id in ("sig-1", "sig-2"):
            self.assertEqual(signals[signal_id]["status"], "pending_judge")
            self.assertEqual(
                signals[signal_id]["note"].count(
                    judge.JUDGE_RETRY_NOTE_PREFIX), 1)
        self.assertEqual(signals["sig-3"]["status"], "bet")
        self.assertEqual([row["signal_id"] for row in self.rows("positions.tsv")],
                         ["sig-3"])
        self.assertEqual(
            {row["signal_id"] for row in self.rows("judge-decisions.tsv")},
            {"sig-3"},
        )

    def test_excess_trailing_zero_scale_does_not_block_valid_signal(self):
        self.add_signal("sig-2", "market-2")
        valid = json.dumps(VALID_RESPONSE)
        invalid = (
            valid.replace("0.8", "0.8000", 1),
            valid.replace("0.9", "0.900", 1),
        )
        files = (
            "signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv",
            "judge-decisions.tsv",
        )
        original = {name: (self.ddir / name).read_bytes() for name in files}
        for raw in invalid:
            with self.subTest(raw=raw):
                for filename, content in original.items():
                    (self.ddir / filename).write_bytes(content)
                self.run_judge(mock.Mock(side_effect=[raw, valid]))
                signals = {
                    row["signal_id"]: row for row in self.rows("signals.tsv")}
                self.assertEqual(signals["sig-1"]["status"], "pending_judge")
                self.assertEqual(
                    signals["sig-1"]["note"].count(
                        judge.JUDGE_RETRY_NOTE_PREFIX), 1)
                self.assertEqual(signals["sig-2"]["status"], "bet")
                self.assertEqual(
                    [row["signal_id"] for row in self.rows("positions.tsv")],
                    ["sig-2"],
                )
                self.assertEqual(
                    {row["signal_id"]
                     for row in self.rows("judge-decisions.tsv")},
                    {"sig-2"},
                )

    def test_unsafe_unicode_does_not_block_later_valid_signal(self):
        self.add_signal("sig-2", "market-2")
        invalid_values = (
            {**VALID_RESPONSE, "rationale": "unsafe\u202etext"},
            {**VALID_RESPONSE, "rationale": "unsafe\u200btext"},
            {**VALID_RESPONSE, "lessons": ["unsafe\ud800text"]},
        )
        files = (
            "signals.tsv", "leakers.tsv", "positions.tsv", "resolved.tsv",
            "judge-decisions.tsv",
        )
        original = {name: (self.ddir / name).read_bytes() for name in files}
        for value in invalid_values:
            with self.subTest(value=value):
                for filename, content in original.items():
                    (self.ddir / filename).write_bytes(content)
                model = mock.Mock(side_effect=[
                    json.dumps(value), json.dumps(VALID_RESPONSE),
                ])
                self.run_judge(model)
                signals = {
                    row["signal_id"]: row for row in self.rows("signals.tsv")}
                self.assertEqual(signals["sig-1"]["status"], "pending_judge")
                self.assertEqual(signals["sig-2"]["status"], "bet")
                self.assertEqual(
                    [row["signal_id"] for row in self.rows("positions.tsv")],
                    ["sig-2"],
                )

    def test_atomic_note_write_failure_leaves_all_state_unchanged(self):
        before = (self.ddir / "signals.tsv").read_bytes()
        with self.assertRaises(OSError):
            self.run_judge(
                mock.Mock(side_effect=RuntimeError("model failed")),
                note_write_error=OSError("replace failed"),
            )

        self.assertEqual((self.ddir / "signals.tsv").read_bytes(), before)
        self.assertEqual(self.rows("positions.tsv"), [])
        self.assertEqual(self.rows("judge-decisions.tsv"), [])


if __name__ == "__main__":
    unittest.main()
