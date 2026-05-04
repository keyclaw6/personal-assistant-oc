import { promises as fs } from "node:fs";
import path from "node:path";

export const ignoredWikiDirs = new Set(["reports", "_views", "_attachments", ".openclaw-wiki"]);
export const publicVisibilities = new Set(["", "local", "shareable"]);
export const defaultRequiredMetadata = ["id", "type", "status", "confidence", "review_after"];

export async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

export function sanitizePrivate(text = "") {
  return String(text).replace(/<private>[\s\S]*?(?:<\/private>|$)/gi, "[private omitted]");
}

export function stripFrontmatter(text) {
  return String(text).replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
}

export function parseScalar(value) {
  const raw = String(value ?? "").trim();
  const withoutComment = raw.replace(/\s+#.*$/, "").trim();
  const trimmed = withoutComment.replace(/^["']|["']$/g, "");
  if (/^(true|false)$/i.test(trimmed)) return /^true$/i.test(trimmed);
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

export function parseInlineList(value) {
  const trimmed = String(value ?? "").trim();
  if (!/^\[.*\]$/.test(trimmed)) return null;
  return trimmed
    .slice(1, -1)
    .split(",")
    .map((item) => parseScalar(item))
    .filter((item) => item !== "");
}

export function parseFrontmatter(text) {
  const match = String(text).match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) return {};

  const data = {};
  const lines = match[1].split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;
    const pair = rawLine.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!pair) continue;

    const [, key, rawValue] = pair;
    const inlineList = parseInlineList(rawValue);
    if (inlineList) {
      data[key] = inlineList;
      continue;
    }
    if (rawValue.trim()) {
      data[key] = parseScalar(rawValue);
      continue;
    }

    const values = [];
    while (index + 1 < lines.length) {
      const item = lines[index + 1].match(/^\s+-\s+(.*)$/);
      if (!item) break;
      values.push(parseScalar(item[1]));
      index += 1;
    }
    data[key] = values;
  }
  return data;
}

export function asList(value) {
  if (Array.isArray(value)) {
    return value.map(String).map((item) => item.trim()).filter(Boolean);
  }
  if (value === undefined || value === null || value === "") return [];
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function titleFrom(text, fallback) {
  const match = String(text).match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : fallback.replace(/\.md$/i, "");
}

export function section(text, heading) {
  const lines = String(text).split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `## ${heading}`);
  if (start === -1) return "";
  const collected = [];
  for (const line of lines.slice(start + 1)) {
    if (/^##\s+/.test(line)) break;
    collected.push(line);
  }
  return collected.join("\n").trim();
}

export function preferredSection(body, headings) {
  for (const heading of headings) {
    const value = section(body, heading);
    if (value) return value;
  }
  return "";
}

export function compact(text, max = 900) {
  const normalized = sanitizePrivate(text)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trim()}\n\n[...]`;
}

export function estimateTokens(text) {
  return Math.max(1, Math.ceil(sanitizePrivate(text).length / 4));
}

export function splitMarkdownTableRow(line) {
  const cells = [];
  let current = "";
  let escaped = false;
  const trimmed = String(line).trim().replace(/^\|/, "").replace(/\|$/, "");
  for (const char of trimmed) {
    if (escaped) {
      current += char;
      escaped = false;
    } else if (char === "\\") {
      current += char;
      escaped = true;
    } else if (char === "|") {
      cells.push(current.trim().replace(/\\\|/g, "|"));
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim().replace(/\\\|/g, "|"));
  return cells;
}

export function parseClaims(body, page) {
  const claimsSection = section(sanitizePrivate(body), "Claims");
  if (!claimsSection) return [];
  const lines = claimsSection.split(/\r?\n/).filter((line) => line.trim().startsWith("|"));
  if (lines.length < 3) return [];

  const separator = splitMarkdownTableRow(lines[1] || "").join("");
  if (!/^[-:]+$/.test(separator)) return [];

  return lines
    .slice(2)
    .map(splitMarkdownTableRow)
    .filter((cells) => cells.length >= 5 && cells[0] && !/^[-:]+$/.test(cells[0]))
    .map(([id, status, confidence, evidence, text]) => ({
      kind: "claim",
      id,
      page: page.path || page.relativePath,
      path: page.path || page.relativePath,
      pageId: page.id,
      pageTitle: page.title,
      title: page.title,
      status: status || "draft",
      confidence: Number(confidence) || 0,
      evidence: sanitizePrivate(evidence || ""),
      visibility: page.visibility || "",
      parentStatus: page.status || "draft",
      parentVisibility: page.visibility || "",
      text: sanitizePrivate(text || ""),
      tokenCost: estimateTokens(text || "")
    }));
}

export function isRecallable(item, options = {}) {
  const status = String(item.status || "draft").toLowerCase();
  const visibility = String(item.visibility || "").toLowerCase();
  const parentStatus = String(item.parentStatus || "").toLowerCase();
  const parentVisibility = String(item.parentVisibility || "").toLowerCase();
  if (!options.includeRetired && status === "retired") return false;
  if (!options.includeRetired && parentStatus === "retired") return false;
  if (!options.includeContested && status === "contested") return false;
  if (!options.includeContested && parentStatus === "contested") return false;
  if (!options.includePrivate && !publicVisibilities.has(visibility)) return false;
  if (!options.includePrivate && parentVisibility && !publicVisibilities.has(parentVisibility)) return false;
  return true;
}

export async function walkMarkdown(dir, options = {}, prefix = "") {
  const ignoredDirs = options.ignoredDirs || ignoredWikiDirs;
  const entries = (await fs.readdir(dir, { withFileTypes: true }))
    .sort((a, b) => a.name.localeCompare(b.name));
  const files = [];

  for (const entry of entries) {
    if (entry.name.startsWith(".") && entry.name !== ".openclaw-wiki") continue;
    if (entry.isDirectory()) {
      if (ignoredDirs.has(entry.name)) continue;
      files.push(...await walkMarkdown(path.join(dir, entry.name), { ignoredDirs }, path.join(prefix, entry.name)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(path.join(prefix, entry.name));
    }
  }

  return files;
}

export function hasMetadata(meta, key) {
  if (!Object.hasOwn(meta, key) || meta[key] === undefined || meta[key] === null || meta[key] === "") return false;
  if (Array.isArray(meta[key])) return meta[key].length > 0;
  return true;
}

export function repoContains(root, target) {
  const relative = path.relative(root, target);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}
