import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "cognee-server.sh"
UNIT = REPO / "systemd" / "user" / "cognee-server.service"
REDACTOR = REPO / "scripts" / "cognee-log-redactor.py"


class _Handler(http.server.BaseHTTPRequestHandler):
    payloads = {}

    def do_GET(self):
        payload = self.payloads.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format, *_args):
        return


class CogneeServerScriptTests(unittest.TestCase):
    def redactor_env(self, **updates):
        env = os.environ.copy()
        for name in tuple(env):
            if name.startswith("COGNEE_REDACTED_LOG_"):
                env.pop(name)
        env.update(updates)
        return env

    def run_script(self, command, port):
        env = os.environ.copy()
        env.update({"COGNEE_HOST": "127.0.0.1", "COGNEE_PORT": str(port)})
        return subprocess.run(
            ["bash", str(SCRIPT), command],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def serve(self, payloads):
        handler = type("Handler", (_Handler,), {"payloads": payloads})
        server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_script_has_dedicated_safe_defaults_and_one_worker(self):
        text = SCRIPT.read_text()
        self.assertIn('${COGNEE_HOST:-127.0.0.1}', text)
        self.assertIn('${COGNEE_PORT:-8001}', text)
        self.assertIn('exec dotenvx run', text)
        self.assertIn('-fk "$KEY_FILE"', text)
        self.assertIn('--workers 1', text)
        self.assertNotIn('--port 8000', text)
        self.assertNotIn('pkill -f', text)

    def test_health_accepts_only_cognee_identity_and_readiness(self):
        good_port = self.serve(
            {
                "/": {"message": "Hello, World, I am alive!"},
                "/health": {
                    "status": "ready",
                    "health": "healthy",
                    "version": "1.0.9",
                },
            }
        )
        good = self.run_script("health", good_port)
        self.assertEqual(good.returncode, 0, good.stderr + good.stdout)

        wrong_port = self.serve(
            {
                "/": {"message": "another service"},
                "/health": {
                    "status": "ready",
                    "health": "healthy",
                    "version": "1.0.9",
                },
            }
        )
        wrong = self.run_script("health", wrong_port)
        self.assertNotEqual(wrong.returncode, 0)

    def test_run_refuses_an_occupied_port_without_disturbing_it(self):
        port = self.serve({"/health": {"service": "not-cognee"}})
        result = self.run_script("run", port)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already occupied", result.stderr)

        request = subprocess.run(
            ["curl", "-fsS", f"http://127.0.0.1:{port}/health"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(request.returncode, 0)

    def test_non_loopback_override_is_rejected(self):
        env = os.environ.copy()
        env.update({"COGNEE_HOST": "0.0.0.0", "COGNEE_PORT": "8001"})
        result = subprocess.run(
            ["bash", str(SCRIPT), "health"],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("loopback", result.stderr)

    def test_systemd_unit_supervises_foreground_server(self):
        text = UNIT.read_text()
        self.assertIn("After=network-online.target", text)
        self.assertIn("ExecStart=%h/personal-assistant-oc/scripts/cognee-server.sh run", text)
        self.assertIn("Environment=COGNEE_HOST=127.0.0.1", text)
        self.assertIn("Environment=COGNEE_PORT=8001", text)
        self.assertIn("Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin", text)
        self.assertIn("Environment=COGNEE_LOG_FILE=false", text)
        self.assertNotIn("COGNEE_REDACTED_LOG_", text)
        self.assertIn("Restart=on-failure", text)
        self.assertIn("StandardOutput=journal", text)
        self.assertIn("StandardError=journal", text)
        self.assertIn("WantedBy=default.target", text)

    def test_redactor_removes_full_secret_and_every_unique_fragment(self):
        canary = "canary-provider-secret-A7z9Q2m4V8k6P3x5"
        env = self.redactor_env(TEST_PROVIDER_API_KEY=canary)
        child = (
            "import os,sys; value=os.environ['TEST_PROVIDER_API_KEY']; "
            "print('full='+value); "
            "print('fragment='+value[7:29], file=sys.stderr); "
            "print('styled='+value[:11]+'\\x1b[31m'+value[11:]+'\\x1b[0m'); "
            "raise SystemExit(7)"
        )
        result = subprocess.run(
            [str(REDACTOR), "--", sys.executable, "-c", child],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 7)
        combined = result.stdout + result.stderr
        self.assertIn("[REDACTED]", combined)
        self.assertNotIn(canary, combined)
        for start in range(len(canary) - 7):
            self.assertNotIn(canary[start : start + 8], combined)

    def test_redactor_drains_both_streams_and_propagates_exit_code(self):
        child = (
            "import sys; "
            "sys.stdout.write('out\\n'*20000); "
            "sys.stderr.write('err\\n'*20000); "
            "raise SystemExit(23)"
        )
        result = subprocess.run(
            [str(REDACTOR), "--", sys.executable, "-c", child],
            cwd=REPO,
            env=self.redactor_env(),
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.stdout.count(b"out\n"), 20000)
        self.assertEqual(result.stderr.count(b"err\n"), 20000)

    def test_redactor_forwards_term_to_child(self):
        child = (
            "import signal,sys,time; "
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(42)); "
            "print('ready', flush=True); time.sleep(30)"
        )
        process = subprocess.Popen(
            [str(REDACTOR), "--", sys.executable, "-c", child],
            cwd=REPO,
            env=self.redactor_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            process.terminate()
            self.assertEqual(process.wait(timeout=5), 42)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_legacy_custom_log_settings_are_ignored_without_file_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            referent = base / "referent"
            referent.mkdir(mode=0o700)
            sentinel = referent / "sentinel"
            sentinel.write_bytes(b"unchanged")
            sentinel.chmod(0o640)
            before = (sentinel.read_bytes(), sentinel.stat().st_mode & 0o777)
            alias = base / "malicious-alias"
            alias.symlink_to(referent, target_is_directory=True)
            env = self.redactor_env(
                COGNEE_REDACTED_LOG_ROOT=str(alias),
                COGNEE_REDACTED_LOG_FILE=str(alias / "server.log"),
                COGNEE_REDACTED_LOG_MAX_BYTES="1",
            )
            result = subprocess.run(
                [str(REDACTOR), "--", sys.executable, "-c", "print('journal-only')"],
                cwd=REPO,
                env=env,
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("journal-only", result.stdout)
            self.assertTrue(alias.is_symlink())
            self.assertFalse((referent / "server.log").exists())
            self.assertFalse((referent / "server.log.1").exists())
            self.assertEqual(
                (sentinel.read_bytes(), sentinel.stat().st_mode & 0o777), before
            )

    def test_no_newline_stream_is_bounded_and_redacted(self):
        canary = "boundary-provider-secret-Q7m3K9v5X2z8N4p6"
        env = self.redactor_env(TEST_PROVIDER_API_KEY=canary)
        child = (
            "import os,sys; value=os.environ['TEST_PROVIDER_API_KEY'].encode(); "
            "os.write(sys.stdout.fileno(), b'x'*(65536-5)+value+b'!'+b'y'*(2*1024*1024))"
        )
        result = subprocess.run(
            [str(REDACTOR), "--", sys.executable, "-c", child],
            cwd=REPO,
            env=env,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertGreater(len(result.stdout), 2 * 1024 * 1024)
        combined = result.stdout + result.stderr
        self.assertNotIn(canary.encode(), combined)
        for start in range(len(canary) - 7):
            self.assertNotIn(canary[start : start + 8].encode(), combined)

    def test_redactor_is_bounded_and_has_no_custom_file_sink(self):
        text = REDACTOR.read_text()
        self.assertIn("stream.read(64 * 1024)", text)
        self.assertNotIn('buffer.find(b"\\n")', text)
        self.assertNotIn("SafeSink", text)
        self.assertNotIn("COGNEE_REDACTED_LOG_", text)
        self.assertNotIn("os.open", text)


if __name__ == "__main__":
    unittest.main()
