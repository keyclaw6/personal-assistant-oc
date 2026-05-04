#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  compact,
  isRecallable,
  preferredSection,
  sanitizePrivate
} from "./memory-lib.mjs";
import { readPages, searchMemory, toMarkdown as searchToMarkdown } from "./memory-search.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function help() {
  return [
    "Usage:",
    "  npm run mem -- search \"query\" [--limit 5] [--format md|json]",
    "  npm run mem -- get <id-or-path> [--level L0|L1|L2|full] [--format md|json]",
    "  npm run mem -- put --title \"Short title\" --summary \"Fact to remember\" [--type observation]",
    "  npm run mem -- check",
    "",
    "Short aliases: s, g, p, c.",
    "Use memory:* scripts only for maintenance, debugging, or CI."
  ].join("\n");
}

function parseFlags(argv) {
  const flags = {};
  const positionals = [];
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value.startsWith("--")) {
      const match = value.match(/^--([^=]+)=(.*)$/);
      const key = match ? match[1] : value.slice(2);
      const inlineValue = match?.[2];
      const next = argv[index + 1];
      if (inlineValue !== undefined) flags[key] = inlineValue;
      else if (!next || next.startsWith("--")) flags[key] = true;
      else {
        flags[key] = next;
        index += 1;
      }
    } else {
      positionals.push(value);
    }
  }
  return { flags, positionals };
}

function numericLimit(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function boolFlag(value) {
  if (value === undefined || value === true) return true;
  if (value === false) return false;
  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return false;
}

function mdCell(value) {
  return String(value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

function cleanTarget(value) {
  return String(value || "")
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "")
    .replace(/\\/g, "/")
    .replace(/^\.\//, "");
}

function sameMemoryPath(pagePath, target) {
  const clean = cleanTarget(target)
    .replace(/^memory-wiki\//i, "")
    .replace(/^\.?\/?memory-wiki\//i, "");
  const normalizedPage = cleanTarget(pagePath);
  return normalizedPage.toLowerCase() === clean.toLowerCase()
    || path.basename(normalizedPage).toLowerCase() === clean.toLowerCase();
}

function pageTextForLevel(page, level) {
  const normalizedLevel = String(level || "L1").toUpperCase();
  if (normalizedLevel === "FULL") return compact(page.body, 4000);
  if (normalizedLevel === "L2") {
    return compact(
      preferredSection(page.body, ["L2", "L1", "L0", "Summary", "Startup Summary"]) || page.body,
      2400
    );
  }
  if (normalizedLevel === "L0") {
    return compact(
      preferredSection(page.body, ["L0", "L0 Summary", "Startup Summary", "Summary"]) || page.summary,
      900
    );
  }
  return compact(
    preferredSection(page.body, ["L1", "L0", "L0 Summary", "Summary", "Startup Summary"]) || page.summary || page.body,
    1600
  );
}

function formatItemMarkdown(item, options = {}) {
  if (!item) return "";
  if (item.kind === "claim") {
    return [
      `# Memory Claim: ${item.id}`,
      "",
      `- Page: \`${item.path}\``,
      `- Status: ${item.status || "draft"}`,
      `- Confidence: ${item.confidence ?? 0}`,
      `- Parent status: ${item.parentStatus || "draft"}`,
      "",
      sanitizePrivate(item.text || ""),
      "",
      item.evidence ? `Evidence: ${sanitizePrivate(item.evidence)}` : ""
    ].filter(Boolean).join("\n");
  }

  const level = String(options.level || "L1").toUpperCase();
  return [
    `# Memory Page: ${item.title}`,
    "",
    `- ID: ${item.id}`,
    `- Path: \`${item.path}\``,
    `- Type: ${item.type}`,
    `- Status: ${item.status || "draft"}`,
    `- Confidence: ${item.confidence ?? 0}`,
    `- Level: ${level}`,
    "",
    pageTextForLevel(item, level)
  ].join("\n");
}

export async function getMemory(target, options = {}) {
  const clean = cleanTarget(target);
  if (!clean) return { target, item: null, suggestions: [] };

  const pages = await readPages();
  const includeRetired = Boolean(options.includeRetired);
  const includeContested = Boolean(options.includeContested);
  const includePrivate = Boolean(options.includePrivate);
  const recallOptions = { includeRetired, includeContested, includePrivate };
  const claimItems = pages.flatMap((page) => page.claims);
  const allItems = [...pages, ...claimItems].filter((item) => isRecallable(item, recallOptions));
  const lower = clean.toLowerCase();

  const item = allItems.find((candidate) => String(candidate.id || "").toLowerCase() === lower)
    || allItems.find((candidate) => candidate.kind !== "claim" && sameMemoryPath(candidate.path, clean))
    || allItems.find((candidate) => candidate.kind !== "claim" && String(candidate.title || "").toLowerCase() === lower);

  if (item) return { target: clean, item, suggestions: [] };

  const suggestions = (await searchMemory(clean, {
    limit: numericLimit(options.limit, 5),
    includeRetired,
    includeContested,
    includePrivate
  })).results;
  return { target: clean, item: null, suggestions };
}

function getToMarkdown(output, options = {}) {
  if (output.item) return formatItemMarkdown(output.item, options);
  const rows = output.suggestions.map((item) => `| ${item.rank} | ${mdCell(item.kind)} | ${mdCell(item.id)} | ${mdCell(item.status || "draft")} | ${Number(item.confidence || 0).toFixed(2)} | \`${mdCell(item.path)}\` | ${mdCell(item.text)} |`);
  return [
    `# Memory Get: ${output.target}`,
    "",
    "No exact page or claim matched.",
    "",
    "| Rank | Kind | ID | Status | Conf | Path | Hint |",
    "| ---: | --- | --- | --- | ---: | --- | --- |",
    ...(rows.length ? rows : ["| - | - | - | - | - | - | No suggestions |"]),
    ""
  ].join("\n");
}

function runNodeScript(scriptName, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(root, "scripts", scriptName), ...args], {
      cwd: root,
      stdio: "inherit",
      windowsHide: true
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${scriptName} exited with code ${code}`));
    });
  });
}

function captureArgs(flags, positionals) {
  const merged = { ...flags };
  if (!merged.title && positionals[0]) merged.title = positionals[0];
  if (!merged.summary && positionals.length > 1) merged.summary = positionals.slice(1).join(" ");
  const allowed = ["type", "title", "summary", "text", "tags", "source", "confidence"];
  return allowed.flatMap((key) => merged[key] === undefined ? [] : [`--${key}`, String(merged[key])]);
}

async function main() {
  const [rawCommand, ...rest] = process.argv.slice(2);
  const command = String(rawCommand || "help").toLowerCase();
  const { flags, positionals } = parseFlags(rest);

  if (["help", "-h", "--help"].includes(command)) {
    console.log(help());
    return;
  }

  if (command === "search" || command === "s") {
    const query = [flags.query || flags.q || "", ...positionals].join(" ").trim();
    if (!query) {
      console.error(help());
      process.exit(2);
    }
    const output = await searchMemory(query, {
      limit: numericLimit(flags.limit, 8),
      includeRetired: boolFlag(flags["include-retired"]),
      includeContested: boolFlag(flags["include-contested"]),
      includePrivate: boolFlag(flags["include-private"])
    });
    if ((flags.format || "md").toLowerCase() === "json") console.log(JSON.stringify(output, null, 2));
    else console.log(searchToMarkdown(output));
    return;
  }

  if (command === "get" || command === "g") {
    const target = [flags.id || flags.path || "", ...positionals].join(" ").trim();
    if (!target) {
      console.error(help());
      process.exit(2);
    }
    const output = await getMemory(target, {
      limit: numericLimit(flags.limit, 5),
      includeRetired: boolFlag(flags["include-retired"]),
      includeContested: boolFlag(flags["include-contested"]),
      includePrivate: boolFlag(flags["include-private"])
    });
    if ((flags.format || "md").toLowerCase() === "json") {
      console.log(JSON.stringify({
        target: output.target,
        item: output.item ? {
          kind: output.item.kind,
          id: output.item.id,
          title: output.item.kind === "claim" ? output.item.pageTitle : output.item.title,
          path: output.item.path,
          status: output.item.status,
          confidence: output.item.confidence,
          text: output.item.kind === "claim" ? output.item.text : pageTextForLevel(output.item, flags.level)
        } : null,
        suggestions: output.suggestions
      }, null, 2));
    } else {
      console.log(getToMarkdown(output, { level: flags.level }));
    }
    return;
  }

  if (command === "put" || command === "p") {
    const args = captureArgs(flags, positionals);
    if (!args.includes("--title") || !(args.includes("--summary") || args.includes("--text"))) {
      console.error(help());
      process.exit(2);
    }
    await runNodeScript("capture-memory.mjs", args);
    return;
  }

  if (command === "check" || command === "c") {
    await runNodeScript("memory-report.mjs", ["--check"]);
    return;
  }

  if (command === "refresh" || command === "r") {
    await runNodeScript("compile-memory.mjs", []);
    await runNodeScript("memory-report.mjs", []);
    await runNodeScript("maintenance-prompt.mjs", []);
    return;
  }

  console.error(help());
  process.exit(2);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
