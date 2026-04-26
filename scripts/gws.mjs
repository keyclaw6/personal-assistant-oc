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

function resolveNpx() {
  const npmExecPath = process.env.npm_execpath;
  const cliCandidates = [
    npmExecPath?.replace(/[\\/]npm-cli\.js$/i, `${path.sep}npx-cli.js`),
    path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npx-cli.js")
  ].filter(Boolean);

  const npxCli = cliCandidates.find((candidate) => existsSync(candidate));
  if (npxCli) {
    return {
      command: process.execPath,
      args: [npxCli, "-y", "@googleworkspace/cli", ...out],
      shell: false
    };
  }

  return {
    command: process.platform === "win32" ? "npx.cmd" : "npx",
    args: ["-y", "@googleworkspace/cli", ...out],
    shell: process.platform === "win32"
  };
}

const { command, args: commandArgs, shell } = resolveNpx();

const result = spawnSync(command, commandArgs, {
  stdio: "inherit",
  shell
});

if (result.error) {
  console.error(result.error.message);
  process.exit(5);
}

process.exit(result.status ?? 0);
