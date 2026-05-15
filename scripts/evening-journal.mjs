#!/usr/bin/env node
/**
 * evening-journal.mjs — Check whether today's evening journal exists and,
 * optionally, ask Albert to send Kristian the reminder prompt.
 *
 * Usage:
 *   node scripts/evening-journal.mjs --status [--json]
 *   node scripts/evening-journal.mjs --message
 *   node scripts/evening-journal.mjs --send [--dry-run]
 */

import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const REPO = process.env.PERSONAL_ASSISTANT_REPO
  ? path.resolve(process.env.PERSONAL_ASSISTANT_REPO)
  : path.resolve(import.meta.dirname, "..");
const WORKSPACE = process.env.ALBERT_WORKSPACE
  ? path.resolve(process.env.ALBERT_WORKSPACE)
  : process.env.COMPANION_WORKSPACE
  ? path.resolve(process.env.COMPANION_WORKSPACE)
  : path.join(REPO, "albert");
const TZ = "Europe/Copenhagen";

const args = new Set(process.argv.slice(2));
const json = args.has("--json");
const dryRun = args.has("--dry-run");
const explicitDate = valueAfter("--date");
const nowMs = (process.env.ALBERT_TEST_NOW ?? process.env.COMPANION_TEST_NOW)
  ? new Date(process.env.ALBERT_TEST_NOW ?? process.env.COMPANION_TEST_NOW).getTime()
  : Date.now();

if (Number.isNaN(nowMs)) {
  throw new Error(`Invalid ALBERT_TEST_NOW/COMPANION_TEST_NOW: ${process.env.ALBERT_TEST_NOW ?? process.env.COMPANION_TEST_NOW}`);
}

function valueAfter(flag) {
  const argv = process.argv.slice(2);
  const index = argv.indexOf(flag);
  return index >= 0 ? argv[index + 1] : undefined;
}

function localDate(offsetDays = 0) {
  if (offsetDays === 0 && explicitDate) return explicitDate;

  const date = new Date(nowMs + offsetDays * 86400000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function journalPath(date = localDate()) {
  return path.join(WORKSPACE, "memory/life/journals", `${date}.md`);
}

function journalState(date = localDate()) {
  const file = journalPath(date);
  if (!existsSync(file)) return { exists: false, hasJournal: false, skipped: false };
  const content = readFileSync(file, "utf8").trim();
  const skipped = content.includes("status: skipped");
  return { exists: true, hasJournal: content.length > 0 && !skipped, skipped };
}

function reminderMessage(date = localDate()) {
  return `Evening journal check-in for ${date}.

Send me a short text or voice note with whatever is true. A few bullets is enough:

1. What actually happened today?
2. What mattered, emotionally or practically?
3. What did you avoid, postpone, or keep circling?
4. Any commitments, replies, promises, or decisions?
5. What does tomorrow need from you?
6. Anything from today that should not be remembered?

If you want to skip tonight, just say: skip journal.`;
}

function status(date = localDate()) {
  const state = journalState(date);
  return {
    date,
    timezone: TZ,
    hasJournal: state.hasJournal,
    skipped: state.skipped,
    path: journalPath(date),
  };
}

function printStatus() {
  const s = status();
  if (json) {
    console.log(JSON.stringify(s, null, 2));
    return;
  }
  const label = s.hasJournal ? "JOURNAL_DONE" : s.skipped ? "JOURNAL_SKIPPED" : "JOURNAL_MISSING";
  console.log(`${label} ${s.date} ${s.path}`);
}

function sendReminder() {
  const s = status();
  if (s.hasJournal || s.skipped) {
    console.log(`Journal ${s.skipped ? "skipped" : "already exists"} for ${s.date}: ${s.path}`);
    return;
  }

  const message = reminderMessage(s.date);
  if (dryRun) {
    console.log(message);
    return;
  }

  execFileSync(
    "openclaw",
    [
      "agent",
      "--agent",
      "main",
      ...(process.env.JOURNAL_REMINDER_REPLY_CHANNEL
        ? ["--reply-channel", process.env.JOURNAL_REMINDER_REPLY_CHANNEL]
        : []),
      ...(process.env.JOURNAL_REMINDER_REPLY_TO
        ? ["--reply-to", process.env.JOURNAL_REMINDER_REPLY_TO]
        : []),
      "--deliver",
      "--message",
      `Send Kristian this exact evening journal reminder and nothing else:\n\n${message}`,
    ],
    { cwd: REPO, stdio: "inherit", timeout: 120000 },
  );
}

mkdirSync(path.dirname(journalPath()), { recursive: true });

if (args.has("--status")) {
  printStatus();
} else if (args.has("--message")) {
  console.log(reminderMessage());
} else if (args.has("--send")) {
  sendReminder();
} else {
  printStatus();
}
