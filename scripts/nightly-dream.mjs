#!/usr/bin/env node
/**
 * nightly-dream.mjs — Compatibility helper for the Companion nightly review job.
 *
 * This script does not run the reflection itself. It provides the exact agent
 * message for the scheduled OpenClaw instance and checks whether yesterday's
 * reflection exists. The actual thinking is done by Companion using
 * companion/jobs/NIGHTLY_REVIEW.md.
 *
 * Usage:
 *   node scripts/nightly-dream.mjs --message
 *   node scripts/nightly-dream.mjs --status [--json]
 */

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const REPO = process.env.PERSONAL_ASSISTANT_REPO
  ? path.resolve(process.env.PERSONAL_ASSISTANT_REPO)
  : path.resolve(import.meta.dirname, "..");
const WORKSPACE = process.env.COMPANION_WORKSPACE
  ? path.resolve(process.env.COMPANION_WORKSPACE)
  : path.join(REPO, "companion");
const TZ = "Europe/Copenhagen";
const args = new Set(process.argv.slice(2));
const json = args.has("--json");
const explicitDate = valueAfter("--date");
const nowMs = process.env.COMPANION_TEST_NOW
  ? new Date(process.env.COMPANION_TEST_NOW).getTime()
  : Date.now();

if (Number.isNaN(nowMs)) {
  throw new Error(`Invalid COMPANION_TEST_NOW: ${process.env.COMPANION_TEST_NOW}`);
}

function valueAfter(flag) {
  const argv = process.argv.slice(2);
  const index = argv.indexOf(flag);
  return index >= 0 ? argv[index + 1] : undefined;
}

function localDate(offsetDays = 0) {
  if (offsetDays === -1 && explicitDate) return explicitDate;

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

function reflectionPath(date = localDate(-1)) {
  return path.join(WORKSPACE, "memory/life/reflections", `${date}.md`);
}

function status(date = localDate(-1)) {
  const file = reflectionPath(date);
  const exists = existsSync(file);
  const bytes = exists ? readFileSync(file, "utf8").trim().length : 0;
  return {
    date,
    timezone: TZ,
    hasReflection: exists && bytes > 0,
    path: file,
    bytes,
  };
}

function dreamMessage() {
  return `Run Companion's nightly review now.

Use ${path.join(WORKSPACE, "jobs/NIGHTLY_REVIEW.md")} as the operating instructions.

Scope constraints:
- This is ONLY the nightly local review/consolidation pass.
- Do not run sensor sweeps.
- Do not perform ambient actions.
- Do not send messages to Kristian.
- Do not update external services.
- Do not create an inner monologue.
- Do not auto-promote pattern or belief conclusions into durable truth.

Target date: yesterday in Europe/Copenhagen unless NIGHTLY_REVIEW.md says otherwise.

Required result: write the reflection and operational log files, then reply only with NIGHTLY_REVIEW_OK and the paths written.`;
}

if (args.has("--message")) {
  console.log(dreamMessage());
} else if (args.has("--status")) {
  const s = status();
  if (json) {
    console.log(JSON.stringify(s, null, 2));
  } else {
    console.log(`${s.hasReflection ? "NIGHTLY_REVIEW_DONE" : "NIGHTLY_REVIEW_MISSING"} ${s.date} ${s.path}`);
  }
} else {
  console.log(dreamMessage());
}
