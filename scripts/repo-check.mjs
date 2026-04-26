#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname } from "node:path";

const textExtensions = new Set([
  ".css",
  ".csv",
  ".gitignore",
  ".html",
  ".js",
  ".json",
  ".json5",
  ".jsonl",
  ".md",
  ".mjs",
  ".ps1",
  ".txt",
  ".yaml",
  ".yml",
]);

const forbiddenTrackedPaths = [
  /^\.openclaw\//,
  /^node_modules\//,
  /^state\/(?!\.gitkeep$)/,
  /(^|\/)auth-profiles\.json$/,
  /(^|\/)credentials(\/|$)/,
  /(^|\/)\.env(\.|$)/,
];

const secretPatterns = [
  { name: "OpenAI-style secret", pattern: /\bsk-[A-Za-z0-9_-]{20,}\b/ },
  { name: "Anthropic-style secret", pattern: /\bsk-ant-[A-Za-z0-9_-]{20,}\b/ },
  { name: "GitHub token", pattern: /\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/ },
  { name: "Google API key", pattern: /\bAIza[0-9A-Za-z_-]{30,}\b/ },
  { name: "Private key block", pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  { name: "OpenClaw gateway token", pattern: /\bgateway\.auth\.token\b\s*[:=]\s*["'][^"']{8,}["']/ },
];

function trackedFiles() {
  const output = execFileSync("git", ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], { encoding: "utf8" });
  return output.split("\0").filter(Boolean);
}

function isTextFile(path) {
  const ext = extname(path).toLowerCase();
  if (textExtensions.has(ext)) return true;
  return [".gitattributes", ".gitignore"].some((suffix) => path.endsWith(suffix));
}

const errors = [];
const files = trackedFiles();

for (const path of files) {
  const normalized = path.replaceAll("\\", "/");

  for (const pattern of forbiddenTrackedPaths) {
    if (pattern.test(normalized)) {
      errors.push(`${path}: forbidden runtime/secret path is tracked`);
    }
  }

  if (!existsSync(path)) continue;

  const stats = statSync(path);
  if (stats.size > 1024 * 1024) {
    errors.push(`${path}: tracked file is larger than 1 MiB; verify this belongs in Git`);
  }

  if (!isTextFile(path)) continue;

  const content = readFileSync(path, "utf8");
  for (const { name, pattern } of secretPatterns) {
    if (pattern.test(content)) {
      errors.push(`${path}: possible ${name}`);
    }
  }

  if (path.endsWith(".json")) {
    try {
      JSON.parse(content);
    } catch (error) {
      errors.push(`${path}: invalid JSON (${error.message})`);
    }
  }

  if (path.endsWith(".jsonl")) {
    const lines = content.split(/\r?\n/);
    lines.forEach((line, index) => {
      if (!line.trim()) return;
      try {
        JSON.parse(line);
      } catch (error) {
        errors.push(`${path}:${index + 1}: invalid JSONL (${error.message})`);
      }
    });
  }
}

if (errors.length > 0) {
  console.error("Repo check failed:");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`Repo check passed (${files.length} tracked or unignored files scanned).`);
