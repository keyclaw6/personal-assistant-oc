export function formatComposioFailure({ toolkit, account, tool, output }) {
  const text = String(output || "").replace(/\u001b\[[0-9;]*m/g, "").trim();

  if (/HTTP 401 Unauthorized/i.test(text)) {
    return [
      `Composio CLI auth failed with HTTP 401 while running ${tool} for ${toolkit} account ${account}.`,
      "Re-authenticate this machine with `composio logout` and `composio login`.",
      `Then verify the CLI with \`composio execute ${tool} --get-schema\`.`,
      `If ${toolkit} still fails after login, reconnect it with \`composio link ${toolkit}\` and re-check the selected account.`,
    ].join(" ");
  }

  if (/No connected account matched/i.test(text)) {
    return [
      `No connected Composio ${toolkit} account matched \`${account}\`.`,
      `Run \`composio link ${toolkit} --list\` to inspect current connections, then reconnect with \`composio link ${toolkit}\` if needed.`,
      "If Composio creates a different account id after reconnect, update the hard-coded alias in plugins/openclaw-composio-limited/src/composio-tools.js.",
    ].join(" ");
  }

  return text;
}
