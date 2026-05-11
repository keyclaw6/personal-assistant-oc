#!/usr/bin/env node
/**
 * morning-brief.mjs — Compile and deliver the daily morning brief.
 *
 * Usage:
 *   node scripts/morning-brief.mjs           # compile + send via Messenger
 *   node scripts/morning-brief.mjs --dry-run  # compile only, print to stdout
 *
 * Requires: gog (Google Workspace CLI), Messenger plugin configured.
 * Falls back to file-only if Messenger send fails.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";

const REPO = path.resolve(import.meta.dirname, "..");
const DRY_RUN = process.argv.includes("--dry-run");
const today = new Date().toISOString().slice(0, 10);
const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

// ── helpers ──────────────────────────────────────────────────────────────────

function read(file) {
  const p = path.join(REPO, file);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

function run(cmd) {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 15000 }).trim();
  } catch {
    return "";
  }
}

// ── gather data ──────────────────────────────────────────────────────────────

// 1. Commitments
const commitmentsRaw = read("memory/life/commitments.md");
const commitmentLines = commitmentsRaw
  .split("\n")
  .filter((l) => l.startsWith("|") && !l.match(/^\|[\s-]+\|/))
  .slice(1); // skip header

// 2. Calendar (via gog)
let calendarEvents = "";
try {
  calendarEvents = run(
    `gog calendar events list --json --no-input --max-results 10 --time-min "${today}T00:00:00" --time-max "${today}T23:59:59" 2>/dev/null`,
  );
} catch {}

// 3. Gmail (via gog)
let gmailCount = "";
try {
  const gmailJson = run(
    `gog gmail messages list --json --no-input --max-results 5 --query "is:unread" 2>/dev/null`,
  );
  if (gmailJson) {
    const parsed = JSON.parse(gmailJson);
    gmailCount = String(parsed.messages?.length ?? 0);
  }
} catch {}

// 4. Beliefs
const beliefsIndex = read("memory/beliefs/_index.md");
const activeBeliefs = beliefsIndex
  .split("\n")
  .filter((l) => l.includes("active") || l.includes("testing"));

// 5. Captured yesterday
const yesterdayClarification = read(
  `memory/sessions/${yesterday}/clarification.md`,
);

// ── compose brief ────────────────────────────────────────────────────────────

let brief = `# Morning Brief — ${today}\n\n`;

// Calendar
brief += `## Schedule\n\n`;
if (calendarEvents) {
  try {
    const events = JSON.parse(calendarEvents);
    const items = events.items || events;
    if (Array.isArray(items) && items.length > 0) {
      for (const ev of items.slice(0, 5)) {
        const time = ev.start?.dateTime || ev.start?.date || "?";
        const summary = ev.summary || "(no title)";
        brief += `- ${time}: ${summary}\n`;
      }
    } else {
      brief += `- No events today\n`;
    }
  } catch {
    brief += `- (gog returned unparseable data)\n`;
  }
} else {
  brief += `- (gog not available — authenticate with \`gog auth login\`)\n`;
}

// Commitments
brief += `\n## Commitments\n\n`;
if (commitmentLines.length > 0) {
  for (const line of commitmentLines.slice(0, 5)) {
    brief += `${line}\n`;
  }
} else {
  brief += `- No tracked commitments\n`;
}

// Beliefs
brief += `\n## Beliefs in Progress\n\n`;
if (activeBeliefs.length > 0) {
  for (const line of activeBeliefs.slice(0, 5)) {
    brief += `${line}\n`;
  }
} else {
  brief += `- No active beliefs\n`;
}

// Mail headline
brief += `\n## Mail\n\n`;
if (gmailCount) {
  brief += `- ${gmailCount} unread message(s)\n`;
} else {
  brief += `- (gog not available)\n`;
}

// Captured yesterday
if (yesterdayClarification.trim()) {
  brief += `\n## Captured Yesterday\n\n`;
  const lines = yesterdayClarification.split("\n").filter((l) => l.trim());
  for (const line of lines.slice(0, 5)) {
    brief += `${line}\n`;
  }
}

// ── output ───────────────────────────────────────────────────────────────────

const briefingsDir = path.join(REPO, "memory/life/briefings");
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
