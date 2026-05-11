# Heartbeat

tasks:

- name: weekly-belief-session-check
  interval: 168h
  prompt: "Check `04_sessions` for completed belief-session folders from the last 7 days. Ignore `README.md`, `_session_template`, and empty scaffold folders. A session counts only if it has `00_manifest.json` plus at least one of `03_interpretive_analysis.md`, `04_deterministic_clarification.json`, or `06_next_actions.md` with meaningful content. If no such session exists, send a short reminder that this belief work is important for Kristian's life and business, and suggest starting one session today. If a qualifying session exists, reply HEARTBEAT_OK."

# Rules

- Keep alerts short and direct.
- Do not modify belief files during heartbeat.
- Do not create sessions during heartbeat.
- Do not analyze patterns during heartbeat.
- If nothing needs attention, reply `HEARTBEAT_OK`.
