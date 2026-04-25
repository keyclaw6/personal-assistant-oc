import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const compiledDir = path.join(root, "memory", "_compiled");
const cacheDir = path.join(wikiDir, ".openclaw-wiki", "cache");

const coreFiles = [
  "PROFILE.md",
  "PREFERENCES.md",
  "STACK.md",
  "PROJECTS.md",
  "DECISIONS.md",
  "PEOPLE.md",
  "WORKING.md"
];

const scanDirs = ["entities", "concepts", "syntheses", "sources"];

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function stripFrontmatter(text) {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
}

function titleFrom(text, fallback) {
  const match = text.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : fallback.replace(/\.md$/i, "");
}

function section(text, heading) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `## ${heading}`);
  if (start === -1) return "";
  const collected = [];
  for (const line of lines.slice(start + 1)) {
    if (/^##\s+/.test(line)) break;
    collected.push(line);
  }
  return collected.join("\n").trim();
}

function compact(text, max = 1200) {
  const normalized = text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trim()}\n\n[...]`;
}

async function readPage(relativePath, max = 1200) {
  const absolutePath = path.join(wikiDir, relativePath);
  const raw = await fs.readFile(absolutePath, "utf8");
  const body = stripFrontmatter(raw);
  const summary = section(body, "Startup Summary") || body;
  return {
    path: relativePath.replaceAll("\\", "/"),
    title: titleFrom(body, path.basename(relativePath)),
    summary: compact(summary, max)
  };
}

async function listMarkdownFiles(dirName) {
  const dir = path.join(wikiDir, dirName);
  if (!(await exists(dir))) return [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => path.join(dirName, entry.name));
}

async function main() {
  await fs.mkdir(compiledDir, { recursive: true });
  await fs.mkdir(cacheDir, { recursive: true });

  const pages = [];

  for (const file of coreFiles) {
    if (await exists(path.join(wikiDir, file))) {
      pages.push(await readPage(file, file === "DECISIONS.md" ? 1800 : 1200));
    }
  }

  for (const dir of scanDirs) {
    const files = await listMarkdownFiles(dir);
    for (const file of files) {
      pages.push(await readPage(file, 800));
    }
  }

  const generatedAt = new Date().toISOString();
  const startup = [
    "# Compiled Startup Memory",
    "",
    `Generated: ${generatedAt}`,
    "",
    "This file is generated. Edit durable memory in `memory-wiki/`, then rerun `npm run memory:compile`.",
    "",
    ...pages.flatMap((page) => [
      `## ${page.title}`,
      "",
      `Source: \`${page.path}\``,
      "",
      page.summary,
      ""
    ])
  ].join("\n");

  const index = [
    "# Compiled Memory Index",
    "",
    `Generated: ${generatedAt}`,
    "",
    ...pages.map((page) => `- [${page.title}](../../memory-wiki/${page.path})`)
  ].join("\n");

  const digest = {
    generatedAt,
    mode: "file-only",
    vectorDatabase: false,
    embeddingProvider: null,
    pages
  };

  await fs.writeFile(path.join(compiledDir, "STARTUP.md"), startup, "utf8");
  await fs.writeFile(path.join(compiledDir, "INDEX.md"), `${index}\n`, "utf8");
  await fs.writeFile(path.join(cacheDir, "agent-digest.json"), `${JSON.stringify(digest, null, 2)}\n`, "utf8");

  console.log(`Compiled ${pages.length} memory pages.`);
  console.log(`Wrote ${path.relative(root, path.join(compiledDir, "STARTUP.md"))}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
