import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";

import { resolveAccount, resolveAccountFromEnv } from "../dist/src/accounts.js";
import { validateSignature } from "../dist/src/signature.js";
import { chunkText } from "../dist/src/send.js";
import { normalizeMessengerInbound } from "../dist/src/inbound.js";
import { downloadMessengerMedia, messengerMediaExtension } from "../dist/src/media-download.js";

test("validateSignature accepts valid Meta sha256 signatures", () => {
  const body = JSON.stringify({ object: "page", entry: [] });
  const secret = "app-secret";
  const sig = `sha256=${crypto.createHmac("sha256", secret).update(body).digest("hex")}`;
  assert.equal(validateSignature(body, sig, secret), true);
});

test("validateSignature rejects invalid signatures", () => {
  assert.equal(validateSignature("{}", "sha256=deadbeef", "app-secret"), false);
  assert.equal(validateSignature("{}", "deadbeef", "app-secret"), false);
});

test("resolveAccount reads top-level messenger config", () => {
  const account = resolveAccount({
    channels: {
      messenger: {
        pageAccessToken: "token",
        appSecret: "secret",
        verifyToken: "verify",
        dm: { policy: "pairing", allowFrom: ["123"] },
      },
    },
  });

  assert.equal(account.accountId, "default");
  assert.equal(account.enabled, true);
  assert.equal(account.pageAccessToken, "token");
  assert.equal(account.appSecret, "secret");
  assert.equal(account.verifyToken, "verify");
  assert.deepEqual(account.config.dm?.allowFrom, ["123"]);
});

test("resolveAccountFromEnv uses env fallback when config token is absent", () => {
  const oldToken = process.env.MESSENGER_PAGE_ACCESS_TOKEN;
  const oldSecret = process.env.MESSENGER_APP_SECRET;
  const oldVerify = process.env.MESSENGER_VERIFY_TOKEN;

  try {
    process.env.MESSENGER_PAGE_ACCESS_TOKEN = "env-token";
    process.env.MESSENGER_APP_SECRET = "env-secret";
    process.env.MESSENGER_VERIFY_TOKEN = "env-verify";
    const account = resolveAccountFromEnv({ channels: { messenger: {} } });
    assert.equal(account.enabled, true);
    assert.equal(account.pageAccessToken, "env-token");
    assert.equal(account.appSecret, "env-secret");
    assert.equal(account.verifyToken, "env-verify");
  } finally {
    if (oldToken === undefined) delete process.env.MESSENGER_PAGE_ACCESS_TOKEN;
    else process.env.MESSENGER_PAGE_ACCESS_TOKEN = oldToken;
    if (oldSecret === undefined) delete process.env.MESSENGER_APP_SECRET;
    else process.env.MESSENGER_APP_SECRET = oldSecret;
    if (oldVerify === undefined) delete process.env.MESSENGER_VERIFY_TOKEN;
    else process.env.MESSENGER_VERIFY_TOKEN = oldVerify;
  }
});

test("chunkText splits long text within the requested limit", () => {
  const chunks = chunkText("a".repeat(4500), 2000);
  assert.equal(chunks.length, 3);
  assert.ok(chunks.every((chunk) => chunk.length <= 2000));
  assert.equal(chunks.join(""), "a".repeat(4500));
});

test("normalizeMessengerInbound preserves text-only messages", () => {
  const inbound = normalizeMessengerInbound({ message: { mid: "m1", text: "hello" } });
  assert.equal(inbound?.text, "hello");
  assert.deepEqual(inbound?.mediaUrls, []);
  assert.equal(inbound?.messageSid, "m1");
});

test("normalizeMessengerInbound handles attachment-only images", () => {
  const inbound = normalizeMessengerInbound({
    message: {
      mid: "m2",
      attachments: [{ type: "image", payload: { url: "https://example.com/image.jpg", sticker_id: 123 } }],
    },
  });
  assert.equal(inbound?.text, "Messenger attachments: image (sticker 123).");
  assert.deepEqual(inbound?.mediaUrls, ["https://example.com/image.jpg"]);
  assert.deepEqual(inbound?.mediaTypes, ["image/jpeg"]);
  assert.equal(inbound?.sticker, "123");
  assert.equal(inbound?.stickerMediaIncluded, true);
});

test("normalizeMessengerInbound handles multiple audio and video attachments", () => {
  const inbound = normalizeMessengerInbound({
    message: {
      text: "see these",
      attachments: [
        { type: "audio", payload: { url: "https://example.com/audio.mp3" } },
        { type: "video", payload: { url: "https://example.com/video.mp4" } },
      ],
    },
  });
  assert.equal(inbound?.text, "see these\nMessenger attachments: audio, video.");
  assert.deepEqual(inbound?.mediaUrls, ["https://example.com/audio.mp3", "https://example.com/video.mp4"]);
  assert.deepEqual(inbound?.mediaTypes, ["audio/mpeg", "video/mp4"]);
});

test("normalizeMessengerInbound preserves postback title", () => {
  const inbound = normalizeMessengerInbound({ postback: { title: "Get started" } });
  assert.equal(inbound?.text, "Get started");
  assert.deepEqual(inbound?.mediaUrls, []);
});

test("normalizeMessengerInbound handles reactions", () => {
  const inbound = normalizeMessengerInbound({ reaction: { action: "react", reaction: "love", emoji: "❤️", mid: "m3" } });
  assert.equal(inbound?.text, "Messenger reaction: react love on message m3.");
  assert.deepEqual(inbound?.mediaUrls, []);
  assert.equal(inbound?.messageSid, "m3");
  assert.deepEqual(inbound?.untrustedStructuredContext, [
    {
      label: "Messenger reaction",
      source: "messenger",
      type: "reaction",
      payload: { action: "react", reaction: "love", emoji: "❤️", mid: "m3" },
    },
  ]);
});

test("messengerMediaExtension infers safe extensions", () => {
  assert.equal(messengerMediaExtension("image/jpeg", "https://example.com/no-ext"), ".jpg");
  assert.equal(messengerMediaExtension(undefined, "https://example.com/file.mp4?x=1"), ".mp4");
  assert.equal(messengerMediaExtension(undefined, "not a url"), ".bin");
});

test("downloadMessengerMedia writes fetched media and records failures", async () => {
  const fetchImpl = async (url) => {
    if (url.endsWith("missing.jpg")) return new Response("missing", { status: 404 });
    return new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-length": "3", "content-type": "image/png" } });
  };

  const result = await downloadMessengerMedia(
    ["https://example.com/image", "https://example.com/missing.jpg"],
    ["image/jpeg", "image/jpeg"],
    { maxBytes: 10, fetchImpl },
  );

  assert.equal(result.paths.length, 1);
  assert.equal(result.mediaPaths.length, 2);
  assert.match(result.paths[0], /media-1\.png$/);
  assert.match(result.mediaPaths[0], /media-1\.png$/);
  assert.equal(result.mediaPaths[1], "");
  assert.deepEqual(result.mediaTypes, ["image/png", "image/jpeg"]);
  assert.ok(result.dir);
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0].error, /HTTP 404/);
});

test("downloadMessengerMedia enforces max bytes", async () => {
  const fetchImpl = async () => new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-length": "3" } });
  const result = await downloadMessengerMedia(["https://example.com/image.jpg"], ["image/jpeg"], { maxBytes: 2, fetchImpl });
  assert.deepEqual(result.paths, []);
  assert.equal(result.dir, undefined);
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0].error, /exceeds max bytes/);
});
