from __future__ import annotations

import hashlib
import hmac
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platform_registry import PlatformEntry, platform_registry
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


ADAPTER_PATH = (
    Path(__file__).resolve().parents[2] / "hermes/plugins/messenger-platform/adapter.py"
)
MODULE_NAME = "local_messenger_platform_adapter"


def _load_adapter_module():
    module = sys.modules.get(MODULE_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(MODULE_NAME, ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


messenger = _load_adapter_module()

if not platform_registry.is_registered("messenger"):
    platform_registry.register(
        PlatformEntry(
            name="messenger",
            label="Messenger",
            adapter_factory=lambda config: messenger.MessengerAdapter(config),
            check_fn=lambda: True,
        )
    )


def _audio_event(
    url: str | None = "https://cdn.example.test/voice.mp4?token=signed-secret",
) -> dict:
    payload = {} if url is None else {"url": url}
    return {
        "sender": {"id": "user-1"},
        "recipient": {"id": "page-1"},
        "message": {
            "mid": "mid-1",
            "text": "Caption from the user",
            "attachments": [{"type": "audio", "payload": payload}],
        },
    }


def _make_adapter(monkeypatch) -> object:
    monkeypatch.setenv("MESSENGER_ALLOW_ALL_USERS", "true")
    monkeypatch.delenv("MESSENGER_ALLOWED_USERS", raising=False)
    return messenger.MessengerAdapter(PlatformConfig(enabled=True))


def _make_runner(stt_enabled: bool = True):
    from gateway.run import GatewayRunner

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(stt_enabled=stt_enabled)
    runner.adapters = {}
    runner._model = "test-model"
    runner._base_url = ""
    runner._has_setup_skill = lambda: False
    return runner


def test_messenger_audio_normalizes_as_voice():
    inbound = messenger._normalize_inbound(_audio_event())

    assert inbound is not None
    assert inbound["message_type"] == MessageType.VOICE


def test_messenger_audio_without_url_has_safe_text_fallback():
    inbound = messenger._normalize_inbound(_audio_event(url=None))

    assert inbound is not None
    assert inbound["message_type"] == MessageType.TEXT
    assert inbound["media_urls"] == []
    assert "downloadable URL" in inbound["text"]


@pytest.mark.asyncio
async def test_messenger_audio_is_cached_before_dispatch_and_preserves_signed_url(
    monkeypatch,
):
    adapter = _make_adapter(monkeypatch)
    captured = None

    async def capture(event):
        nonlocal captured
        captured = event

    adapter.handle_message = capture
    signed_url = "https://cdn.example.test/voice.mp4?token=signed-secret&expires=123"
    cache = AsyncMock(return_value="/tmp/hermes-cache/voice.mp4")
    with patch.object(messenger, "cache_audio_from_url", cache, create=True):
        await adapter._dispatch_event(_audio_event(signed_url))

    cache.assert_awaited_once_with(signed_url, ext=".mp4")
    assert captured is not None
    assert captured.message_type == MessageType.VOICE
    assert captured.media_urls == ["/tmp/hermes-cache/voice.mp4"]
    assert "Caption from the user" in captured.text


@pytest.mark.asyncio
async def test_messenger_caches_every_audio_attachment(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    captured = None

    async def capture(event):
        nonlocal captured
        captured = event

    adapter.handle_message = capture
    event = _audio_event()
    event["message"]["attachments"] = [
        {"type": "audio", "payload": {"url": "https://cdn.example.test/one.m4a?sig=2"}},
        {"type": "audio", "payload": {"url": "https://cdn.example.test/two.ogg?sig=3"}},
    ]
    cache = AsyncMock(side_effect=["/tmp/one.m4a", "/tmp/two.ogg"])
    with patch.object(messenger, "cache_audio_from_url", cache, create=True):
        await adapter._dispatch_event(event)

    assert [call.args for call in cache.await_args_list] == [
        ("https://cdn.example.test/one.m4a?sig=2",),
        ("https://cdn.example.test/two.ogg?sig=3",),
    ]
    assert [call.kwargs for call in cache.await_args_list] == [
        {"ext": ".m4a"},
        {"ext": ".ogg"},
    ]
    assert captured.message_type == MessageType.VOICE
    assert captured.media_urls == [
        "/tmp/one.m4a",
        "/tmp/two.ogg",
    ]
    assert captured.media_types == ["audio/mpeg", "audio/mpeg"]


@pytest.mark.asyncio
async def test_messenger_audio_download_failure_is_safe_and_does_not_leak_url(
    monkeypatch, caplog
):
    adapter = _make_adapter(monkeypatch)
    captured = None

    async def capture(event):
        nonlocal captured
        captured = event

    adapter.handle_message = capture
    signed_url = "https://cdn.example.test/voice.ogg?access_token=must-not-leak"
    cache = AsyncMock(side_effect=RuntimeError(f"download failed for {signed_url}"))
    with patch.object(messenger, "cache_audio_from_url", cache, create=True):
        await adapter._dispatch_event(_audio_event(signed_url))

    assert captured is not None
    assert captured.message_type == MessageType.VOICE
    assert captured.media_urls == []
    assert "could not be downloaded" in captured.text
    assert "must-not-leak" not in caplog.text


@pytest.mark.asyncio
async def test_cached_messenger_voice_reaches_stt_and_keeps_caption():
    runner = _make_runner(stt_enabled=True)
    source = SessionSource(
        platform=Platform("messenger"), chat_id="user-1", chat_type="dm"
    )
    echo_adapter = AsyncMock()
    runner.adapters = {source.platform: echo_adapter}
    event = MessageEvent(
        text="Caption from the user",
        message_type=MessageType.VOICE,
        source=source,
        media_urls=["/tmp/hermes-cache/voice.ogg"],
        media_types=["audio/ogg"],
    )

    with patch(
        "tools.transcription_tools.transcribe_audio",
        return_value={
            "success": True,
            "transcript": "transcribed words",
            "provider": "local",
        },
    ) as transcribe:
        result = await runner._prepare_inbound_message_text(
            event=event, source=source, history=[]
        )

    transcribe.assert_called_once_with("/tmp/hermes-cache/voice.ogg")
    assert "transcribed words" in result
    assert "Caption from the user" in result
    echo_adapter.send.assert_awaited_once()
    assert echo_adapter.send.await_args.args[:2] == ("user-1", '🎙️ "transcribed words"')


@pytest.mark.asyncio
async def test_failed_messenger_transcription_keeps_useful_caption():
    runner = _make_runner(stt_enabled=True)
    source = SessionSource(
        platform=Platform("messenger"), chat_id="user-1", chat_type="dm"
    )
    event = MessageEvent(
        text="Caption from the user",
        message_type=MessageType.VOICE,
        source=source,
        media_urls=["/tmp/hermes-cache/voice.ogg"],
        media_types=["audio/ogg"],
    )

    with patch(
        "tools.transcription_tools.transcribe_audio",
        return_value={
            "success": False,
            "transcript": "",
            "error": "local STT unavailable",
        },
    ):
        result = await runner._prepare_inbound_message_text(
            event=event, source=source, history=[]
        )

    assert "trouble transcribing" in result
    assert "Caption from the user" in result


def test_messenger_image_remains_photo_and_unknown_media_remains_document():
    image = _audio_event()
    image["message"]["attachments"] = [
        {"type": "image", "payload": {"url": "https://cdn.example.test/photo.jpg"}}
    ]
    unknown = _audio_event()
    unknown["message"]["attachments"] = [
        {"type": "unknown", "payload": {"url": "https://cdn.example.test/blob"}}
    ]

    assert messenger._normalize_inbound(image)["message_type"] == MessageType.PHOTO
    assert messenger._normalize_inbound(unknown)["message_type"] == MessageType.DOCUMENT


@pytest.mark.asyncio
async def test_other_platform_audio_still_bypasses_stt():
    runner = _make_runner(stt_enabled=True)
    source = SessionSource(platform=Platform.TELEGRAM, chat_id="1", chat_type="dm")
    event = MessageEvent(
        text="song",
        message_type=MessageType.AUDIO,
        source=source,
        media_urls=["/tmp/song.mp3"],
        media_types=["audio/mpeg"],
    )

    with (
        patch(
            "tools.transcription_tools.transcribe_audio",
            side_effect=AssertionError("AUDIO must not reach STT"),
        ),
        patch(
            "tools.credential_files.to_agent_visible_cache_path",
            side_effect=lambda value: value,
        ),
    ):
        result = await runner._prepare_inbound_message_text(
            event=event, source=source, history=[]
        )

    assert "audio file attachment" in result.lower()


@pytest.mark.asyncio
async def test_invalid_webhook_signature_is_rejected(monkeypatch):
    adapter = _make_adapter(monkeypatch)
    adapter.app_secret = "test-secret"
    request = AsyncMock()
    request.headers = {"x-hub-signature-256": "sha256=00"}
    request.read = AsyncMock(return_value=b'{"object":"page"}')

    response = await adapter._handle_webhook(request)

    assert response.status == 403
    assert messenger._validate_signature(
        b"body",
        "sha256=" + hmac.new(b"test-secret", b"body", hashlib.sha256).hexdigest(),
        "test-secret",
    )
