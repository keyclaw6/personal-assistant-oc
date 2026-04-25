import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const reportsDir = path.join(wikiDir, "reports");
const compiledStartup = path.join(root, "memory", "_compiled", "STARTUP.md");
const checkMode = process.argv.includes("--check");

const ignoredDirs = new Set(["reports", "_views", "_attachments", ".openclaw-wiki"]);

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function walk(dir, prefix = "") {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (entry.name.startsWith(".") && entry.name !== ".openclaw-wiki") continue;
    if (entry.isDirectory()) {
      if (ignoredDirs.has(entry.name)) continue;
      files.push(...await walk(path.join(dir, entry.name), path.join(prefix, entry.name)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(path.join(prefix, entry.name));
    }
  }

  return files;
}

function parseFrontmatter(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) return {};

  const data = {};
  for (const line of match[1].split(/\r?\n/)) {
    const pair = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (pair) data[pair[1]] = pair[2].replace(/^["']|["']$/g, "");
  }
  return data;
}

function titleFrom(text, fallback) {
  const match = text.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : fallback;
}

function daysUntil(dateString) {
  if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) return null;
  const today = new Date();
  const target = new Date(`${dateString}T00:00:00Z`);
  return Math.ceil((target.getTime() - today.getTime()) / 86400000);
}

async function main() {
  await fs.mkdir(reportsDir, { recursive: true });

  const files = await walk(wikiDir);
  const missingMetadata = [];
  const stale = [];
  const contested = [];
  const lowConfidence = [];
  const markers = [];

  for (const relativePath of files) {
    const absolutePath = path.join(wikiDir, relativePath);
    const text = await fs.readFile(absolutePath, "utf8");
    const meta = parseFrontmatter(text);
    const title = titleFrom(text, relativePath);

    if (!meta.id || !meta.status || !meta.confidence || !meta.review_after) {
      missingMetadata.push({ relativePath, title });
    }

    const confidence = Number(meta.confidence);
    if (Number.isFinite(confidence) && confidence < 0.6) {
      lowConfidence.push({ relativePath, title, confidence });
    }

    if (String(meta.status).toLowerCase() === "contested") {
      contested.push({ relativePath, title });
    }

    const delta = daysUntil(meta.review_after);
    if (delta !== null && delta < 0) {
      stale.push({ relativePath, title, reviewAfter: meta.review_after, overdueDays: Math.abs(delta) });
    }

    const flaggedLines = text
      .split(/\r?\n/)
      .map((line, index) => ({ line, number: index + 1 }))
      .filter(({ line }) => /^\s*(CONFLICT|TODO|OPEN QUESTION|VERIFY)\s*:/i.test(line));

    for (const item of flaggedLines) {
      markers.push({ relativePath, title, number: item.number, line: item.line.trim() });
    }
  }

  const startupExists = await exists(compiledStartup);
  const generatedAt = new Date().toISOString();
  const report = [
    "# Memory Report",
    "",
    `Generated: ${generatedAt}`,
    "",
    `Compiled startup present: ${startupExists ? "yes" : "no"}`,
    "",
    "## Summary",
    "",
    `- Wiki pages scanned: ${files.length}`,
    `- Missing metadata: ${missingMetadata.length}`,
    `- Stale pages: ${stale.length}`,
    `- Contested pages: ${contested.length}`,
    `- Low confidence pages: ${lowConfidence.length}`,
    `- Review markers: ${markers.length}`,
    "",
    "## Stale Pages",
    "",
    stale.length ? stale.map((item) => `- \`${item.relativePath}\` overdue by ${item.overdueDays} day(s), review_after ${item.reviewAfter}`).join("\n") : "- None",
    "",
    "## Contested Pages",
    "",
    contested.length ? contested.map((item) => `- \`${item.relativePath}\` (${item.title})`).join("\n") : "- None",
    "",
    "## Low Confidence Pages",
    "",
    lowConfidence.length ? lowConfidence.map((item) => `- \`${item.relativePath}\` confidence ${item.confidence}`).join("\n") : "- None",
    "",
    "## Missing Metadata",
    "",
    missingMetadata.length ? missingMetadata.map((item) => `- \`${item.relativePath}\` (${item.title})`).join("\n") : "- None",
    "",
    "## Review Markers",
    "",
    markers.length ? markers.map((item) => `- \`${item.relativePath}:${item.number}\` ${item.line}`).join("\n") : "- None",
    ""
  ].join("\n");

  await fs.writeFile(path.join(reportsDir, "memory-report.md"), report, "utf8");
  console.log(report);

  if (checkMode && (!startupExists || contested.length > 0)) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
