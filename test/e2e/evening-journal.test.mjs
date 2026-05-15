import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(import.meta.dirname, "../..");
const script = path.join(repoRoot, "scripts/evening-journal.mjs");
const testNow = "2026-05-15T12:00:00.000Z";
const testDate = "2026-05-15";

async function makeWorkspace() {
  const workspace = await mkdtemp(path.join(tmpdir(), "albert-journal-e2e-"));
  await mkdir(path.join(workspace, "memory/life/journals"), { recursive: true });
  return workspace;
}

async function runJournal(args, workspace) {
  return execFileAsync(process.execPath, [script, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      ALBERT_WORKSPACE: workspace,
      ALBERT_TEST_NOW: testNow,
    },
  });
}

test("missing journal produces the evening reminder in dry-run mode", async () => {
  const workspace = await makeWorkspace();

  const { stdout } = await runJournal(["--send", "--dry-run"], workspace);

  assert.match(stdout, /Evening journal check-in for 2026-05-15/);
  assert.match(stdout, /What actually happened today\?/);
  assert.match(stdout, /If you want to skip tonight, just say: skip journal\./);
  assert.doesNotMatch(stdout, /already exists/);
  assert.doesNotMatch(stdout, /Journal skipped/);
});

test("existing journal suppresses the reminder", async () => {
  const workspace = await makeWorkspace();
  await writeFile(
    path.join(workspace, "memory/life/journals", `${testDate}.md`),
    "# Journal\n\nToday happened.\n",
  );

  const { stdout } = await runJournal(["--send", "--dry-run"], workspace);

  assert.match(stdout, /Journal already exists for 2026-05-15/);
  assert.doesNotMatch(stdout, /Evening journal check-in/);
  assert.doesNotMatch(stdout, /What actually happened today\?/);
});

test("skipped journal suppresses the reminder", async () => {
  const workspace = await makeWorkspace();
  await writeFile(
    path.join(workspace, "memory/life/journals", `${testDate}.md`),
    "---\nstatus: skipped\n---\n",
  );

  const { stdout } = await runJournal(["--send", "--dry-run"], workspace);

  assert.match(stdout, /Journal skipped for 2026-05-15/);
  assert.doesNotMatch(stdout, /Evening journal check-in/);
  assert.doesNotMatch(stdout, /What actually happened today\?/);
});

test("status reports existing and skipped journal state as JSON", async () => {
  const workspace = await makeWorkspace();
  await writeFile(
    path.join(workspace, "memory/life/journals", `${testDate}.md`),
    "---\nstatus: skipped\n---\n",
  );

  const { stdout } = await runJournal(["--status", "--json"], workspace);
  const status = JSON.parse(stdout);

  assert.equal(status.date, testDate);
  assert.equal(status.timezone, "Europe/Copenhagen");
  assert.equal(status.hasJournal, false);
  assert.equal(status.skipped, true);
  assert.equal(
    status.path,
    path.join(workspace, "memory/life/journals", `${testDate}.md`),
  );
});
