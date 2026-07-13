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
import sources  # noqa: E402


SIGNAL_HEADER = ("signal_id\tts_detected\tdomain\tleaker_id\tplatform\tpost_url\tpost_ts\t"
                 "claim\tcall_class\thedged\tmarket_id\tevent_id\tmarket_question\ttoken_id\t"
                 "side\tprice_at_signal\tliquidity_usd\tstatus\tjudge_p\tjudge_conf\tedge\t"
                 "resolved_outcome\tstat_counted\tnote\n")
LEAKER_HEADER = ("leaker_id\tplatform\thandle\tdomain\tcall_class\tstatus\tn_calls\thits\t"
                 "hit_rate\tavg_price_at_call\test_edge\tedge_lcb\tn_unpriced\tn_live\t"
                 "last_seen_ts\tnotes\n")


class HeartbeatTransactionTests(unittest.TestCase):
    def test_all_claims_and_completion_marker_share_one_atomic_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            (ddir / "domain.md").write_text("brief", encoding="utf-8")
            (ddir / "signals.tsv").write_text(SIGNAL_HEADER, encoding="utf-8")
            (ddir / "leakers.tsv").write_text(LEAKER_HEADER, encoding="utf-8")
            lib.append_tsv(ddir / "leakers.tsv", {
                "leaker_id": "x-source", "platform": "x", "handle": "source",
                "domain": "d", "call_class": "timing", "status": "probation",
            })
            # A historical row on this URL must not suppress prospective rows.
            lib.append_tsv(ddir / "signals.tsv", {
                "signal_id": "hist-1", "domain": "d", "leaker_id": "x-source",
                "platform": "x", "post_url": "https://x.com/source/status/7",
                "post_ts": "2026-01-01T00:00:00Z", "claim": "claim 0",
                "status": "historical",
            })
            posts = [{
                "id": "7", "ts": "2026-01-01T00:00:00Z",
                "url": "https://x.com/source/status/7", "text": "six claims",
            }]
            extraction = {"claims": [
                {"post_index": 0, "claim": f"claim {i}", "call_class": "timing",
                 "market_query": f"query {i}", "hedged": False}
                for i in range(6)
            ]}
            writes = []

            def atomic_write(path, rows):
                writes.append([dict(row) for row in rows])
                lib.write_tsv(path, rows)

            cfg = {"thresholds": {"min_liquidity_usd": 1000},
                   "call_classes": {"d": ["timing"]}}
            with (mock.patch.object(heartbeat.argparse.ArgumentParser, "parse_args",
                                    return_value=SimpleNamespace(domain="d")),
                  mock.patch.object(heartbeat, "domain_dir", return_value=ddir),
                  mock.patch.object(heartbeat, "load_config", return_value=cfg),
                  mock.patch.object(heartbeat, "agent_context", return_value=""),
                  mock.patch.object(heartbeat, "fetch_posts", return_value=posts),
                  mock.patch.object(heartbeat, "call_json", return_value=extraction),
                  mock.patch.object(heartbeat.pm, "search_markets", return_value=[]),
                  mock.patch.object(heartbeat, "write_tsv", side_effect=atomic_write),
                  mock.patch.object(heartbeat, "append_lessons"),
                  mock.patch.object(heartbeat, "write_note"),
                  mock.patch.object(heartbeat, "log_result"),
                  mock.patch.object(heartbeat.cognee, "add")):
                heartbeat.main()

            self.assertEqual(1, len(writes))
            added = writes[0][1:]
            self.assertEqual(6, sum(row.get("status") == "no_market" for row in added))
            markers = [row for row in added if row.get("status") == heartbeat.POST_COMPLETE]
            self.assertEqual(1, len(markers))
            self.assertEqual("post_id=7", markers[0]["note"])
            self.assertEqual({f"claim {i}" for i in range(6)},
                             {row["claim"] for row in added if row.get("claim")})

    def test_watermark_orders_equal_timestamps_by_stable_post_id(self):
        signals = [
            {"leaker_id": "x-a", "status": heartbeat.POST_COMPLETE,
             "post_ts": "2026-01-01T00:00:00Z", "post_url": "u/a",
             "note": "post_id=a"},
            {"leaker_id": "x-a", "status": heartbeat.POST_COMPLETE,
             "post_ts": "2026-01-01T00:00:00Z", "post_url": "u/b",
             "note": "post_id=b"},
        ]
        self.assertEqual(("2026-01-01T00:00:00Z", "b"),
                         heartbeat.watermark(signals, [], "x-a"))


class SourceBacklogTests(unittest.TestCase):
    @staticmethod
    def reddit_page(numbers, after):
        return {"data": {"after": after, "children": [
            {"data": {"id": str(i), "created_utc": i,
                      "permalink": f"/r/test/comments/{i}", "title": str(i)}}
            for i in numbers
        ]}}

    def test_reddit_returns_contiguous_oldest_prefix_beyond_first_page(self):
        pages = [self.reddit_page(range(120, 60, -1), "next"),
                 self.reddit_page(range(60, 0, -1), None)]
        with mock.patch.object(sources, "_get_json", side_effect=pages) as get_json:
            posts = sources.reddit_user_posts(
                "source", limit=15,
                cfg={"sources": {"reddit_user_agent": "test"}},
                start_iso="1970-01-01T00:00:00Z", oldest_first=True)

        self.assertEqual(2, get_json.call_count)
        self.assertEqual([str(i) for i in range(1, 16)], [post["id"] for post in posts])

    def test_x_api_paginates_before_selecting_oldest_prefix(self):
        first = {"data": [
            {"id": str(i), "created_at": lib.unix_to_iso(1000 + i), "text": str(i)}
            for i in range(150, 50, -1)
        ], "meta": {"next_token": "next"}}
        second = {"data": [
            {"id": str(i), "created_at": lib.unix_to_iso(1000 + i), "text": str(i)}
            for i in range(50, 0, -1)
        ], "meta": {}}
        responses = [{"data": {"id": "uid"}}, first, second]
        cfg = {"sources": {"x_bearer_env": "TOKEN"}}
        with (mock.patch.dict(sources.os.environ, {"TOKEN": "secret"}),
              mock.patch.object(sources, "_get_json", side_effect=responses) as get_json):
            posts = sources._x_api("source", "1970-01-01T00:00:00Z", 15,
                                   cfg, oldest_first=True)

        self.assertEqual(3, get_json.call_count)
        self.assertEqual([str(i) for i in range(1, 16)], [post["id"] for post in posts])

    def test_equal_timestamp_cursor_is_filtered_before_source_limit(self):
        ts = "2026-01-01T00:00:00Z"
        page = {"data": {"after": None, "children": [
            {"data": {"id": f"{i:02d}", "created_utc": 1767225600,
                      "permalink": f"/r/test/comments/{i:02d}", "title": str(i)}}
            for i in range(20, 0, -1)
        ]}}
        with mock.patch.object(sources, "_get_json", return_value=page):
            posts = sources.reddit_user_posts(
                "source", limit=5,
                cfg={"sources": {"reddit_user_agent": "test"}},
                start_iso=ts, oldest_first=True, after_id="10")

        self.assertEqual([f"{i:02d}" for i in range(11, 16)],
                         [post["id"] for post in posts])

    def test_exa_saturated_one_second_window_fails_closed(self):
        saturated = [{"id": str(i), "ts": "2026-01-01T00:00:00Z",
                      "url": f"u/{i}", "text": ""}
                     for i in range(sources.EXA_PAGE_SIZE)]
        with (mock.patch.object(sources, "_exa_query", return_value=saturated),
              mock.patch.object(sources, "_warn") as warn):
            posts = sources._x_exa_oldest(
                "source", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 15, {})

        self.assertEqual([], posts)
        warn.assert_called_once()

    def test_exa_includes_unseen_ids_at_strict_timestamp_watermark(self):
        ts = "2026-01-01T00:00:00Z"
        published = sources._parse_iso(ts)
        dataset = [{"id": f"{i:02d}", "ts": ts, "url": f"u/{i:02d}", "text": ""}
                   for i in range(1, 21)]

        def strict_query(_handle, start, end, _cfg, _limit):
            if sources._parse_iso(start) < published < sources._parse_iso(end):
                return dataset
            return []

        with mock.patch.object(sources, "_exa_query", side_effect=strict_query):
            posts = sources._x_exa_oldest(
                "source", ts, "2026-01-01T00:00:10Z", 5, {}, after_id="10")

        self.assertEqual([f"{i:02d}" for i in range(11, 16)],
                         [post["id"] for post in posts])

    def test_exa_bisection_overlaps_strict_midpoint(self):
        start = sources._parse_iso("2026-01-01T00:00:00Z")
        dataset = []
        for second in range(11):
            count = 1 if second == 5 else 10
            for i in range(count):
                ts = (start + sources.timedelta(seconds=second)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")
                dataset.append({"id": f"{second:02d}-{i:02d}", "ts": ts,
                                "url": f"u/{second}/{i}", "text": ""})

        def strict_query(_handle, lower, upper, _cfg, limit):
            lo, hi = sources._parse_iso(lower), sources._parse_iso(upper)
            matching = [post for post in dataset
                        if lo < sources._parse_iso(post["ts"]) < hi]
            return matching[:limit]

        with mock.patch.object(sources, "_exa_query", side_effect=strict_query):
            posts = sources._x_exa_oldest(
                "source", "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:10Z", 200, {})

        self.assertEqual(101, len(posts))
        self.assertIn("05-00", {post["id"] for post in posts})


if __name__ == "__main__":
    unittest.main()
