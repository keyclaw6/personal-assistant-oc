# Live OpenClaw Config Status

Date checked: 2026-04-26

## Result

OpenClaw CLI is installed:

```text
openclaw --version
2026.4.23
```

The live OpenClaw config is set up with this workspace as the isolated `belief` agent:

```text
openclaw agents add belief --workspace "C:\Users\Kristian Bilstrup\Documents\Belief Change System" --model openai/gpt-5.5 --non-interactive
```

The default `main` agent remains separate and points at the personal/coder workspace.

## Meaning

The project is OpenClaw-ready and should be used as a separate belief-work agent workspace:

```text
C:/Users/Kristian Bilstrup/Documents/Belief Change System
```

Use `_system/openclaw/openclaw.example.json5` as the configuration reference.

## Isolation Rule

Do not merge this workspace into the main personal/coder workspace. Use a separate private channel binding for belief work when the communication channel is ready.
