#!/usr/bin/env node
import { chmodSync, existsSync, lstatSync, mkdirSync, readFileSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import os from "node:os";

const REPO = path.resolve(import.meta.dirname, "..");
const HERMES_HOME = process.env.HERMES_HOME || path.join(os.homedir(), ".hermes");
const OPENCLAW_HOME = process.env.OPENCLAW_HOME || path.join(os.homedir(), ".openclaw");
const OPENCLAW_CONFIG = path.join(OPENCLAW_HOME, "openclaw.json");
const CODEX_AUTH = path.join(os.homedir(), ".codex/auth.json");
const HERMES_AGENT = path.join(HERMES_HOME, "hermes-agent");
const HERMES_PYTHON = path.join(HERMES_AGENT, "venv/bin/python");
const HERMES_ENV = path.join(HERMES_HOME, ".env");
const HERMES_CONFIG = path.join(HERMES_HOME, "config.yaml");

function readJson(file, fallback = undefined) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function nested(obj, pathParts, fallback = undefined) {
  let cur = obj;
  for (const part of pathParts) {
    if (!cur || typeof cur !== "object" || !(part in cur)) return fallback;
    cur = cur[part];
  }
  return cur ?? fallback;
}

function parseEnv(file) {
  const out = new Map();
  if (!existsSync(file)) return out;
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    out.set(line.slice(0, index), line.slice(index + 1));
  }
  return out;
}

function shellQuote(value) {
  const text = String(value ?? "");
  if (/^[A-Za-z0-9_./:@%+=,-]*$/.test(text)) return text;
  return JSON.stringify(text);
}

function writeEnvMerged(file, updates) {
  mkdirSync(path.dirname(file), { recursive: true });
  const existingLines = existsSync(file) ? readFileSync(file, "utf8").split(/\r?\n/) : [];
  const removeKeys = new Set(updates.__remove || []);
  const remaining = new Map(
    Object.entries(updates).filter(([key, value]) => (
      key !== "__remove" && value !== undefined && value !== null && String(value) !== ""
    )),
  );
  const lines = [];
  for (const line of existingLines) {
    if (!line.includes("=") || line.trim().startsWith("#")) {
      if (line !== "" || lines.length > 0) lines.push(line);
      continue;
    }
    const key = line.slice(0, line.indexOf("="));
    if (removeKeys.has(key)) continue;
    if (remaining.has(key)) {
      lines.push(`${key}=${shellQuote(remaining.get(key))}`);
      remaining.delete(key);
    } else {
      lines.push(line);
    }
  }
  if (remaining.size) {
    if (lines.length && lines[lines.length - 1] !== "") lines.push("");
    lines.push("# Albert Hermes migration");
    for (const [key, value] of remaining) lines.push(`${key}=${shellQuote(value)}`);
  }
  writeFileSync(file, lines.join("\n").replace(/\n*$/, "\n"), { mode: 0o600 });
  chmodSync(file, 0o600);
}

function linkPlugin(name) {
  const target = path.join(REPO, "hermes/plugins", name);
  const link = path.join(HERMES_HOME, "plugins", name);
  mkdirSync(path.dirname(link), { recursive: true });
  if (existsSync(link)) {
    const stat = lstatSync(link);
    if (stat.isSymbolicLink()) unlinkSync(link);
    else return { name, linked: false, reason: "path exists and is not a symlink" };
  }
  symlinkSync(target, link, "dir");
  return { name, linked: true, target, link };
}

async function inferMessengerHomeChannel() {
  const sessionsDir = path.join(OPENCLAW_HOME, "agents/main/sessions");
  try {
    const files = (await readdir(sessionsDir))
      .filter((name) => name.endsWith(".jsonl") || name.endsWith(".trajectory.jsonl"))
      .slice(-80);
    const counts = new Map();
    for (const file of files) {
      const text = await readFile(path.join(sessionsDir, file), "utf8").catch(() => "");
      for (const match of text.matchAll(/messenger:dm:(\d{5,})/g)) {
        counts.set(match[1], (counts.get(match[1]) || 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  } catch {
    return "";
  }
}

function importCodexAuth() {
  const codexCliAuth = readJson(CODEX_AUTH, {});
  const codexCliTokens = codexCliAuth?.tokens || {};
  let payload;
  let source;

  if (
    codexCliAuth?.auth_mode === "chatgpt" &&
    codexCliTokens.access_token &&
    codexCliTokens.refresh_token
  ) {
    source = "codex-cli";
    payload = {
      tokens: {
        access_token: codexCliTokens.access_token,
        refresh_token: codexCliTokens.refresh_token,
      },
      last_refresh: codexCliAuth.last_refresh,
      label: codexCliAuth.userEmail || "codex-cli-import",
    };
  }

  const authProfiles = readJson(path.join(OPENCLAW_HOME, "agents/main/agent/auth-profiles.json"), {});
  const profiles = authProfiles.profiles || {};
  const profile = Object.values(profiles).find((item) => item && item.provider === "openai-codex" && item.access && item.refresh);
  if (!payload && profile) {
    source = "openclaw";
    payload = {
      tokens: { access_token: profile.access, refresh_token: profile.refresh },
      label: profile.email || "openclaw-import",
    };
  }

  if (!payload) return { imported: false, reason: "No Codex CLI or OpenClaw openai-codex OAuth profile found" };
  const temp = path.join(os.tmpdir(), `hermes-codex-auth-${process.pid}.json`);
  writeFileSync(temp, JSON.stringify(payload), { mode: 0o600 });
  chmodSync(temp, 0o600);
  const code = `
import json, sys
from hermes_cli.auth import _save_codex_tokens
with open(sys.argv[1], "r", encoding="utf-8") as f:
    payload = json.load(f)
_save_codex_tokens(payload["tokens"], last_refresh=payload.get("last_refresh"), label=payload.get("label"))
print("imported")
`;
  const proc = spawnSync(HERMES_PYTHON, ["-c", code, temp], {
    cwd: HERMES_AGENT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  unlinkSync(temp);
  if (proc.status !== 0) {
    return { imported: false, reason: (proc.stderr || proc.stdout).trim() };
  }
  return { imported: true, label: payload.label, source };
}

function updateHermesConfig(payload) {
  const temp = path.join(os.tmpdir(), `hermes-config-${process.pid}.json`);
  writeFileSync(temp, JSON.stringify(payload), { mode: 0o600 });
  chmodSync(temp, 0o600);
  const code = `
import json, sys
from pathlib import Path
import yaml
config_path = Path(sys.argv[1])
payload_path = Path(sys.argv[2])
data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
if not isinstance(data, dict):
    data = {}
payload = json.loads(payload_path.read_text(encoding="utf-8"))
def ensure_dict(parent, key):
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value
def ensure_list(parent, key):
    value = parent.get(key)
    if not isinstance(value, list):
        value = []
        parent[key] = value
    return value
model = ensure_dict(data, "model")
model["provider"] = "openai-codex"
model["default"] = "gpt-5.6-luna"
model["base_url"] = "https://chatgpt.com/backend-api/codex"
agent = ensure_dict(data, "agent")
agent["reasoning_effort"] = "xhigh"
terminal = ensure_dict(data, "terminal")
terminal["cwd"] = payload["workspace"]
terminal["timeout"] = 180
plugins = ensure_dict(data, "plugins")
enabled = ensure_list(plugins, "enabled")
for name in ("messenger-platform", "composio-limited", "cognee-memory"):
    if name not in enabled:
        enabled.append(name)
memory = ensure_dict(data, "memory")
memory["provider"] = "cognee-memory"
memory["memory_enabled"] = True
memory["user_profile_enabled"] = True
gateway = ensure_dict(data, "gateway")
platforms = ensure_dict(gateway, "platforms")
messenger = ensure_dict(platforms, "messenger")
messenger["enabled"] = True
extra = ensure_dict(messenger, "extra")
extra["webhook_path"] = payload["webhook_path"]
extra["host"] = payload["messenger_host"]
extra["port"] = payload["messenger_port"]
extra.pop("home_channel", None)
if payload.get("messenger_home_channel"):
    messenger["home_channel"] = {
        "platform": "messenger",
        "chat_id": payload["messenger_home_channel"],
        "name": "Messenger home",
    }
toolsets = ensure_dict(data, "platform_toolsets")
messenger_toolsets = toolsets.get("messenger")
if not isinstance(messenger_toolsets, list):
    messenger_toolsets = []
    toolsets["messenger"] = messenger_toolsets
for name in ("hermes-cli", "composio-limited"):
    if name not in messenger_toolsets:
        messenger_toolsets.append(name)
cli_toolsets = toolsets.get("cli")
if not isinstance(cli_toolsets, list):
    cli_toolsets = []
    toolsets["cli"] = cli_toolsets
if "composio-limited" not in cli_toolsets:
    cli_toolsets.append("composio-limited")
curator = ensure_dict(data, "curator")
curator["enabled"] = True
curator["paused"] = False
config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
`;
  const proc = spawnSync(HERMES_PYTHON, ["-c", code, HERMES_CONFIG, temp], {
    cwd: HERMES_AGENT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  unlinkSync(temp);
  if (proc.status !== 0) throw new Error((proc.stderr || proc.stdout).trim());
}

const openclaw = readJson(OPENCLAW_CONFIG, {});
const messengerConfig =
  nested(openclaw, ["channels", "messenger"], {}) ||
  nested(openclaw, ["plugins", "entries", "messenger", "config"], {}) ||
  {};
const messengerEntryConfig = nested(openclaw, ["plugins", "entries", "messenger", "config"], {}) || {};
const mergedMessenger = { ...messengerConfig, ...messengerEntryConfig };
const allowFrom = [
  ...(Array.isArray(mergedMessenger.allowFrom) ? mergedMessenger.allowFrom : []),
  ...(Array.isArray(mergedMessenger.dm?.allowFrom) ? mergedMessenger.dm.allowFrom : []),
].map(String);
const inferredHome = await inferMessengerHomeChannel();
const homeChannel = process.env.MESSENGER_HOME_CHANNEL || allowFrom[0] || inferredHome;

const envUpdates = {
  __remove: ["MESSAGING_CWD"],
  PERSONAL_ASSISTANT_REPO: REPO,
  ALBERT_WORKSPACE: path.join(REPO, "albert"),
  ALBERT_COGNEE_ENV: path.join(REPO, ".env.cognee"),
  COGNEE_BASE_URL: process.env.COGNEE_BASE_URL || "http://127.0.0.1:8000",
  COGNEE_DATASETS_FILE: path.join(OPENCLAW_HOME, "memory/cognee/datasets.json"),
  COGNEE_DATASET_NAME: "openclaw",
  COGNEE_SEARCH_TYPE: nested(openclaw, ["plugins", "entries", "cognee-openclaw", "config", "searchType"], "CHUNKS"),
  TAVILY_API_KEY: nested(openclaw, ["plugins", "entries", "tavily", "config", "webSearch", "apiKey"], ""),
  MESSENGER_PAGE_ACCESS_TOKEN: mergedMessenger.pageAccessToken || process.env.MESSENGER_PAGE_ACCESS_TOKEN || "",
  MESSENGER_APP_SECRET: mergedMessenger.appSecret || process.env.MESSENGER_APP_SECRET || "",
  MESSENGER_VERIFY_TOKEN: mergedMessenger.verifyToken || process.env.MESSENGER_VERIFY_TOKEN || "",
  MESSENGER_WEBHOOK_PATH: mergedMessenger.webhookPath || "/messenger/webhook",
  MESSENGER_HOST: process.env.MESSENGER_HOST || "127.0.0.1",
  MESSENGER_PORT: process.env.MESSENGER_PORT || "18891",
  MESSENGER_ALLOWED_USERS: allowFrom.join(","),
  MESSENGER_ALLOW_ALL_USERS: allowFrom.length ? "false" : "true",
  MESSENGER_HOME_CHANNEL: homeChannel,
  COMPOSIO_BIN: process.env.COMPOSIO_BIN || "/home/kab/.composio/composio",
};

const links = ["messenger-platform", "cognee-memory", "composio-limited"].map(linkPlugin);
writeEnvMerged(HERMES_ENV, envUpdates);
const auth = importCodexAuth();
updateHermesConfig({
  workspace: path.join(REPO, "albert"),
  webhook_path: envUpdates.MESSENGER_WEBHOOK_PATH,
  messenger_host: envUpdates.MESSENGER_HOST,
  messenger_port: Number(envUpdates.MESSENGER_PORT),
  messenger_home_channel: envUpdates.MESSENGER_HOME_CHANNEL,
});

const summary = {
  hermesHome: HERMES_HOME,
  pluginLinks: links,
  codexAuth: auth.imported ? { imported: true, label: auth.label, source: auth.source } : auth,
  messenger: {
    webhookPath: envUpdates.MESSENGER_WEBHOOK_PATH,
    host: envUpdates.MESSENGER_HOST,
    port: envUpdates.MESSENGER_PORT,
    hasPageToken: Boolean(envUpdates.MESSENGER_PAGE_ACCESS_TOKEN),
    hasAppSecret: Boolean(envUpdates.MESSENGER_APP_SECRET),
    hasVerifyToken: Boolean(envUpdates.MESSENGER_VERIFY_TOKEN),
    allowedUsersCount: allowFrom.length,
    allowAllUsers: envUpdates.MESSENGER_ALLOW_ALL_USERS === "true",
    hasHomeChannel: Boolean(homeChannel),
  },
  cognee: {
    envFile: envUpdates.ALBERT_COGNEE_ENV,
    datasetsFile: envUpdates.COGNEE_DATASETS_FILE,
    datasetName: envUpdates.COGNEE_DATASET_NAME,
    searchType: envUpdates.COGNEE_SEARCH_TYPE,
  },
};

console.log(JSON.stringify(summary, null, 2));
