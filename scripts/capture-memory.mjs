import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const memoryDir = path.join(root, "memory");
const defaultTimeZone = process.env.PERSONAL_ASSISTANT_TZ || "Europe/Copenhagen";

function argsToObject(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item.startsWith("--")) {
      const key = item.slice(2);
      const next = argv[i + 1];
      if (!next || next.startsWith("--")) out[key] = true;
      else {
        out[key] = next;
        i += 1;
      }
    }
  }
  return out;
}

function sanitizePrivate(text = "") {
  return String(text).replace(/<private>[\s\S]*?(?:<\/private>|$)/gi, "[private omitted]");
}

function slugify(text) {
  return sanitizePrivate(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64) || "memory";
}

function safeLabel(value, fallback, pattern = /^[a-z][a-z0-9_-]*$/) {
  const label = sanitizePrivate(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return pattern.test(label) ? label : fallback;
}

function localDateParts(date = new Date()) {
  const dateParts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: defaultTimeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(date);
  const timeParts = new Intl.DateTimeFormat("en-GB", {
    timeZone: defaultTimeZone,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(date);
  return {
    date: dateParts,
    time: `${dateParts}T${timeParts}`,
    compactTime: timeParts.replaceAll(":", "")
  };
}

async function append(filePath, content) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.appendFile(filePath, content, "utf8");
}

async function nextAvailablePath(filePath) {
  const { dir, name, ext } = path.parse(filePath);
  await fs.mkdir(dir, { recursive: true });
  let candidate = filePath;
  let counter = 2;
  while (true) {
    try {
      await fs.access(candidate);
      candidate = path.join(dir, `${name}-${counter}${ext}`);
      counter += 1;
    } catch {
      return candidate;
    }
  }
}

async function main() {
  const args = argsToObject(process.argv.slice(2));
  const title = args.title || args._ || "";
  const summary = args.summary || args.text || "";

  if (!title || !summary) {
    console.error("Usage: node scripts/capture-memory.mjs --type preference --title \"Short title\" --summary \"What happened\" [--tags a,b] [--source conversation] [--confidence 0.7]");
    process.exit(1);
  }

  const { date, time, compactTime } = localDateParts();
  const type = safeLabel(args.type, "observation");
  const source = safeLabel(args.source, "conversation", /^[a-z0-9][a-z0-9_-]*$/);
  const confidence = Number(args.confidence ?? 0.6);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    console.error("Confidence must be a number from 0 to 1.");
    process.exit(1);
  }
  const tags = String(args.tags || "")
    .split(",")
    .map((tag) => safeLabel(tag, ""))
    .filter(Boolean);
  const id = `${date.replaceAll("-", "")}-${compactTime}-${slugify(title)}`;
  const safeTitle = sanitizePrivate(title).trim().slice(0, 120);
  const safeSummary = sanitizePrivate(summary);

  const event = {
    id,
    time,
    type,
    title: safeTitle,
    summary: safeSummary,
    tags,
    source,
    confidence,
    time_zone: defaultTimeZone,
    promoted: false
  };

  await append(path.join(memoryDir, "events", `${date}.jsonl`), `${JSON.stringify(event)}\n`);
  await append(
    path.join(memoryDir, "daily", `${date}.md`),
    [`\n## ${safeTitle}`, "", `- Type: ${type}`, `- Source: ${source}`, `- Confidence: ${confidence}`, `- Tags: ${tags.join(", ") || "-"}`, "", safeSummary, ""].join("\n")
  );

  const inboxPath = await nextAvailablePath(path.join(memoryDir, "inbox", `${id}.md`));
  await fs.writeFile(
    inboxPath,
    [
      "---",
      `id: ${id}`,
      `type: ${type}`,
      "status: inbox",
      `confidence: ${confidence}`,
      `source: ${source}`,
      `created_at: ${time}`,
      "---",
      "",
      `# ${safeTitle}`,
      "",
      safeSummary,
      "",
      "## Promotion Notes",
      "",
      "- Likely canonical page:",
      "- Conflicts checked: no",
      "- Safe to store long-term: yes",
      ""
    ].join("\n"),
    "utf8"
  );

  console.log(`Captured memory ${id}`);
  console.log(`Inbox draft: ${path.relative(root, inboxPath)}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
