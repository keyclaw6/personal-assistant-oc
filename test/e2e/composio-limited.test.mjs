import test from "node:test";
import assert from "node:assert/strict";

import { formatComposioFailure } from "../../plugins/openclaw-composio-limited/src/composio-errors.js";

test("formats Composio 401 failures as re-auth instructions", () => {
  const message = formatComposioFailure({
    toolkit: "googlecalendar",
    account: "googlecalendar_deave-cheer",
    tool: "GOOGLECALENDAR_LIST_CALENDARS",
    output: "services/HttpServerError • HTTP 401 Unauthorized",
  });

  assert.match(message, /HTTP 401/);
  assert.match(message, /composio logout/);
  assert.match(message, /composio login/);
  assert.match(message, /composio execute GOOGLECALENDAR_LIST_CALENDARS --get-schema/);
  assert.match(message, /composio link googlecalendar/);
});

test("formats missing connected account failures as reconnect instructions", () => {
  const message = formatComposioFailure({
    toolkit: "gmail",
    account: "gmail_jodo-boort",
    tool: "GMAIL_GET_PROFILE",
    output: 'Error • No connected account matched "gmail_jodo-boort" for toolkit "gmail".',
  });

  assert.match(message, /No connected Composio gmail account matched/);
  assert.match(message, /composio link gmail --list/);
  assert.match(message, /composio link gmail/);
  assert.match(message, /hard-coded alias/);
});

test("preserves unrelated Composio failures verbatim", () => {
  const message = formatComposioFailure({
    toolkit: "googlecalendar",
    account: "googlecalendar_deave-cheer",
    tool: "GOOGLECALENDAR_LIST_CALENDARS",
    output: "some other composio error",
  });

  assert.equal(message, "some other composio error");
});
