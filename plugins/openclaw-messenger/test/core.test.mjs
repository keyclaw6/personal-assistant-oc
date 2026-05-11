import assert from "node:assert/strict";
import crypto from "node:crypto";
import { test } from "node:test";

import { resolveAccount, resolveAccountFromEnv } from "../dist/src/accounts.js";
import { validateSignature } from "../dist/src/signature.js";
import { chunkText } from "../dist/src/send.js";

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
