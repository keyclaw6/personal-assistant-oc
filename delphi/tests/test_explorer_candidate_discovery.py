from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


DELPHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DELPHI / "scripts"))

import explorer  # noqa: E402
import lib  # noqa: E402
import sources  # noqa: E402


def evidence(item: int, *, text: str | None = None,
             linked_source: str = "example.com") -> dict:
    return {
        "canonical_id": f"reddit:item-{item}",
        "canonical_url": f"https://www.reddit.com/r/test/comments/item-{item}/post/",
        "text": text or f"title {item}\nsubstantive body {item}",
        "publisher": f"reddit/u/publisher{item}",
        "linked_source": linked_source,
    }


class CandidateDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(lib.load_config())
        self.cfg["sources"].update({
            "discovery_evidence_budget": 28,
            "discovery_page_size": 20,
            "discovery_max_pages_per_source": 5,
            "discovery_evidence_chars": 600,
        })

    @staticmethod
    def brief(*feeds: str) -> str:
        return "## Sweep sources\n" + ", ".join(
            f"reddit:r/{feed}" for feed in feeds)

    def test_feed_four_linked_source_reaches_decision_and_materializes(self):
        pages = {
            "one": [evidence(1)],
            "two": [evidence(2)],
            "three": [evidence(3)],
            "four": [evidence(4, linked_source="x/@real_originator")],
        }
        prompts = []
        appended = []

        def fetch(source, _after, _limit, _cfg):
            return sources.DiscoveryPage(pages[source], "")

        def decide(_role, prompt, _cfg):
            prompts.append(prompt)
            self.assertIn('"linked_source":"x/@real_originator"', prompt)
            return {"candidates": [{
                "platform": "x", "handle": "real_originator",
                "rationale": "linked as the origin",
            }]}

        with mock.patch.object(explorer, "reddit_sub_page", side_effect=fetch) as pager, \
             mock.patch.object(explorer, "call_json", side_effect=decide), \
             mock.patch.object(explorer, "append_lessons"), \
             mock.patch.object(explorer, "append_tsv",
                               side_effect=lambda _path, row: appended.append(row)):
            added = explorer.propose_candidates(
                self.cfg, "context", "ai-releases",
                self.brief("one", "two", "three", "four"), [], [])

        self.assertEqual(4, pager.call_count)
        self.assertEqual(1, added)
        self.assertEqual("real_originator", appended[0]["handle"])
        self.assertEqual(1, len(prompts))

    def test_item_after_twenty_and_body_only_reaches_decision(self):
        first = [evidence(i) for i in range(1, 21)]
        body = "the only mention of @body_originator is deep in the post body"
        second = [evidence(21, text=f"ordinary title\n{body}")]
        calls = []

        def fetch(_source, after, limit, _cfg):
            calls.append((after, limit))
            if not after:
                return sources.DiscoveryPage(first, "next-page")
            return sources.DiscoveryPage(second, "")

        appended = []
        with mock.patch.object(explorer, "reddit_sub_page", side_effect=fetch), \
             mock.patch.object(explorer, "call_json",
                               return_value={"candidates": [{
                                   "platform": "x", "handle": "body_originator",
                                   "rationale": "named in the body",
                               }]}) as decision, \
             mock.patch.object(explorer, "append_lessons"), \
             mock.patch.object(explorer, "append_tsv",
                               side_effect=lambda _path, row: appended.append(row)):
            added = explorer.propose_candidates(
                self.cfg, "context", "ai-releases", self.brief("only"), [], [])

        self.assertEqual([("", 20), ("next-page", 20)], calls)
        prompt = decision.call_args.args[1]
        self.assertIn(body, prompt)
        self.assertIn('"canonical_id":"reddit:item-21"', prompt)
        self.assertEqual(1, added)
        self.assertEqual("body_originator", appended[0]["handle"])

    def test_round_robin_budget_fairness_across_multiple_pages(self):
        self.cfg["sources"].update({
            "discovery_evidence_budget": 9,
            "discovery_page_size": 2,
        })
        requested = []

        def fetch(source, after, _limit, _cfg):
            requested.append((source, after))
            base = {"one": 100, "two": 200, "three": 300, "four": 400}[source]
            page = 0 if not after else 1
            return sources.DiscoveryPage(
                [evidence(base + page * 2 + offset) for offset in range(2)],
                "" if page else f"{source}-page-2")

        rows = explorer.discovery_evidence(
            self.cfg, self.brief("one", "two", "three", "four"),
            fetch_page=fetch)

        self.assertEqual(9, len(rows))
        self.assertEqual(
            ["reddit:r/one", "reddit:r/two", "reddit:r/three", "reddit:r/four",
             "reddit:r/one", "reddit:r/two", "reddit:r/three", "reddit:r/four",
             "reddit:r/one"],
            [row["source_provenance"][0] for row in rows])
        self.assertEqual(
            [("one", ""), ("two", ""), ("three", ""), ("four", ""),
             ("one", "one-page-2"), ("two", "two-page-2"),
             ("three", "three-page-2"), ("four", "four-page-2")],
            requested)

    def test_stable_dedup_merges_provenance_without_spending_budget(self):
        self.cfg["sources"]["discovery_evidence_budget"] = 2
        duplicate = evidence(1)
        pages = {
            "one": sources.DiscoveryPage([duplicate, evidence(2)], ""),
            "two": sources.DiscoveryPage([dict(duplicate)], ""),
        }

        rows = explorer.discovery_evidence(
            self.cfg, self.brief("one", "two"),
            fetch_page=lambda source, *_args: pages[source])

        self.assertEqual(["reddit:item-1", "reddit:item-2"],
                         [row["canonical_id"] for row in rows])
        self.assertEqual(["reddit:r/one", "reddit:r/two"],
                         rows[0]["source_provenance"])

    def test_malformed_entries_do_not_consume_useful_budget(self):
        self.cfg["sources"]["discovery_evidence_budget"] = 2
        bad_url = {**evidence(1), "canonical_url": "javascript:alert(1)"}
        bad_content = {**evidence(2), "text": "unsafe\x00content"}
        missing_id = {**evidence(3), "canonical_id": ""}
        page = sources.DiscoveryPage(
            [bad_url, bad_content, missing_id, evidence(4), evidence(5)], "")

        rows = explorer.discovery_evidence(
            self.cfg, self.brief("only"),
            fetch_page=lambda *_args: page)

        self.assertEqual(["reddit:item-4", "reddit:item-5"],
                         [row["canonical_id"] for row in rows])

    def test_one_source_failure_does_not_erase_other_sources(self):
        pages = {
            "good-one": sources.DiscoveryPage([evidence(1)], ""),
            "broken": sources.DiscoveryPage([], "", failed=True),
            "good-two": sources.DiscoveryPage([evidence(2)], ""),
        }
        rows = explorer.discovery_evidence(
            self.cfg, self.brief("good-one", "broken", "good-two"),
            fetch_page=lambda source, *_args: pages[source])

        self.assertEqual(["reddit:item-1", "reddit:item-2"],
                         [row["canonical_id"] for row in rows])

    def test_invalid_or_duplicate_rows_do_not_burn_a_source_turn(self):
        self.cfg["sources"]["discovery_evidence_budget"] = 2
        duplicate = evidence(1)
        invalid = {**evidence(3), "text": "unsafe\x00content"}
        pages = {
            "loud": sources.DiscoveryPage([duplicate, evidence(2)], ""),
            "later": sources.DiscoveryPage([invalid, dict(duplicate), evidence(4)], ""),
        }

        rows = explorer.discovery_evidence(
            self.cfg, self.brief("loud", "later"),
            fetch_page=lambda source, *_args: pages[source])

        self.assertEqual(["reddit:item-1", "reddit:item-4"],
                         [row["canonical_id"] for row in rows])
        self.assertEqual(["reddit:r/later", "reddit:r/loud"],
                         rows[0]["source_provenance"])

    def test_identity_conflicts_are_rejected_independent_of_row_and_feed_order(self):
        self.cfg["sources"]["discovery_evidence_budget"] = 2
        same_id_a = evidence(1)
        same_id_b = {**evidence(1), "canonical_url": evidence(2)["canonical_url"]}
        same_url_other_id = {
            **evidence(3), "canonical_url": evidence(2)["canonical_url"],
        }
        safe = evidence(4)

        def collect(feeds, pages):
            return explorer.discovery_evidence(
                self.cfg, self.brief(*feeds),
                fetch_page=lambda source, *_args: sources.DiscoveryPage(
                    pages[source], ""))

        first = collect(
            ("one", "two"),
            {"one": [same_id_a, safe], "two": [same_id_b, same_url_other_id]})
        second = collect(
            ("two", "one"),
            {"one": [safe, same_id_a], "two": [same_url_other_id, same_id_b]})

        self.assertEqual(["reddit:item-4"],
                         [row["canonical_id"] for row in first])
        self.assertEqual(first, second)

    def test_identity_conflicts_are_rejected_across_cursor_pages(self):
        self.cfg["sources"].update({
            "discovery_evidence_budget": 1,
            "discovery_page_size": 1,
            "discovery_max_pages_per_source": 3,
        })
        same_a = evidence(1)
        same_b = {**evidence(1), "canonical_url": evidence(2)["canonical_url"]}
        safe = evidence(4)

        def collect(first, second):
            calls = []

            def fetch(_source, after, _limit, _cfg):
                calls.append(after)
                if not after:
                    return sources.DiscoveryPage([first], "page-2")
                return sources.DiscoveryPage([second, safe], "")

            rows = explorer.discovery_evidence(
                self.cfg, self.brief("only"), fetch_page=fetch)
            self.assertEqual(["", "page-2"], calls)
            return rows

        forward = collect(same_a, same_b)
        reverse = collect(same_b, same_a)

        self.assertEqual(["reddit:item-4"],
                         [row["canonical_id"] for row in forward])
        self.assertEqual(forward, reverse)

    def test_explicit_budget_is_validated_and_must_visit_every_feed(self):
        self.cfg["sources"]["discovery_evidence_budget"] = 3
        with self.assertRaises(explorer.DiscoveryConfigError):
            explorer.discovery_evidence(
                self.cfg, self.brief("one", "two", "three", "four"),
                fetch_page=lambda *_args: None)

        self.cfg["sources"]["discovery_evidence_budget"] = True
        with self.assertRaises(explorer.DiscoveryConfigError):
            explorer.discovery_evidence(
                self.cfg, self.brief("one"), fetch_page=lambda *_args: None)

    def test_aggregate_discovery_work_is_validated(self):
        self.cfg["sources"].update({
            "discovery_evidence_budget": 20,
            "discovery_page_size": 100,
            "discovery_max_pages_per_source": 20,
            "discovery_evidence_chars": 400,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate discovery request"):
            explorer.discovery_evidence(
                self.cfg,
                self.brief("one", "two", "three", "four", "five", "six"),
                fetch_page=lambda *_args: None)

        self.cfg["sources"].update({
            "discovery_evidence_budget": 20,
            "discovery_page_size": 100,
            "discovery_max_pages_per_source": 20,
            "discovery_evidence_chars": 400,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate discovery raw item"):
            explorer.discovery_evidence(
                self.cfg, self.brief("one", "two", "three", "four", "five"),
                fetch_page=lambda *_args: None)

        self.cfg["sources"].update({
            "discovery_evidence_budget": 20,
            "discovery_page_size": 50,
            "discovery_max_pages_per_source": 20,
            "discovery_evidence_chars": 1500,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate scanned evidence"):
            explorer.discovery_evidence(
                self.cfg, self.brief("one", "two", "three", "four"),
                fetch_page=lambda *_args: None)

        self.cfg["sources"].update({
            "discovery_evidence_budget": 20,
            "discovery_page_size": 100,
            "discovery_max_pages_per_source": 20,
            "discovery_evidence_chars": 400,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate scanned evidence"):
            explorer.discovery_evidence(
                self.cfg, self.brief("one", "two", "three", "four"),
                fetch_page=lambda *_args: None)

        self.cfg["sources"].update({
            "discovery_evidence_budget": 100,
            "discovery_page_size": 20,
            "discovery_max_pages_per_source": 5,
            "discovery_evidence_chars": 1500,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate retained evidence"):
            explorer.discovery_evidence(
                self.cfg, self.brief("one"), fetch_page=lambda *_args: None)

        self.cfg["sources"].update({
            "discovery_evidence_budget": 64,
            "discovery_page_size": 20,
            "discovery_max_pages_per_source": 5,
            "discovery_evidence_chars": 600,
        })
        with self.assertRaisesRegex(
                explorer.DiscoveryConfigError, "aggregate retained evidence"):
            explorer.discovery_evidence(
                self.cfg, self.brief("one", "two", "three", "four"),
                fetch_page=lambda *_args: None)

    def test_utf8_evidence_bound_is_validated_before_provider_work(self):
        self.cfg["sources"].update({
            "discovery_evidence_budget": 48,
            "discovery_page_size": 100,
            "discovery_max_pages_per_source": 1,
            "discovery_evidence_chars": 600,
        })
        with mock.patch.object(
                explorer, "reddit_sub_page") as pager:
            with self.assertRaisesRegex(
                    explorer.DiscoveryConfigError, "aggregate retained evidence"):
                explorer.discovery_evidence(self.cfg, self.brief("only"))

        pager.assert_not_called()

    def test_actual_serialized_evidence_is_bounded_before_model_call(self):
        oversized = evidence(1, text="😀" * 30_000)
        oversized["source_provenance"] = ["reddit:r/only"]
        with mock.patch.object(
                explorer, "discovery_evidence", return_value=[oversized]), \
             mock.patch.object(explorer, "call_json") as decision, \
             mock.patch.object(explorer, "append_lessons"):
            with self.assertRaisesRegex(
                    explorer.DiscoveryConfigError, "serialized discovery evidence"):
                explorer.propose_candidates(
                    self.cfg, "context", "ai-releases", self.brief("only"), [], [])

        decision.assert_not_called()

    def test_candidates_must_bind_to_evidence_and_never_exceed_cap(self):
        self.cfg["sources"]["explorer_max_candidates_per_run"] = 1
        self.cfg["kickstart"]["explorer_max_candidates_per_run"] = 1
        item = evidence(
            1,
            text=("body names @body_origin and u/reddit_body as originators"),
            linked_source="x/@linked_origin",
        )
        item["publisher"] = "reddit/u/publisher_origin"
        proposed = [
            {"platform": "x", "handle": "hallucination", "rationale": "not present"},
            {"platform": "x", "handle": "linked_origin", "rationale": "linked"},
            {"platform": "reddit", "handle": "publisher_origin",
             "rationale": "publisher"},
            {"platform": "x", "handle": "body_origin", "rationale": "body"},
            {"platform": "reddit", "handle": "reddit_body", "rationale": "body"},
        ]
        appended = []

        with mock.patch.object(
                explorer, "reddit_sub_page",
                return_value=sources.DiscoveryPage([item], "")), \
             mock.patch.object(explorer, "call_json",
                               return_value={"candidates": proposed}), \
             mock.patch.object(explorer, "append_lessons"), \
             mock.patch.object(explorer, "append_tsv",
                               side_effect=lambda _path, row: appended.append(row)):
            added = explorer.propose_candidates(
                self.cfg, "context", "ai-releases", self.brief("only"), [], [])

        self.assertEqual(1, added)
        self.assertEqual(["linked_origin"], [row["handle"] for row in appended])

    def test_normalized_publisher_identity_can_bind_a_reddit_candidate(self):
        item = evidence(1)
        item["publisher"] = "Reddit/U/Publisher_Origin"
        appended = []

        with mock.patch.object(
                explorer, "reddit_sub_page",
                return_value=sources.DiscoveryPage([item], "")), \
             mock.patch.object(explorer, "call_json", return_value={
                 "candidates": [{
                     "platform": "reddit", "handle": "publisher_origin",
                     "rationale": "the original publisher",
                 }]}), \
             mock.patch.object(explorer, "append_lessons"), \
             mock.patch.object(explorer, "append_tsv",
                               side_effect=lambda _path, row: appended.append(row)):
            added = explorer.propose_candidates(
                self.cfg, "context", "ai-releases", self.brief("only"), [], [])

        self.assertEqual(1, added)
        self.assertEqual("publisher_origin", appended[0]["handle"])

    def test_candidate_platform_and_handle_must_be_actual_strings(self):
        item = evidence(1, text="@true @123 @none @valid_origin")
        proposed = [
            {"platform": "x", "handle": True, "rationale": "boolean"},
            {"platform": "x", "handle": 123, "rationale": "number"},
            {"platform": "x", "handle": None, "rationale": "null"},
            {"platform": ["x"], "handle": "valid_origin", "rationale": "list"},
            {"platform": "x", "handle": {"name": "valid_origin"},
             "rationale": "object"},
            {"platform": "x", "handle": "valid_origin", "rationale": "valid"},
        ]
        appended = []

        with mock.patch.object(
                explorer, "reddit_sub_page",
                return_value=sources.DiscoveryPage([item], "")), \
             mock.patch.object(explorer, "call_json",
                               return_value={"candidates": proposed}), \
             mock.patch.object(explorer, "append_lessons"), \
             mock.patch.object(explorer, "append_tsv",
                               side_effect=lambda _path, row: appended.append(row)):
            added = explorer.propose_candidates(
                self.cfg, "context", "ai-releases", self.brief("only"), [], [])

        self.assertEqual(1, added)
        self.assertEqual(["valid_origin"], [row["handle"] for row in appended])

    def test_body_url_grounding_rejects_spoofed_hosts_and_validates_boundaries(self):
        row = explorer._normalize_discovery_entry(evidence(1, text=(
            "evilx.com/fakeorigin fake-twitter.com/fakeorigin "
            "notreddit.com/u/fakeorigin evilreddit.com/user/fakeorigin "
            "x.com/badending.extra reddit.com/u/badending/extra "
            "sub.x.com/sub_origin //x.com/protocol_origin "
            "ftp://x.com/ftp_origin prefix/x.com/path_origin "
            "evil_x.com/underscore_origin"
        )), 800)
        self.assertIsNotNone(row)
        for platform, handle in (
                ("x", "fakeorigin"), ("reddit", "fakeorigin"),
                ("x", "badending"), ("reddit", "badending"),
                ("x", "sub_origin"), ("x", "protocol_origin"),
                ("x", "ftp_origin"), ("x", "path_origin"),
                ("x", "underscore_origin")):
            self.assertFalse(explorer._candidate_grounded(platform, handle, [row]))

        valid = explorer._normalize_discovery_entry(evidence(2, text=(
            "(https://x.com/http_origin/status/123), "
            "twitter.com/bare_origin; "
            "[https://reddit.com/u/reddit_origin]. "
            "not-a-host @mention_origin!"
        )), 800)
        self.assertTrue(explorer._candidate_grounded("x", "http_origin", [valid]))
        self.assertTrue(explorer._candidate_grounded("x", "bare_origin", [valid]))
        self.assertTrue(explorer._candidate_grounded("reddit", "reddit_origin", [valid]))
        self.assertTrue(explorer._candidate_grounded("x", "mention_origin", [valid]))

    def test_body_url_grounding_rejects_unicode_prefixes_and_empty_segments(self):
        row = explorer._normalize_discovery_entry(evidence(1, text=(
            "éx.com/unicode_origin éreddit.com/u/unicode_reddit "
            "x.com//double_origin x.com/status_origin//status/123 "
            "reddit.com//u/double_reddit reddit.com/u//empty_reddit"
        )), 800)
        self.assertIsNotNone(row)
        for platform, handle in (
                ("x", "unicode_origin"), ("reddit", "unicode_reddit"),
                ("x", "double_origin"), ("x", "status_origin"),
                ("reddit", "double_reddit"), ("reddit", "empty_reddit")):
            with self.subTest(platform=platform, handle=handle):
                self.assertFalse(
                    explorer._candidate_grounded(platform, handle, [row]))

    def test_body_grounding_rejects_idna_dots_and_unicode_mention_prefixes(self):
        row = explorer._normalize_discovery_entry(evidence(1, text=(
            "。x.com/ideo_x ．x.com/full_x "
            "｡reddit.com/u/half_reddit "
            "\u0301@mn_origin \u093e@mc_origin \u20dd@me_origin "
            "\u203f@pc_origin \u0301u/mn_reddit \u203fu/pc_reddit"
        )), 800)
        self.assertIsNotNone(row)
        for platform, handle in (
                ("x", "ideo_x"), ("x", "full_x"),
                ("reddit", "half_reddit"), ("x", "mn_origin"),
                ("x", "mc_origin"), ("x", "me_origin"),
                ("x", "pc_origin"), ("reddit", "mn_reddit"),
                ("reddit", "pc_reddit")):
            with self.subTest(platform=platform, handle=handle):
                self.assertFalse(
                    explorer._candidate_grounded(platform, handle, [row]))


class RedditDiscoveryProviderTests(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(lib.load_config())

    @staticmethod
    def listing(children, after=""):
        return {"data": {"children": [{"data": child} for child in children],
                         "after": after or None}}

    def test_provider_keeps_body_publisher_linked_identity_and_cursor(self):
        child = {
            "id": "abc123",
            "created_utc": 1_700_000_000,
            "permalink": "/r/test/comments/abc123/example/",
            "title": "ordinary title",
            "selftext": "body-only @originator evidence",
            "author": "observer",
            "url_overridden_by_dest": "https://x.com/originator/status/999",
        }
        response = self.listing([child], after="next-cursor")

        with mock.patch.object(sources, "_get_json", return_value=response) as get:
            page = sources.reddit_sub_page("test", "prior", 20, self.cfg)

        self.assertFalse(page.failed)
        self.assertEqual("next-cursor", page.next_cursor)
        self.assertEqual("reddit:abc123", page.items[0]["canonical_id"])
        self.assertEqual("reddit/u/observer", page.items[0]["publisher"])
        self.assertEqual("x/@originator", page.items[0]["linked_source"])
        self.assertIn("body-only @originator evidence", page.items[0]["text"])
        self.assertIn("limit=20", get.call_args.args[0])
        self.assertIn("after=prior", get.call_args.args[0])

    def test_provider_rejects_malformed_rows_but_keeps_valid_siblings(self):
        good = {
            "id": "good",
            "created_utc": 1_700_000_000,
            "permalink": "/r/test/comments/good/example/",
            "title": "good",
            "selftext": "substantive body",
            "author": "observer",
            "url": "https://example.com/report",
        }
        malformed = {**good, "id": "bad id", "permalink": "javascript:bad"}
        response = self.listing([malformed, good])

        with mock.patch.object(sources, "_get_json", return_value=response):
            page = sources.reddit_sub_page("test", "", 20, self.cfg)

        self.assertEqual(["reddit:good"],
                         [item["canonical_id"] for item in page.items])

    def test_provider_rejects_traversal_encoded_traversal_and_id_mismatch(self):
        def child(stable_id, permalink):
            return {
                "id": stable_id,
                "created_utc": 1_700_000_000,
                "permalink": permalink,
                "title": "title",
                "selftext": "substantive body",
                "author": "observer",
                "url": "https://example.com/report",
            }

        children = [
            child("plain", "/r/test/comments/../plain/title/"),
            child("encoded", "/r/test/comments/%2e%2e/encoded/title/"),
            child("double", "/r/test/comments/%252e%252e/double/title/"),
            child("slash", "/r/test/comments/slash%2f../title/"),
            child("expected", "/r/test/comments/different/title/"),
            child("wrongshape", "/user/observer/comments/wrongshape/title/"),
            child("good", "/r/test/comments/good/a-title-that-is-not-canonical/"),
        ]

        with mock.patch.object(
                sources, "_get_json", return_value=self.listing(children)):
            page = sources.reddit_sub_page("test", "", 20, self.cfg)

        self.assertEqual(["reddit:good"],
                         [item["canonical_id"] for item in page.items])
        self.assertEqual("https://www.reddit.com/r/test/comments/good/",
                         page.items[0]["canonical_url"])

    def test_provider_failure_has_an_explicit_isolated_contract(self):
        with mock.patch.object(sources, "_get_json", side_effect=OSError("down")):
            page = sources.reddit_sub_page("test", "", 20, self.cfg)

        self.assertTrue(page.failed)
        self.assertEqual([], page.items)
        self.assertEqual("", page.next_cursor)

    def test_provider_enforces_requested_page_size_before_normalizing(self):
        children = []
        for number in range(50):
            stable_id = f"a{number:x}"
            children.append({
                "id": stable_id,
                "created_utc": 1_700_000_000 + number,
                "permalink": f"/r/test/comments/{stable_id}/title/",
                "title": f"title {number}",
                "selftext": f"body {number}",
                "author": "observer",
                "url": "https://example.com/report",
            })

        with mock.patch.object(
                sources, "_get_json", return_value=self.listing(children)):
            page = sources.reddit_sub_page("test", "", 1, self.cfg)

        self.assertEqual(["reddit:a0"],
                         [item["canonical_id"] for item in page.items])

    def test_raw_text_is_sliced_before_control_scans_and_normalization(self):
        self.cfg["sources"]["discovery_evidence_chars"] = 600
        huge_tail = "\x00" + ("x" * 4_100_000)
        child = {
            "id": "bounded",
            "created_utc": 1_700_000_000,
            "permalink": "/r/test/comments/bounded/title/",
            "title": (" " * 600) + huge_tail,
            "selftext": "bounded body evidence" + ("y" * 600) + huge_tail,
            "author": "observer",
            "url": "https://example.com/report",
        }

        with mock.patch.object(
                sources, "_get_json", return_value=self.listing([child])):
            page = sources.reddit_sub_page("test", "", 1, self.cfg)

        self.assertEqual(1, len(page.items))
        self.assertTrue(page.items[0]["text"].startswith("bounded body evidence"))
        self.assertLessEqual(len(page.items[0]["text"]), 600)

        raw = evidence(1, text=("safe evidence" + ("z" * 600) + huge_tail))
        normalized = explorer._normalize_discovery_entry(raw, 600)
        self.assertIsNotNone(normalized)
        self.assertLessEqual(len(normalized["text"]), 600)

    def test_linked_source_rejects_reserved_and_malformed_x_routes(self):
        reserved = (
            "https://x.com/i/status/123",
            "https://x.com/intent/tweet",
            "https://x.com/home",
            "https://twitter.com/i/status/123",
            "https://twitter.com/intent/tweet",
            "https://twitter.com/home",
            "https://x.com/valid_origin/status/not-a-number",
            "https://x.com/valid_origin/likes",
            "https://x.com/premium",
            "https://x.com/business",
            "https://x.com/developers",
            "https://x.com/ads",
            "https://x.com/communities/123",
            "https://twitter.com/premium",
        )
        for url in reserved:
            with self.subTest(url=url):
                self.assertEqual("x.com", sources._linked_source_identity(url))

        valid = {
            "https://x.com/profile_origin": "x/@profile_origin",
            "https://x.com/status_origin/status/123": "x/@status_origin",
            "https://twitter.com/profile_origin/": "x/@profile_origin",
            "https://twitter.com/status_origin/status/456": "x/@status_origin",
        }
        for url, identity in valid.items():
            with self.subTest(url=url):
                self.assertEqual(identity, sources._linked_source_identity(url))

    def test_linked_source_rejects_empty_segments_userinfo_and_ports(self):
        malformed_routes = (
            "https://x.com//profile_origin",
            "https://x.com/profile_origin//status/123",
            "https://twitter.com//profile_origin",
        )
        for url in malformed_routes:
            with self.subTest(url=url):
                self.assertEqual("x.com", sources._linked_source_identity(url))

        unsafe_authorities = (
            "https://user@x.com/profile_origin",
            "https://user:pass@twitter.com/profile_origin",
            "https://x.com:443/profile_origin",
            "https://twitter.com:8443/profile_origin",
        )
        for url in unsafe_authorities:
            with self.subTest(url=url):
                self.assertEqual("", sources._linked_source_identity(url))


if __name__ == "__main__":
    unittest.main()
