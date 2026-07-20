from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from tools.registry import tool_error, tool_result

PLUGIN_DIR = Path(__file__).resolve().parent
BRIDGE = PLUGIN_DIR / "bridge.mjs"

ACCOUNTS = {
    "gmail_jodo-boort": {"toolkit": "gmail", "label": "Personal Gmail"},
    "gmail_enfree-apod": {"toolkit": "gmail", "label": "Work Gmail"},
    "googlecalendar_deave-cheer": {"toolkit": "googlecalendar", "label": "Google Calendar account"},
    "googletasks_urial-mon": {"toolkit": "googletasks", "label": "Google Tasks account"},
    "linkedin_mbuba-doing": {"toolkit": "linkedin", "label": "LinkedIn account"},
}


def _run_bridge(command: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = ["node", str(BRIDGE), command]
    if payload is not None:
        args.append(json.dumps(payload))
    proc = subprocess.run(args, text=True, capture_output=True, timeout=120)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or f"bridge exited {proc.returncode}").strip()
        raise RuntimeError(message)
    return json.loads(proc.stdout or "{}")


def _handle_status(args: dict, **kwargs) -> str:
    del args, kwargs
    try:
        return tool_result(_run_bridge("status"))
    except Exception as exc:
        return tool_error(f"Composio status failed: {exc}")


def _handle_execute(tool_name: str, fixed_account: str | None = None, toolkit: str | None = None):
    def handler(args: dict, **kwargs) -> str:
        del kwargs
        account = fixed_account or str(args.get("account") or "").strip()
        tool = str(args.get("tool") or "").strip()
        if not account:
            return tool_error("account is required")
        if not tool:
            return tool_error("tool is required")
        if account not in ACCOUNTS:
            return tool_error(f"Account is not allowed: {account}")
        if toolkit and ACCOUNTS[account]["toolkit"] != toolkit:
            return tool_error(f"Account {account} is not allowed for {toolkit}")
        try:
            result = _run_bridge("execute", {
                "toolName": tool_name,
                "account": account,
                "tool": tool,
                "arguments": args.get("arguments") or {},
            })
            return tool_result(result)
        except Exception as exc:
            return tool_error(str(exc))
    return handler


def _schema(name: str, description: str, *, account_enum: list[str] | None = None, fixed_account: str | None = None) -> dict:
    properties: Dict[str, Any] = {
        "tool": {
            "type": "string",
            "description": "Allowlisted Composio tool slug to execute. Run composio_status to inspect the current allowlist.",
        },
        "arguments": {
            "type": "object",
            "description": "Arguments for the selected Composio tool.",
            "additionalProperties": True,
        },
    }
    required = ["tool"]
    if account_enum is not None:
        properties["account"] = {
            "type": "string",
            "enum": account_enum,
            "description": "Allowed connected Composio account id.",
        }
        required.insert(0, "account")
    if fixed_account is not None:
        description = f"{description} This tool is pinned to {ACCOUNTS[fixed_account]['label']} ({fixed_account})."
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def register(ctx) -> None:
    ctx.register_tool(
        name="composio_status",
        toolset="composio-limited",
        schema={
            "name": "composio_status",
            "description": "Show the only Composio accounts and toolkits currently exposed to Albert.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handler=_handle_status,
    )
    ctx.register_tool(
        name="composio_gmail_personal",
        toolset="composio-limited",
        schema=_schema("composio_gmail_personal", "Execute Gmail tools for the personal Gmail account.", fixed_account="gmail_jodo-boort"),
        handler=_handle_execute("composio_gmail_personal", fixed_account="gmail_jodo-boort"),
    )
    ctx.register_tool(
        name="composio_gmail_work",
        toolset="composio-limited",
        schema=_schema("composio_gmail_work", "Execute Gmail tools for the work Gmail account.", fixed_account="gmail_enfree-apod"),
        handler=_handle_execute("composio_gmail_work", fixed_account="gmail_enfree-apod"),
    )
    ctx.register_tool(
        name="composio_calendar",
        toolset="composio-limited",
        schema=_schema("composio_calendar", "Execute Google Calendar tools for the allowed calendar account.", fixed_account="googlecalendar_deave-cheer"),
        handler=_handle_execute("composio_calendar", fixed_account="googlecalendar_deave-cheer"),
    )
    ctx.register_tool(
        name="composio_tasks",
        toolset="composio-limited",
        schema=_schema("composio_tasks", "Execute Google Tasks tools for the allowed tasks account.", fixed_account="googletasks_urial-mon"),
        handler=_handle_execute("composio_tasks", fixed_account="googletasks_urial-mon"),
    )
    ctx.register_tool(
        name="composio_linkedin",
        toolset="composio-limited",
        schema=_schema("composio_linkedin", "Execute LinkedIn tools for the allowed LinkedIn account.", fixed_account="linkedin_mbuba-doing"),
        handler=_handle_execute("composio_linkedin", fixed_account="linkedin_mbuba-doing"),
    )
