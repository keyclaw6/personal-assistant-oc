from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


DELPHI = Path(__file__).resolve().parents[1]
SCRIPTS = DELPHI / "scripts"
sys.path.insert(0, str(SCRIPTS))

import explorer  # noqa: E402
import heartbeat  # noqa: E402
import lib  # noqa: E402
import source_timestamps  # noqa: E402
import sources  # noqa: E402


UTC = timezone.utc
NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)
SIGNAL_HEADER = (
    "signal_id\tts_detected\tdomain\tleaker_id\tplatform\tpost_url\tpost_ts\t"
    "source_post_id\t"
    "claim\tcall_class\thedged\tmarket_id\tevent_id\tmarket_question\ttoken_id\t"
    "side\tprice_at_signal\tliquidity_usd\tstatus\tjudge_p\tjudge_conf\tedge\t"
    "resolved_outcome\tstat_counted\tnote\n"
)
LEAKER_HEADER = (
    "leaker_id\tplatform\thandle\tdomain\tcall_class\tstatus\tn_calls\thits\t"
    "hit_rate\tavg_price_at_call\test_edge\tedge_lcb\tn_unpriced\tn_live\t"
    "last_seen_ts\tnotes\n"
)


class SourceTimestampContractTests(unittest.TestCase):
    def test_canonical_timestamp_and_adapter_offset_contract(self):
        self.assertEqual(
            "2026-07-14T12:00:00Z",
            source_timestamps.validate_source_timestamp(
                "2026-07-14T12:00:00Z", now=NOW),
        )
        self.assertEqual(
            "2026-07-14T12:00:00Z",
            source_timestamps.validate_source_timestamp(
                "2026-07-14T14:00:00.999999+02:00",
                now=NOW,
                normalize_provider=True,
            ),
        )
        with self.assertRaises(source_timestamps.SourceTimestampError):
            source_timestamps.validate_source_timestamp(
                "2026-07-14T14:00:00+02:00", now=NOW)

        with mock.patch.object(source_timestamps, "utc_now", return_value=NOW):
            self.assertEqual(
                "2026-07-14T12:00:00Z",
                sources._normalize_iso("2026-07-14T14:00:00.5+02:00"),
            )

    def test_naive_date_only_invalid_calendar_and_whitespace_are_rejected(self):
        invalid = [
            "2026-07-14T12:00:00",
            "2026-07-14",
            "2026-02-30T12:00:00Z",
            " 2026-07-14T12:00:00Z",
            "2026-07-14T12:00:00Z ",
            "2026-07-14t12:00:00z",
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(
                    source_timestamps.SourceTimestampError):
                source_timestamps.validate_source_timestamp(
                    value, now=NOW, normalize_provider=True)

    def test_provider_offsets_require_bounded_hour_and_minute_components(self):
        invalid_offsets = [
            "+01:60", "+00:60", "+00:99", "+22:99", "+24:00", "+99:00",
            "-01:60", "-00:60", "-00:99", "-22:99", "-24:00", "-99:00",
        ]
        for offset in invalid_offsets:
            with self.subTest(offset=offset), self.assertRaises(
                    source_timestamps.SourceTimestampError):
                source_timestamps.validate_source_timestamp(
                    f"2026-07-13T12:00:00{offset}", now=NOW,
                    normalize_provider=True)

        valid_boundaries = {
            "+23:59": "2026-07-12T12:01:00Z",
            "-23:59": "2026-07-14T11:59:00Z",
            "+00:59": "2026-07-13T11:01:00Z",
            "-00:59": "2026-07-13T12:59:00Z",
        }
        for offset, canonical in valid_boundaries.items():
            with self.subTest(offset=offset):
                self.assertEqual(
                    canonical,
                    source_timestamps.validate_source_timestamp(
                        f"2026-07-13T12:00:00.5{offset}", now=NOW,
                        normalize_provider=True),
                )

    def test_clock_tolerance_boundary_is_inclusive_and_one_second_later_rejected(self):
        tolerance = source_timestamps.SOURCE_CLOCK_TOLERANCE
        accepted = NOW + tolerance
        rejected = accepted + timedelta(seconds=1)

        self.assertEqual(
            accepted.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_timestamps.validate_source_timestamp(
                accepted.strftime("%Y-%m-%dT%H:%M:%SZ"), now=NOW),
        )
        with self.assertRaises(source_timestamps.SourceTimestampError):
            source_timestamps.validate_source_timestamp(
                rejected.strftime("%Y-%m-%dT%H:%M:%SZ"), now=NOW)


class HeartbeatTimestampTests(unittest.TestCase):
    def test_future_post_never_poisons_cursor_and_normal_post_retries(self):
        normal = {
            "id": "100", "ts": "2026-07-14T11:00:00Z",
            "url": "https://x.com/source/status/100", "text": "normal",
        }
        future = {
            "id": "999", "ts": "2099-01-01T00:00:00Z",
            "url": "https://x.com/source/status/999", "text": "poison",
        }

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            (ddir / "domain.md").write_text("brief", encoding="utf-8")
            (ddir / "signals.tsv").write_text(SIGNAL_HEADER, encoding="utf-8")
            (ddir / "leakers.tsv").write_text(LEAKER_HEADER, encoding="utf-8")
            lib.append_tsv(ddir / "leakers.tsv", {
                "leaker_id": "x-source", "platform": "x", "handle": "source",
                "domain": "d", "call_class": "timing", "status": "probation",
            })
            cfg = {
                "thresholds": {"min_liquidity_usd": 1000},
                "call_classes": {"d": ["timing"]},
            }

            with (
                mock.patch.object(
                    heartbeat.argparse.ArgumentParser, "parse_args",
                    return_value=SimpleNamespace(domain="d"),
                ),
                mock.patch.object(heartbeat, "domain_dir", return_value=ddir),
                mock.patch.object(heartbeat, "load_config", return_value=cfg),
                mock.patch.object(heartbeat, "agent_context", return_value=""),
                mock.patch.object(
                    heartbeat, "fetch_posts", return_value=[future, normal],
                ) as fetch,
                mock.patch.object(
                    heartbeat, "call_json",
                    side_effect=[None, {"claims": []}],
                ),
                mock.patch.object(heartbeat, "utc_now", return_value=NOW),
                mock.patch.object(heartbeat, "append_lessons"),
                mock.patch.object(heartbeat, "write_note"),
                mock.patch.object(heartbeat, "log_result"),
                mock.patch.object(heartbeat.cognee, "add"),
            ):
                heartbeat.main()  # extraction failure: normal post stays retryable
                self.assertEqual([], lib.read_tsv(ddir / "signals.tsv"))
                heartbeat.main()

            rows = lib.read_tsv(ddir / "signals.tsv")

        markers = [row for row in rows
                   if row.get("status") == heartbeat.POST_COMPLETE]
        self.assertEqual(1, len(markers))
        self.assertEqual("100", heartbeat.marker_post_id(markers[0]))
        self.assertNotEqual("2099-01-01T00:00:00Z", markers[0]["post_ts"])
        self.assertEqual(2, fetch.call_count)
        self.assertEqual("", fetch.call_args_list[1].kwargs["after_id"])

    def test_existing_future_marker_is_ignored_as_a_watermark(self):
        signals = [
            {"leaker_id": "x-source", "status": heartbeat.POST_COMPLETE,
             "post_ts": "2026-07-14T11:00:00Z", "note": "post_id=100"},
            {"leaker_id": "x-source", "status": heartbeat.POST_COMPLETE,
             "post_ts": "2099-01-01T00:00:00Z", "note": "post_id=999"},
        ]

        self.assertEqual(
            ("2026-07-14T11:00:00Z", "100"),
            heartbeat.watermark(signals, [], "x-source", now=NOW),
        )


class ExplorerTimestampTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "thresholds": {
                "verify_min_calls": 10, "verify_min_edge": 0.05,
                "verify_z": 1.2816,
            },
            "call_classes": {"d": ["timing", "unclassified"]},
        }
        self.candidate = {
            "platform": "x", "handle": "source", "rationale": "test",
            "_provider": "x_api", "_start": "2025-01-01T00:00:00Z",
            "_limit": 100, "_call_class": "-",
        }

    def test_future_post_cannot_reach_qualification_market_search_or_pricing(self):
        post = {
            "id": "999", "ts": "2099-01-01T00:00:00Z",
            "url": "https://x.com/source/status/999", "text": "future claim",
        }
        leakers: list[dict] = []

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(explorer, "domain_dir", return_value=Path(tmp)),
            mock.patch.object(explorer, "utc_now", return_value=NOW),
            mock.patch.object(explorer, "call_json") as llm,
            mock.patch.object(explorer.pm, "search_markets") as search,
            mock.patch.object(explorer.pm, "price_at") as price,
        ):
            summary, completed = explorer.qualify(
                self.cfg, "", "d", "", leakers, self.candidate,
                set(), 100, "2025-01-01T00:00:00Z", posts=[post],
            )

        self.assertFalse(completed)
        self.assertIn("invalid source timestamp", summary)
        self.assertEqual([], leakers)
        llm.assert_not_called()
        search.assert_not_called()
        price.assert_not_called()

    def test_invalid_history_row_cannot_advance_or_mark_exhausted(self):
        valid = {
            "id": "100", "ts": "2026-07-14T11:00:00Z",
            "url": "https://x.com/source/status/100", "text": "normal",
        }
        invalid = {
            "id": "999", "ts": "2099-01-01T00:00:00Z",
            "url": "https://x.com/source/status/999", "text": "poison",
        }

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            with (
                mock.patch.object(explorer, "domain_dir", return_value=ddir),
                mock.patch.object(explorer, "utc_now", return_value=NOW),
                mock.patch.object(
                    explorer, "fetch_history_page",
                    return_value=sources.HistoryPage(
                        [invalid, valid], exhausted=True, provider="x_api"),
                ),
                mock.patch.object(explorer, "qualify") as qualify,
            ):
                _summary, terminal = explorer.run_history_page(
                    self.cfg, "", "d", "", [], self.candidate, set(), [])
            row = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)[0]

        self.assertFalse(terminal)
        self.assertEqual("coverage_gap", row["status"])
        self.assertEqual(("", ""), (row["newest_ts"], row["before_ts"]))
        self.assertEqual("2026-07-14T12:00:00Z", row["updated_at"])
        qualify.assert_not_called()


class ProviderTimestampOrderTests(unittest.TestCase):
    @staticmethod
    def reddit_page(items, after):
        return {"data": {"after": after, "children": [
            {"data": {
                "id": stable_id, "created_utc": created,
                "permalink": f"/u/source/{stable_id}", "title": stable_id,
            }}
            for stable_id, created in items
        ]}}

    def test_provider_reverse_chronology_regression_fails_closed(self):
        # The second provider page jumps newer than the oldest timestamp on the
        # first page. Sorting locally would hide that missing/duplicated region.
        pages = [
            self.reddit_page([("300", 300), ("200", 200)], "next"),
            self.reddit_page([("250", 250), ("100", 100)], None),
        ]
        cfg = {"sources": {"reddit_user_agent": "test"}}

        with mock.patch.object(sources, "_get_json", side_effect=pages):
            page = sources.fetch_history_page(
                "reddit", "source", "1970-01-01T00:00:00Z", None, 100, cfg)

        self.assertFalse(page.exhausted)
        self.assertEqual([], page.posts)
        self.assertIn("chronological", page.coverage_gap)


if __name__ == "__main__":
    unittest.main()
