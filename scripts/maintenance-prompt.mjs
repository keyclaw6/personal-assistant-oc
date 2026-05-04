import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const compiledDir = path.join(root, "memory", "_compiled");
const inboxDir = path.join(root, "memory", "inbox");
const dailyDir = path.join(root, "memory", "daily");
const reportsDir = path.join(root, "memory-wiki", "reports");

async function listRecent(dir, limit = 8) {
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
      if (!entry.isFile() || entry.name === "README.md") continue;
      const full = path.join(dir, entry.name);
      const stat = await fs.stat(full);
      files.push({ name: entry.name, full, mtime: stat.mtimeMs });
    }
    return files.sort((a, b) => b.mtime - a.mtime).slice(0, limit);
  } catch {
    return [];
  }
}

async function maybeRead(filePath) {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch {
    return "";
  }
}

async function main() {
  await fs.mkdir(compiledDir, { recursive: true });

  const inbox = await listRecent(inboxDir);
  const daily = await listRecent(dailyDir);
  const report = await maybeRead(path.join(reportsDir, "memory-report.md"));

  const prompt = [
    "# Memory Maintenance Prompt",
    "",
    "Use this as a heartbeat or session-close checklist. Do not blindly promote everything.",
    "",
    "## Goal",
    "",
    "Keep memory accurate, small, sourced, and useful without a vector database.",
    "",
    "## Steps",
    "",
    "1. Review recent inbox drafts and daily notes.",
    "2. Promote only durable facts into `memory-wiki/` with a claim row and evidence.",
    "3. Archive noisy or obsolete inbox items in `memory/archive/`.",
    "4. Create a conflict note if facts disagree.",
    "5. Run `npm run mem -- refresh`, then `npm run mem -- check`.",
    "",
    "## Recent Inbox Files",
    "",
    inbox.length ? inbox.map((item) => `- \`${path.relative(root, item.full)}\``).join("\n") : "- None",
    "",
    "## Recent Daily Notes",
    "",
    daily.length ? daily.map((item) => `- \`${path.relative(root, item.full)}\``).join("\n") : "- None",
    "",
    "## Latest Memory Report",
    "",
    report ? report.slice(0, 3000).trim() : "No report yet. Run `npm run memory:report`.",
    ""
  ].join("\n");

  await fs.writeFile(path.join(compiledDir, "MAINTENANCE_PROMPT.md"), `${prompt}\n`, "utf8");
  console.log("Wrote memory/_compiled/MAINTENANCE_PROMPT.md");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
