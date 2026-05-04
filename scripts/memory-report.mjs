import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  asList,
  estimateTokens,
  exists,
  hasMetadata,
  ignoredWikiDirs,
  isRecallable,
  parseClaims,
  parseFrontmatter,
  repoContains,
  sanitizePrivate,
  stripFrontmatter,
  titleFrom,
  walkMarkdown
} from "./memory-lib.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const reportsDir = path.join(wikiDir, "reports");
const compiledDir = path.join(root, "memory", "_compiled");
const checkMode = process.argv.includes("--check");
const defaultTimeZone = process.env.PERSONAL_ASSISTANT_TZ || "Europe/Copenhagen";

const requiredCompiled = ["SESSION_INDEX.md", "STARTUP.md", "INDEX.md", "CLAIMS.jsonl"];
const requiredMetadata = ["schema", "id", "type", "status", "confidence", "freshness", "review_after", "sources"];
const allowedSchemas = new Set(["memory-page/v1"]);
const allowedStatuses = new Set(["active", "draft", "contested", "retired"]);
const allowedVisibilities = new Set(["", "private", "local", "shareable"]);
const allowedFreshness = new Set(["session", "daily", "weekly", "monthly", "quarterly", "stable"]);
const maxPageTokens = 2500;
const highConfidenceSecretPatterns = [
  /\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b/,
  /\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b/
];
const possibleSecretPatterns = [
  /\b[A-Za-z0-9_-]{32,}\b/
];

function hasUnclosedPrivateBlock(text = "") {
  const opens = String(text).match(/<private>/gi)?.length || 0;
  const closes = String(text).match(/<\/private>/gi)?.length || 0;
  return opens > closes;
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

function isRepoPathReference(value) {
  const text = normalizeReference(value);
  const wrapped = String(value || "").trim() !== text;
  if (!text || /^https?:\/\//i.test(text)) return false;
  if (/^(current setup request|conversation|smoke-test|gog workspace integration update)$/i.test(text)) return false;
  if (/[<>*?"|]/.test(text)) return false;
  if (text.includes(" ") && !wrapped && !text.includes("/") && !text.includes("\\")) return false;
  return text.includes("/") || text.includes("\\") || /\.(md|json|jsonl|txt|yaml|yml|csv|js|mjs)$/i.test(text);
}

function normalizeReference(value) {
  return String(value || "").trim().replace(/^`|`$/g, "").replace(/^["']|["']$/g, "");
}

function sourceParts(value) {
  return asList(value)
    .flatMap((item) => String(item).split(/[;,]/))
    .map((item) => item.trim().replace(/^`|`$/g, ""))
    .filter(Boolean);
}

async function brokenPathReferences(page, references) {
  const broken = [];
  for (const reference of references) {
    if (!isRepoPathReference(reference)) continue;
    const trimmed = normalizeReference(reference);
    const normalized = path.isAbsolute(trimmed) ? trimmed : trimmed.replaceAll("\\", "/").replace(/^\.\//, "");
    const absolutePath = path.resolve(root, normalized);
    if (!repoContains(root, absolutePath) || !(await exists(absolutePath))) {
      broken.push({ relativePath: page.relativePath, title: page.title, reference });
    }
  }
  return broken;
}

async function inboxCount() {
  const inboxDir = path.join(root, "memory", "inbox");
  if (!(await exists(inboxDir))) return 0;
  const entries = await fs.readdir(inboxDir, { withFileTypes: true });
  return entries.filter((entry) => entry.isFile() && !["README.md", ".gitkeep"].includes(entry.name)).length;
}

async function newestMtime(files, baseDir) {
  let newest = 0;
  for (const file of files) {
    const stats = await fs.stat(path.join(baseDir, file));
    newest = Math.max(newest, stats.mtimeMs);
  }
  return newest;
}

async function readPages() {
  const files = await walkMarkdown(wikiDir, { ignoredDirs: ignoredWikiDirs });
  const pages = [];

  for (const relativePath of files) {
    const absolutePath = path.join(wikiDir, relativePath);
    const raw = await fs.readFile(absolutePath, "utf8");
    const body = stripFrontmatter(raw);
    const meta = parseFrontmatter(raw);
    const title = titleFrom(body, relativePath);
    const page = {
      relativePath,
      path: relativePath.replaceAll("\\", "/"),
      absolutePath,
      raw,
      body,
      meta,
      id: meta.id || relativePath,
      title,
      status: meta.status || "draft",
      visibility: meta.visibility || "local"
    };
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
  const invalidMetadata = [];
  const duplicatePageIds = [];
  const duplicateClaimIds = [];
  const oversizedPages = [];
  const brokenSourceReferences = [];
  const staleCompiled = [];
  const markers = [];
  const privateLeaks = [];
  const unclosedPrivateBlocks = [];
  const highConfidenceSecrets = [];
  const possibleSecrets = [];

  for (const file of requiredCompiled) {
    if (!(await exists(path.join(compiledDir, file)))) missingCompiled.push(file);
  }

  const unresolvedInboxCount = await inboxCount();
  const newestWikiPageMtime = await newestMtime(pages.map((page) => page.relativePath), wikiDir);
  for (const file of requiredCompiled) {
    const absolutePath = path.join(compiledDir, file);
    if (!(await exists(absolutePath))) continue;
    const stats = await fs.stat(absolutePath);
    if (stats.mtimeMs + 1000 < newestWikiPageMtime) staleCompiled.push(file);
  }

  const pageIds = new Map();
  const claimIds = new Map();

  for (const page of pages) {
    const { meta, title, relativePath, raw, body } = page;
    const pageId = meta.id || relativePath;
    if (pageIds.has(pageId)) {
      duplicatePageIds.push({ id: pageId, first: pageIds.get(pageId), second: relativePath });
    } else {
      pageIds.set(pageId, relativePath);
    }

    const missingFields = requiredMetadata.filter((field) => !hasMetadata(meta, field));
    if (missingFields.length) {
      missingMetadata.push({ relativePath, title, missingFields });
    }

    const status = String(meta.status || "").toLowerCase();
    const freshness = String(meta.freshness || "").toLowerCase();
    const visibility = String(meta.visibility || "").toLowerCase();
    const confidence = Number(meta.confidence);
    const reviewAfter = String(meta.review_after || "");
    if (hasMetadata(meta, "schema") && !allowedSchemas.has(String(meta.schema))) {
      invalidMetadata.push({ relativePath, title, field: "schema", value: meta.schema });
    }
    if (hasMetadata(meta, "status") && !allowedStatuses.has(status)) {
      invalidMetadata.push({ relativePath, title, field: "status", value: meta.status });
    }
    if (hasMetadata(meta, "freshness") && !allowedFreshness.has(freshness)) {
      invalidMetadata.push({ relativePath, title, field: "freshness", value: meta.freshness });
    }
    if (hasMetadata(meta, "visibility") && !allowedVisibilities.has(visibility)) {
      invalidMetadata.push({ relativePath, title, field: "visibility", value: meta.visibility });
    }
    if (hasMetadata(meta, "confidence") && (!Number.isFinite(confidence) || confidence < 0 || confidence > 1)) {
      invalidMetadata.push({ relativePath, title, field: "confidence", value: meta.confidence });
    }
    if (hasMetadata(meta, "review_after") && (daysUntil(reviewAfter) === null)) {
      invalidMetadata.push({ relativePath, title, field: "review_after", value: meta.review_after });
    }

    const tokenCost = estimateTokens(body);
    if (tokenCost > maxPageTokens) {
      oversizedPages.push({ relativePath, title, tokenCost });
    }

    brokenSourceReferences.push(...await brokenPathReferences(page, [
      ...sourceParts(meta.sources),
      ...sourceParts(meta.source_refs)
    ]));

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

  const reportableClaims = claims.filter((claim) => isRecallable(claim, {
    includeContested: true,
    includeRetired: true,
    includePrivate: false
  }));

  for (const claim of claims) {
    if (claimIds.has(claim.id)) {
      duplicateClaimIds.push({ id: claim.id, first: claimIds.get(claim.id), second: claim.page });
    } else {
      claimIds.set(claim.id, claim.page);
    }
    if (claim.status.toLowerCase() === "contested") contestedClaims.push(claim);
    if (claim.confidence < 0.6) lowConfidenceClaims.push(claim);
    if (!claim.evidence || claim.evidence === "-" || claim.evidence.toLowerCase() === "none") {
      claimsMissingEvidence.push(claim);
    }
    brokenSourceReferences.push(...await brokenPathReferences(
      { relativePath: claim.page, title: claim.pageTitle },
      sourceParts(claim.evidence)
    ));
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
    `- Stale compiled artifacts: ${staleCompiled.length}`,
    `- Missing metadata: ${missingMetadata.length}`,
    `- Invalid metadata: ${invalidMetadata.length}`,
    `- Duplicate page IDs: ${duplicatePageIds.length}`,
    `- Duplicate claim IDs: ${duplicateClaimIds.length}`,
    `- Oversized pages: ${oversizedPages.length}`,
    `- Unresolved inbox items: ${unresolvedInboxCount}`,
    `- Broken source/evidence path references: ${brokenSourceReferences.length}`,
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
    "## Stale Compiled Artifacts",
    "",
    list(staleCompiled, (file) => `- \`${file}\` is older than the newest wiki page; run \`npm run mem -- refresh\``),
    "",
    "## Duplicate IDs",
    "",
    duplicatePageIds.length || duplicateClaimIds.length
      ? [
          ...duplicatePageIds.map((item) => `- page id \`${item.id}\` appears in \`${item.first}\` and \`${item.second}\``),
          ...duplicateClaimIds.map((item) => `- claim id \`${item.id}\` appears in \`${item.first}\` and \`${item.second}\``)
        ].join("\n")
      : "- None",
    "",
    "## Oversized Pages",
    "",
    list(oversizedPages, (item) => `- \`${item.relativePath}\` is ~${item.tokenCost} tokens (limit ${maxPageTokens})`),
    "",
    "## Inbox",
    "",
    `- Unresolved inbox items: ${unresolvedInboxCount}`,
    "",
    "## Broken Source Or Evidence Paths",
    "",
    list(brokenSourceReferences, (item) => `- \`${item.relativePath}\` references missing path \`${item.reference}\``),
    "",
    "## Invalid Metadata",
    "",
    list(invalidMetadata, (item) => `- \`${item.relativePath}\` field \`${item.field}\` has invalid value \`${item.value}\``),
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
    list(missingMetadata, (item) => `- \`${item.relativePath}\` (${item.title}) missing: ${item.missingFields.join(", ")}`),
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
    list(reportableClaims, (claim) => `- \`${claim.id}\` ${claim.status} ${claim.confidence.toFixed(2)} - ${claim.text} (${claim.page})`),
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
    ...staleCompiled,
    ...duplicatePageIds.map((item) => item.id),
    ...duplicateClaimIds.map((item) => item.id),
    ...oversizedPages.map((item) => item.relativePath),
    ...brokenSourceReferences.map((item) => `${item.relativePath}:${item.reference}`),
    ...missingMetadata.map((item) => item.relativePath),
    ...invalidMetadata.map((item) => `${item.relativePath}:${item.field}`),
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
