from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import heartbeat  # noqa: E402
import lib  # noqa: E402


SIGNAL_HEADER = ("signal_id\tts_detected\tdomain\tleaker_id\tplatform\tpost_url\tpost_ts\t"
                 "source_post_id\t"
                 "claim\tcall_class\thedged\tmarket_id\tevent_id\tmarket_question\ttoken_id\t"
                 "side\tprice_at_signal\tliquidity_usd\tstatus\tjudge_p\tjudge_conf\tedge\t"
                 "resolved_outcome\tstat_counted\tnote\n")
LEAKER_HEADER = ("leaker_id\tplatform\thandle\tdomain\tcall_class\tstatus\tn_calls\thits\t"
                 "hit_rate\tavg_price_at_call\test_edge\tedge_lcb\tn_unpriced\tn_live\t"
                 "last_seen_ts\tnotes\n")


def market(market_id: str) -> dict:
    return {
        "id": market_id,
        "event_id": f"event-{market_id}",
        "question": f"Will {market_id} happen?",
        "description": f"Resolution criteria for {market_id}",
        "yes_token": f"yes-{market_id}",
        "yes_price": 0.4,
        "liquidity": 5000,
    }


def mapping_input(claim_id: str, *markets: dict) -> dict:
    return {"claim_id": claim_id, "claim": f"claim {claim_id}",
            "markets": list(markets)}


def mapping_record(claim_id: str, *, match: bool,
                   market_id: str = "", implied_side: str = "") -> dict:
    return {"claim_id": claim_id, "market_id": market_id,
            "match": match, "implied_side": implied_side}


class MappingValidationTests(unittest.TestCase):
    def test_accepts_zero_one_and_multiple_complete_records_in_any_order(self):
        self.assertEqual({}, heartbeat.validated_mappings({"mappings": []}, []))

        m0, m1 = market("m0"), market("m1")
        one = heartbeat.validated_mappings(
            {"mappings": [mapping_record(
                "claim-0", match=True, market_id="m0", implied_side="YES")]},
            [mapping_input("claim-0", m0)],
        )
        self.assertEqual((m0, "YES"), one["claim-0"])

        multiple = heartbeat.validated_mappings(
            {"mappings": [
                mapping_record("claim-1", match=False),
                mapping_record("claim-0", match=True,
                               market_id="m0", implied_side="NO"),
            ]},
            [mapping_input("claim-0", m0), mapping_input("claim-1", m1)],
        )
        self.assertEqual({"claim-0", "claim-1"}, set(multiple))
        self.assertEqual((m0, "NO"), multiple["claim-0"])
        self.assertEqual((None, ""), multiple["claim-1"])

    def test_rejects_missing_unknown_extra_duplicate_and_ambiguous_claim_ids(self):
        m0, m1 = market("m0"), market("m1")
        inputs = [mapping_input("claim-0", m0), mapping_input("claim-1", m1)]
        valid0 = mapping_record(
            "claim-0", match=True, market_id="m0", implied_side="YES")
        valid1 = mapping_record("claim-1", match=False)
        invalid_outputs = {
            "missing": {"mappings": [valid0]},
            "unknown": {"mappings": [valid0, mapping_record("claim-x", match=False)]},
            "extra": {"mappings": [valid0, valid1,
                                      mapping_record("claim-x", match=False)]},
            "duplicate": {"mappings": [valid0, valid0]},
        }
        for label, response in invalid_outputs.items():
            with self.subTest(label=label):
                self.assertIsNone(heartbeat.validated_mappings(response, inputs))

        ambiguous_inputs = [mapping_input("claim-0", m0),
                            mapping_input("claim-0", m1)]
        self.assertIsNone(heartbeat.validated_mappings(
            {"mappings": [valid0, valid0]}, ambiguous_inputs))
        self.assertIsNone(heartbeat.validated_mappings(
            {"mappings": []}, [mapping_input("", m0)]))
        self.assertIsNone(heartbeat.validated_mappings(
            {"mappings": []}, [mapping_input(0, m0)]))

    def test_rejects_malformed_schema_types_and_fields(self):
        m0 = market("m0")
        inputs = [mapping_input("claim-0", m0)]
        invalid = [
            None,
            {},
            {"mappings": [], "extra": True},
            {"mappings": "not-a-list"},
            {"mappings": ["not-an-object"]},
            {"mappings": [{"claim_id": "claim-0"}]},
            {"mappings": [{**mapping_record("claim-0", match=False), "extra": True}]},
            {"mappings": [mapping_record(0, match=False)]},
            {"mappings": [mapping_record("claim-0", match=1)]},
            {"mappings": [mapping_record("claim-0", match=True,
                                          market_id=0, implied_side="YES")]},
            {"mappings": [mapping_record("claim-0", match=True,
                                          market_id="m0", implied_side=None)]},
            {"mappings": [mapping_record("claim-0", match=True,
                                          market_id="unknown", implied_side="YES")]},
            {"mappings": [mapping_record("claim-0", match=True,
                                          market_id="m0", implied_side="MAYBE")]},
            {"mappings": [mapping_record("claim-0", match=False,
                                          market_id="m0")]},
            {"mappings": [mapping_record("claim-0", match=False,
                                          implied_side="NO")]},
        ]
        for response in invalid:
            with self.subTest(response=response):
                self.assertIsNone(heartbeat.validated_mappings(response, inputs))

    def test_rejects_noncanonical_input_and_output_identifiers(self):
        bad_claim_ids = (" claim-0 ", "claim-\t0", "claim-\n0", "claim-\v0",
                         "claim-\x000", "claim-\x1b0", "claim-\x7f0",
                         "claim-\u200b0")
        for claim_id in bad_claim_ids:
            with self.subTest(input_claim_id=claim_id):
                candidate = market("m0")
                self.assertIsNone(heartbeat.validated_mappings(
                    {"mappings": [mapping_record(
                        claim_id, match=True, market_id="m0",
                        implied_side="YES")]},
                    [mapping_input(claim_id, candidate)],
                ))

        bad_market_ids = (" m0 ", "m\t0", "m\n0", "m\v0", "m\x000",
                          "m\x1b0", "m\x7f0", "m\u200b0")
        for market_id in bad_market_ids:
            with self.subTest(input_market_id=market_id):
                candidate = market(market_id)
                self.assertIsNone(heartbeat.validated_mappings(
                    {"mappings": [mapping_record(
                        "claim-0", match=True, market_id=market_id,
                        implied_side="YES")]},
                    [mapping_input("claim-0", candidate)],
                ))

        inputs = [mapping_input("claim-0", market("m0"))]
        for record in (
            mapping_record(" claim-0 ", match=False),
            mapping_record("claim-\x000", match=False),
            mapping_record("claim-0", match=True,
                           market_id=" m0 ", implied_side="YES"),
            mapping_record("claim-0", match=True,
                           market_id="m\u200b0", implied_side="YES"),
        ):
            with self.subTest(output_record=record):
                self.assertIsNone(heartbeat.validated_mappings(
                    {"mappings": [record]}, inputs))


class HeartbeatMappingTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ddir = Path(self.tmp.name)
        (self.ddir / "domain.md").write_text("brief", encoding="utf-8")
        (self.ddir / "signals.tsv").write_text(SIGNAL_HEADER, encoding="utf-8")
        (self.ddir / "leakers.tsv").write_text(LEAKER_HEADER, encoding="utf-8")
        lib.append_tsv(self.ddir / "leakers.tsv", {
            "leaker_id": "x-source", "platform": "x", "handle": "source",
            "domain": "d", "call_class": "timing", "status": "probation",
        })
        self.posts = [{
            "id": "7", "ts": "2026-01-01T00:00:00Z",
            "url": "https://x.com/source/status/7", "text": "two claims",
        }]
        self.claims = [
            {"post_index": 0, "claim": f"claim {i}", "call_class": "timing",
             "market_query": f"query {i}", "hedged": False}
            for i in range(2)
        ]
        self.cfg = {"thresholds": {"min_liquidity_usd": 1000},
                    "call_classes": {"d": ["timing"]}}

    def tearDown(self):
        self.tmp.cleanup()

    def run_heartbeat(self, mapping_response, *, claims=None, replace=None,
                      market_ids=("m0", "m1")):
        mapping_prompts = []

        def llm(_role, prompt, _cfg):
            if "Perform market mapping now" in prompt:
                mapping_prompts.append(prompt)
                return mapping_response
            return {"claims": self.claims if claims is None else claims,
                    "lessons": []}

        def search(query, **_kwargs):
            return [market(market_ids[0] if query.endswith("0") else market_ids[1])]

        patches = [
            mock.patch.object(heartbeat.argparse.ArgumentParser, "parse_args",
                              return_value=SimpleNamespace(domain="d")),
            mock.patch.object(heartbeat, "domain_dir", return_value=self.ddir),
            mock.patch.object(heartbeat, "load_config", return_value=self.cfg),
            mock.patch.object(heartbeat, "agent_context", return_value=""),
            mock.patch.object(heartbeat, "fetch_posts", return_value=self.posts),
            mock.patch.object(heartbeat, "call_json", side_effect=llm),
            mock.patch.object(heartbeat.pm, "search_markets", side_effect=search),
            mock.patch.object(heartbeat.pm, "midpoint", return_value=0.4),
            mock.patch.object(heartbeat, "append_lessons"),
            mock.patch.object(heartbeat, "write_note"),
            mock.patch.object(heartbeat, "log_result"),
            mock.patch.object(heartbeat.cognee, "add"),
        ]
        if replace is not None:
            patches.append(mock.patch.object(lib.os, "replace", side_effect=replace))
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        if len(patches) == 13:
                                                            with patches[12]:
                                                                heartbeat.main()
                                                        else:
                                                            heartbeat.main()
        return mapping_prompts

    def signal_rows(self):
        return lib.read_tsv(self.ddir / "signals.tsv")

    def test_zero_claim_post_commits_only_marker_without_mapping_call(self):
        prompts = self.run_heartbeat(None, claims=[])

        self.assertEqual([], prompts)
        rows = self.signal_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(heartbeat.POST_COMPLETE, rows[0]["status"])

    def test_incomplete_mapping_leaves_every_claim_and_marker_retryable(self):
        incomplete = {"mappings": [mapping_record(
            "claim-0", match=True, market_id="m0", implied_side="YES")]}
        prompts = self.run_heartbeat(incomplete)

        self.assertEqual(1, len(prompts))
        self.assertIn("claim_id claim-0", prompts[0])
        self.assertIn("claim_id claim-1", prompts[0])
        self.assertEqual([], self.signal_rows())

    def test_unmarked_legacy_claim_cannot_suppress_the_complete_retry(self):
        lib.append_tsv(self.ddir / "signals.tsv", {
            "signal_id": "legacy-partial", "domain": "d",
            "leaker_id": "x-source", "platform": "x",
            "post_url": self.posts[0]["url"], "post_ts": self.posts[0]["ts"],
            "claim": "claim 0", "call_class": "timing", "status": "",
        })
        valid = {"mappings": [
            mapping_record("claim-0", match=True,
                           market_id="m0", implied_side="YES"),
            mapping_record("claim-1", match=False),
        ]}

        prompts = self.run_heartbeat(valid)

        self.assertEqual(1, len(prompts))
        self.assertIn("claim_id claim-0", prompts[0])
        self.assertIn("claim_id claim-1", prompts[0])
        rows = self.signal_rows()
        self.assertEqual("legacy-partial", rows[0]["signal_id"])
        committed = rows[1:]
        self.assertEqual(3, len(committed))
        self.assertEqual({"claim 0", "claim 1"},
                         {row["claim"] for row in committed if row["claim"]})
        self.assertEqual(1, sum(
            row["status"] == heartbeat.POST_COMPLETE for row in committed))

    def test_padded_output_identifiers_leave_the_whole_post_retryable(self):
        invalid_responses = [
            {"mappings": [
                mapping_record(" claim-0 ", match=True,
                               market_id="m0", implied_side="YES"),
                mapping_record("claim-1", match=False),
            ]},
            {"mappings": [
                mapping_record("claim-0", match=True,
                               market_id=" m0 ", implied_side="YES"),
                mapping_record("claim-1", match=False),
            ]},
        ]
        for response in invalid_responses:
            with self.subTest(response=response):
                prompts = self.run_heartbeat(response)
                self.assertEqual(1, len(prompts))
                self.assertEqual([], self.signal_rows())

    def test_control_and_format_market_ids_cannot_commit_any_post_rows(self):
        for bad_id in ("m0\x00", "m0\x1b", "m0\x7f", "m0\u200b"):
            with self.subTest(market_id=repr(bad_id)):
                (self.ddir / "signals.tsv").write_text(
                    SIGNAL_HEADER, encoding="utf-8")
                response = {"mappings": [
                    mapping_record("claim-0", match=True,
                                   market_id=bad_id, implied_side="YES"),
                    mapping_record("claim-1", match=False),
                ]}
                prompts = self.run_heartbeat(
                    response, market_ids=(bad_id, "123456790"))
                self.assertEqual(1, len(prompts))
                self.assertEqual([], self.signal_rows())

    def test_numeric_polymarket_id_remains_valid(self):
        market_id = "123456789"
        response = {"mappings": [
            mapping_record("claim-0", match=True,
                           market_id=market_id, implied_side="YES"),
            mapping_record("claim-1", match=False),
        ]}

        self.run_heartbeat(response, market_ids=(market_id, "123456790"))

        rows = self.signal_rows()
        self.assertEqual(3, len(rows))
        self.assertEqual(market_id, rows[0]["market_id"])
        self.assertEqual(heartbeat.POST_COMPLETE, rows[-1]["status"])

    def test_invalid_mapping_retries_then_commits_once_and_replay_is_idempotent(self):
        self.run_heartbeat({"mappings": [mapping_record("claim-x", match=False),
                                                  mapping_record("claim-1", match=False)]})
        self.assertEqual([], self.signal_rows())

        valid = {"mappings": [
            mapping_record("claim-1", match=False),
            mapping_record("claim-0", match=True,
                           market_id="m0", implied_side="YES"),
        ]}
        prompts = self.run_heartbeat(valid)
        self.assertEqual(1, len(prompts))
        rows = self.signal_rows()
        self.assertEqual(3, len(rows))
        self.assertEqual(1, sum(row["status"] == "tracked_probation" for row in rows))
        self.assertEqual(1, sum(row["status"] == "no_market" for row in rows))
        self.assertEqual(1, sum(row["status"] == heartbeat.POST_COMPLETE for row in rows))

        prompts = self.run_heartbeat(valid)
        self.assertEqual([], prompts)
        self.assertEqual(rows, self.signal_rows())

    def test_atomic_write_failure_preserves_empty_file_and_next_run_retries(self):
        valid = {"mappings": [
            mapping_record("claim-0", match=True,
                           market_id="m0", implied_side="YES"),
            mapping_record("claim-1", match=False),
        ]}
        with self.assertRaises(OSError):
            self.run_heartbeat(valid, replace=OSError("injected replace failure"))
        self.assertEqual([], self.signal_rows())

        self.run_heartbeat(valid)
        rows = self.signal_rows()
        self.assertEqual(3, len(rows))
        self.assertEqual(1, sum(row["status"] == heartbeat.POST_COMPLETE for row in rows))


if __name__ == "__main__":
    unittest.main()
