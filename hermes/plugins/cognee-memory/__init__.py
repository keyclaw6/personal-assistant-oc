from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)

DEFAULT_REPO = Path("/home/kab/personal-assistant-oc")
DEFAULT_WORKSPACE = DEFAULT_REPO / "albert"
DEFAULT_ENV_FILE = DEFAULT_REPO / ".env.cognee"
DEFAULT_DATASETS_FILE = Path("/home/kab/.openclaw/memory/cognee/datasets.json")
TEXT_SUFFIXES = {".md", ".txt"}


def _load_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    raw_text = path.read_text(encoding="utf-8", errors="replace")
    if "encrypted:" in raw_text:
        command = [
            "dotenvx", "get", "--strict", "--format", "json", "--no-armor", "--no-native",
            "-f", str(path),
        ]
        key_file = Path(
            os.environ.get("DOTENVX_KEY_FILE", "~/.config/dotenvx/.env.keys")
        ).expanduser()
        if key_file.is_file():
            command.extend(["-fk", str(key_file)])
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            loaded = json.loads(result.stdout)
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Encrypted env requires dotenvx and the shared private key outside Git"
            ) from exc
        if not isinstance(loaded, dict):
            raise RuntimeError("dotenvx returned an invalid environment payload")
        values = {
            str(key): str(value)
            for key, value in loaded.items()
            if not str(key).startswith("DOTENV_PUBLIC_KEY")
        }
    else:
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw = stripped.split("=", 1)
            values[key.strip()] = raw.strip().strip('"').strip("'")

    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_results(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and "results" in data:
        return _normalize_results(data["results"])
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for index, item in enumerate(data):
        if isinstance(item, str):
            out.append({"id": f"result-{index}", "text": item, "score": 1})
            continue
        if isinstance(item, dict):
            if isinstance(item.get("text"), str):
                text = item["text"]
            elif isinstance(item.get("search_result"), list):
                text = "\n".join(str(x) for x in item["search_result"])
            elif isinstance(item.get("search_result"), str):
                text = item["search_result"]
            else:
                text = json.dumps(item, ensure_ascii=False)
            out.append({
                "id": item.get("id") or item.get("dataset_id") or f"result-{index}",
                "text": text,
                "score": item.get("score", 1),
                "metadata": item.get("metadata"),
            })
            continue
        out.append({"id": f"result-{index}", "text": str(item), "score": 1})
    return out


def _query_terms(query: str) -> List[str]:
    terms: List[str] = []
    for raw in query.lower().replace("_", " ").replace("-", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) >= 3 and word not in terms:
            terms.append(word)
    return terms[:12]


class CogneeMemoryProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "cognee-memory"

    def __init__(self) -> None:
        self._session_id = ""
        self._base_url = os.getenv("COGNEE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self._api_key = os.getenv("COGNEE_API_KEY", "")
        self._username = os.getenv("COGNEE_USERNAME", "default_user@example.com")
        self._password = os.getenv("COGNEE_PASSWORD", "default_password")
        self._auth_token = ""
        self._search_type = os.getenv("COGNEE_SEARCH_TYPE", "CHUNKS")
        self._max_tokens = int(os.getenv("COGNEE_MAX_TOKENS", "4000"))
        self._timeout = float(os.getenv("COGNEE_TIMEOUT_SECONDS", "10"))
        self._dataset_name = os.getenv("COGNEE_DATASET_NAME", "openclaw")
        self._workspace = Path(os.getenv("ALBERT_WORKSPACE", str(DEFAULT_WORKSPACE)))
        self._repo = Path(os.getenv("PERSONAL_ASSISTANT_REPO", str(DEFAULT_REPO)))
        self._datasets_file = Path(os.getenv("COGNEE_DATASETS_FILE", str(DEFAULT_DATASETS_FILE)))
        self._dataset_ids: List[str] = []
        self._last_error = ""

    def is_available(self) -> bool:
        env_file = Path(os.getenv("ALBERT_COGNEE_ENV", str(DEFAULT_ENV_FILE)))
        if env_file.exists():
            _load_dotenv(env_file)
        return bool(self._base_url and (self._datasets_file.exists() or self._workspace.exists()))

    def initialize(self, session_id: str, **kwargs) -> None:
        del kwargs
        self._session_id = session_id
        env_file = Path(os.getenv("ALBERT_COGNEE_ENV", str(DEFAULT_ENV_FILE)))
        values = _load_dotenv(env_file)
        self._base_url = os.getenv("COGNEE_BASE_URL", values.get("COGNEE_BASE_URL", self._base_url)).rstrip("/")
        self._api_key = os.getenv("COGNEE_API_KEY", values.get("COGNEE_API_KEY", self._api_key))
        self._username = os.getenv("COGNEE_USERNAME", values.get("COGNEE_USERNAME", self._username))
        self._password = os.getenv("COGNEE_PASSWORD", values.get("COGNEE_PASSWORD", self._password))
        datasets = _read_json(self._datasets_file)
        if isinstance(datasets, dict):
            selected = datasets.get(self._dataset_name)
            self._dataset_ids = [selected] if isinstance(selected, str) else [
                item for item in datasets.values() if isinstance(item, str)
            ]

    def system_prompt_block(self) -> str:
        return (
            "Cognee memory is active. File memory under albert/memory remains the "
            "source of truth; Cognee is the retrieval layer. Use cognee_search "
            "when explicit long-term recall would improve the answer."
        )

    def _login(self) -> None:
        if self._api_key or self._auth_token:
            return
        form = urllib.parse.urlencode({
            "username": self._username or "default_user@example.com",
            "password": self._password or "default_password",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/api/v1/auth/login",
            data=form,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
        token = data.get("access_token") or data.get("token")
        if not token:
            raise RuntimeError("Cognee login succeeded without returning an access token")
        self._auth_token = str(token)

    def _headers(self, has_payload: bool) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if has_payload:
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        elif self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def _request_once(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        headers = self._headers(payload is not None)
        request = urllib.request.Request(f"{self._base_url}{path}", data=body, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        if path != "/health":
            self._login()
        try:
            return self._request_once(method, path, payload)
        except urllib.error.HTTPError as exc:
            if exc.code != 401 or self._api_key or path == "/health":
                raise
            self._auth_token = ""
            self._login()
            return self._request_once(method, path, payload)

    def _search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        payload = {
            "query": query,
            "searchType": self._search_type,
            "datasetIds": self._dataset_ids or None,
            "max_tokens": self._max_tokens,
            "session_id": self._session_id or None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        try:
            data = self._request("POST", "/api/v1/search", payload)
            self._last_error = ""
            return _normalize_results(data)[: max(1, min(limit, 20))]
        except Exception as exc:
            self._last_error = f"Cognee search failed; using file-memory fallback when possible: {exc}"
            fallback = self._file_search(query, limit=limit)
            if fallback:
                return fallback
            raise

    def _file_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        terms = _query_terms(query)
        if not terms:
            return []
        memory_root = self._workspace / "memory"
        if not memory_root.exists():
            return []
        scored: List[Dict[str, Any]] = []
        for file in memory_root.rglob("*"):
            if not file.is_file() or file.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lower = text.lower()
            score = sum(lower.count(term) for term in terms)
            if score <= 0:
                continue
            first = min((lower.find(term) for term in terms if lower.find(term) >= 0), default=0)
            start = max(0, first - 350)
            excerpt = text[start:start + 1200].strip()
            scored.append({
                "id": str(file.relative_to(self._workspace)),
                "text": excerpt,
                "score": score,
                "metadata": {"source": "file-memory-fallback", "path": str(file)},
            })
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[: max(1, min(limit, 20))]

    def _search_with_error_capture(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            return self._search(query, limit=limit)
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        del session_id
        if not query.strip():
            return ""
        try:
            results = self._search_with_error_capture(query, limit=5)
        except Exception as exc:
            logger.debug("Cognee prefetch failed: %s", exc)
            return ""
        if not results:
            return ""
        lines = ["<cognee_memories>"]
        for result in results:
            text = str(result.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"- {text[:1200]}")
        lines.append("</cognee_memories>")
        return "\n".join(lines)

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        del messages
        return "Before compressing, preserve durable user facts and decisions in the file memory under albert/memory."

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        del action, target, content, metadata
        # Built-in Hermes memory remains enabled. Albert's durable source of
        # truth is file memory, so this provider does not mirror writes into
        # Cognee directly; Cognee indexes the files.

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "cognee_search",
                "description": "Search Albert's Cognee memory index. Use for long-term recall over albert/memory and prior imported memory files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "cognee_status",
                "description": "Check Albert's Cognee memory bridge configuration and local API health without exposing secrets.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        del kwargs
        if tool_name == "cognee_search":
            query = str(args.get("query") or "").strip()
            if not query:
                return tool_error("query is required")
            limit = int(args.get("limit") or 5)
            try:
                return tool_result({"results": self._search(query, limit=limit)})
            except Exception as exc:
                return tool_error(f"Cognee search failed: {exc}")
        if tool_name == "cognee_status":
            health: Any
            try:
                health = self._request("GET", "/health")
                ok = True
            except Exception as exc:
                health = str(exc)
                ok = False
            return tool_result({
                "available": self.is_available(),
                "api_ok": ok,
                "base_url": self._base_url,
                "workspace": str(self._workspace),
                "datasets_file": str(self._datasets_file),
                "dataset_ids": self._dataset_ids,
                "search_type": self._search_type,
                "last_error": self._last_error,
                "health": health,
            })
        return tool_error(f"Unknown Cognee tool: {tool_name}")


def register(ctx) -> None:
    ctx.register_memory_provider(CogneeMemoryProvider())
