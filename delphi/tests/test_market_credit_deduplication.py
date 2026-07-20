from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import explorer  # noqa: E402
import lib  # noqa: E402
import resolve  # noqa: E402


THRESHOLDS = {
    "verify_min_calls": 10,
    "verify_min_edge": 0.05,
    "verify_z": 1.2816,
}


class ExplorerMarketCreditTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "thresholds": THRESHOLDS,
            "call_classes": {"d": ["timing", "unclassified"]},
        }
        self.leakers: list[dict] = []
        self.rows: list[dict] = []
        self.counted_pairs: set[tuple[str, str]] = set()
        self.markets = {
            "m1-early": self.market("m1", "event-shared"),
            "m2": self.market("m2", "event-shared"),
            "m1-late": self.market("m1", "event-shared"),
            "missing": self.market("", "event-invalid"),
        }

    @staticmethod
    def market(market_id: str, event_id: str) -> dict:
        return {
            "id": market_id,
            "event_id": event_id,
            "question": f"Will {market_id or 'missing'} happen?",
            "description": "resolution criteria",
            "yes_token": f"yes-{market_id}",
            "liquidity": 2000,
        }

    @staticmethod
    def posts(*queries: str) -> list[dict]:
        return [{
            "id": f"post-{index}",
            "ts": f"2026-01-0{index + 1}T00:00:00Z",
            "url": f"https://example.test/post-{index}",
            "text": query,
        } for index, query in enumerate(queries)]

    def qualify(self, handle: str, posts: list[dict], price_at=0.4) -> tuple[str, bool]:
        queries = [post["text"] for post in sorted(posts, key=explorer.post_key)]

        def llm(_role, prompt, _cfg):
            if "Perform Task B now" in prompt:
                return {"claims": [{
                    "post_index": index,
                    "claim": f"claim for {query}",
                    "market_query": query,
                    "call_class": "timing",
                } for index, query in enumerate(queries)]}
            return {"mappings": [{
                "claim_index": index,
                "market_id": self.markets[query]["id"],
                "match": True,
                "implied_side": "YES",
            } for index, query in enumerate(queries)]}

        candidate = {
            "platform": "x", "handle": handle, "rationale": "test",
        }
        with (mock.patch.object(explorer, "call_json", side_effect=llm),
              mock.patch.object(explorer, "append_lessons"),
              mock.patch.object(
                  explorer.pm, "search_markets",
                  side_effect=lambda query, **_kwargs: [self.markets[query]]),
              mock.patch.object(explorer.pm, "winning_side", return_value="YES"),
              mock.patch.object(
                  explorer.pm, "price_at",
                  side_effect=lambda token, timestamp: (
                      price_at(token, timestamp) if callable(price_at) else price_at)),
              mock.patch.object(
                  explorer, "append_tsv",
                  side_effect=lambda _path, row: self.rows.append(row))):
            return explorer.qualify(
                self.cfg, "context", "d", "brief", self.leakers, candidate,
                self.counted_pairs, 100, "2025-01-01T00:00:00Z", posts=posts)

    def test_exact_market_key_allows_sibling_markets_and_independent_leakers(self):
        summary, complete = self.qualify(
            "source", self.posts("m1-early", "m2", "m1-late", "missing"))
        self.assertTrue(complete, summary)

        summary, complete = self.qualify("other", self.posts("m1-early"))
        self.assertTrue(complete, summary)

        credited = [(row["leaker_id"], row["market_id"], row["post_url"])
                    for row in self.rows]
        self.assertEqual([
            ("x-source", "m1", "https://example.test/post-0"),
            ("x-source", "m2", "https://example.test/post-1"),
            ("x-other", "m1", "https://example.test/post-0"),
        ], credited)
        self.assertEqual({
            ("x-source", "m1"),
            ("x-source", "m2"),
            ("x-other", "m1"),
        }, self.counted_pairs)
        self.assertNotIn(("x-source", "event-shared"), self.counted_pairs)
        self.assertFalse(any(not row["market_id"] for row in self.rows))

    def test_equal_timestamp_credits_lower_source_id_not_url_or_input_order(self):
        self.markets.update({
            "source-100": self.market("m-equal", "event-equal"),
            "source-200": self.market("m-equal", "event-equal"),
        })
        timestamp = "2026-01-01T00:00:00Z"
        posts = [
            {"id": "200", "ts": timestamp, "url": "https://example.test/a",
             "text": "source-200"},
            {"id": "100", "ts": timestamp, "url": "https://example.test/z",
             "text": "source-100"},
        ]

        summary, complete = self.qualify("source", posts)

        self.assertTrue(complete, summary)
        self.assertEqual(1, len(self.rows))
        self.assertEqual(("100", "https://example.test/z"),
                         (self.rows[0]["source_post_id"],
                          self.rows[0]["post_url"]))

    def test_unpriced_earliest_row_does_not_reserve_market_credit(self):
        self.markets.update({
            "early": self.market("m-price", "event-price"),
            "later": self.market("m-price", "event-price"),
        })
        posts = [
            {"id": "100", "ts": "2026-01-01T00:00:00Z",
             "url": "https://example.test/early", "text": "early"},
            {"id": "200", "ts": "2026-01-02T00:00:00Z",
             "url": "https://example.test/later", "text": "later"},
        ]
        early_unix = lib.iso_to_unix(posts[0]["ts"])

        summary, complete = self.qualify(
            "source", posts,
            price_at=lambda _token, timestamp: None if timestamp == early_unix else 0.4)

        self.assertTrue(complete, summary)
        self.assertEqual(["false", "true"],
                         [row["stat_counted"] for row in self.rows])
        self.assertEqual(["100", "200"],
                         [row["source_post_id"] for row in self.rows])
        self.assertEqual({("x-source", "m-price")}, self.counted_pairs)

    def test_shared_order_key_rejects_invalid_identity_and_has_legacy_fallback(self):
        source_100 = {
            "post_ts": "2026-01-01T00:00:00Z", "source_post_id": "100",
            "signal_id": "sig-z",
        }
        source_200 = {**source_100, "source_post_id": "200", "signal_id": "sig-a"}
        self.assertLess(lib.score_credit_order_key(source_100),
                        lib.score_credit_order_key(source_200))
        self.assertIsNone(lib.score_credit_order_key(
            {**source_100, "post_ts": "2026-01-01"}))
        self.assertIsNone(lib.score_credit_order_key(
            {**source_100, "source_post_id": " bad "}))
        self.assertIsNone(lib.score_credit_order_key(
            {"post_ts": source_100["post_ts"], "source_post_id": ""}))
        self.assertIsNotNone(lib.score_credit_order_key(
            {"post_ts": source_100["post_ts"], "signal_id": "legacy-sig"}))

    def test_startup_reconstruction_uses_only_canonical_market_ids(self):
        signals = [
            self.signal_row("early-unpriced", "x-source", "m1", "event-shared",
                            "2026-01-01T00:00:00Z", "100", "", "true"),
            self.signal_row("later-priced", "x-source", "m1", "event-shared",
                            "2026-01-02T00:00:00Z", "200", "0.4", "false"),
            self.signal_row("sibling", "x-source", "m2", "event-shared",
                            "2026-01-03T00:00:00Z", "300", "0.4", "false"),
            self.signal_row("missing", "x-source", "", "event-invalid",
                            "2026-01-04T00:00:00Z", "400", "0.4", "true"),
            self.signal_row("malformed", "x-source", " bad ", "event-invalid-2",
                            "2026-01-05T00:00:00Z", "500", "0.4", "true"),
            self.signal_row("other", "x-other", "m1", "event-shared",
                            "2026-01-06T00:00:00Z", "600", "0.4", "false"),
        ]

        expected = {
            ("x-source", "m1"),
            ("x-source", "m2"),
            ("x-other", "m1"),
        }
        self.assertEqual(expected, explorer._score_credit_pairs(signals))
        self.assertEqual(expected,
                         explorer._score_credit_pairs(list(reversed(signals))))

    @staticmethod
    def signal_row(signal_id: str, leaker_id: str, market_id: str, event_id: str,
                   post_ts: str, source_post_id: str, price: str,
                   stat_counted: str) -> dict:
        return {
            "signal_id": signal_id, "leaker_id": leaker_id,
            "market_id": market_id, "event_id": event_id,
            "post_ts": post_ts, "source_post_id": source_post_id,
            "side": "YES", "resolved_outcome": "YES",
            "price_at_signal": price, "status": "historical",
            "stat_counted": stat_counted,
        }


class ResolveMarketCreditTests(unittest.TestCase):
    @staticmethod
    def signal(signal_id: str, leaker_id: str, market_id: str, event_id: str,
               post_ts: str, source_post_id: str = "source", **overrides) -> dict:
        row = {
            "signal_id": signal_id,
            "ts_detected": post_ts,
            "domain": "d",
            "leaker_id": leaker_id,
            "platform": "x",
            "post_url": f"https://example.test/{signal_id}",
            "post_ts": post_ts,
            "source_post_id": source_post_id,
            "claim": signal_id,
            "call_class": "timing",
            "market_id": market_id,
            "event_id": event_id,
            "side": "YES",
            "price_at_signal": "0.400",
            "status": "historical",
            "resolved_outcome": "YES",
            "stat_counted": "true",
            "note": "",
        }
        row.update(overrides)
        return row

    def test_replay_credits_exact_market_pair_once_and_is_idempotent(self):
        signals = [
            self.signal("a-m1-late", "x-a", "m1", "event-shared",
                        "2026-01-03T00:00:00Z", "300", status="pass",
                        note="keep duplicate call on event — not scored"),
            self.signal("a-m1-early", "x-a", "m1", "event-shared",
                        "2026-01-01T00:00:00Z", "100"),
            self.signal("a-m2", "x-a", "m2", "event-shared",
                        "2026-01-02T00:00:00Z", "200", status="pass",
                        note="sibling context duplicate call on event — not scored"),
            self.signal("b-m1", "x-b", "m1", "event-shared",
                        "2026-01-04T00:00:00Z", "400", status="expired"),
            self.signal("missing", "x-a", "", "event-invalid",
                        "2026-01-05T00:00:00Z", "500"),
            self.signal("malformed", "x-a", " bad ", "event-invalid-2",
                        "2026-01-06T00:00:00Z", "600"),
        ]
        original_events = [signal["event_id"] for signal in signals]
        leakers = [{
            "leaker_id": leaker_id,
            "platform": "x",
            "handle": leaker_id.removeprefix("x-"),
            "domain": "d",
            "call_class": "timing",
            "status": "candidate",
            "n_calls": 0,
            "hits": 0,
            "hit_rate": "",
            "avg_price_at_call": "",
            "est_edge": "",
            "edge_lcb": "",
            "n_unpriced": 0,
            "n_live": 0,
            "last_seen_ts": "",
            "notes": "",
        } for leaker_id in ("x-a", "x-b")]

        resolve.rebuild_leaker_stats(signals, leakers, THRESHOLDS, "d")

        by_id = {signal["signal_id"]: signal for signal in signals}
        self.assertEqual("true", by_id["a-m1-early"]["stat_counted"])
        self.assertEqual("false", by_id["a-m1-late"]["stat_counted"])
        self.assertEqual("true", by_id["a-m2"]["stat_counted"])
        self.assertEqual("true", by_id["b-m1"]["stat_counted"])
        self.assertEqual("false", by_id["missing"]["stat_counted"])
        self.assertEqual("false", by_id["malformed"]["stat_counted"])
        self.assertEqual("keep duplicate call on market — not scored",
                         by_id["a-m1-late"]["note"])
        self.assertEqual("sibling context", by_id["a-m2"]["note"])

        rows = {row["leaker_id"]: row for row in leakers}
        self.assertEqual((2, 2, 1),
                         (rows["x-a"]["n_calls"], rows["x-a"]["hits"],
                          rows["x-a"]["n_live"]))
        self.assertEqual((1, 1, 1),
                         (rows["x-b"]["n_calls"], rows["x-b"]["hits"],
                          rows["x-b"]["n_live"]))
        self.assertEqual(original_events,
                         [signal["event_id"] for signal in signals])

        snapshot = copy.deepcopy((signals, leakers))
        changed, promotions = resolve.rebuild_leaker_stats(
            signals, leakers, THRESHOLDS, "d")
        self.assertFalse(changed)
        self.assertEqual([], promotions)
        self.assertEqual(snapshot, (signals, leakers))

    def test_source_order_unpriced_eligibility_and_input_reorder_are_stable(self):
        original = [
            self.signal("unpriced", "x-a", "m1", "event-1",
                        "2026-01-01T00:00:00Z", "100", price_at_signal=""),
            self.signal("priced", "x-a", "m1", "event-1",
                        "2026-01-02T00:00:00Z", "200",
                        note="priced context duplicate call on event — not scored"),
            self.signal("sig-a", "x-a", "m2", "event-2",
                        "2026-01-03T00:00:00Z", "200",
                        note="duplicate context duplicate call on event — not scored"),
            self.signal("sig-z", "x-a", "m2", "event-2",
                        "2026-01-03T00:00:00Z", "100"),
        ]

        projections = []
        for rows in (copy.deepcopy(original), list(reversed(copy.deepcopy(original)))):
            leakers = self.leaker_rows("x-a")
            resolve.rebuild_leaker_stats(rows, leakers, THRESHOLDS, "d")
            projections.append((
                {row["signal_id"]: (row["stat_counted"], row["note"])
                 for row in rows},
                copy.deepcopy(leakers),
            ))

        self.assertEqual(projections[0], projections[1])
        flags = projections[0][0]
        self.assertEqual("false", flags["unpriced"][0])
        self.assertEqual(("true", "priced context"), flags["priced"])
        self.assertEqual(("false", "duplicate context duplicate call on market — not scored"),
                         flags["sig-a"])
        self.assertEqual("true", flags["sig-z"][0])
        row = projections[0][1][0]
        self.assertEqual((2, 2, 1),
                         (row["n_calls"], row["hits"], row["n_unpriced"]))

    @staticmethod
    def leaker_rows(*leaker_ids: str) -> list[dict]:
        return [{
            "leaker_id": leaker_id, "platform": "x",
            "handle": leaker_id.removeprefix("x-"), "domain": "d",
            "call_class": "timing", "status": "candidate",
            "n_calls": 0, "hits": 0, "hit_rate": "",
            "avg_price_at_call": "", "est_edge": "", "edge_lcb": "",
            "n_unpriced": 0, "n_live": 0, "last_seen_ts": "", "notes": "",
        } for leaker_id in leaker_ids]


if __name__ == "__main__":
    unittest.main()
