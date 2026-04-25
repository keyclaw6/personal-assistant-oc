import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const reportsDir = path.join(wikiDir, "reports");
const compiledDir = path.join(root, "memory", "_compiled");
const checkMode = process.argv.includes("--check");
const defaultTimeZone = process.env.PERSONAL_ASSISTANT_TZ || "Europe/Copenhagen";

const ignoredDirs = new Set(["reports", "_views", "_attachments", ".openclaw-wiki"]);
const requiredCompiled = ["SESSION_INDEX.md", "STARTUP.md", "INDEX.md", "CLAIMS.jsonl"];
const highConfidenceSecretPatterns = [
  /\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b/,
  /\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b/
];
const possibleSecretPatterns = [
  /\b[A-Za-z0-9_-]{32,}\b/
];

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function walk(dir, prefix = "") {
  const entries = (await fs.readdir(dir, { withFileTypes: true }))
    .sort((a, b) => a.name.localeCompare(b.name));
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

function sanitizePrivate(text = "") {
  return String(text).replace(/<private>[\s\S]*?(?:<\/private>|$)/gi, "[private omitted]");
}

function hasUnclosedPrivateBlock(text = "") {
  const opens = String(text).match(/<private>/gi)?.length || 0;
  const closes = String(text).match(/<\/private>/gi)?.length || 0;
  return opens > closes;
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

function stripFrontmatter(text) {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
}

function titleFrom(text, fallback) {
  const match = text.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : fallback;
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

  const separator = splitTableRow(lines[1] || "").join("");
  if (!/^[-:]+$/.test(separator)) return [];

  return lines
    .slice(2)
    .map(splitTableRow)
    .filter((cells) => cells.length >= 5 && cells[0] && !/^[-:]+$/.test(cells[0]))
    .map(([id, status, confidence, evidence, text]) => ({
      id,
      page: page.relativePath,
      pageTitle: page.title,
      status: status || "draft",
      confidence: Number(confidence) || 0,
      evidence: evidence || "",
      text: sanitizePrivate(text || "")
    }));
}

function daysUntil(dateString) {
  if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) return null;
  const today = new Date(`${localDateString()}T00:00:00Z`);
  const target = new Date(`${dateString}T00:00:00Z`);
  return Math.ceil((target.getTime() - today.getTime()) / 86400000);
}

function localDateString(date = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: defaultTimeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(date);
}

function list(items, formatter) {
  return items.length ? items.map(formatter).join("\n") : "- None";
}

async function readPages() {
  const files = await walk(wikiDir);
  const pages = [];

  for (const relativePath of files) {
    const absolutePath = path.join(wikiDir, relativePath);
    const raw = await fs.readFile(absolutePath, "utf8");
    const body = stripFrontmatter(raw);
    const meta = parseFrontmatter(raw);
    const title = titleFrom(body, relativePath);
    const page = { relativePath, absolutePath, raw, body, meta, title };
    page.claims = parseClaims(body, page);
    pages.push(page);
  }

  return pages;
}

async function main() {
  await fs.mkdir(reportsDir, { recursive: true });

  const pages = await readPages();
  const claims = pages.flatMap((page) => page.claims);
  const missingCompiled = [];
  const missingMetadata = [];
  const stale = [];
  const contestedPages = [];
  const contestedClaims = [];
  const lowConfidencePages = [];
  const lowConfidenceClaims = [];
  const claimsMissingEvidence = [];
  const markers = [];
  const privateLeaks = [];
  const unclosedPrivateBlocks = [];
  const highConfidenceSecrets = [];
  const possibleSecrets = [];

  for (const file of requiredCompiled) {
    if (!(await exists(path.join(compiledDir, file)))) missingCompiled.push(file);
  }

  for (const page of pages) {
    const { meta, title, relativePath, raw, body } = page;
    if (!meta.id || !meta.status || !meta.confidence || !meta.review_after) {
      missingMetadata.push({ relativePath, title });
    }

    const confidence = Number(meta.confidence);
    if (Number.isFinite(confidence) && confidence < 0.6) {
      lowConfidencePages.push({ relativePath, title, confidence });
    }

    if (String(meta.status).toLowerCase() === "contested") {
      contestedPages.push({ relativePath, title });
    }

    const delta = daysUntil(meta.review_after);
    if (delta !== null && delta < 0) {
      stale.push({ relativePath, title, reviewAfter: meta.review_after, overdueDays: Math.abs(delta) });
    }

    const flaggedLines = body
      .split(/\r?\n/)
      .map((line, index) => ({ line, number: index + 1 }))
      .filter(({ line }) => /^\s*(CONFLICT|TODO|OPEN QUESTION|VERIFY)\s*:/i.test(line));

    for (const item of flaggedLines) {
      markers.push({ relativePath, title, number: item.number, line: item.line.trim() });
    }

    if (/<private>[\s\S]*?<\/private>/i.test(raw)) {
      privateLeaks.push({ relativePath, title });
    }

    if (hasUnclosedPrivateBlock(raw)) {
      unclosedPrivateBlocks.push({ relativePath, title });
    }

    const sanitizedRaw = sanitizePrivate(raw);
    const hasHighConfidenceSecret = highConfidenceSecretPatterns.some((pattern) => pattern.test(sanitizedRaw));
    if (hasHighConfidenceSecret) {
      highConfidenceSecrets.push({ relativePath, title });
    } else {
      for (const pattern of possibleSecretPatterns) {
        if (pattern.test(sanitizedRaw)) {
          possibleSecrets.push({ relativePath, title });
          break;
        }
      }
    }
  }

  for (const claim of claims) {
    if (claim.status.toLowerCase() === "contested") contestedClaims.push(claim);
    if (claim.confidence < 0.6) lowConfidenceClaims.push(claim);
    if (!claim.evidence || claim.evidence === "-" || claim.evidence.toLowerCase() === "none") {
      claimsMissingEvidence.push(claim);
    }
  }

  const report = [
    "# Memory Report",
    "",
    "Generated report. This file is intentionally ignored by Git.",
    "",
    "## Summary",
    "",
    `- Wiki pages scanned: ${pages.length}`,
    `- Structured claims scanned: ${claims.length}`,
    `- Missing compiled artifacts: ${missingCompiled.length}`,
    `- Missing metadata: ${missingMetadata.length}`,
    `- Stale pages: ${stale.length}`,
    `- Contested pages: ${contestedPages.length}`,
    `- Contested claims: ${contestedClaims.length}`,
    `- Low confidence pages: ${lowConfidencePages.length}`,
    `- Low confidence claims: ${lowConfidenceClaims.length}`,
    `- Claims missing evidence: ${claimsMissingEvidence.length}`,
    `- Review markers: ${markers.length}`,
    `- Private blocks in source pages: ${privateLeaks.length}`,
    `- Unclosed private blocks: ${unclosedPrivateBlocks.length}`,
    `- High-confidence secrets outside private blocks: ${highConfidenceSecrets.length}`,
    `- Possible long tokens outside private blocks: ${possibleSecrets.length}`,
    "",
    "## Missing Compiled Artifacts",
    "",
    list(missingCompiled, (file) => `- \`${file}\``),
    "",
    "## Stale Pages",
    "",
    list(stale, (item) => `- \`${item.relativePath}\` overdue by ${item.overdueDays} day(s), review_after ${item.reviewAfter}`),
    "",
    "## Contested Memory",
    "",
    list([...contestedPages, ...contestedClaims], (item) => item.page ? `- claim \`${item.id}\` in \`${item.page}\`` : `- page \`${item.relativePath}\``),
    "",
    "## Low Confidence",
    "",
    list([...lowConfidencePages, ...lowConfidenceClaims], (item) => item.page ? `- claim \`${item.id}\` in \`${item.page}\` confidence ${item.confidence}` : `- page \`${item.relativePath}\` confidence ${item.confidence}`),
    "",
    "## Claims Missing Evidence",
    "",
    list(claimsMissingEvidence, (claim) => `- \`${claim.id}\` in \`${claim.page}\``),
    "",
    "## Missing Metadata",
    "",
    list(missingMetadata, (item) => `- \`${item.relativePath}\` (${item.title})`),
    "",
    "## Review Markers",
    "",
    list(markers, (item) => `- \`${item.relativePath}:${item.number}\` ${item.line}`),
    "",
    "## Privacy And Secret Checks",
    "",
    privateLeaks.length ? "Private blocks are allowed in source pages and stripped from compiled artifacts." : "No closed private blocks found.",
    "",
    "### Unclosed Private Blocks",
    "",
    list(unclosedPrivateBlocks, (item) => `- unclosed private block in \`${item.relativePath}\``),
    "",
    "### High-Confidence Secrets Outside Private Blocks",
    "",
    list(highConfidenceSecrets, (item) => `- likely secret in \`${item.relativePath}\``),
    "",
    "### Possible Long Tokens Outside Private Blocks",
    "",
    list(possibleSecrets, (item) => `- long token-like value in \`${item.relativePath}\``),
    ""
  ].join("\n");

  const claimHealth = [
    "# Claim Health",
    "",
    `Claims scanned: ${claims.length}`,
    "",
    "## Claims",
    "",
    list(claims, (claim) => `- \`${claim.id}\` ${claim.status} ${claim.confidence.toFixed(2)} - ${claim.text} (${claim.page})`),
    ""
  ].join("\n");

  const staleReport = [
    "# Stale Pages",
    "",
    list(stale, (item) => `- \`${item.relativePath}\` overdue by ${item.overdueDays} day(s), review_after ${item.reviewAfter}`),
    ""
  ].join("\n");

  const lowConfidenceReport = [
    "# Low Confidence",
    "",
    list([...lowConfidencePages, ...lowConfidenceClaims], (item) => item.page ? `- claim \`${item.id}\` in \`${item.page}\` confidence ${item.confidence}` : `- page \`${item.relativePath}\` confidence ${item.confidence}`),
    ""
  ].join("\n");

  const contradictionsReport = [
    "# Contradictions",
    "",
    list([...contestedPages, ...contestedClaims], (item) => item.page ? `- claim \`${item.id}\` in \`${item.page}\`` : `- page \`${item.relativePath}\``),
    ""
  ].join("\n");

  await fs.writeFile(path.join(reportsDir, "memory-report.md"), `${report}\n`, "utf8");
  await fs.writeFile(path.join(reportsDir, "claim-health.generated.md"), `${claimHealth}\n`, "utf8");
  await fs.writeFile(path.join(reportsDir, "stale-pages.generated.md"), `${staleReport}\n`, "utf8");
  await fs.writeFile(path.join(reportsDir, "low-confidence.generated.md"), `${lowConfidenceReport}\n`, "utf8");
  await fs.writeFile(path.join(reportsDir, "contradictions.generated.md"), `${contradictionsReport}\n`, "utf8");

  console.log(report);

  const hardFailures = [
    ...missingCompiled,
    ...missingMetadata.map((item) => item.relativePath),
    ...claimsMissingEvidence.map((claim) => claim.id),
    ...unclosedPrivateBlocks.map((item) => item.relativePath),
    ...highConfidenceSecrets.map((item) => item.relativePath)
  ];

  if (checkMode && hardFailures.length > 0) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
