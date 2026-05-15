#!/usr/bin/env node
/**
 * repo-check.mjs — Verify repo hygiene for the Companion workspace.
 *
 * Checks:
 * 1. No secrets or credentials committed.
 * 2. No .env files committed (except .env.template).
 * 3. No node_modules/ or dist/ committed under plugins/.
 * 4. .cognee_system/ and .cognee_data/ are gitignored.
 * 5. Companion runtime prompt files are non-empty.
 * 6. companion/memory/ tree exists with expected subdirectories.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const REPO = path.resolve(import.meta.dirname, "..");
const COMPANION = "companion";

// ── helpers ──────────────────────────────────────────────────────────────────

function trackedFiles() {
  const out = execFileSync("git", ["ls-files"], {
    cwd: REPO,
    encoding: "utf8",
  });
  return out.split("\n").filter(Boolean);
}

function read(file) {
  const p = path.join(REPO, file);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

function companionPath(file) {
  return path.join(COMPANION, file);
}

function isGitignored(pattern) {
  try {
    execFileSync("git", ["check-ignore", pattern], { cwd: REPO, encoding: "utf8" });
    return true;
  } catch {
    return false;
  }
}

// ── checks ───────────────────────────────────────────────────────────────────

const errors = [];
const files = trackedFiles();

// 1. No .env files committed
for (const f of files) {
  const base = path.basename(f);
  if (/^\.env(\..*)?$/.test(base) && base !== ".env.template") {
    errors.push(`${f}: .env file should not be committed`);
  }
}

// 2. No node_modules or dist under plugins/ (except openclaw-messenger/dist/ — committed intentionally)
for (const f of files) {
  if (f.startsWith("plugins/") && f.includes("/node_modules/")) {
    errors.push(`${f}: dependency artifact should not be committed`);
  }
  if (f.startsWith("plugins/") && f.includes("/dist/") && !f.startsWith("plugins/openclaw-messenger/dist/")) {
    errors.push(`${f}: build artifact should not be committed`);
  }
}

// 3. Cognee runtime dirs gitignored
if (!isGitignored(".cognee_system/")) {
  errors.push(".cognee_system/ is not gitignored");
}
if (!isGitignored(".cognee_data/")) {
  errors.push(".cognee_data/ is not gitignored");
}

// 4. Companion runtime identity files non-empty
const identityFiles = [
  "IDENTITY.md",
  "SOUL.md",
  "USER.md",
  "AGENTS.md",
  "TOOLS.md",
  "MEMORY.md",
  "HEARTBEAT.md",
  "DREAM.md",
];
for (const f of identityFiles) {
  const content = read(companionPath(f));
  if (!content.trim()) {
    errors.push(`${companionPath(f)}: identity file is empty`);
  }
}

if (!read("README.md").trim()) {
  errors.push("README.md: repo overview is empty");
}
// 5. memory/ tree exists
const memoryDirs = [
  "memory/profile",
  "memory/beliefs",
  "memory/patterns",
  "memory/observations",
  "memory/sessions",
  "memory/life",
  "memory/life/journals",
  "memory/life/reflections",
  "memory/life/dream-logs",
  "memory/life/dream-staging",
  "memory/life/dream-backups",
  "memory/sources",
];
for (const dir of memoryDirs) {
  if (!existsSync(path.join(REPO, COMPANION, dir))) {
    errors.push(`${companionPath(dir)}/: expected memory subdirectory missing`);
  }
}

// 6. Required job/method prompts exist
const workflowFiles = [
  "jobs/MORNING_BRIEF.md",
  "jobs/EVENING_JOURNAL_REMINDER.md",
  "jobs/NIGHTLY_REVIEW.md",
  "jobs/WEEKLY_REVIEW.md",
  "jobs/BOOK_INGESTION.md",
  "jobs/PROMPT_OPTIMIZER.md",
  "methods/BELIEF_WORK.md",
  "methods/PATTERN_WORK.md",
];
for (const f of workflowFiles) {
  const content = read(companionPath(f));
  if (!content.trim()) {
    errors.push(`${companionPath(f)}: workflow file is empty or missing`);
  }
}

// 7. conflicts.md exists
if (!existsSync(path.join(REPO, COMPANION, "memory/conflicts.md"))) {
  errors.push("companion/memory/conflicts.md: missing");
}

// 8. Secret patterns in tracked text files
const secretPatterns = [
  { name: "OpenRouter API key", pattern: /sk-or-v1-[A-Za-z0-9]{20,}/ },
  { name: "Tavily API key", pattern: /tvly-[A-Za-z0-9_-]{20,}/ },
  { name: "OpenAI-style secret", pattern: /\bsk-[A-Za-z0-9_-]{20,}\b/ },
  { name: "Anthropic-style secret", pattern: /\bsk-ant-[A-Za-z0-9_-]{20,}\b/ },
  { name: "GitHub token", pattern: /\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/ },
  { name: "Private key block", pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
];

const textExts = new Set([".md", ".json", ".mjs", ".js", ".ts", ".yaml", ".yml", ".txt", ".gitignore"]);
for (const f of files) {
  const ext = path.extname(f).toLowerCase();
  if (!textExts.has(ext)) continue;
  const content = read(f);
  for (const { name, pattern } of secretPatterns) {
    if (pattern.test(content)) {
      errors.push(`${f}: possible ${name} found in tracked file`);
    }
  }
}

// ── report ───────────────────────────────────────────────────────────────────

if (errors.length > 0) {
  console.error("Repo check failed:");
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log(`Repo check passed (${files.length} files scanned).`);
