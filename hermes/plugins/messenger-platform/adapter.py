from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

try:
    import aiohttp
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except Exception:
    aiohttp = None
    web = None
    AIOHTTP_AVAILABLE = False

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_audio_from_url,
)

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
TEXT_CHUNK_LIMIT = int(os.getenv("MESSENGER_TEXT_CHUNK_LIMIT", "2000"))
_AUDIO_CACHE_EXTENSIONS = frozenset(
    {
        ".aac",
        ".flac",
        ".m4a",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".ogg",
        ".opus",
        ".wav",
        ".webm",
    }
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _validate_signature(body: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    received = signature[7:]
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(bytes.fromhex(received), bytes.fromhex(computed))
    except ValueError:
        return False


def _attachment_media_type(kind: str | None) -> str:
    normalized = (kind or "").lower()
    if normalized == "image":
        return "image/jpeg"
    if normalized == "video":
        return "video/mp4"
    if normalized == "audio":
        return "audio/mpeg"
    return "application/octet-stream"


def _attachment_label(attachment: Dict[str, Any]) -> str:
    payload = attachment.get("payload") or {}
    kind = attachment.get("type") or "file"
    title = f' "{payload.get("title")}"' if payload.get("title") else ""
    sticker = f" (sticker {payload.get('sticker_id')})" if payload.get("sticker_id") else ""
    return f"{kind}{title}{sticker}"


def _audio_extension_from_url(url: str) -> str:
    extension = os.path.splitext(urlsplit(url).path)[1].lower()
    return extension if extension in _AUDIO_CACHE_EXTENSIONS else ".ogg"


def _normalize_inbound(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if event.get("reaction"):
        reaction = event["reaction"]
        action = reaction.get("action") or "react"
        value = reaction.get("reaction") or reaction.get("emoji") or "reaction"
        mid = reaction.get("mid") or "unknown"
        return {
            "text": f"Messenger reaction: {action} {value} on message {mid}.",
            "message_id": mid,
            "media_urls": [],
            "media_types": [],
            "message_type": MessageType.TEXT,
        }

    message = event.get("message")
    postback = event.get("postback")
    if not message and not postback:
        return None

    attachments = message.get("attachments") if isinstance(message, dict) else []
    attachments = attachments if isinstance(attachments, list) else []
    media = [
        item
        for item in attachments
        if isinstance(item, dict)
        and isinstance((item.get("payload") or {}).get("url"), str)
        and (item.get("payload") or {}).get("url").strip()
    ]
    original = ""
    if isinstance(message, dict):
        original = message.get("text") or ""
    if not original and isinstance(postback, dict):
        original = postback.get("title") or postback.get("payload") or ""

    attachment_summary = ""
    if attachments:
        attachment_summary = (
            "Messenger attachments: "
            + ", ".join(_attachment_label(a) for a in attachments)
            + "."
        )
    missing_audio_urls = sum(
        1
        for item in attachments
        if isinstance(item, dict)
        and (item.get("type") or "").lower() == "audio"
        and not str((item.get("payload") or {}).get("url") or "").strip()
    )
    missing_audio_note = (
        "Messenger voice attachment did not include a downloadable URL."
        if missing_audio_urls
        else ""
    )
    text = "\n".join(
        part for part in (original, attachment_summary, missing_audio_note) if part
    )
    if not text:
        return None

    msg_type = MessageType.TEXT
    attachment_types = [
        (item.get("type") or "").lower()
        for item in media
    ]
    if "audio" in attachment_types:
        # Messenger does not expose a reliable voice-note vs audio-file
        # distinction. Treat its audio attachment as voice so Hermes routes
        # the cached local file through STT. Other platforms keep their AUDIO
        # semantics unchanged.
        msg_type = MessageType.VOICE
    elif "image" in attachment_types:
        msg_type = MessageType.PHOTO
    elif "video" in attachment_types:
        msg_type = MessageType.VIDEO
    elif attachment_types:
        msg_type = MessageType.DOCUMENT

    return {
        "text": text,
        "message_id": message.get("mid") if isinstance(message, dict) else None,
        "media_urls": [(item.get("payload") or {}).get("url") for item in media],
        "media_types": [_attachment_media_type(item.get("type")) for item in media],
        "message_type": msg_type,
    }


async def _cache_voice_attachments(inbound: Dict[str, Any]) -> None:
    cached_urls: List[str] = []
    cached_types: List[str] = []
    failed_downloads = 0

    for index, url in enumerate(inbound.get("media_urls") or []):
        media_types = inbound.get("media_types") or []
        media_type = media_types[index] if index < len(media_types) else ""
        if not media_type.startswith("audio/"):
            cached_urls.append(url)
            cached_types.append(media_type)
            continue

        if os.path.isabs(url):
            cached_urls.append(url)
            cached_types.append(media_type)
            continue

        if not url.startswith(("http://", "https://")):
            failed_downloads += 1
            continue

        try:
            cached_path = await cache_audio_from_url(
                url,
                ext=_audio_extension_from_url(url),
            )
            cached_urls.append(cached_path)
            cached_types.append(media_type)
        except Exception as exc:
            failed_downloads += 1
            # Do not include the exception text: HTTP client errors may embed
            # Messenger's signed attachment URL and credentials.
            logger.warning(
                "Failed to cache Messenger voice attachment (%s)",
                type(exc).__name__,
            )

    inbound["media_urls"] = cached_urls
    inbound["media_types"] = cached_types
    if failed_downloads:
        fallback = (
            "Messenger voice attachment could not be downloaded for transcription."
        )
        inbound["text"] = "\n".join(
            part for part in (inbound.get("text"), fallback) if part
        )


def _chunk_text(text: str, limit: int = TEXT_CHUNK_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        brk = limit
        nl = remaining.rfind("\n", 0, limit)
        if nl > limit * 0.5:
            brk = nl + 1
        chunks.append(remaining[:brk])
        remaining = remaining[brk:]
    return chunks


async def _graph_send(token: str, body: Dict[str, Any]) -> Dict[str, Any]:
    if not AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp is not installed")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{GRAPH_API_BASE}/me/messages",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            json=body,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Messenger API {response.status}: {text[:500]}")
            try:
                return json.loads(text) if text else {}
            except json.JSONDecodeError:
                return {"raw": text}


class MessengerAdapter(BasePlatformAdapter):
    MAX_MESSAGE_LENGTH = TEXT_CHUNK_LIMIT

    def __init__(self, config: PlatformConfig):
        super().__init__(config=config, platform=Platform("messenger"))
        extra = config.extra or {}
        self.page_access_token = os.getenv("MESSENGER_PAGE_ACCESS_TOKEN") or extra.get("page_access_token", "")
        self.app_secret = os.getenv("MESSENGER_APP_SECRET") or extra.get("app_secret", "")
        self.verify_token = os.getenv("MESSENGER_VERIFY_TOKEN") or extra.get("verify_token", "")
        self.webhook_path = os.getenv("MESSENGER_WEBHOOK_PATH") or extra.get("webhook_path", "/messenger/webhook")
        if not self.webhook_path.startswith("/"):
            self.webhook_path = "/" + self.webhook_path
        self.host = os.getenv("MESSENGER_HOST") or extra.get("host", "127.0.0.1")
        self.port = int(os.getenv("MESSENGER_PORT") or extra.get("port", 18891))
        self.allowed_users = set(_split_csv(os.getenv("MESSENGER_ALLOWED_USERS") or extra.get("allowed_users", "")))
        self.allow_all_users = _env_bool("MESSENGER_ALLOW_ALL_USERS", bool(extra.get("allow_all_users", False)))
        self._runner = None
        self._site = None

    async def connect(self) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.error("Messenger platform requires aiohttp")
            return False
        app = web.Application()
        app.router.add_get(self.webhook_path, self._handle_verify)
        app.router.add_post(self.webhook_path, self._handle_webhook)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._mark_connected()
        logger.info("Messenger webhook listening on http://%s:%s%s", self.host, self.port, self.webhook_path)
        return True

    async def disconnect(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._mark_disconnected()

    async def _handle_verify(self, request):
        params = request.rel_url.query
        if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == self.verify_token:
            return web.Response(text=params.get("hub.challenge", ""))
        return web.Response(status=403, text="Forbidden")

    async def _handle_webhook(self, request):
        body = await request.read()
        signature = request.headers.get("x-hub-signature-256", "")
        if self.app_secret and not _validate_signature(body, signature, self.app_secret):
            return web.Response(status=403, text="Invalid signature")
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return web.Response(status=400, text="Bad JSON")
        if payload.get("object") != "page":
            return web.Response(status=400, text="Not a page webhook")
        asyncio.create_task(self._dispatch_payload(payload))
        return web.Response(text="OK")

    async def _dispatch_payload(self, payload: Dict[str, Any]) -> None:
        for entry in payload.get("entry") or []:
            for event in entry.get("messaging") or []:
                try:
                    await self._dispatch_event(event)
                except Exception:
                    logger.exception("Messenger dispatch failed")

    async def _dispatch_event(self, event: Dict[str, Any]) -> None:
        if (event.get("message") or {}).get("is_echo"):
            return
        sender_id = str((event.get("sender") or {}).get("id") or "")
        if not sender_id:
            return
        if not self.allow_all_users and sender_id not in self.allowed_users:
            logger.info("Ignoring Messenger sender not in allowlist: %s", sender_id)
            return
        inbound = _normalize_inbound(event)
        if not inbound:
            return
        if inbound["message_type"] == MessageType.VOICE:
            await _cache_voice_attachments(inbound)
        source = self.build_source(
            chat_id=sender_id,
            chat_name=f"Messenger {sender_id}",
            chat_type="dm",
            user_id=sender_id,
            user_name=sender_id,
            message_id=inbound.get("message_id"),
            role_authorized=True,
        )
        msg_event = MessageEvent(
            text=inbound["text"],
            message_type=inbound["message_type"],
            source=source,
            raw_message=event,
            message_id=inbound.get("message_id"),
            media_urls=[u for u in inbound["media_urls"] if u],
            media_types=inbound["media_types"],
            timestamp=datetime.now(),
        )
        await self.handle_message(msg_event)

    async def send(self, chat_id: str, content: Any, reply_to: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        del reply_to, metadata
        text = str(content or "")
        try:
            last_id = None
            for chunk in _chunk_text(text):
                result = await _graph_send(self.page_access_token, {
                    "recipient": {"id": str(chat_id).replace("messenger:", "")},
                    "messaging_type": "RESPONSE",
                    "message": {"text": chunk},
                })
                last_id = result.get("message_id") or last_id
            return SendResult(success=True, message_id=last_id, raw_response={"chunks": max(1, len(_chunk_text(text)))})
        except Exception as exc:
            return SendResult(success=False, error=str(exc), retryable=True)

    async def send_typing(self, chat_id: str, is_typing: bool = True) -> None:
        action = "typing_on" if is_typing else "typing_off"
        try:
            await _graph_send(self.page_access_token, {
                "recipient": {"id": str(chat_id).replace("messenger:", "")},
                "sender_action": action,
            })
        except Exception:
            logger.debug("Messenger typing action failed", exc_info=True)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"id": chat_id, "name": f"Messenger {chat_id}", "type": "dm"}


def check_requirements() -> bool:
    return AIOHTTP_AVAILABLE and bool(os.getenv("MESSENGER_PAGE_ACCESS_TOKEN"))


def validate_config(config) -> bool:
    extra = getattr(config, "extra", {}) or {}
    return bool(os.getenv("MESSENGER_PAGE_ACCESS_TOKEN") or extra.get("page_access_token"))


def is_connected(config) -> bool:
    return validate_config(config)


def _env_enablement() -> Optional[Dict[str, Any]]:
    if not os.getenv("MESSENGER_PAGE_ACCESS_TOKEN"):
        return None
    seeded: Dict[str, Any] = {
        "webhook_path": os.getenv("MESSENGER_WEBHOOK_PATH", "/messenger/webhook"),
    }
    if os.getenv("MESSENGER_HOST"):
        seeded["host"] = os.getenv("MESSENGER_HOST")
    if os.getenv("MESSENGER_PORT"):
        try:
            seeded["port"] = int(os.environ["MESSENGER_PORT"])
        except ValueError:
            pass
    if os.getenv("MESSENGER_HOME_CHANNEL"):
        seeded["home_channel"] = {
            "chat_id": os.getenv("MESSENGER_HOME_CHANNEL"),
            "name": "Messenger home",
        }
    return seeded


async def _standalone_send(pconfig, chat_id: str, message: str, **kwargs) -> Dict[str, Any]:
    del pconfig, kwargs
    token = os.getenv("MESSENGER_PAGE_ACCESS_TOKEN", "")
    if not token or not chat_id:
        return {"error": "Messenger standalone send missing token or chat_id"}
    try:
        last_id = None
        for chunk in _chunk_text(message or ""):
            result = await _graph_send(token, {
                "recipient": {"id": str(chat_id).replace("messenger:", "")},
                "messaging_type": "MESSAGE_TAG",
                "tag": "CONFIRMED_EVENT_UPDATE",
                "message": {"text": chunk},
            })
            last_id = result.get("message_id") or last_id
        return {"success": True, "message_id": last_id}
    except Exception as exc:
        return {"error": str(exc)}


def register(ctx) -> None:
    ctx.register_platform(
        name="messenger",
        label="Messenger",
        adapter_factory=lambda cfg: MessengerAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["MESSENGER_PAGE_ACCESS_TOKEN", "MESSENGER_APP_SECRET", "MESSENGER_VERIFY_TOKEN"],
        install_hint="pip install aiohttp",
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="MESSENGER_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="MESSENGER_ALLOWED_USERS",
        allow_all_env="MESSENGER_ALLOW_ALL_USERS",
        max_message_length=TEXT_CHUNK_LIMIT,
        emoji="M",
        pii_safe=False,
        allow_update_command=True,
        platform_hint=(
            "You are chatting through Facebook Messenger. Keep replies direct, "
            "warm, and readable in plain text. Messenger does not reliably render Markdown tables."
        ),
    )
