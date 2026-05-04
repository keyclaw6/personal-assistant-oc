import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  asList,
  compact,
  estimateTokens,
  exists,
  ignoredWikiDirs,
  isRecallable,
  parseClaims,
  parseFrontmatter,
  preferredSection,
  stripFrontmatter,
  titleFrom,
  walkMarkdown
} from "./memory-lib.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const compiledDir = path.join(root, "memory", "_compiled");
const cacheDir = path.join(wikiDir, ".openclaw-wiki", "cache");

const priorityFiles = [
  "PROFILE.md",
  "PREFERENCES.md",
  "STACK.md",
  "PROJECTS.md",
  "DECISIONS.md",
  "PEOPLE.md",
  "WORKING.md"
];

async function readPage(relativePath, max = 900) {
  const absolutePath = path.join(wikiDir, relativePath);
  const raw = await fs.readFile(absolutePath, "utf8");
  const meta = parseFrontmatter(raw);
  const body = stripFrontmatter(raw);
  const title = titleFrom(body, path.basename(relativePath));
  const l0 = preferredSection(body, ["L0", "L0 Summary", "L0 - Startup", "Startup Summary"]);
  const l1 = preferredSection(body, ["L1", "L1 Summary", "L1 - Retrieval", "L1 - Retrieval Summary", "Summary"]);
  const l2 = preferredSection(body, ["L2", "L2 Details", "L2 - Details"]);
  const summary = l0 || l1 || body;
  const page = {
    id: meta.id || relativePath.replace(/[\\/]/g, ".").replace(/\.md$/i, ""),
    schema: meta.schema || meta.schema_version || "memory-page/v1",
    type: meta.type || "note",
    status: meta.status || "draft",
    confidence: Number(meta.confidence) || 0,
    freshness: meta.freshness || "unknown",
    reviewAfter: meta.review_after || "",
    updatedAt: meta.updated_at || "",
    scope: meta.scope || "",
    owner: meta.owner || "",
    agent: meta.agent || "",
    visibility: meta.visibility || "local",
    importance: meta.importance || "",
    sources: asList(meta.sources),
    sourceRefs: asList(meta.source_refs),
    related: asList(meta.related),
    tags: asList(meta.tags),
    path: relativePath.replaceAll("\\", "/"),
    title,
    tokenCost: estimateTokens(body),
    summary: compact(summary, max),
    l0: compact(l0 || summary, Math.min(max, 500)),
    l1: compact(l1 || summary, max),
    l2: l2 ? compact(l2, max) : ""
  };
  page.claims = parseClaims(body, page);
  return page;
}

async function listWikiFiles() {
  const files = await walkMarkdown(wikiDir, { ignoredDirs: ignoredWikiDirs });
  const priority = new Map(priorityFiles.map((file, index) => [file, index]));
  return files.sort((a, b) => {
    const aPriority = priority.has(a) ? priority.get(a) : Number.MAX_SAFE_INTEGER;
    const bPriority = priority.has(b) ? priority.get(b) : Number.MAX_SAFE_INTEGER;
    return aPriority - bPriority || a.localeCompare(b);
  });
}

function mdCell(value) {
  return String(value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

function pageIndexRows(pages) {
  return pages.map((page) => {
    const confidence = page.confidence ? page.confidence.toFixed(2) : "-";
    const importance = page.importance ? page.importance : "-";
    const tags = page.tags.length ? page.tags.join(", ") : "-";
    return `| ${mdCell(page.id)} | ${mdCell(page.type)} | ${mdCell(page.status)} | ${confidence} | ${mdCell(importance)} | ~${page.tokenCost} | ${mdCell(tags)} | ${mdCell(page.title)} | \`${page.path}\` |`;
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

  const files = await listWikiFiles();
  for (const file of files) {
    if (await exists(path.join(wikiDir, file))) {
      pages.push(await readPage(file, file === "DECISIONS.md" ? 1300 : 900));
    }
  }

  const recallablePages = pages.filter((page) => isRecallable(page));
  const claims = recallablePages.flatMap((page) => page.claims.filter((claim) => isRecallable(claim)));
  const sessionIndex = [
    "# Session Memory Index",
    "",
    "This is the first file to scan. It shows what memory exists and the approximate read cost. Fetch details only when useful.",
    "",
    "## Retrieval Protocol",
    "",
    "L0: scan this index and high-signal claims.",
    "L1: use `npm run mem -- search \"query\"` to find focused pages or claims.",
    "L2: use `npm run mem -- get <id-or-path>` and cited source files only when details matter.",
    "",
    "After memory edits, run `npm run mem -- refresh` and `npm run mem -- check`.",
    "",
    "## Page Index",
    "",
    "| ID | Type | Status | Conf | Importance | Cost | Tags | Page | Path |",
    "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- |",
    ...pageIndexRows(recallablePages),
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
    "Prefer `SESSION_INDEX.md` first. This digest favors L0/L1 sections and omits L2 detail unless a page has no compact summary.",
    "",
    ...recallablePages.flatMap((page) => [
      `## ${page.title}`,
      "",
      `Source: \`${page.path}\` | ID: \`${page.id}\` | Status: ${page.status} | Importance: ${page.importance || "-"} | Cost: ~${page.tokenCost} tokens`,
      "",
      page.summary,
      ""
    ])
  ].join("\n");

  const index = [
    "# Compiled Memory Index",
    "",
    ...recallablePages.map((page) => `- [${page.title}](../../memory-wiki/${page.path}) - ${page.type}, ${page.status}, ~${page.tokenCost} tokens`)
  ].join("\n");

  const claimJsonl = claims.map((claim) => JSON.stringify(claim)).join("\n");
  const digest = {
    generatedAt: new Date().toISOString(),
    mode: "file-only-progressive-disclosure",
    vectorDatabase: false,
    embeddingProvider: null,
    pages: recallablePages,
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
