from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


DELPHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DELPHI / "scripts"))

import explorer  # noqa: E402
import lib  # noqa: E402
import llm  # noqa: E402


class _HTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


class LLMBackendSmokeTests(unittest.TestCase):
    def test_every_configured_role_constructs_its_backend_without_network(self):
        cfg = lib.load_config()
        codex_calls = []

        def fake_run(cmd, **kwargs):
            codex_calls.append((cmd, kwargs))
            outfile = Path(cmd[cmd.index("--output-last-message") + 1])
            outfile.write_text("ok", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(llm, "tmp_dir", return_value=Path(tmp)), \
             patch.object(llm.subprocess, "run", side_effect=fake_run), \
             patch.object(llm.urllib.request, "urlopen", return_value=_HTTPResponse()) as urlopen:
            for role in cfg["roles"]:
                self.assertEqual("ok", llm.call(role, "smoke", cfg))

        self.assertEqual(4, len(codex_calls))
        self.assertTrue(all(call[1]["cwd"] == str(lib.ROOT) for call in codex_calls))
        urlopen.assert_not_called()


class ExplorerValidationTests(unittest.TestCase):
    def test_post_indices_must_be_nonnegative_in_range_and_in_current_chunk(self):
        posts = [
            {"ts": "2026-01-01T00:00:00Z", "url": "old"},
            {"ts": "2026-01-02T00:00:00Z", "url": "new"},
        ]
        raw = [
            {"post_index": -1, "claim": "negative"},
            {"post_index": 1.5, "claim": "fractional"},
            {"post_index": 2, "claim": "too large"},
            {"post_index": 0, "claim": "wrong chunk"},
            {"post_index": 1, "claim": "valid"},
        ]

        claims = explorer._canonical_claims(posts, raw, {1})

        self.assertEqual(["valid"], [claim["claim"] for claim in claims])
        self.assertEqual("new", claims[0]["post_url"])

    def test_mapping_accepts_only_exact_candidate_pairs(self):
        allowed = [(0, "market-a"), (1, "market-b")]
        raw = [
            {"claim_index": 0, "market_id": "market-a", "match": False},
            {"claim_index": 1, "market_id": "market-b", "match": False},
            {"claim_index": 0, "market_id": "market-b", "match": True},
        ]

        self.assertEqual({}, explorer._accepted_mappings(raw, allowed))
        self.assertIsNone(explorer._accepted_mappings(raw[2:], allowed))


class ExplorerCompletionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = lib.load_config()
        self.candidate = {
            "platform": "x", "handle": "source", "rationale": "test",
        }

    @staticmethod
    def _posts(count: int):
        # Deliberately newest-first, as the real source adapters return them.
        return [
            {
                "id": f"post-{i}",
                "ts": f"2026-01-{1 + i // 24:02d}T{i % 24:02d}:00:00Z",
                "url": f"post-{i}",
                "text": f"claim {i}",
            }
            for i in reversed(range(count))
        ]

    @staticmethod
    def _market(query: str):
        return {
            "id": f"market-{query}", "event_id": f"event-{query}",
            "question": query, "description": "criteria", "yes_token": query,
            "liquidity": 2000,
        }

    def test_all_claim_chunks_complete_before_global_oldest_first_scoring(self):
        posts = self._posts(45)
        rows = []
        task_counts = {"b": 0, "c": 0}

        def fake_llm(_role, prompt, _cfg):
            if "Perform Task B now" in prompt:
                task_counts["b"] += 1
                indices = [int(v) for v in re.findall(r"^- post_index (\d+) \|", prompt, re.M)]
                return {"claims": [
                    {"post_index": i, "claim": f"claim {i}",
                     "market_query": f"q{i}", "call_class": "release-timing"}
                    for i in indices
                ]}
            task_counts["c"] += 1
            pairs = re.findall(r"^- claim_index (\d+) \| market_id ([^ |]+)", prompt, re.M)
            return {"mappings": [
                {"claim_index": int(i), "market_id": market_id,
                 "match": True, "implied_side": "YES"}
                for i, market_id in pairs
            ]}

        with patch.object(explorer, "fetch_posts", return_value=posts), \
             patch.object(explorer, "call_json", side_effect=fake_llm), \
             patch.object(explorer, "append_lessons"), \
             patch.object(explorer.pm, "search_markets",
                          side_effect=lambda query, **_kwargs: [self._market(query)]), \
             patch.object(explorer.pm, "winning_side", return_value="YES"), \
             patch.object(explorer.pm, "price_at", return_value=0.4), \
             patch.object(explorer, "append_tsv", side_effect=lambda _path, row: rows.append(row)):
            summary, completed = explorer.qualify(
                self.cfg, "context", "ai-releases", "brief", [], self.candidate,
                set(), 100, "2025-01-01T00:00:00Z")

        self.assertTrue(completed)
        self.assertIn("45 claims", summary)
        self.assertEqual(45, len(rows))
        self.assertEqual(sorted(row["post_ts"] for row in rows),
                         [row["post_ts"] for row in rows])
        self.assertEqual({"b": 3, "c": 3}, task_counts)

    def test_failed_chunk_scores_nothing_and_remains_retryable(self):
        responses = [
            {"claims": [{"post_index": 0, "claim": "first",
                          "market_query": "first", "call_class": "release-timing"}]},
            None,
        ]
        leakers = []
        rows = []

        with patch.object(explorer, "fetch_posts", return_value=self._posts(21)), \
             patch.object(explorer, "call_json", side_effect=responses), \
             patch.object(explorer, "append_lessons"), \
             patch.object(explorer.pm, "search_markets") as search, \
             patch.object(explorer, "append_tsv", side_effect=lambda _path, row: rows.append(row)):
            _summary, completed = explorer.qualify(
                self.cfg, "context", "ai-releases", "brief", leakers, self.candidate,
                set(), 100, "2025-01-01T00:00:00Z")

        self.assertFalse(completed)
        self.assertEqual([], rows)
        self.assertEqual([], leakers)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
