import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeWebhookPath,
  pageIdFromDebugToken,
  parseEnv,
  tailscaleDnsName,
} from "../../scripts/hermes-messenger-webhook-sync.mjs";

test("normalizes the Messenger webhook path", () => {
  assert.equal(normalizeWebhookPath("messenger/webhook"), "/messenger/webhook");
  assert.equal(normalizeWebhookPath("/custom"), "/custom");
});

test("derives the current Tailscale DNS name without persisting an old tailnet", () => {
  assert.equal(
    tailscaleDnsName({ Self: { DNSName: "omarchy.tail-current.ts.net." } }),
    "omarchy.tail-current.ts.net",
  );
  assert.throws(() => tailscaleDnsName({ Self: {} }), /usable ts.net DNS name/);
});

test("derives the subscribed Page from the Page token metadata", () => {
  assert.equal(
    pageIdFromDebugToken({
      granular_scopes: [
        { scope: "public_profile" },
        { scope: "pages_messaging", target_ids: ["1206651492532355"] },
      ],
    }),
    "1206651492532355",
  );
});

test("parses quoted Hermes environment values", () => {
  assert.deepEqual(parseEnv('A=plain\nB="quoted value"\n# comment\n'), {
    A: "plain",
    B: "quoted value",
  });
});
