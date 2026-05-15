import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(import.meta.dirname, "../..");
const script = path.join(repoRoot, "scripts/nightly-dream.mjs");
const testNow = "2026-05-15T12:00:00.000Z";
const targetDate = "2026-05-14";

async function makeWorkspace() {
  const workspace = await mkdtemp(path.join(tmpdir(), "albert-review-e2e-"));
  await mkdir(path.join(workspace, "memory/life/reflections"), { recursive: true });
  await mkdir(path.join(workspace, "jobs"), { recursive: true });
  await writeFile(path.join(workspace, "jobs/NIGHTLY_REVIEW.md"), "# NIGHTLY_REVIEW\n");
  return workspace;
}

async function runDream(args, workspace) {
  return execFileAsync(process.execPath, [script, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      ALBERT_WORKSPACE: workspace,
      ALBERT_TEST_NOW: testNow,
    },
  });
}

test("nightly review message contains the agreed scope constraints", async () => {
  const workspace = await makeWorkspace();

  const { stdout } = await runDream(["--message"], workspace);

  assert.match(stdout, /Run Albert's nightly review now\./);
  assert.match(stdout, new RegExp(`Use ${escapeRegExp(path.join(workspace, "jobs/NIGHTLY_REVIEW.md"))} as the operating instructions\\.`));
  assert.match(stdout, /This is ONLY the nightly local review\/consolidation pass\./);
  assert.match(stdout, /Do not run sensor sweeps\./);
  assert.match(stdout, /Do not perform ambient actions\./);
  assert.match(stdout, /Do not send messages to Kristian\./);
  assert.match(stdout, /Do not update external services\./);
  assert.match(stdout, /Do not create an inner monologue\./);
  assert.match(stdout, /Do not auto-promote pattern or belief conclusions into durable truth\./);
  assert.match(stdout, /Required result: write the reflection and operational log files/);
  assert.match(stdout, /NIGHTLY_REVIEW_OK/);
});

test("dream status reports missing reflection", async () => {
  const workspace = await makeWorkspace();

  const { stdout } = await runDream(["--status", "--json"], workspace);
  const status = JSON.parse(stdout);

  assert.equal(status.date, targetDate);
  assert.equal(status.timezone, "Europe/Copenhagen");
  assert.equal(status.hasReflection, false);
  assert.equal(status.bytes, 0);
  assert.equal(
    status.path,
    path.join(workspace, "memory/life/reflections", `${targetDate}.md`),
  );
});

test("dream status reports present non-empty reflection", async () => {
  const workspace = await makeWorkspace();
  const reflectionPath = path.join(
    workspace,
    "memory/life/reflections",
    `${targetDate}.md`,
  );
  await writeFile(reflectionPath, "# Reflection\n\nCompleted.\n");

  const { stdout } = await runDream(["--status", "--json"], workspace);
  const status = JSON.parse(stdout);

  assert.equal(status.date, targetDate);
  assert.equal(status.hasReflection, true);
  assert.equal(status.path, reflectionPath);
  assert.ok(status.bytes > 0);
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
