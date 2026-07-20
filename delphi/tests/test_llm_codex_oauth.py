from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DELPHI = Path(__file__).resolve().parents[1]
SCRIPTS = DELPHI / "scripts"
sys.path.insert(0, str(SCRIPTS))

import llm  # noqa: E402


class CodexOAuthProviderTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((DELPHI / "config.json").read_text(encoding="utf-8"))

    def test_all_roles_use_codex_cli_and_judge_uses_schema(self):
        roles = self.cfg["roles"]
        self.assertEqual(set(roles), {"explorer", "heartbeat", "judge", "orchestrator"})
        self.assertTrue(all(role["backend"] == "codex-cli" for role in roles.values()))
        self.assertEqual(roles["judge"]["model"], "gpt-5.6-luna")
        self.assertEqual(roles["judge"]["reasoning"], "high")
        self.assertEqual(roles["judge"]["output_schema"], "schemas/judge-output.json")
        active = json.dumps(self.cfg).lower()
        for forbidden in ("open" + "router", "op" + "us"):
            self.assertNotIn(forbidden, active)

    def test_judge_schema_is_exact_and_strict(self):
        schema = json.loads(
            (DELPHI / "schemas" / "judge-output.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["required"],
            ["p_yes", "confidence", "rationale", "lessons"],
        )
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertEqual(schema["properties"]["lessons"]["maxItems"], 3)

    def test_judge_command_is_noninteractive_read_only_and_schema_constrained(self):
        with tempfile.TemporaryDirectory(prefix=".oauth-", dir=DELPHI) as td:
            outdir = Path(td)

            def complete(cmd, **kwargs):
                outfile = Path(cmd[cmd.index("--output-last-message") + 1])
                outfile.write_text('{"p_yes":0.8}', encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")

            with (mock.patch.object(llm, "tmp_dir", return_value=outdir),
                  mock.patch.object(llm, "gen_id", return_value="out-unique"),
                  mock.patch.object(llm.subprocess, "run", side_effect=complete) as run):
                result = llm.call("judge", "private prompt", self.cfg)

            self.assertEqual(result, '{"p_yes":0.8}')
            cmd = run.call_args.args[0]
            for token in (
                    "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
                    "--sandbox", "read-only", "-C", "--output-schema",
                    "--output-last-message", "-"):
                self.assertIn(token, cmd)
            self.assertEqual(cmd[cmd.index("-C") + 1], str(DELPHI))
            self.assertEqual(
                cmd[cmd.index("--output-schema") + 1],
                str(DELPHI / "schemas" / "judge-output.json"),
            )
            self.assertEqual(cmd[cmd.index("-m") + 1], "gpt-5.6-luna")
            self.assertIn('model_reasoning_effort="high"', cmd)
            self.assertEqual(run.call_args.kwargs["input"], b"private prompt")
            self.assertEqual(run.call_args.kwargs["cwd"], str(DELPHI))
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertNotIn("env", run.call_args.kwargs)
            self.assertEqual(list(outdir.iterdir()), [])

    def test_output_file_is_unique_and_cleaned_on_subprocess_error(self):
        with tempfile.TemporaryDirectory(prefix=".oauth-", dir=DELPHI) as td:
            outdir = Path(td)
            seen = []

            def fail(cmd, **_kwargs):
                outfile = Path(cmd[cmd.index("--output-last-message") + 1])
                seen.append(outfile)
                outfile.write_text("partial", encoding="utf-8")
                raise RuntimeError("codex failed")

            with (mock.patch.object(llm, "tmp_dir", return_value=outdir),
                  mock.patch.object(llm, "gen_id", side_effect=["out-a", "out-b"]),
                  mock.patch.object(llm.subprocess, "run", side_effect=fail)):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, "codex failed"):
                        llm.call("judge", "prompt", self.cfg)

            self.assertEqual(len(set(seen)), 2)
            self.assertEqual(list(outdir.iterdir()), [])

    def test_nonzero_exit_rejects_valid_looking_output_file_and_cleans_it(self):
        with tempfile.TemporaryDirectory(prefix=".oauth-", dir=DELPHI) as td:
            outdir = Path(td)

            def fail(cmd, **_kwargs):
                outfile = Path(cmd[cmd.index("--output-last-message") + 1])
                outfile.write_text('{"p_yes":0.8}', encoding="utf-8")
                return subprocess.CompletedProcess(
                    cmd, 7, b'{"p_yes":0.9}', b"private diagnostic")

            with (mock.patch.object(llm, "tmp_dir", return_value=outdir),
                  mock.patch.object(llm, "gen_id", return_value="out-failed"),
                  mock.patch.object(llm.subprocess, "run", side_effect=fail),
                  self.assertRaisesRegex(RuntimeError, "nonzero")):
                llm.call("judge", "prompt", self.cfg)

            self.assertEqual(list(outdir.iterdir()), [])

    def test_zero_exit_requires_nonempty_output_file_and_ignores_stdout(self):
        for output in (None, "", "   \n"):
            with self.subTest(output=output), tempfile.TemporaryDirectory(
                    prefix=".oauth-", dir=DELPHI) as td:
                outdir = Path(td)

                def incomplete(cmd, **_kwargs):
                    outfile = Path(cmd[cmd.index("--output-last-message") + 1])
                    if output is not None:
                        outfile.write_text(output, encoding="utf-8")
                    return subprocess.CompletedProcess(
                        cmd, 0, b'{"p_yes":0.8}', b"private diagnostic")

                with (mock.patch.object(llm, "tmp_dir", return_value=outdir),
                      mock.patch.object(llm, "gen_id", return_value="out-empty"),
                      mock.patch.object(
                          llm.subprocess, "run", side_effect=incomplete),
                      self.assertRaisesRegex(RuntimeError, "nonempty")):
                    llm.call("judge", "prompt", self.cfg)

                self.assertEqual(list(outdir.iterdir()), [])

    def test_cron_exports_codex_login_environment(self):
        text = (DELPHI / "crontab.example").read_text(encoding="utf-8")
        self.assertIn("PATH=/home/kab/.local/bin:/usr/local/bin:/usr/bin:/bin", text)
        self.assertIn("CODEX_HOME=/home/kab/.codex", text)
        self.assertLess(text.index("PATH="), text.index("*/10"))
        self.assertLess(text.index("CODEX_HOME="), text.index("*/10"))


if __name__ == "__main__":
    unittest.main()
