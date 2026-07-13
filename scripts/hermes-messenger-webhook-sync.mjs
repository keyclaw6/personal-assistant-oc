#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const DEFAULT_GRAPH_VERSION = "v25.0";
const DEFAULT_WEBHOOK_PATH = "/messenger/webhook";
const DEFAULT_PROXY_PORT = "18890";

export function parseEnv(text) {
  const result = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const index = trimmed.indexOf("=");
    const key = trimmed.slice(0, index);
    let value = trimmed.slice(index + 1);
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }
  return result;
}

export function normalizeWebhookPath(value = DEFAULT_WEBHOOK_PATH) {
  const trimmed = String(value || DEFAULT_WEBHOOK_PATH).trim();
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function tailscaleDnsName(status) {
  const raw = status?.Self?.DNSName;
  const dnsName = typeof raw === "string" ? raw.replace(/\.+$/, "") : "";
  if (!dnsName.endsWith(".ts.net")) {
    throw new Error("Tailscale did not report a usable ts.net DNS name");
  }
  return dnsName;
}

export function pageIdFromDebugToken(data) {
  const granular = Array.isArray(data?.granular_scopes) ? data.granular_scopes : [];
  for (const item of granular) {
    if (item?.scope !== "pages_messaging" || !Array.isArray(item.target_ids)) continue;
    const pageId = item.target_ids.find((id) => /^\d+$/.test(String(id)));
    if (pageId) return String(pageId);
  }
  throw new Error("Page token does not expose a pages_messaging target page");
}

function loadEnvironment() {
  const hermesHome = process.env.HERMES_HOME || path.join(os.homedir(), ".hermes");
  const envFile = path.join(hermesHome, ".env");
  const fileEnv = existsSync(envFile) ? parseEnv(readFileSync(envFile, "utf8")) : {};
  return { ...fileEnv, ...process.env };
}

function required(env, key) {
  const value = env[key];
  if (!value) throw new Error(`${key} is required in ~/.hermes/.env`);
  return value;
}

function graphError(payload, status) {
  const error = payload?.error;
  const message = error?.message || `HTTP ${status}`;
  const code = error?.code ? ` (code ${error.code})` : "";
  return new Error(`Meta Graph API request failed: ${message}${code}`);
}

async function graphRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(20_000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.error) throw graphError(payload, response.status);
  return payload;
}

async function verifyPublicCallback(callbackUrl, verifyToken) {
  const challenge = `ALBERT_WEBHOOK_SYNC_${randomUUID()}`;
  const url = new URL(callbackUrl);
  url.searchParams.set("hub.mode", "subscribe");
  url.searchParams.set("hub.verify_token", verifyToken);
  url.searchParams.set("hub.challenge", challenge);
  const response = await fetch(url, { signal: AbortSignal.timeout(20_000) });
  const body = await response.text();
  if (!response.ok || body !== challenge) {
    throw new Error(`Public Messenger callback verification failed with HTTP ${response.status}`);
  }
}

export async function syncMessengerWebhook({ env = loadEnvironment() } = {}) {
  const pageToken = required(env, "MESSENGER_PAGE_ACCESS_TOKEN");
  const appSecret = required(env, "MESSENGER_APP_SECRET");
  const verifyToken = required(env, "MESSENGER_VERIFY_TOKEN");
  const webhookPath = normalizeWebhookPath(env.MESSENGER_WEBHOOK_PATH);
  const proxyPort = env.MESSENGER_PROXY_PORT || DEFAULT_PROXY_PORT;
  const graphVersion = env.MESSENGER_GRAPH_API_VERSION || DEFAULT_GRAPH_VERSION;

  const tailscaleStatus = JSON.parse(
    execFileSync("tailscale", ["status", "--json"], { encoding: "utf8" }),
  );
  const dnsName = tailscaleDnsName(tailscaleStatus);
  const callbackUrl = `https://${dnsName}${webhookPath}`;
  const proxyUrl = `http://127.0.0.1:${proxyPort}${webhookPath}`;

  execFileSync(
    "tailscale",
    ["funnel", "--bg", "--yes", `--set-path=${webhookPath}`, proxyUrl],
    { stdio: "pipe" },
  );
  await verifyPublicCallback(callbackUrl, verifyToken);

  const graphBase = `https://graph.facebook.com/${graphVersion}`;
  const debugUrl = new URL(`${graphBase}/debug_token`);
  debugUrl.searchParams.set("input_token", pageToken);
  debugUrl.searchParams.set("access_token", pageToken);
  const debug = await graphRequest(debugUrl);
  if (!debug?.data?.is_valid || debug.data.type !== "PAGE") {
    throw new Error("MESSENGER_PAGE_ACCESS_TOKEN is not a valid Page token");
  }

  const appId = String(debug.data.app_id || "");
  if (!/^\d+$/.test(appId)) throw new Error("Could not derive the Meta app ID from the Page token");
  const pageId = pageIdFromDebugToken(debug.data);
  const appAccessToken = `${appId}|${appSecret}`;

  const subscriptionsUrl = new URL(`${graphBase}/${appId}/subscriptions`);
  subscriptionsUrl.searchParams.set("access_token", appAccessToken);
  let subscriptions = await graphRequest(subscriptionsUrl);
  let active = subscriptions?.data?.some(
    (item) =>
      item?.object === "page" &&
      item?.active === true &&
      item?.callback_url === callbackUrl &&
      item?.fields?.some((field) => field?.name === "messages"),
  );
  const callbackUpdated = !active;

  if (callbackUpdated) {
    await graphRequest(`${graphBase}/${appId}/subscriptions`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        object: "page",
        callback_url: callbackUrl,
        verify_token: verifyToken,
        fields: "messages",
        access_token: appAccessToken,
      }),
    });
  }

  await graphRequest(`${graphBase}/${pageId}/subscribed_apps`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      subscribed_fields: "messages",
      access_token: pageToken,
    }),
  });

  subscriptions = await graphRequest(subscriptionsUrl);
  active = subscriptions?.data?.some(
    (item) =>
      item?.object === "page" &&
      item?.active === true &&
      item?.callback_url === callbackUrl &&
      item?.fields?.some((field) => field?.name === "messages"),
  );
  if (!active) throw new Error("Meta did not retain the active Messenger callback subscription");

  return { callbackUrl, appId, pageId, webhookPath, proxyUrl, callbackUpdated, active: true };
}

async function main() {
  const result = await syncMessengerWebhook();
  console.log(JSON.stringify(result, null, 2));
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch((error) => {
    console.error(`Messenger webhook sync failed: ${error.message}`);
    process.exitCode = 1;
  });
}
