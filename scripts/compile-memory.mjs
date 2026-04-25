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

function sanitizePrivate(text) {
  return text.replace(/<private>[\s\S]*?<\/private>/gi, "[private omitted]");
}

function stripFrontmatter(text) {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
}

function parseFrontmatter(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) return {};

  const data = {};
  for (const line of match[1].split(/\r?\n/)) {
    const pair = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (pair) data[pair[1]] = pair[2].trim().replace(/^["']|["']$/g, "");
  }
  return data;
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

function compact(text, max = 900) {
  const normalized = sanitizePrivate(text)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trim()}\n\n[...]`;
}

function estimateTokens(text) {
  return Math.max(1, Math.ceil(sanitizePrivate(text).length / 4));
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function parseClaims(body, page) {
  const claimsSection = section(body, "Claims");
  if (!claimsSection) return [];
  const lines = claimsSection.split(/\r?\n/).filter((line) => line.trim().startsWith("|"));
  if (lines.length < 3) return [];

  const rows = lines
    .slice(2)
    .map(splitTableRow)
    .filter((cells) => cells.length >= 5 && cells[0] && !/^[-:]+$/.test(cells[0]));

  return rows.map(([id, status, confidence, evidence, text]) => ({
    id,
    page: page.path,
    pageTitle: page.title,
    status: status || "draft",
    confidence: Number(confidence) || 0,
    evidence: evidence || "",
    text: sanitizePrivate(text || ""),
    tokenCost: estimateTokens(text || "")
  }));
}

async function readPage(relativePath, max = 900) {
  const absolutePath = path.join(wikiDir, relativePath);
  const raw = await fs.readFile(absolutePath, "utf8");
  const meta = parseFrontmatter(raw);
  const body = stripFrontmatter(raw);
  const title = titleFrom(body, path.basename(relativePath));
  const summary = section(body, "Startup Summary") || section(body, "Summary") || body;
  const page = {
    id: meta.id || relativePath.replace(/[\\/]/g, ".").replace(/\.md$/i, ""),
    type: meta.type || "note",
    status: meta.status || "draft",
    confidence: Number(meta.confidence) || 0,
    freshness: meta.freshness || "unknown",
    reviewAfter: meta.review_after || "",
    path: relativePath.replaceAll("\\", "/"),
    title,
    tokenCost: estimateTokens(body),
    summary: compact(summary, max)
  };
  page.claims = parseClaims(body, page);
  return page;
}

async function listMarkdownFiles(dirName) {
  const dir = path.join(wikiDir, dirName);
  if (!(await exists(dir))) return [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => path.join(dirName, entry.name));
}

function mdCell(value) {
  return String(value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

function pageIndexRows(pages) {
  return pages.map((page) => {
    const confidence = page.confidence ? page.confidence.toFixed(2) : "-";
    return `| ${mdCell(page.id)} | ${mdCell(page.type)} | ${mdCell(page.status)} | ${confidence} | ~${page.tokenCost} | ${mdCell(page.title)} | \`${page.path}\` |`;
  });
}

function claimRows(claims) {
  return claims.map((claim) => {
    const confidence = claim.confidence ? claim.confidence.toFixed(2) : "-";
    return `| ${mdCell(claim.id)} | ${mdCell(claim.status)} | ${confidence} | ${mdCell(claim.text)} | \`${claim.page}\` |`;
  });
}

function finalNewline(text) {
  return `${text.trimEnd()}\n`;
}

async function main() {
  await fs.mkdir(compiledDir, { recursive: true });
  await fs.mkdir(cacheDir, { recursive: true });

  const pages = [];

  for (const file of coreFiles) {
    if (await exists(path.join(wikiDir, file))) {
      pages.push(await readPage(file, file === "DECISIONS.md" ? 1300 : 900));
    }
  }

  for (const dir of scanDirs) {
    const files = await listMarkdownFiles(dir);
    for (const file of files) {
      pages.push(await readPage(file, 700));
    }
  }

  const claims = pages.flatMap((page) => page.claims);
  const sessionIndex = [
    "# Session Memory Index",
    "",
    "This is the first file to scan. It shows what memory exists and the approximate read cost. Fetch details only when useful.",
    "",
    "## Retrieval Protocol",
    "",
    "1. Scan the page index below.",
    "2. Read only the one or two source pages that match the current task.",
    "3. Search raw logs under `memory/` only when the wiki does not answer the question.",
    "4. Keep new durable facts in `memory/inbox/` until they can be promoted with evidence.",
    "",
    "## Page Index",
    "",
    "| ID | Type | Status | Conf | Cost | Page | Path |",
    "| --- | --- | --- | ---: | ---: | --- | --- |",
    ...pageIndexRows(pages),
    "",
    "## High-Signal Claims",
    "",
    claims.length
      ? [
          "| ID | Status | Conf | Claim | Path |",
          "| --- | --- | ---: | --- | --- |",
          ...claimRows(claims)
        ].join("\n")
      : "No structured claims yet.",
    ""
  ].join("\n");

  const startup = [
    "# Compiled Startup Memory",
    "",
    "Prefer `SESSION_INDEX.md` first. Use this file when a fuller startup digest is needed.",
    "",
    ...pages.flatMap((page) => [
      `## ${page.title}`,
      "",
      `Source: \`${page.path}\` | ID: \`${page.id}\` | Cost: ~${page.tokenCost} tokens`,
      "",
      page.summary,
      ""
    ])
  ].join("\n");

  const index = [
    "# Compiled Memory Index",
    "",
    ...pages.map((page) => `- [${page.title}](../../memory-wiki/${page.path}) - ${page.type}, ${page.status}, ~${page.tokenCost} tokens`)
  ].join("\n");

  const claimJsonl = claims.map((claim) => JSON.stringify(claim)).join("\n");
  const digest = {
    generatedAt: new Date().toISOString(),
    mode: "file-only-progressive-disclosure",
    vectorDatabase: false,
    embeddingProvider: null,
    pages,
    claims
  };

  await fs.writeFile(path.join(compiledDir, "SESSION_INDEX.md"), finalNewline(sessionIndex), "utf8");
  await fs.writeFile(path.join(compiledDir, "STARTUP.md"), finalNewline(startup), "utf8");
  await fs.writeFile(path.join(compiledDir, "INDEX.md"), finalNewline(index), "utf8");
  await fs.writeFile(path.join(compiledDir, "CLAIMS.jsonl"), claimJsonl ? `${claimJsonl}\n` : "", "utf8");
  await fs.writeFile(path.join(cacheDir, "agent-digest.json"), `${JSON.stringify(digest, null, 2)}\n`, "utf8");
  await fs.writeFile(path.join(cacheDir, "claims.jsonl"), claimJsonl ? `${claimJsonl}\n` : "", "utf8");

  console.log(`Compiled ${pages.length} pages and ${claims.length} claims.`);
  console.log(`Wrote ${path.relative(root, path.join(compiledDir, "SESSION_INDEX.md"))}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
