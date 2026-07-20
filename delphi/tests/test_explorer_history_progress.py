from __future__ import annotations

import re
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import explorer  # noqa: E402
import lib  # noqa: E402
import sources  # noqa: E402


class ExplorerHistoryProgressTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "thresholds": {
                "verify_min_calls": 10, "verify_min_edge": 0.05,
                "verify_z": 1.2816,
            },
            "call_classes": {"d": ["timing", "existence", "unclassified"]},
        }
        self.candidate = {
            "platform": "x", "handle": "source", "rationale": "test",
            "_start": "2025-01-01T00:00:00Z", "_limit": 100,
            "_call_class": "-",
        }

    @staticmethod
    def _posts(count: int) -> list[dict]:
        return [{
            "id": f"{i:03d}",
            "ts": lib.unix_to_iso(1_735_689_600 + i),
            "url": f"https://x.com/source/status/{i:03d}",
            "text": f"post {i}",
        } for i in range(count)]

    def _run(self, ddir: Path, progress: list[dict], fetch, inspected: set[str],
             candidate: dict | None = None, updates=None):
        def llm(_role, prompt, _cfg):
            if "Perform Task B now" in prompt:
                inspected.update(re.findall(r"status/(\d{3})", prompt))
                return {"claims": []}
            self.fail("no mapping request is expected when every post is a miss")

        with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
              mock.patch.object(explorer, "fetch_history_page", side_effect=fetch),
              mock.patch.object(
                  explorer, "fetch_history_updates",
                  side_effect=(updates or (lambda *_args: sources.HistoryUpdates(
                      [], caught_up=True, provider="x_api")))),
              mock.patch.object(explorer, "call_json", side_effect=llm),
              mock.patch.object(explorer, "append_lessons")):
            return explorer.run_history_page(
                self.cfg, "context", "d", "brief", [],
                candidate or self.candidate, set(), progress)

    def test_capped_150_posts_advance_across_restart_and_include_oldest_misses(self):
        dataset = self._posts(150)
        requests = []

        def capped_provider(_platform, _handle, start_iso, before, limit, _cfg):
            requests.append((start_iso, before, limit))
            eligible = [post for post in dataset
                        if before is None or sources.post_key(post) < before]
            page = sorted(eligible, key=sources.post_key, reverse=True)[:limit]
            return sources.HistoryPage(
                page, exhausted=len(eligible) <= limit, provider="x_api")

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            inspected: set[str] = set()

            progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
            _summary, terminal = self._run(ddir, progress, capped_provider, inspected)
            self.assertFalse(terminal)

            # A new read simulates a fresh process after the first durable run.
            progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
            _summary, terminal = self._run(ddir, progress, capped_provider, inspected)
            self.assertTrue(terminal)
            progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)

        self.assertEqual({f"{i:03d}" for i in range(150)}, inspected)
        self.assertIsNone(requests[0][1])
        self.assertEqual(sources.post_key(dataset[50]), requests[1][1])
        self.assertEqual("exhausted", progress[0]["status"])
        self.assertEqual(sources.post_key(dataset[0]),
                         (progress[0]["before_ts"], progress[0]["before_id"]))

    def test_new_arrival_is_drained_before_the_next_backward_page(self):
        dataset = self._posts(150)
        inspected: set[str] = set()

        def backward(_platform, _handle, _start, before, limit, _cfg):
            eligible = [post for post in dataset
                        if before is None or sources.post_key(post) < before]
            page = sorted(eligible, key=sources.post_key, reverse=True)[:limit]
            return sources.HistoryPage(
                page, exhausted=len(eligible) <= limit, provider="x_api")

        def updates(_platform, _handle, newest_ts, seen_ids, limit, _cfg):
            eligible = sorted((post for post in dataset
                               if post["ts"] > newest_ts
                               or (post["ts"] == newest_ts
                                   and post["id"] not in seen_ids)),
                              key=sources.post_key)
            return sources.HistoryUpdates(
                eligible[:limit], caught_up=len(eligible) <= limit,
                provider="x_api")

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            progress = []
            self._run(ddir, progress, backward, inspected, updates=updates)

            # Exact verifier repro: a newer post arrives while backward state
            # is durably parked at post 050.
            dataset.append({
                "id": "150", "ts": lib.unix_to_iso(1_735_689_750),
                "url": "https://x.com/source/status/150", "text": "new",
            })
            progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
            _summary, terminal = self._run(
                ddir, progress, backward, inspected, updates=updates)
            row = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)[0]

        self.assertTrue(terminal)
        self.assertEqual({f"{i:03d}" for i in range(151)}, inspected)
        self.assertEqual((dataset[-1]["ts"], "150"),
                         (row["newest_ts"], json.loads(row["newest_ids"])[-1]))
        self.assertEqual((dataset[0]["ts"], "000"),
                         (row["before_ts"], row["before_id"]))

    def test_reddit_late_same_timestamp_ids_survive_multiple_restarts(self):
        ts = "2026-01-01T00:00:00Z"

        def post(stable_id):
            return {"id": stable_id, "ts": ts,
                    "url": f"https://reddit.test/status/{stable_id}", "text": stable_id}

        indexed = [post("z")]
        inspected: set[str] = set()
        candidate = {
            "platform": "reddit", "handle": "source", "rationale": "test",
            "_provider": "reddit", "_start": "2025-01-01T00:00:00Z",
            "_limit": 100, "_call_class": "-",
        }

        def backward(*_args):
            return sources.HistoryPage([indexed[0]], exhausted=True,
                                       provider="reddit")

        def updates(_platform, _handle, newest_ts, seen_ids, _limit, _cfg):
            unseen = [item for item in indexed
                      if item["ts"] > newest_ts
                      or (item["ts"] == newest_ts and item["id"] not in seen_ids)]
            return sources.HistoryUpdates(unseen, caught_up=True, provider="reddit")

        def llm(_role, prompt, _cfg):
            if "Perform Task B now" in prompt:
                inspected.update(re.findall(r"status/([^\s]+)", prompt))
            return {"claims": []}

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
                  mock.patch.object(explorer, "fetch_history_page", side_effect=backward),
                  mock.patch.object(explorer, "fetch_history_updates", side_effect=updates),
                  mock.patch.object(explorer, "call_json", side_effect=llm),
                  mock.patch.object(explorer, "append_lessons")):
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], candidate, set(), [])
                indexed.append(post("10"))  # base36 36, but raw lexical < "z"
                progress = explorer.load_history_progress(ddir)
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], candidate, set(), progress)
                indexed.extend([post("0y"), post("11")])
                progress = explorer.load_history_progress(ddir)
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], candidate, set(), progress)

            row = explorer.load_history_progress(ddir)[0]

        self.assertEqual({"z", "10", "0y", "11"}, inspected)
        self.assertEqual({"z", "10", "0y", "11"},
                         set(json.loads(row["newest_ids"])))

    def test_equal_timestamp_overlap_is_filtered_before_advancing(self):
        ts = "2026-01-01T00:00:00Z"
        first = [{"id": f"{i:03d}", "ts": ts, "url": f"u/{i:03d}", "text": ""}
                 for i in range(150, 50, -1)]
        overlap = [{"id": f"{i:03d}", "ts": ts, "url": f"u/{i:03d}", "text": ""}
                   for i in range(55, 0, -1)]
        calls = 0

        def provider(_platform, _handle, _start, _before, _limit, _cfg):
            nonlocal calls
            calls += 1
            return sources.HistoryPage(first if calls == 1 else overlap,
                                       exhausted=calls == 2, provider="reddit")

        def llm(_role, prompt, _cfg):
            return {"claims": []}

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
                  mock.patch.object(explorer, "fetch_history_page", side_effect=provider),
                  mock.patch.object(explorer, "fetch_history_updates", return_value=
                                    sources.HistoryUpdates(
                                        [], caught_up=True, provider="reddit")),
                  mock.patch.object(explorer, "call_json", side_effect=llm),
                  mock.patch.object(explorer, "append_lessons")):
                progress = []
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], self.candidate, set(), progress)
                progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], self.candidate, set(), progress)

            row = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)[0]

        # IDs 055..051 overlap the prior page and must not move/repeat the cursor.
        self.assertEqual((ts, "001"), (row["before_ts"], row["before_id"]))
        self.assertEqual("exhausted", row["status"])

    def test_unknown_completeness_and_transient_failures_never_advance(self):
        posts = self._posts(100)
        pages = [
            sources.HistoryPage(list(reversed(posts)), exhausted=False, provider="exa",
                                coverage_gap="search results are capped and unordered",
                                prefix_complete=False),
            sources.HistoryPage([], exhausted=False, provider="x_api",
                                retryable_error="HTTP 429"),
            sources.HistoryPage(list(reversed(posts)), exhausted=False,
                                provider="x_api"),
        ]
        inspected: set[str] = set()

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            for expected_status in ("coverage_gap", "retryable_error", "active"):
                progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
                self._run(ddir, progress, lambda *_args: pages.pop(0), inspected)
                row = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)[0]
                self.assertEqual(expected_status, row["status"])
                if expected_status != "active":
                    self.assertEqual(("", ""), (row["before_ts"], row["before_id"]))

        self.assertEqual({f"{i:03d}" for i in range(100)}, inspected)

    def test_deepening_is_selected_per_unverified_call_class(self):
        leakers = [
            {"leaker_id": "x-source", "platform": "x", "handle": "source",
             "call_class": "timing", "status": "verified", "n_calls": "12"},
            {"leaker_id": "x-source", "platform": "x", "handle": "source",
             "call_class": "existence", "status": "probation", "n_calls": "4"},
            {"leaker_id": "reddit-other", "platform": "reddit", "handle": "other",
             "call_class": "timing", "status": "candidate", "n_calls": "1"},
        ]

        targets = explorer.deepen_targets(leakers, 10)

        self.assertEqual(
            [("reddit-other", "timing"), ("x-source", "existence")],
            [(target["platform"] + "-" + target["handle"],
              target["_call_class"]) for target in targets])

    def test_new_class_progress_inherits_standard_boundary_and_targets_class(self):
        standard = {
            "provider": "exa", "platform": "x", "handle": "source",
            "call_class": "-",
            "window_start": "2025-01-01T00:00:00Z",
            "newest_ts": "2026-01-01T00:00:00Z", "newest_ids": '["100"]',
            "before_ts": "2025-06-01T00:00:00Z", "before_id": "050",
            "status": "active", "detail": "",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        candidate = {**self.candidate, "_call_class": "existence"}
        requested = []
        prompts = []

        def provider(_platform, _handle, _start, before, _limit, _cfg):
            requested.append(before)
            post = {"id": "049", "ts": "2025-05-01T00:00:00Z",
                    "url": "u/049", "text": "claim"}
            return sources.HistoryPage([post], exhausted=True, provider="x_api")

        def llm(_role, prompt, _cfg):
            prompts.append(prompt)
            return {"claims": []}

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            lib.write_tsv(ddir / explorer.HISTORY_PROGRESS_FILE, [standard])
            progress = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)
            with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
                  mock.patch.object(explorer, "fetch_history_page", side_effect=provider),
                  mock.patch.object(explorer, "fetch_history_updates", return_value=
                                    sources.HistoryUpdates(
                                        [], caught_up=True, provider="x_api")),
                  mock.patch.object(explorer, "call_json", side_effect=llm),
                  mock.patch.object(explorer, "append_lessons")):
                explorer.run_history_page(
                    self.cfg, "", "d", "", [], candidate, set(), progress)

        self.assertEqual([("2025-06-01T00:00:00Z", "050")], requested)
        self.assertTrue(any("TARGET CALL CLASS\nexistence" in prompt for prompt in prompts))

    def test_qualification_failure_keeps_the_same_page_retryable(self):
        posts = self._posts(21)
        attempts = 0

        def provider(_platform, _handle, _start, _before, _limit, _cfg):
            return sources.HistoryPage(
                list(reversed(posts)), exhausted=True, provider="x_api")

        def llm(_role, _prompt, _cfg):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                return None
            return {"claims": []}

        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            explorer.ensure_history_progress_file(ddir)
            with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
                  mock.patch.object(explorer, "fetch_history_page", side_effect=provider),
                  mock.patch.object(explorer, "call_json", side_effect=llm),
                  mock.patch.object(explorer, "append_lessons")):
                progress = []
                _summary, terminal = explorer.run_history_page(
                    self.cfg, "", "d", "", [], self.candidate, set(), progress)

            row = lib.read_tsv(ddir / explorer.HISTORY_PROGRESS_FILE)[0]

        self.assertFalse(terminal)
        self.assertEqual("retryable_error", row["status"])
        self.assertEqual(("", ""), (row["before_ts"], row["before_id"]))

    def test_progress_is_isolated_when_the_x_provider_changes(self):
        progress = [{
            "provider": "exa", "platform": "x", "handle": "source",
            "call_class": "-", "window_start": "2025-01-01T00:00:00Z",
            "before_ts": "2025-06-01T00:00:00Z", "before_id": "050",
            "status": "active", "detail": "", "updated_at": "earlier",
        }]
        cfg = {"sources": {"x_backend": "x_api", "x_bearer_env": "TOKEN",
                           "exa_api_key_env": "EXA"}}
        with mock.patch.dict(sources.os.environ, {"TOKEN": "secret"}, clear=True):
            row = explorer._progress_row(progress, self.candidate, cfg)

        self.assertEqual(2, len(progress))
        self.assertEqual("x_api", row["provider"])
        self.assertEqual(("", ""), (row["before_ts"], row["before_id"]))

    def test_partial_progress_row_fails_closed_without_replacing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            path = ddir / explorer.HISTORY_PROGRESS_FILE
            original = ("\t".join(explorer.HISTORY_PROGRESS_COLUMNS)
                        + "\nx_api\tx\tsource\n")
            path.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(explorer.HistoryProgressError,
                                        "invalid row 1"):
                explorer.load_history_progress(ddir)

            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_progress_requires_exact_header_unique_keys_and_canonical_fields(self):
        valid = {
            "provider": "x_api", "platform": "x", "handle": "source",
            "call_class": "timing", "window_start": "2025-01-01T00:00:00Z",
            "newest_ts": "2026-01-01T00:00:00Z", "newest_ids": '["100"]',
            "before_ts": "2025-06-01T00:00:00Z", "before_id": "050",
            "status": "active", "detail": "ok",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        explorer.validate_history_progress([valid])
        bad_cases = [
            [valid, dict(valid)],
            [{**valid, "before_id": ""}],
            [{**valid, "window_start": "2025-01-01"}],
            [{**valid, "status": "done"}],
            [{**valid, "handle": ""}],
        ]
        for rows in bad_cases:
            with self.subTest(rows=rows), self.assertRaises(
                    explorer.HistoryProgressError):
                explorer.validate_history_progress(rows)

    def test_startup_reconciles_cursor_ahead_of_durable_leaker_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            production = Path(__file__).resolve().parents[1] / "domains" / "ai-releases"
            for name in ("signals.tsv", "leakers.tsv"):
                header = (production / name).read_text(encoding="utf-8").splitlines()[0]
                (ddir / name).write_text(header + "\n", encoding="utf-8")
            lib.append_tsv(ddir / "leakers.tsv", {
                "leaker_id": "x-source", "platform": "x", "handle": "source",
                "domain": "d", "call_class": "timing", "status": "candidate",
                "n_calls": 0, "hits": 0,
            })
            lib.append_tsv(ddir / "signals.tsv", {
                "signal_id": "hist-1", "ts_detected": "2026-01-02T00:00:00Z",
                "domain": "d", "leaker_id": "x-source", "platform": "x",
                "post_url": "u/1", "post_ts": "2026-01-01T00:00:00Z",
                "source_post_id": "source-1",
                "claim": "claim", "call_class": "timing", "hedged": "false",
                "market_id": "m1", "event_id": "e1", "side": "YES",
                "price_at_signal": "0.400", "status": "historical",
                "resolved_outcome": "YES", "stat_counted": "true",
            })
            leakers = lib.read_tsv(ddir / "leakers.tsv")

            explorer.reconcile_history_projection(ddir, leakers, self.cfg, "d")
            recovered = lib.read_tsv(ddir / "leakers.tsv")[0]

        self.assertEqual(("1", "1", "1.000"),
                         (recovered["n_calls"], recovered["hits"],
                          recovered["hit_rate"]))

    def test_leaker_projection_is_durable_before_cursor_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            ddir = Path(tmp)
            production = Path(__file__).resolve().parents[1] / "domains" / "ai-releases"
            header = (production / "leakers.tsv").read_text(
                encoding="utf-8").splitlines()[0]
            (ddir / "leakers.tsv").write_text(header + "\n", encoding="utf-8")
            lib.append_tsv(ddir / "leakers.tsv", {
                "leaker_id": "x-source", "platform": "x", "handle": "source",
                "domain": "d", "call_class": "timing", "status": "candidate",
                "n_calls": 0, "hits": 0,
            })
            explorer.ensure_history_progress_file(ddir)
            leakers = lib.read_tsv(ddir / "leakers.tsv")
            post = self._posts(1)[0]
            real_persist = explorer._persist_progress

            def qualify(*_args, **_kwargs):
                leakers[0]["n_calls"] = 1
                leakers[0]["hits"] = 1
                return "scored", True

            def cursor_write(path, progress):
                persisted = lib.read_tsv(ddir / "leakers.tsv")[0]
                self.assertEqual("1", persisted["n_calls"])
                real_persist(path, progress)

            with (mock.patch.object(explorer, "domain_dir", return_value=ddir),
                  mock.patch.object(explorer, "fetch_history_page", return_value=
                                    sources.HistoryPage(
                                        [post], exhausted=True, provider="x_api")),
                  mock.patch.object(explorer, "qualify", side_effect=qualify),
                  mock.patch.object(explorer, "_persist_progress",
                                    side_effect=cursor_write)):
                explorer.run_history_page(
                    self.cfg, "", "d", "", leakers, self.candidate, set(), [])


class HistoryProviderContractTests(unittest.TestCase):
    @staticmethod
    def reddit_page(numbers, after):
        return {"data": {"after": after, "children": [
            {"data": {"id": f"{i:03d}", "created_utc": i,
                      "permalink": f"/u/source/{i:03d}", "title": str(i)}}
            for i in numbers
        ]}}

    def test_reddit_history_page_uses_cursor_pages_and_explicit_exhaustion(self):
        pages = [self.reddit_page(range(150, 50, -1), "next"),
                 self.reddit_page(range(50, 0, -1), None)]
        cfg = {"sources": {"reddit_user_agent": "test"}}
        with mock.patch.object(sources, "_get_json", side_effect=pages) as request:
            page = sources.fetch_history_page(
                "reddit", "source", lib.unix_to_iso(1),
                (lib.unix_to_iso(51), "051"), 100, cfg)

        self.assertEqual(2, request.call_count)
        self.assertTrue(page.exhausted)
        self.assertEqual([f"{i:03d}" for i in range(50, 0, -1)],
                         [post["id"] for post in page.posts])

    def test_reddit_terminal_before_window_is_coverage_gap_not_exhaustion(self):
        page_data = self.reddit_page(range(100, 49, -1), None)
        cfg = {"sources": {"reddit_user_agent": "test"}}
        with mock.patch.object(sources, "_get_json", return_value=page_data):
            page = sources.fetch_history_page(
                "reddit", "source", "1970-01-01T00:00:00Z", None, 100, cfg)

        self.assertTrue(page.coverage_gap)
        self.assertFalse(page.exhausted)

    def test_reddit_updates_include_unseen_id_below_raw_lexical_frontier(self):
        epoch = 1767225600
        data = {"data": {"after": None, "children": [
            {"data": {"id": stable_id, "created_utc": created,
                      "permalink": f"/u/source/{stable_id}", "title": stable_id}}
            for stable_id, created in (("z", epoch), ("10", epoch), ("y", epoch - 1))
        ]}}
        cfg = {"sources": {"reddit_user_agent": "test"}}
        with mock.patch.object(sources, "_get_json", return_value=data):
            updates = sources.fetch_history_updates(
                "reddit", "source", lib.unix_to_iso(epoch), {"z"}, 100, cfg)

        self.assertTrue(updates.caught_up)
        self.assertEqual(["10"], [post["id"] for post in updates.posts])
        self.assertLess(sources.provider_id_key("reddit", "z"),
                        sources.provider_id_key("reddit", "10"))
        self.assertLess(sources.provider_id_key("x_api", "9"),
                        sources.provider_id_key("x_api", "10"))

    def test_exa_even_one_result_is_an_explicit_coverage_gap(self):
        posts = [{"id": "1", "ts": "2026-01-01T00:00:00Z",
                  "url": "u/1", "text": ""}]
        cfg = {"sources": {"x_backend": "exa", "exa_api_key_env": "EXA",
                           "x_bearer_env": "TOKEN"}}
        with (mock.patch.dict(sources.os.environ, {"EXA": "secret"}, clear=False),
              mock.patch.object(sources, "_exa_query", return_value=posts)):
            page = sources.fetch_history_page(
                "x", "source", "2025-01-01T00:00:00Z", None, 100, cfg)

        self.assertEqual("exa", page.provider)
        self.assertTrue(page.coverage_gap)
        self.assertFalse(page.exhausted)

    def test_exa_refresh_uses_contents_max_age_not_deprecated_livecrawl(self):
        bodies = []

        def post(_url, body, _headers):
            bodies.append(body)
            return {"results": []}

        cfg = {"sources": {"exa_api_key_env": "EXA"}}
        with (mock.patch.dict(sources.os.environ, {"EXA": "secret"}),
              mock.patch.object(sources, "_post_json", side_effect=post)):
            sources._exa_query("source", None, None, cfg, 10)

        self.assertEqual(0, bodies[0]["contents"]["maxAgeHours"])
        self.assertNotIn("livecrawl", bodies[0])

    def test_x_api_paginates_past_equal_timestamp_boundary_to_exhaustion(self):
        ts = "2026-01-01T00:00:00Z"
        first = {"data": [
            {"id": f"{i:03d}", "created_at": ts, "text": str(i)}
            for i in range(150, 50, -1)
        ], "meta": {"next_token": "next"}}
        second = {"data": [
            {"id": f"{i:03d}", "created_at": ts, "text": str(i)}
            for i in range(50, 0, -1)
        ], "meta": {}}
        cfg = {"sources": {"x_backend": "x_api", "x_bearer_env": "TOKEN",
                           "exa_api_key_env": "EXA"}}
        responses = [{"data": {"id": "uid"}}, first, second]
        with (mock.patch.dict(sources.os.environ, {"TOKEN": "secret"}, clear=True),
              mock.patch.object(sources, "_get_json", side_effect=responses) as request):
            page = sources.fetch_history_page(
                "x", "source", ts, (ts, "080"), 100, cfg)

        self.assertEqual(3, request.call_count)
        self.assertTrue(page.exhausted)
        self.assertEqual([f"{i:03d}" for i in range(79, 0, -1)],
                         [post["id"] for post in page.posts])

    def test_x_terminal_before_window_is_coverage_gap_not_exhaustion(self):
        timeline = {"data": [{
            "id": "1", "created_at": "2026-01-01T00:00:00Z", "text": "one",
        }], "meta": {}}
        cfg = {"sources": {"x_backend": "x_api", "x_bearer_env": "TOKEN",
                           "exa_api_key_env": "EXA"}}
        responses = [{"data": {"id": "uid"}}, timeline]
        with (mock.patch.dict(sources.os.environ, {"TOKEN": "secret"}, clear=True),
              mock.patch.object(sources, "_get_json", side_effect=responses)):
            page = sources.fetch_history_page(
                "x", "source", "2025-01-01T00:00:00Z", None, 100, cfg)

        self.assertTrue(page.coverage_gap)
        self.assertFalse(page.exhausted)

    def test_provider_exception_is_retryable_not_exhaustion(self):
        cfg = {"sources": {"reddit_user_agent": "test"}}
        with mock.patch.object(sources, "_get_json", side_effect=OSError("429")):
            page = sources.fetch_history_page(
                "reddit", "source", "2025-01-01T00:00:00Z", None, 100, cfg)

        self.assertIn("429", page.retryable_error)
        self.assertFalse(page.exhausted)


if __name__ == "__main__":
    unittest.main()
