#!/usr/bin/env node
/**
 * morning-brief.mjs — Compile and deliver the daily morning brief.
 *
 * Usage:
 *   node scripts/morning-brief.mjs           # compile + send via Messenger
 *   node scripts/morning-brief.mjs --dry-run  # compile only, print to stdout
 *
 * File-local fallback compiler. The scheduled morning brief agent should use
 * jobs/MORNING_BRIEF.md and Composio tools for live Calendar/Gmail/Tasks data.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import path from "node:path";

const REPO = path.resolve(import.meta.dirname, "..");
const WORKSPACE = path.join(REPO, "albert");
const DRY_RUN = process.argv.includes("--dry-run");
const today = new Date().toISOString().slice(0, 10);
const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

// ── helpers ──────────────────────────────────────────────────────────────────

function read(file) {
  const p = path.join(WORKSPACE, file);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

// ── gather data ──────────────────────────────────────────────────────────────

// 1. Commitments
const commitmentsRaw = read("memory/life/commitments.md");
const commitmentLines = commitmentsRaw
  .split("\n")
  .filter((l) => l.startsWith("|") && !l.match(/^\|[\s-]+\|/))
  .slice(1); // skip header

// 2. Current context / priorities
const currentContext = read("memory/profile/current-context.md");

// 3. Recent nightly review
const yesterdayReview = read(`memory/life/reflections/${yesterday}.md`);

// 4. Beliefs / patterns
const beliefsIndex = read("memory/beliefs/_index.md");
const activeBeliefs = beliefsIndex
  .split("\n")
  .filter((l) => l.includes("working") || l.includes("testing") || l.includes("active"));

// 5. Captured yesterday
const yesterdayClarification = read(
  `memory/sessions/${yesterday}/clarification.md`,
);

// ── compose brief ────────────────────────────────────────────────────────────

const contextLines = currentContext
  .split("\n")
  .filter((l) => l.trim() && !l.startsWith("#"))
  .filter((l) => !/empty by design|populated through conversation/i.test(l));
const priority = contextLines.slice(0, 2).join(" ") || "No explicit current priority recorded yet.";

let brief = `# Morning Brief — ${today}\n\n`;
brief += `Morning, Kristian.\n\n`;
brief += `## Today\n\n`;
brief += `- Calendar: live calendar is gathered by the scheduled agent via Composio Calendar. This script is file-local fallback only.\n`;
brief += `- Must-not-miss: no file-local must-not-miss item recorded.\n`;

// Commitments
if (commitmentLines.length > 0) {
  brief += `- Commitments:\n`;
  for (const line of commitmentLines.slice(0, 5)) {
    brief += `  ${line}\n`;
  }
} else {
  brief += `- Commitments: no tracked commitments.\n`;
}
brief += `- Suggested priority: ${priority}\n`;

const watchLines = [];
if (activeBeliefs.length > 0) {
  watchLines.push(...activeBeliefs.slice(0, 2));
}
if (yesterdayReview.trim()) {
  const lines = yesterdayReview.split("\n").filter((l) => l.trim() && !l.startsWith("#"));
  watchLines.push(...lines.slice(0, 2));
}
if (yesterdayClarification.trim()) {
  const lines = yesterdayClarification.split("\n").filter((l) => l.trim());
  watchLines.push(...lines.slice(0, 2));
}

if (watchLines.length > 0) {
  brief += `\n## Watch\n\n`;
  for (const line of watchLines.slice(0, 3)) brief += `- ${line}\n`;
}

brief += `\n## Optional\n\n`;
brief += `- Want me to summarize mail? Live mail headline is gathered by the scheduled agent via Composio Gmail.\n`;

// ── output ───────────────────────────────────────────────────────────────────

const briefingsDir = path.join(WORKSPACE, "memory/life/briefings");
const briefPath = path.join(briefingsDir, `${today}.md`);

if (DRY_RUN) {
  console.log(brief);
  console.log(`\n---\nWould write to: ${briefPath}`);
  process.exit(0);
}

// Write to briefings/
mkdirSync(briefingsDir, { recursive: true });
writeFileSync(briefPath, brief);

// Send via Messenger (best-effort)
console.log(brief);
console.log(`\nBrief written to ${briefPath}`);
console.log("Deliver via Messenger or Android notify (not yet wired).");
