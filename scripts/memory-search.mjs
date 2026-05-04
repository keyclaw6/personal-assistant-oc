#!/usr/bin/env node
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  asList,
  estimateTokens,
  ignoredWikiDirs,
  isRecallable,
  parseClaims,
  parseFrontmatter,
  sanitizePrivate,
  section,
  stripFrontmatter,
  titleFrom,
  walkMarkdown
} from "./memory-lib.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "memory-wiki");
const statusBoosts = new Map([
  ["active", 4],
  ["draft", 1],
  ["contested", -6],
  ["retired", -10]
]);
const importanceBoosts = new Map([
  ["critical", 5],
  ["high", 3],
  ["medium", 1],
  ["low", -1]
]);

function tokenize(text) {
  return Array.from(String(text).toLowerCase().matchAll(/[a-z0-9]+/g), (match) => match[0]);
}

function termCounts(text) {
  const counts = new Map();
  for (const token of tokenize(text)) counts.set(token, (counts.get(token) || 0) + 1);
  return counts;
}

function parseDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}/.test(String(value))) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function parseBoolean(value, fallback = false) {
  if (value === undefined) return true;
  if (value === true || value === false) return value;
  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
}

function metadataScore(meta, tokenCost) {
  const status = String(meta.status || "draft").toLowerCase();
  const confidence = Number(meta.confidence) || 0;
  const importance = String(meta.importance || "").toLowerCase();
  const score = {
    value: (statusBoosts.get(status) ?? 0) + confidence * 5 + (importanceBoosts.get(importance) ?? 0),
    reasons: []
  };

  if (statusBoosts.has(status)) score.reasons.push(`status:${status}`);
  if (confidence) score.reasons.push(`confidence:${confidence.toFixed(2)}`);
  if (importance) score.reasons.push(`importance:${importance}`);

  const reviewAfter = parseDate(meta.review_after);
  if (reviewAfter) {
    const days = Math.round((reviewAfter.getTime() - Date.now()) / 86400000);
    if (days >= 0) {
      score.value += Math.min(2, days / 90);
      score.reasons.push("review:fresh");
    } else {
      score.value -= Math.min(4, Math.abs(days) / 30);
      score.reasons.push("review:stale");
    }
  }

  const updatedAt = parseDate(meta.updated_at);
  if (updatedAt) {
    const daysOld = Math.max(0, Math.round((Date.now() - updatedAt.getTime()) / 86400000));
    const boost = Math.max(0, 2 - daysOld / 45);
    if (boost > 0) {
      score.value += boost;
      score.reasons.push("updated:recent");
    }
  }

  score.value -= Math.min(6, tokenCost / 900);
  score.reasons.push("cost:penalty");
  return score;
}

function queryScore(queryTerms, fields) {
  let score = 0;
  const reasons = [];
  const matchedTerms = new Set();
  const weights = [
    ["title", 8],
    ["path", 5],
    ["id", 4],
    ["tags", 4],
    ["summary", 3],
    ["body", 1]
  ];

  for (const [field, weight] of weights) {
    const counts = termCounts(fields[field] || "");
    let hits = 0;
    const fieldMatches = new Set();
    for (const term of queryTerms) {
      const count = counts.get(term) || 0;
      if (!count) continue;
      hits += Math.min(count, 2);
      fieldMatches.add(term);
      matchedTerms.add(term);
    }
    if (!hits) continue;
    score += hits * weight + fieldMatches.size * weight;
    reasons.push(`${field}:${fieldMatches.size}`);
  }

  if (matchedTerms.size) {
    score += matchedTerms.size * 6;
    if (matchedTerms.size === queryTerms.length) score += 10;
    reasons.push(`coverage:${matchedTerms.size}/${queryTerms.length}`);
  }
  return { score, reasons, coverage: matchedTerms.size, termCount: queryTerms.length };
}

export async function readPages() {
  const files = await walkMarkdown(wikiDir, { ignoredDirs: ignoredWikiDirs });
  const pages = [];
  for (const relativePath of files) {
    const raw = await fs.readFile(path.join(wikiDir, relativePath), "utf8");
    const meta = parseFrontmatter(raw);
    const body = stripFrontmatter(raw);
    const safeBody = sanitizePrivate(body);
    const title = titleFrom(body, path.basename(relativePath));
    const page = {
      kind: "page",
      id: meta.id || relativePath.replace(/[\\/]/g, ".").replace(/\.md$/i, ""),
      schema: meta.schema || meta.schema_version || "memory-page/v1",
      title,
      path: relativePath.replaceAll("\\", "/"),
      type: meta.type || "note",
      status: meta.status || "draft",
      confidence: Number(meta.confidence) || 0,
      importance: meta.importance || "",
      visibility: meta.visibility || "local",
      review_after: meta.review_after || "",
      updated_at: meta.updated_at || "",
      tags: asList(meta.tags),
      sourceRefs: asList(meta.source_refs),
      related: asList(meta.related),
      body: safeBody,
      summary: sanitizePrivate(section(body, "L0") || section(body, "L0 Summary") || section(body, "Startup Summary") || section(body, "Summary") || body),
      tokenCost: estimateTokens(body)
    };
    page.claims = parseClaims(body, page);
    pages.push(page);
  }
  return pages;
}

function scoreResult(item, queryTerms) {
  const itemText = sanitizePrivate(item.text || "");
  const itemSummary = sanitizePrivate(item.summary || "");
  const itemBody = sanitizePrivate(item.body || "");
  const fields = item.kind === "claim"
    ? {
        title: item.pageTitle,
        path: item.path,
        id: item.id,
        tags: "",
        summary: itemText,
        body: `${itemText} ${sanitizePrivate(item.evidence)}`
      }
    : {
        title: item.title,
        path: item.path,
        id: item.id,
        tags: item.tags.join(" "),
        summary: itemSummary,
        body: itemBody
      };

  const lexical = queryScore(queryTerms, fields);
  const meta = metadataScore(item, item.tokenCost);
  const claimBoost = item.kind === "claim" ? 12 : 0;
  const score = lexical.score + meta.value + claimBoost;
  const reasons = [...lexical.reasons, ...meta.reasons];
  if (claimBoost) reasons.push("claim:boost");
  return {
    score,
    reasons,
    matched: lexical.score > 0,
    coverage: lexical.coverage,
    termCount: lexical.termCount
  };
}

export async function searchMemory(query, options = {}) {
  const rawLimit = Number(options.limit);
  const limit = Number.isFinite(rawLimit) && rawLimit >= 0 ? rawLimit : 10;
  const includeRetired = Boolean(options.includeRetired);
  const includeContested = Boolean(options.includeContested);
  const includePrivate = Boolean(options.includePrivate);
  const fixtures = Array.isArray(options.fixtures) ? options.fixtures : [];
  const queryTerms = Array.from(new Set(tokenize(query)));
  if (!queryTerms.length) {
    return { query, terms: [], results: [] };
  }

  const pages = options.fixtureOnly ? [] : await readPages();
  const candidates = [...pages.flatMap((page) => [page, ...page.claims]), ...fixtures];
  const results = candidates
    .filter((item) => isRecallable(item, { includeRetired, includeContested, includePrivate }))
    .map((item) => {
      const scored = scoreResult(item, queryTerms);
      return {
        kind: item.kind,
        id: item.id,
        title: item.kind === "claim" ? item.pageTitle : item.title,
        path: item.path,
        score: Number(scored.score.toFixed(3)),
        reasons: scored.reasons,
        status: item.status,
        confidence: item.confidence,
        importance: item.importance || "",
        tokenCost: item.tokenCost,
        matched: scored.matched,
        coverage: scored.coverage,
        termCount: scored.termCount,
        text: item.kind === "claim" ? sanitizePrivate(item.text) : sanitizePrivate(String(item.summary)).slice(0, 320).trim()
      };
    })
    .filter((item) => item.matched && item.score > 0)
    .sort((a, b) => (
      b.coverage - a.coverage
      || b.score - a.score
      || a.kind.localeCompare(b.kind)
      || a.path.localeCompare(b.path)
      || a.id.localeCompare(b.id)
    ))
    .slice(0, limit)
    .map(({ matched, ...item }, index) => ({ rank: index + 1, ...item }));

  return { query, terms: queryTerms, results };
}

function parseArgs(argv) {
  const options = { format: "json", limit: 10, includeRetired: false, includeContested: false, includePrivate: false };
  const query = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const flagMatch = arg.match(/^--([^=]+)=(.*)$/);
    const flag = flagMatch ? `--${flagMatch[1]}` : arg;
    const inlineValue = flagMatch?.[2];
    if (flag === "--format") options.format = inlineValue ?? argv[++index] ?? "json";
    else if (flag === "--limit") options.limit = Number(inlineValue ?? argv[++index]);
    else if (flag === "--include-retired") options.includeRetired = parseBoolean(inlineValue);
    else if (flag === "--include-contested") options.includeContested = parseBoolean(inlineValue);
    else if (flag === "--include-private") options.includePrivate = parseBoolean(inlineValue);
    else if (flag === "--query" || flag === "-q") query.push(inlineValue ?? argv[++index] ?? "");
    else query.push(arg);
  }
  return { query: query.join(" ").trim(), options };
}

function mdCell(value) {
  return String(value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

export function toMarkdown(output) {
  const rows = output.results.map((item) => `| ${item.rank} | ${item.score.toFixed(3)} | ${mdCell(`${item.coverage}/${item.termCount}`)} | ${mdCell(item.status)} | ${Number(item.confidence || 0).toFixed(2)} | ${mdCell(item.kind)} | ${mdCell(item.id)} | \`${mdCell(item.path)}\` | ${mdCell(item.reasons.join(", ")).slice(0, 120)} | ${mdCell(item.text)} |`);
  return [
    `# Memory Search: ${output.query}`,
    "",
    `Terms: ${output.terms.map((term) => `\`${term}\``).join(", ") || "-"}`,
    "",
    "| Rank | Score | Match | Status | Conf | Kind | ID | Path | Why | Text |",
    "| ---: | ---: | ---: | --- | ---: | --- | --- | --- | --- | --- |",
    ...(rows.length ? rows : ["| - | - | - | - | - | - | - | - | - | No results |"]),
    ""
  ].join("\n");
}

async function main() {
  const { query, options } = parseArgs(process.argv.slice(2));
  if (!query) {
    console.error("Usage: npm run mem -- search \"query\" [--format md]");
    process.exit(2);
  }
  const output = await searchMemory(query, options);
  if (options.format === "md" || options.format === "markdown") {
    console.log(toMarkdown(output));
  } else {
    console.log(JSON.stringify(output, null, 2));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
