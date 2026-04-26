#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const out = [];

for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];

  if (arg === "--params-file" || arg === "--json-file") {
    const filePath = args[i + 1];
    if (!filePath) {
      console.error(`${arg} requires a file path`);
      process.exit(3);
    }
    if (!existsSync(filePath)) {
      console.error(`${arg} file not found: ${filePath}`);
      process.exit(3);
    }
    const raw = readFileSync(filePath, "utf8").trim();
    try {
      JSON.parse(raw);
    } catch (error) {
      console.error(`${arg} contains invalid JSON: ${error.message}`);
      process.exit(3);
    }
    out.push(arg === "--params-file" ? "--params" : "--json", raw);
    i += 1;
    continue;
  }

  if (arg === "--params-json" || arg === "--body-json") {
    const raw = args[i + 1];
    if (!raw) {
      console.error(`${arg} requires a JSON string`);
      process.exit(3);
    }
    try {
      JSON.parse(raw);
    } catch (error) {
      console.error(`${arg} contains invalid JSON: ${error.message}`);
      process.exit(3);
    }
    out.push(arg === "--params-json" ? "--params" : "--json", raw);
    i += 1;
    continue;
  }

  out.push(arg);
}

const command = process.execPath;
const npxCli = process.platform === "win32"
  ? path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npx-cli.js")
  : "npx";
const commandArgs = process.platform === "win32"
  ? [npxCli, "-y", "@googleworkspace/cli", ...out]
  : ["-y", "@googleworkspace/cli", ...out];

const result = spawnSync(command, commandArgs, {
  stdio: "inherit",
  shell: false
});

if (result.error) {
  console.error(result.error.message);
  process.exit(5);
}

process.exit(result.status ?? 0);
