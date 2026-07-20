#!/usr/bin/env node
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { formatComposioFailure } from "../../../plugins/openclaw-composio-limited/src/composio-errors.js";

const REPO = process.env.PERSONAL_ASSISTANT_REPO || "/home/kab/personal-assistant-oc";
const SOURCE = resolve(REPO, "plugins/openclaw-composio-limited/src/composio-tools.js");
const COMPOSIO_BIN = process.env.COMPOSIO_BIN || "/home/kab/.composio/composio";

function extractBalanced(source, startIndex, open, close) {
  const start = source.indexOf(open, startIndex);
  if (start < 0) throw new Error(`Could not find ${open}`);
  let depth = 0;
  let quote = "";
  let escaped = false;
  for (let i = start; i < source.length; i++) {
    const ch = source[i];
    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === quote) {
        quote = "";
      }
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === open) depth++;
    if (ch === close) depth--;
    if (depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`Unbalanced ${open}${close}`);
}

async function loadAllowlist() {
  const source = await readFile(SOURCE, "utf8");
  const accountsStart = source.indexOf("const ACCOUNTS");
  const toolsStart = source.indexOf("const TOOLS_BY_TOOLKIT");
  if (accountsStart < 0 || toolsStart < 0) throw new Error("Could not find Composio allowlist constants");
  const accountsExpr = extractBalanced(source, accountsStart, "[", "]");
  const toolsExpr = extractBalanced(source, toolsStart, "{", "}");
  return Function(`return { ACCOUNTS: ${accountsExpr}, TOOLS_BY_TOOLKIT: ${toolsExpr} };`)();
}

function parseComposioJson(output) {
  const text = String(output || "").replace(/\u001b\[[0-9;]*m/g, "").trim();
  if (!text) {
    throw new Error("Composio returned no output. Run `composio whoami`; if it is not logged in, run `composio login`, then retry.");
  }
  const starts = [text.indexOf("{"), text.indexOf("[")].filter((index) => index >= 0);
  if (starts.length === 0) return { raw: text };
  return JSON.parse(text.slice(Math.min(...starts)));
}

async function runComposio(tool, account, args, toolkit) {
  const dir = await mkdtemp(join(tmpdir(), "hermes-composio-"));
  const dataPath = join(dir, "input.json");
  await writeFile(dataPath, JSON.stringify(args ?? {}), "utf8");
  try {
    const child = spawn(COMPOSIO_BIN, ["execute", tool, "--account", account, "-d", `@${dataPath}`], {
      env: {
        ...process.env,
        HOME: process.env.HOME || "/home/kab",
        PATH: `${process.env.HOME || "/home/kab"}/.composio:${process.env.PATH || ""}`,
        NO_COLOR: "1",
        FORCE_COLOR: "0",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const [stdout, stderr, code] = await new Promise((resolveDone) => {
      let out = "";
      let err = "";
      child.stdout.on("data", (chunk) => { out += chunk; });
      child.stderr.on("data", (chunk) => { err += chunk; });
      child.on("close", (exitCode) => resolveDone([out, err, exitCode]));
    });
    if (code !== 0) {
      throw new Error(formatComposioFailure({ toolkit, account, tool, output: stderr || stdout || `composio exited with ${code}` }));
    }
    return parseComposioJson(stdout);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

const command = process.argv[2];
const payload = process.argv[3] ? JSON.parse(process.argv[3]) : {};
const allowlist = await loadAllowlist();
const accounts = allowlist.ACCOUNTS;
const toolsByToolkit = allowlist.TOOLS_BY_TOOLKIT;

if (command === "status") {
  console.log(JSON.stringify({ accounts, toolsByToolkit }, null, 2));
  process.exit(0);
}

if (command === "execute") {
  const account = accounts.find((item) => item.id === payload.account);
  if (!account) throw new Error(`Account is not allowed: ${payload.account}`);
  const allowedTools = toolsByToolkit[account.toolkit] || [];
  if (!allowedTools.includes(payload.tool)) {
    throw new Error(`Tool is not allowed for ${account.label}: ${payload.tool}`);
  }
  const result = await runComposio(payload.tool, account.id, payload.arguments || {}, account.toolkit);
  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}

throw new Error(`Unknown bridge command: ${command}`);
