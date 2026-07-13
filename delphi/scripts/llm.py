#!/usr/bin/env python3
"""LLM invocation layer. Two backends (config.json `roles`):

- codex-cli : runs `codex exec` non-interactively on the machine's existing
              Codex OAuth login (subscription — no API key, per house rule).
- http      : any OpenAI-compatible chat-completions endpoint (default:
              OpenRouter for the judge). API key comes from the env var named
              in `api_key_env` (dotenvx-managed, never plaintext in the repo).

Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

from lib import extract_json, gen_id, load_config, tmp_dir


def call(role: str, prompt: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    r = cfg["roles"][role]
    timeout = cfg.get("llm", {}).get("timeout_seconds", 600)
    if r["backend"] == "codex-cli":
        return _codex(cfg, r, prompt, timeout)
    if r["backend"] == "http":
        return _http(r, prompt, timeout)
    raise ValueError(f"unknown backend for role {role}: {r['backend']}")


def call_json(role: str, prompt: str, cfg: dict | None = None):
    """call() + robust JSON extraction, with one terse retry (PROGRAM.md §6)."""
    cfg = cfg or load_config()
    retries = cfg.get("llm", {}).get("max_json_retries", 1)
    text = call(role, prompt, cfg)
    parsed = extract_json(text)
    attempts = 0
    while parsed is None and attempts < retries:
        attempts += 1
        text = call(role, prompt + "\n\nREPLY WITH THE JSON OBJECT ONLY. NO PROSE.", cfg)
        parsed = extract_json(text)
    return parsed


def _codex(cfg: dict, r: dict, prompt: str, timeout: int) -> str:
    outfile = tmp_dir() / f"codex-{gen_id('out')}.txt"
    cmd = [a.format(model=r["model"], reasoning=r.get("reasoning", "medium"),
                    outfile=str(outfile)) for a in cfg["codex_cmd"]]
    try:
        proc = subprocess.run(cmd, input=prompt.encode("utf-8"),
                              capture_output=True, timeout=timeout)
        if outfile.exists():
            text = outfile.read_text(encoding="utf-8", errors="replace")
            outfile.unlink(missing_ok=True)
            if text.strip():
                return text
        # fallback: last chunk of stdout
        return proc.stdout.decode("utf-8", errors="replace")[-8000:]
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError as e:
        raise RuntimeError(
            "codex CLI not found on PATH — explorer/heartbeat roles need the "
            "logged-in Codex CLI, or switch the role's backend to 'http' in "
            "delphi/config.json") from e


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
