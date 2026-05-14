import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { jsonResult, readStringParam } from "openclaw/plugin-sdk/core";
import { Type } from "typebox";

const COMPOSIO_BIN = process.env.COMPOSIO_BIN || "/home/kab/.composio/composio";

const ACCOUNTS = [
  { id: "gmail_jodo-boort", toolkit: "gmail", label: "Personal Gmail" },
  { id: "gmail_enfree-apod", toolkit: "gmail", label: "Work Gmail" },
  { id: "googlecalendar_deave-cheer", toolkit: "googlecalendar", label: "Google Calendar account" },
  { id: "googletasks_urial-mon", toolkit: "googletasks", label: "Google Tasks account" },
  { id: "linkedin_mbuba-doing", toolkit: "linkedin", label: "LinkedIn account" },
];

const TOOLS_BY_TOOLKIT = {
  gmail: [
    "GMAIL_ADD_LABEL_TO_EMAIL",
    "GMAIL_BATCH_DELETE_MESSAGES",
    "GMAIL_BATCH_MODIFY_MESSAGES",
    "GMAIL_GET_PROFILE",
    "GMAIL_LIST_LABELS",
    "GMAIL_GET_LABEL",
    "GMAIL_CREATE_FILTER",
    "GMAIL_CREATE_LABEL",
    "GMAIL_CREATE_PROMPT_POST",
    "GMAIL_DELETE_DRAFT",
    "GMAIL_DELETE_FILTER",
    "GMAIL_DELETE_LABEL",
    "GMAIL_DELETE_MESSAGE",
    "GMAIL_DELETE_THREAD",
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
    "GMAIL_LIST_THREADS",
    "GMAIL_GET_ATTACHMENT",
    "GMAIL_GET_AUTO_FORWARDING",
    "GMAIL_GET_CONTACTS",
    "GMAIL_LIST_DRAFTS",
    "GMAIL_GET_DRAFT",
    "GMAIL_GET_FILTER",
    "GMAIL_GET_LANGUAGE_SETTINGS",
    "GMAIL_GET_PEOPLE",
    "GMAIL_GET_VACATION_SETTINGS",
    "GMAIL_IMPORT_MESSAGE",
    "GMAIL_INSERT_MESSAGE",
    "GMAIL_LIST_CSE_IDENTITIES",
    "GMAIL_LIST_CSE_KEYPAIRS",
    "GMAIL_LIST_FILTERS",
    "GMAIL_LIST_FORWARDING_ADDRESSES",
    "GMAIL_LIST_HISTORY",
    "GMAIL_LIST_MESSAGES",
    "GMAIL_LIST_SEND_AS",
    "GMAIL_LIST_SMIME_INFO",
    "GMAIL_MODIFY_THREAD_LABELS",
    "GMAIL_MOVE_THREAD_TO_TRASH",
    "GMAIL_MOVE_TO_TRASH",
    "GMAIL_PATCH_LABEL",
    "GMAIL_PATCH_SEND_AS",
    "GMAIL_REMOVE_LABEL",
    "GMAIL_REPLY_TO_THREAD",
    "GMAIL_SEARCH_PEOPLE",
    "GMAIL_CREATE_EMAIL_DRAFT",
    "GMAIL_UPDATE_DRAFT",
    "GMAIL_SEND_DRAFT",
    "GMAIL_SEND_EMAIL",
    "GMAIL_FORWARD_MESSAGE",
    "GMAIL_SETTINGS_GET_IMAP",
    "GMAIL_SETTINGS_GET_POP",
    "GMAIL_SETTINGS_SEND_AS_GET",
    "GMAIL_STOP_WATCH",
    "GMAIL_UNTRASH_MESSAGE",
    "GMAIL_UNTRASH_THREAD",
    "GMAIL_UPDATE_IMAP_SETTINGS",
    "GMAIL_UPDATE_LABEL",
    "GMAIL_UPDATE_LANGUAGE_SETTINGS",
    "GMAIL_UPDATE_POP_SETTINGS",
    "GMAIL_UPDATE_SEND_AS",
    "GMAIL_UPDATE_USER_ATTRIBUTES_VALUES",
    "GMAIL_UPDATE_VACATION_SETTINGS",
  ],
  googlecalendar: [
    "GOOGLECALENDAR_ACL_DELETE",
    "GOOGLECALENDAR_ACL_GET",
    "GOOGLECALENDAR_ACL_INSERT",
    "GOOGLECALENDAR_ACL_LIST",
    "GOOGLECALENDAR_ACL_PATCH",
    "GOOGLECALENDAR_ACL_UPDATE",
    "GOOGLECALENDAR_ACL_WATCH",
    "GOOGLECALENDAR_BATCH_EVENTS",
    "GOOGLECALENDAR_CALENDARS_DELETE",
    "GOOGLECALENDAR_CALENDARS_UPDATE",
    "GOOGLECALENDAR_CALENDAR_LIST_DELETE",
    "GOOGLECALENDAR_CALENDAR_LIST_GET",
    "GOOGLECALENDAR_CALENDAR_LIST_INSERT",
    "GOOGLECALENDAR_CALENDAR_LIST_PATCH",
    "GOOGLECALENDAR_CALENDAR_LIST_UPDATE",
    "GOOGLECALENDAR_CALENDAR_LIST_WATCH",
    "GOOGLECALENDAR_CHANNELS_STOP",
    "GOOGLECALENDAR_CLEAR_CALENDAR",
    "GOOGLECALENDAR_COLORS_GET",
    "GOOGLECALENDAR_CREATE_EVENT",
    "GOOGLECALENDAR_DELETE_EVENT",
    "GOOGLECALENDAR_DUPLICATE_CALENDAR",
    "GOOGLECALENDAR_EVENTS_GET",
    "GOOGLECALENDAR_EVENTS_IMPORT",
    "GOOGLECALENDAR_EVENTS_INSTANCES",
    "GOOGLECALENDAR_EVENTS_LIST",
    "GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS",
    "GOOGLECALENDAR_EVENTS_MOVE",
    "GOOGLECALENDAR_EVENTS_WATCH",
    "GOOGLECALENDAR_FIND_EVENT",
    "GOOGLECALENDAR_FIND_FREE_SLOTS",
    "GOOGLECALENDAR_FREE_BUSY_QUERY",
    "GOOGLECALENDAR_GET_CALENDAR",
    "GOOGLECALENDAR_GET_CALENDAR_PROFILE",
    "GOOGLECALENDAR_GET_CURRENT_DATE_TIME",
    "GOOGLECALENDAR_LIST_BUILDINGS",
    "GOOGLECALENDAR_LIST_CALENDARS",
    "GOOGLECALENDAR_LIST_CALENDAR_RESOURCES",
    "GOOGLECALENDAR_LIST_SETTINGS",
    "GOOGLECALENDAR_PATCH_CALENDAR",
    "GOOGLECALENDAR_PATCH_EVENT",
    "GOOGLECALENDAR_QUICK_ADD",
    "GOOGLECALENDAR_REMOVE_ATTENDEE",
    "GOOGLECALENDAR_SETTINGS_GET",
    "GOOGLECALENDAR_SETTINGS_LIST",
    "GOOGLECALENDAR_SETTINGS_WATCH",
    "GOOGLECALENDAR_SYNC_EVENTS",
    "GOOGLECALENDAR_UPDATE_EVENT",
  ],
  googletasks: [
    "GOOGLETASKS_BATCH_EXECUTE",
    "GOOGLETASKS_BULK_INSERT_TASKS",
    "GOOGLETASKS_CLEAR_TASKS",
    "GOOGLETASKS_CREATE_TASK_LIST",
    "GOOGLETASKS_DELETE_TASK",
    "GOOGLETASKS_DELETE_TASK_LIST",
    "GOOGLETASKS_GET_TASK",
    "GOOGLETASKS_GET_TASK_LIST",
    "GOOGLETASKS_INSERT_TASK",
    "GOOGLETASKS_LIST_ALL_TASKS",
    "GOOGLETASKS_LIST_TASKS",
    "GOOGLETASKS_LIST_TASK_LISTS",
    "GOOGLETASKS_MOVE_TASK",
    "GOOGLETASKS_PATCH_TASK",
    "GOOGLETASKS_PATCH_TASK_LIST",
    "GOOGLETASKS_UPDATE_TASK",
    "GOOGLETASKS_UPDATE_TASK_FULL",
    "GOOGLETASKS_UPDATE_TASK_LIST",
  ],
  linkedin: [
    "LINKEDIN_CREATE_ARTICLE_OR_URL_SHARE",
    "LINKEDIN_CREATE_COMMENT_ON_POST",
    "LINKEDIN_CREATE_LINKED_IN_POST",
    "LINKEDIN_DELETE_LINKED_IN_POST",
    "LINKEDIN_DELETE_POST",
    "LINKEDIN_DELETE_UGC_POST",
    "LINKEDIN_GET_AD_TARGETING_FACETS",
    "LINKEDIN_GET_AUDIENCE_COUNTS",
    "LINKEDIN_GET_COMPANY_INFO",
    "LINKEDIN_GET_IMAGE",
    "LINKEDIN_GET_IMAGES",
    "LINKEDIN_GET_MY_INFO",
    "LINKEDIN_GET_NETWORK_SIZE",
    "LINKEDIN_GET_ORG_PAGE_STATS",
    "LINKEDIN_GET_PERSON",
    "LINKEDIN_GET_POST_CONTENT",
    "LINKEDIN_GET_SHARE_STATS",
    "LINKEDIN_GET_VIDEOS",
    "LINKEDIN_INITIALIZE_IMAGE_UPLOAD",
    "LINKEDIN_LIST_REACTIONS",
    "LINKEDIN_REGISTER_IMAGE_UPLOAD",
    "LINKEDIN_SEARCH_AD_TARGETING_ENTITIES",
  ],
};

function accountsForToolkit(toolkit) {
  return ACCOUNTS.filter((account) => account.toolkit === toolkit).map((account) => account.id);
}

function parseComposioJson(output) {
  const text = output.replace(/\u001b\[[0-9;]*m/g, "").trim();
  const starts = [text.indexOf("{"), text.indexOf("[")].filter((index) => index >= 0);
  if (starts.length === 0) return { raw: text };
  return JSON.parse(text.slice(Math.min(...starts)));
}

async function runComposio(tool, account, args) {
  const dir = await mkdtemp(join(tmpdir(), "openclaw-composio-"));
  const dataPath = join(dir, "input.json");
  await writeFile(dataPath, JSON.stringify(args ?? {}), "utf8");
  try {
    const child = spawn(COMPOSIO_BIN, ["execute", tool, "--account", account, "-d", `@${dataPath}`], {
      env: {
        ...process.env,
        HOME: process.env.HOME || "/home/kab",
        PATH: `${process.env.HOME || "/home/kab"}/.composio:${process.env.PATH || ""}`,
        NO_COLOR: "1",
        FORCE_COLOR: "0",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const [stdout, stderr, code] = await new Promise((resolve) => {
      let out = "";
      let err = "";
      child.stdout.on("data", (chunk) => { out += chunk; });
      child.stderr.on("data", (chunk) => { err += chunk; });
      child.on("close", (exitCode) => resolve([out, err, exitCode]));
    });
    if (code !== 0) throw new Error(stderr || stdout || `composio exited with ${code}`);
    return parseComposioJson(stdout);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function createToolkitTool(toolkit, name, label, description) {
  const accountIds = accountsForToolkit(toolkit);
  const toolSlugs = TOOLS_BY_TOOLKIT[toolkit];
  return {
    name,
    label,
    description: `${description} Only this ${toolkit} allowlist is available through Composio; GOG and other Composio toolkits are not exposed.`,
    parameters: Type.Object({
      account: Type.String({ enum: accountIds, description: `Allowed account: ${accountIds.join(" or ")}.` }),
      tool: Type.String({ enum: toolSlugs, description: "The allowlisted Composio tool slug to execute." }),
      arguments: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: "Arguments for the selected Composio tool." })),
    }, { additionalProperties: false }),
    execute: async (_toolCallId, rawParams) => {
      const account = readStringParam(rawParams, "account", { required: true });
      const tool = readStringParam(rawParams, "tool", { required: true });
      if (!accountIds.includes(account)) throw new Error(`Account is not allowed for ${toolkit}: ${account}`);
      if (!toolSlugs.includes(tool)) throw new Error(`Tool is not allowed for ${toolkit}: ${tool}`);
      return jsonResult(await runComposio(tool, account, rawParams.arguments ?? {}));
    },
  };
}

function createFixedAccountTool(accountId, name, label, description) {
  const account = ACCOUNTS.find((item) => item.id === accountId);
  if (!account) throw new Error(`Unknown Composio account: ${accountId}`);
  const toolSlugs = TOOLS_BY_TOOLKIT[account.toolkit];
  return {
    name,
    label,
    description: `${description} This tool is pinned to ${account.label} (${account.id}); no account parameter is needed. GOG and other Composio toolkits are not exposed.`,
    parameters: Type.Object({
      tool: Type.String({ enum: toolSlugs, description: "The allowlisted Composio Gmail tool slug to execute." }),
      arguments: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: "Arguments for the selected Composio tool." })),
    }, { additionalProperties: false }),
    execute: async (_toolCallId, rawParams) => {
      const tool = readStringParam(rawParams, "tool", { required: true });
      if (!toolSlugs.includes(tool)) throw new Error(`Tool is not allowed for ${account.label}: ${tool}`);
      return jsonResult(await runComposio(tool, account.id, rawParams.arguments ?? {}));
    },
  };
}

export function registerComposioLimitedTools(api) {
  api.registerTool({
    name: "composio_status",
    label: "Composio Status",
    description: "Show the only Composio accounts and toolkits currently exposed to this agent. Use this instead of GOG; GOG has been removed from the exposed skill surface.",
    parameters: Type.Object({}, { additionalProperties: false }),
    execute: async () => jsonResult({ accounts: ACCOUNTS, toolsByToolkit: TOOLS_BY_TOOLKIT }),
  });
  api.registerTool(createFixedAccountTool("gmail_jodo-boort", "composio_gmail_personal", "Composio Personal Gmail", "Execute Gmail tools for the personal Gmail account."));
  api.registerTool(createFixedAccountTool("gmail_enfree-apod", "composio_gmail_work", "Composio Work Gmail", "Execute Gmail tools for the work Gmail account."));
  api.registerTool(createToolkitTool("googlecalendar", "composio_calendar", "Composio Calendar", "Execute Google Calendar tools for the allowed calendar account."));
  api.registerTool(createToolkitTool("googletasks", "composio_tasks", "Composio Tasks", "Execute Google Tasks tools for the allowed tasks account."));
  api.registerTool(createToolkitTool("linkedin", "composio_linkedin", "Composio LinkedIn", "Execute LinkedIn tools for the allowed LinkedIn account."));
}
