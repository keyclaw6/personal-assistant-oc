#!/usr/bin/env python3
"""LLM invocation layer. Two backends (config.json `roles`):

- codex-cli : runs `codex exec` non-interactively on the machine's existing
              Codex OAuth login (subscription — no API key, per house rule).
- http      : any OpenAI-compatible chat-completions endpoint. API key comes
              from the env var named in `api_key_env` (dotenvx-managed, never
              plaintext in the repo).

Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

from lib import ROOT, extract_json, gen_id, load_config, tmp_dir


def call(role: str, prompt: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    r = cfg["roles"][role]
    timeout = cfg.get("llm", {}).get("timeout_seconds", 600)
    if r["backend"] == "codex-cli":
        return _codex(cfg, r, prompt, timeout)
    if r["backend"] == "http":
        return _http(r, prompt, timeout)
    raise ValueError(f"unknown backend for role {role}: {r['backend']}")


def call_json(role: str, prompt: str, cfg: dict | None = None, *, decoder=None):
    """Call a model and decode JSON, with one terse retry (PROGRAM.md §6).

    Most extraction roles retain the existing best-effort decoder.  Callers
    whose output can authorize state transitions may supply a strict decoder.
    Decoder failures are retried, then raised so the caller can keep its item
    retryable without mistaking malformed output for a semantic decision.
    """
    cfg = cfg or load_config()
    retries = cfg.get("llm", {}).get("max_json_retries", 1)
    decode = decoder or extract_json
    last_error = None
    for attempt in range(retries + 1):
        retry = "\n\nREPLY WITH THE JSON OBJECT ONLY. NO PROSE." if attempt else ""
        try:
            text = call(role, prompt + retry, cfg)
        except RuntimeError as exc:
            last_error = exc
            continue
        try:
            parsed = decode(text)
        except (TypeError, ValueError) as exc:
            last_error = exc
            parsed = None
        if parsed is not None:
            return parsed
    if last_error is not None:
        raise last_error
    return None


def _codex(cfg: dict, r: dict, prompt: str, timeout: int) -> str:
    outfile = tmp_dir() / f"codex-{gen_id('out')}.txt"
    cmd = [a.format(model=r["model"], reasoning=r.get("reasoning", "medium"),
                    cwd=str(ROOT), outfile=str(outfile))
           for a in cfg["codex_cmd"]]
    if r.get("output_schema"):
        schema = str((ROOT / r["output_schema"]).resolve())
        output_index = cmd.index("--output-last-message")
        cmd[output_index:output_index] = ["--output-schema", schema]
    try:
        proc = subprocess.run(cmd, input=prompt.encode("utf-8"),
                              capture_output=True, timeout=timeout,
                              cwd=str(ROOT))  # Delphi-only working directory
        if proc.returncode != 0:
            raise RuntimeError("codex CLI exited with a nonzero status")
        if not outfile.exists():
            raise RuntimeError(
                "codex CLI did not create a nonempty output-last-message file")
        text = outfile.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise RuntimeError(
                "codex CLI did not create a nonempty output-last-message file")
        return text
    except subprocess.TimeoutExpired:
        raise RuntimeError("codex CLI timed out") from None
    except FileNotFoundError as e:
        raise RuntimeError(
            "codex CLI not found on PATH — DELPHI roles need the logged-in "
            "Codex CLI (see delphi/README.md)") from e
    finally:
        outfile.unlink(missing_ok=True)


def _http(r: dict, prompt: str, timeout: int) -> str:
    key = os.environ.get(r["api_key_env"], "")
    if not key:
        raise RuntimeError(
            f"env var {r['api_key_env']} not set — run via dotenvx "
            f"(see delphi/README.md) or switch this role to backend 'codex-cli'")
    body = json.dumps({
        "model": r["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        r["base_url"].rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data["choices"][0]["message"]["content"]
