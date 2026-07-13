#!/usr/bin/env python3
"""Cognee client — SAME local server as the assistant, ISOLATED dataset.

Every call names the `delphi-trading` dataset explicitly (config `cognee`);
Albert's datasets are never read, written, or cognified from here, and Delphi
never starts/stops the server (that is assistant infrastructure — see
docs/cognee-setup.md at the repo root).

All operations are best-effort: files are the source of truth, Cognee is
retrieval only. First failure latches the client off for the rest of the
process, so a down server costs one warning per run (PROGRAM.md §5).
"""
from __future__ import annotations

import json
import os
import urllib.request

from lib import load_config

_disabled = False


def _c() -> dict:
    return load_config()["cognee"]


def _base(c: dict) -> str:
    return (os.environ.get(c["url_env"]) or c["default_url"]).rstrip("/")


def _headers(c: dict) -> dict:
    h = {"Content-Type": "application/json"}
    tok = os.environ.get(c["token_env"], "")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _post(c: dict, path: str, body: dict):
    req = urllib.request.Request(_base(c) + path, data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(c), method="POST")
    with urllib.request.urlopen(req, timeout=c["timeout_seconds"]) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _off(reason: str) -> None:
    global _disabled
    if not _disabled:
        print(f"  [cognee] disabled for this run: {reason}")
    _disabled = True


def add(text: str, meta: str = "") -> bool:
    """Ingest one text item into the delphi dataset."""
    c = _c()
    if not c.get("enabled") or _disabled or not text:
        return False
    payload = f"[{meta}] {text}" if meta else text
    body = {"data": payload, "datasetName": c["dataset"]}
    try:
        _post(c, "/api/v1/add", body)
        return True
    except Exception as e:  # noqa: BLE001 — best-effort boundary
        try:  # some server versions want a list
            _post(c, "/api/v1/add", {"data": [payload], "datasetName": c["dataset"]})
            return True
        except Exception:  # noqa: BLE001
            _off(str(e))
            return False


def cognify() -> bool:
    """Build/refresh the graph for the delphi dataset only. Heavier — call from
    resolve/orchestrator cadence, never from the 10-min heartbeat."""
    c = _c()
    if not c.get("enabled") or _disabled:
        return False
    try:
        _post(c, "/api/v1/cognify", {"datasets": [c["dataset"]]})
        return True
    except Exception as e:  # noqa: BLE001
        _off(str(e))
        return False


def search(query: str, limit: int = 3) -> list[str]:
    """Retrieve from the delphi dataset only. Returns short text snippets."""
    c = _c()
    if not c.get("enabled") or _disabled or not query:
        return []
    body = {"query": query, "searchType": c.get("search_type", "CHUNKS"),
            "datasets": [c["dataset"]]}
    try:
        res = _post(c, "/api/v1/search", body)
    except Exception as e:  # noqa: BLE001
        _off(str(e))
        return []
    items = res if isinstance(res, list) else res.get("results", []) if isinstance(res, dict) else [res]
    out = []
    for it in items[:limit]:
        if isinstance(it, dict):
            it = it.get("text") or it.get("content") or json.dumps(it)
        s = str(it).strip()
        if s:
            out.append(s[:400])
    return out
