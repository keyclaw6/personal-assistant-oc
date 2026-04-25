import { execFile as execFileCallback } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFile = promisify(execFileCallback);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function listFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries.filter((entry) => entry.isFile()).map((entry) => path.join(dir, entry.name));
}

async function main() {
  const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "paoc-memory-smoke-"));
  try {
    const scriptsDir = path.join(tempRoot, "scripts");
    await fs.mkdir(scriptsDir, { recursive: true });
    const captureScript = path.join(scriptsDir, "capture-memory.mjs");
    await fs.copyFile(path.join(root, "scripts", "capture-memory.mjs"), captureScript);

    await execFile(process.execPath, [
      captureScript,
      "--type",
      "observation",
      "--title",
      "Capture smoke test",
      "--summary",
      "Temporary capture with <private>hidden test secret</private> stripped",
      "--source",
      "smoke-test",
      "--confidence",
      "0.7",
      "--tags",
      "smoke,temporary"
    ]);

    const eventFiles = await listFiles(path.join(tempRoot, "memory", "events"));
    const inboxFiles = await listFiles(path.join(tempRoot, "memory", "inbox"));
    if (eventFiles.length !== 1 || inboxFiles.length !== 1) {
      throw new Error("Expected exactly one event file and one inbox draft.");
    }

    const inboxText = await fs.readFile(inboxFiles[0], "utf8");
    const eventText = await fs.readFile(eventFiles[0], "utf8");
    const combined = `${inboxText}\n${eventText}`;
    if (!combined.includes("[private omitted]")) {
      throw new Error("Private block was not replaced with the omission marker.");
    }
    if (combined.includes("hidden test secret")) {
      throw new Error("Private block leaked into captured memory.");
    }
    if (!inboxText.includes("time_zone: Europe/Copenhagen")) {
      throw new Error("Inbox draft did not include timezone metadata.");
    }

    console.log("Memory smoke test passed.");
  } finally {
    await fs.rm(tempRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
