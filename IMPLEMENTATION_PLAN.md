# Implementation Plan — Companion (Personal Agent Pivot)

> Status: APPROVED, PARTIALLY EXECUTED (planning + Messenger plugin commit done).
> Owner: Kristian Bilstrup.
> Execution agent: a fresh OpenClaw / Claude Code session, in build mode.
>
> **Before doing anything, read `PHILOSOPHY.md`.** It is the stable center of
> this project. Every architectural decision below traces back to it. If the
> codebase ever contradicts the philosophy, the codebase is wrong, not the
> philosophy.
>
> Integration model confirmed: Cognee is installed as the official OpenClaw
> plugin `@cognee/cognee-openclaw` (manifest id `memory-cognee`). It augments
> OpenClaw's file-based memory by indexing files into a Cognee knowledge graph
> and injecting graph-search results before each agent run. Files remain the
> source of truth and stay hand-editable.
>
> Already done in the planning session that produced this file:
> - `PHILOSOPHY.md` written (root statement of intent)
> - `IMPLEMENTATION_PLAN.md` written (this file)
> - `plugins/openclaw-messenger/` committed (was previously untracked)
>
> So Phase 4 (Messenger plugin commit) is already complete; the executing
> agent can skip the commit step but should still run the plugin verification
> steps to confirm nothing regressed.

## Vision

A single personal agent for Kristian, accessed through Facebook Messenger, with OpenClaw dashboard/CLI for maintenance only. Three responsibilities:

1. Life ops — Gmail, Calendar, Tasks/Keep, commitments
2. Belief change system — active beliefs, lifecycle stages, sessions, experiments
3. Shadow + self-knowledge — longitudinal memory with active-interpreter posture

No coding tools. No IDE integration. No coder identity.

Daily Messenger morning brief at 07:30 Europe/Copenhagen with: schedule, priorities, commitments, belief status.

## Locked decisions

| Decision | Value |
|---|---|
| Agent placeholder name | Companion |
| Channel | Facebook Messenger primary; OpenClaw dashboard/CLI for maintenance |
| Memory model | File-first Markdown; Cognee indexes on top via the OpenClaw plugin |
| Cognee integration | OpenClaw plugin `@cognee/cognee-openclaw` (manifest id `memory-cognee`) |
| LLM provider | OpenRouter (single API key for everything possible) |
| LLM model | DeepSeek (slug TBC at execution: confirm exact OpenRouter ID for current high-reasoning DeepSeek; pick fastest reasoning-capable variant) |
| Embedding provider | OpenRouter (preferred). Fallback: Ollama + nomic-embed-text local |
| Vector store | LanceDB (Cognee default, file-based) |
| Graph store | Kuzu (Cognee default, file-based) |
| Relational store | SQLite (Cognee default) |
| Belief surfacing | Daily morning brief belief status section |
| Agent posture | Active interlocutor (see `PHILOSOPHY.md`). Not a mirror, not an oracle. Proposes interpretations, draws parallels unprompted, offers reframings, designs experiments, disagrees gently — all as hypotheses Kristian can accept or reject. |
| Shadow framework | Flexible (IFS / Jungian / attachment / somatic / cognitive). Agent tracks which lenses land for Kristian over time and defaults toward those. |
| Beliefs ↔ life coupling | Loose: signals only |
| Auto-capture | Aggressive + auto-promote |
| Friday cron | Removed |
| Profile content | Start fresh, populated through Messenger conversation |
| Old `memory/`, `memory-wiki/`, `belief-system/`, `templates/` | Move to `archive/` for reference, not loaded into Cognee |
| Old Node memory scripts | Removed (`mem`, `memory-lib`, `memory-search`, `compile-memory`, `memory-report`, `memory-eval`, `maintenance-prompt`, `capture-memory`, `smoke-test`) |
| Messenger plugin | Currently untracked; commit during execution |
| Repo posture | Stay on private GitHub. All `memory/` source files committed. Cognee runtime data (`.cognee_system/`) gitignored — binary and regenerable from source files. |

## File system shape (target)

One root for memory. Semantic, not numbered. Light optional frontmatter.

```
personal-assistant-oc/
├── PHILOSOPHY.md        # ★ root statement of intent — read first
├── IDENTITY.md          # Companion's name, role, tone
├── SOUL.md              # character, posture, boundaries
├── USER.md              # Kristian (sparse, durable)
├── AGENTS.md            # operating rules for the agent
├── TOOLS.md             # tool list, conventions
├── MEMORY.md            # one-pager: how memory works (plugin + files)
├── HEARTBEAT.md         # what to do on heartbeat
├── README.md
├── IMPLEMENTATION_PLAN.md
│
├── memory/                          # everything the agent reads/writes
│   ├── profile/
│   │   ├── values.md
│   │   ├── current-context.md
│   │   ├── learning-style.md
│   │   ├── shadow-themes.md
│   │   └── belief-philosophy.md     # Perceived Best Option Principle
│   │
│   ├── beliefs/
│   │   ├── _index.md                # human table: slug, stage, started
│   │   └── <slug>.md                # one belief per file; frontmatter = stage + dates
│   │
│   ├── shadow/
│   │   └── <pattern-slug>.md        # named patterns; interpretive notes
│   │
│   ├── sessions/
│   │   └── YYYY-MM-DD/
│   │       ├── transcript.md        # auto-captured raw conversation
│   │       └── clarification.md     # deterministic fact-only summary
│   │
│   ├── life/
│   │   ├── commitments.md           # rolling list, owner/due/status
│   │   └── briefings/
│   │       └── YYYY-MM-DD.md        # morning brief outputs worth keeping
│   │
│   ├── sources/
│   │   └── books/<book-slug>/
│   │       ├── notes.md
│   │       └── belief-map.md
│   │
│   └── conflicts.md                 # one file; things currently contested
│
├── plugins/openclaw-messenger/      # commit this (currently untracked)
├── scripts/
│   ├── gws.mjs                      # Google Workspace fallback
│   ├── morning-brief.mjs            # daily cron job
│   └── repo-check.mjs               # rewritten for the new layout
│
├── skills/
│   ├── gog/
│   └── google_workspace_assistant/
│
├── docs/
│   ├── architecture.md              # rewritten
│   ├── cognee-setup.md              # new
│   ├── openclaw-setup.md            # lightly edited
│   ├── security-hardening.md
│   ├── google-workspace-integration.md
│   └── proactive-assistant-programs.md
│
├── openclaw-config/
├── archive/                          # old structures moved aside
│   ├── memory-old/
│   ├── memory-wiki-old/
│   ├── belief-system-old/
│   └── templates-old/
│
├── .env.cognee                       # gitignored
├── .cognee_system/                   # gitignored (Cognee runtime data)
├── .gitignore
└── package.json
```

### Frontmatter conventions (light, optional, not validated)

Beliefs (`memory/beliefs/<slug>.md`):
```yaml
---
slug: must-be-ready-before-acting
stage: active            # candidate | active | testing | integrated | maintenance | archived
started: 2026-05-12
last_touched: 2026-05-15
completion: ""           # "" | recommended_ready | complete_integrated | complete_dissolved | complete_contextualized | complete_rejected | complete_archived
---
```

Shadow patterns (`memory/shadow/<pattern-slug>.md`):
```yaml
---
slug: avoidance-hard-conversations
framing: ifs             # free-form label, e.g. ifs | jungian | somatic | cognitive
confidence: medium       # low | medium | high — confidence in this interpretation
first_observed: 2026-05-12
last_observed: 2026-05-15
---
```

Sessions, profile, life: no required frontmatter. Plain Markdown.

## Execution rules

- **Read `PHILOSOPHY.md` first.** Then this plan. Then act.
- Do all phases in order. Stop at any phase that fails verification and ask.
- Make a git commit at the end of each phase with the phase name.
- Never commit secrets (`.env.cognee`, OpenRouter API key, OAuth tokens).
- Always read a file before editing it.
- Never delete `plugins/openclaw-messenger/`.
- Never edit `PHILOSOPHY.md` without surfacing the disagreement to Kristian first.
- When in doubt about model slugs or API shapes, look up current docs at execution time rather than guess.

## Phase 0 — Pre-flight

- [ ] Read `PHILOSOPHY.md` end to end
- [ ] Read this plan end to end
- [ ] Tag a snapshot: `git tag pre-pivot-snapshot && git push origin pre-pivot-snapshot`
- [ ] Confirm OpenRouter API key in hand
- [ ] Confirm exact OpenRouter model slug for chosen DeepSeek high-reasoning variant
- [ ] Confirm OpenClaw gateway is up: `openclaw status --json`
- [ ] Confirm `gog` installed and authenticated: `gog auth status --json --no-input`
- [ ] Confirm Messenger plugin tests pass: `cd plugins/openclaw-messenger && npm install && npm test`
- [ ] Confirm OpenClaw plugin install path works: `openclaw plugins list`

## Phase 1 — Identity strip and archive

### 1.1 Archive existing content
```bash
mkdir -p archive
git mv memory archive/memory-old
git mv memory-wiki archive/memory-wiki-old
git mv belief-system archive/belief-system-old
git mv templates archive/templates-old
```

### 1.2 Remove obsolete Node memory pipeline
Delete:
- `scripts/mem.mjs`
- `scripts/memory-lib.mjs`
- `scripts/memory-search.mjs`
- `scripts/compile-memory.mjs`
- `scripts/memory-report.mjs`
- `scripts/memory-eval.mjs`
- `scripts/maintenance-prompt.mjs`
- `scripts/capture-memory.mjs`
- `scripts/smoke-test.mjs`

Keep:
- `scripts/gws.mjs`
- `scripts/repo-check.mjs` (rewritten in Phase 7)

### 1.3 Remove obsolete docs
Delete:
- `docs/agent-memory-interface.md`
- `docs/memory-lifecycle.md`
- `docs/retrieval.md`
- `docs/comparison.md`
- `docs/two-agent-openclaw.md`

Keep (lightly edit to remove coder framing):
- `docs/openclaw-setup.md`
- `docs/openclaw-runtime-verification.md`
- `docs/security-hardening.md`
- `docs/google-workspace-integration.md`
- `docs/proactive-assistant-programs.md`
- `docs/proactive-integration-audit-2026-04-26.md`
- `docs/architecture.md` (rewrite entirely)

### 1.4 Rewrite top-level identity files

All of these should align with `PHILOSOPHY.md`. Quote or summarize from it where useful; do not contradict it.

- `IDENTITY.md` — Name: Companion (placeholder). Role: Kristian's personal agent for life ops, belief change, and shadow work. Posture: active interlocutor, not a mirror, not an oracle.
- `SOUL.md` — Warm, practical, curious, willing to push back. Active-interlocutor posture (per PHILOSOPHY.md): proposes interpretations, draws parallels, offers reframings, designs experiments, disagrees gently. All as hypotheses Kristian can confirm or reject. Honors user-owned completion marks. Privacy-first.
- `USER.md` — Kristian Bilstrup, Europe/Copenhagen. Deeper content populates through Messenger over time.
- `MEMORY.md` — One-pager: file layout, Cognee plugin handles retrieval, files are source of truth.
- `AGENTS.md` — Operating rules: Messenger primary channel, file-first memory under `memory/`, Cognee plugin indexes, gog for Google Workspace, aggressive auto-capture, morning brief, active-interlocutor behavior rules (propose interpretations, draw parallels unprompted, offer multiple reframings, name what's avoided, suggest experiments, flag contradictions, propose which belief to work on, build shadow hypotheses), belief lifecycle, user-owned completion marks. No coder rules, no two-agent architecture, no passive-mirror posture.
- `TOOLS.md` — Tool list: OpenClaw CLI, Messenger plugin, gog, Cognee plugin, OpenRouter, Ollama (if used).
- `HEARTBEAT.md` — On heartbeat: surface active beliefs untouched for 7+ days; flag stale commitments; surface unresolved entries in `memory/conflicts.md`.
- `README.md` — End-to-end rewrite as a personal agent project. Point readers to `PHILOSOPHY.md` first.

### 1.5 Phase 1 verification
- `git status` shows only intended renames and edits
- `grep -ri "coder\|coding agent\|coding project\|coding tools" --include='*.md' .` returns matches only in `archive/`
- `grep -ri "passive mirror\|just a mirror\|simply reflect" --include='*.md' .` returns no matches (the active-interlocutor posture is consistent)
- Top-level identity files have no empty/placeholder remnants from the coder era
- `PHILOSOPHY.md` is unchanged from the planning session

### 1.6 Phase 1 commit
`git commit -m "Strip coder identity, archive old memory and belief-system, rewrite identity layer"`

## Phase 2 — Create new file system

### 2.1 Create memory tree
```bash
mkdir -p memory/profile
mkdir -p memory/beliefs
mkdir -p memory/shadow
mkdir -p memory/sessions
mkdir -p memory/life/briefings
mkdir -p memory/sources/books
```

### 2.2 Seed profile files (sparse, no fabricated content)
- `memory/profile/values.md` — empty with header, populated through conversation
- `memory/profile/current-context.md` — empty
- `memory/profile/learning-style.md` — empty
- `memory/profile/shadow-themes.md` — empty
- `memory/profile/belief-philosophy.md` — Perceived Best Option Principle as central frame:
  > People do what currently seems best to them, given their understanding of the world, their perceived options, and their expected pain and joy. Belief work updates understanding until different choices honestly appear better.

### 2.3 Seed `memory/beliefs/_index.md`
```markdown
# Beliefs Index

Human-readable table of beliefs. Generated by hand or by the agent; Cognee handles search.

| Slug | Stage | Started | Last Touched | Completion |
|---|---|---|---|---|
```

### 2.4 Seed `memory/life/commitments.md`
```markdown
# Commitments

Rolling list. Each commitment: owner, source, due/review date, status, next action.

| Slug | Owner | Source | Due/Review | Status | Next Action |
|---|---|---|---|---|---|
```

### 2.5 Seed `memory/conflicts.md`
```markdown
# Open Conflicts

Things currently contested in memory. Brief by design.

(empty)
```

### 2.6 Phase 2 commit
`git commit -m "Create new memory/ tree with profile, beliefs, shadow, sessions, life, sources, conflicts"`

## Phase 3 — Install and configure the Cognee plugin

### 3.1 Install the plugin
```bash
openclaw plugins install @cognee/cognee-openclaw@2026.3.4
```
(Pin to exact version. Bump after testing.)

### 3.2 Watch for known install bug
OpenClaw bug #24429 / PR #24796: installer may register the config entry under `cognee-openclaw` instead of the manifest id `memory-cognee`. After install:
```bash
openclaw plugins list
# Verify the entry shows id memory-cognee, not cognee-openclaw
```
If mismatch is present, manually edit `~/.openclaw/openclaw.json` so `plugins.entries.memory-cognee` exists (not `plugins.entries.cognee-openclaw`). Then restart the gateway.

### 3.3 Configure plugin to point at our memory tree
The plugin scans `workspaceDir/MEMORY.md` and `workspaceDir/memory/`. Confirm OpenClaw's workspace is set to this repo root:
```bash
openclaw config get agents.defaults.workspace
# Expected: /home/kab/personal-assistant-oc
```
If not, set it:
```bash
openclaw config set agents.defaults.workspace "/home/kab/personal-assistant-oc"
```

### 3.4 Configure Cognee env (OpenRouter primary path)
File: `.env.cognee` at repo root, **gitignored**.

```dotenv
# LLM via OpenRouter
LLM_PROVIDER=custom
LLM_MODEL=openrouter/<TBC at execution>
LLM_ENDPOINT=https://openrouter.ai/api/v1
LLM_API_KEY=<openrouter key>

# Embeddings — primary: OpenRouter direct
EMBEDDING_PROVIDER=custom
EMBEDDING_MODEL=openrouter/<TBC at execution>
EMBEDDING_API_KEY=<openrouter key>
EMBEDDING_DIMENSIONS=<dim of chosen model>

# Fallback embedding config (uncomment if OpenRouter embeddings fail):
# EMBEDDING_PROVIDER=ollama
# EMBEDDING_MODEL=nomic-embed-text
# EMBEDDING_ENDPOINT=http://localhost:11434
# EMBEDDING_DIMENSIONS=768

# Local stores (defaults)
VECTOR_DB_PROVIDER=lancedb
GRAPH_DATABASE_PROVIDER=kuzu
DB_PROVIDER=sqlite

# Data location
SYSTEM_ROOT_DIRECTORY=/home/kab/personal-assistant-oc/.cognee_system
```

Confirm at execution time how the plugin consumes this config (env file, OpenClaw config section, or both) per the integration's README. Adapt placement accordingly.

### 3.5 Restart OpenClaw gateway
```bash
openclaw gateway restart
```

### 3.6 Initial sync
The plugin should scan `memory/` and `MEMORY.md` on startup, call `cognee.add()` + `cognee.cognify()` for each file, and build the graph. Watch logs:
```bash
openclaw logs --follow
```
Expect to see add/cognify activity. Confirm `.cognee_system/` directory appears with LanceDB + Kuzu data.

### 3.7 Fallback path
If OpenRouter embeddings fail with `Unmapped LLM provider`:
1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
2. `ollama pull nomic-embed-text`
3. Switch `.env.cognee` to the Ollama embedding block
4. `openclaw gateway restart`
5. Document fallback in `docs/cognee-setup.md`

### 3.8 Phase 3 verification
- `openclaw plugins list` shows `memory-cognee` enabled, no mismatch warnings
- `.cognee_system/` exists and has data
- A test agent run that asks about `belief-philosophy.md` content returns relevant info (Cognee retrieval working)

### 3.9 Phase 3 commit
`git commit -m "Install and configure @cognee/cognee-openclaw plugin with OpenRouter and fallback"`

## Phase 4 — Messenger plugin verification

> The plugin was committed during the planning session (commit message
> "Commit Facebook Messenger channel plugin (previously untracked)").
> This phase only verifies it still works.

### 4.1 Confirm plugin is tracked
```bash
git ls-files plugins/openclaw-messenger | head
```
Expect to see `openclaw.plugin.json`, `src/*.ts`, `index.ts`, `package.json`, etc.

### 4.2 Run plugin tests
```bash
cd plugins/openclaw-messenger && npm install && npm test
```

### 4.3 Test webhook locally
```bash
curl 'http://127.0.0.1:18789/messenger/webhook?hub.mode=subscribe&hub.verify_token=TEST&hub.challenge=abc123'
# Expected: abc123
```

### 4.4 Tailscale Funnel (deferred but documented)
Public webhook URL via Tailscale Funnel. Steps already in `plugins/openclaw-messenger/README.md`. Mark TODO if Funnel not enabled in the tailnet admin UI yet.

### 4.5 Phase 4 commit (only if changes were made)
If `npm install` updated lockfiles or anything else regressed, commit those:
`git commit -m "Verify Messenger plugin still passes after pivot prep"`
Otherwise skip — nothing to commit.

## Phase 5 — Belief, shadow, and active-interlocutor rules in AGENTS.md

AGENTS.md was rewritten in Phase 1.4 with placeholder content; this phase fills in the operating-rule detail.

### 5.1 Active-interlocutor behavior rules
Document the proactive behaviors from `PHILOSOPHY.md` as concrete agent rules:
- Propose interpretations as hypotheses ("My read is X — does that land?"), state confidence.
- When patterns repeat across two or more sessions, surface them unprompted.
- When Kristian brings a belief, offer at least two honest reframings.
- When the conversation circles or avoids a subject, name it.
- When a belief update lands, propose a concrete daily-life experiment.
- When new claims contradict prior memory, flag the contradiction in the moment and append to `memory/conflicts.md`.
- When Kristian rejects a framing, record the rejection in the relevant file. Do not re-propose without new evidence.
- Once a week (heartbeat), propose which belief seems most worth working on next based on stuckness, recency, and life-ops signals.

### 5.2 Belief lifecycle rules
- Stages: `candidate → active → testing → integrated → maintenance → archived`.
- Completion types: `complete_integrated | complete_dissolved | complete_contextualized | complete_rejected | complete_archived`.
- Agent may recommend `ready_for_user_decision`. Kristian owns the final mark.
- Perceived Best Option Principle is the philosophical frame (see `memory/profile/belief-philosophy.md`).
- Working lenses: current belief, preference logic, protective function, cost, evidence, alternative model, daily-life implication, experiment.

### 5.3 Shadow rules
- Framework-flexible (IFS, Jungian, attachment, somatic, cognitive).
- Hypotheses, not diagnosis. No clinical language. No pathologizing.
- Track which framings land (Kristian confirms / produces behavior change) vs. don't (Kristian rejects / stays intellectual). Default toward what lands; stay open to new lenses.
- Build cumulative hypotheses under `memory/shadow/<slug>.md` and test them against new material as it arrives.

### 5.4 Two-pass session writing
- Live conversation in Messenger is interpretive and warm.
- After each meaningful session (5+ minute pause defines end), write:
  - `memory/sessions/YYYY-MM-DD/transcript.md` — the raw conversation, unedited.
  - `memory/sessions/YYYY-MM-DD/clarification.md` — deterministic fact-only summary drawn only from transcript. No coaching flourish, no speculative pattern claims, no persuasion.
- Pattern analysis (now or later) reads only clarifications. Never live impressions.

### 5.5 Auto-capture rules
- Aggressive: capture by default. Salient beliefs, shadow signals, commitments, and decisions go directly into the appropriate file under `memory/`.
- Acknowledgment loop: next morning brief includes "captured yesterday" section listing new auto-promotions so Kristian can correct mistakes.
- Forget shortcut: Messenger message `forget: <fact>` edits/deletes the relevant file. Plugin re-syncs.

### 5.6 Memory operating rules
- File-first: `memory/` is source of truth.
- Cognee is automatic: indexing happens via the plugin. The agent does not call Cognee directly; it relies on the plugin's pre-run context injection and reads files when needed.
- Writing memory means writing a file under `memory/`. The plugin picks up changes.
- Forgetting means deleting or editing the file. The plugin re-syncs.
- Conflicts: append to `memory/conflicts.md` with a one-line summary and pointers. Do not silently overwrite.

### 5.7 Phase 5 commit
`git commit -m "Document active-interlocutor behavior, belief lifecycle, shadow rules, two-pass session discipline, and memory operating rules in AGENTS.md"`

## Phase 6 — Morning brief and auto-capture

### 6.1 Create morning brief script
File: `scripts/morning-brief.mjs`. Steps:
1. Read `memory/life/commitments.md` for due/overdue items.
2. Call `gog calendar events list` for today's events.
3. Call `gog gmail messages list` for recent unread.
4. Read `memory/beliefs/_index.md` and any beliefs with `stage` in `{active, testing}`.
5. Compose Messenger message: schedule, priorities, commitments, beliefs in progress, mail headline count.
6. Append a "captured yesterday" section listing new auto-promotions from `memory/sessions/YYYY-MM-DD/clarification.md` (yesterday's date).
7. Write the brief to `memory/life/briefings/YYYY-MM-DD.md` so Cognee indexes it too.
8. Send via the Messenger plugin.
9. On send failure: fall back to Android `system.notify` to `Kristian's S22`.
10. On both failures: leave the file in `briefings/` and surface in next OpenClaw heartbeat.

### 6.2 Register morning brief cron
```bash
openclaw cron create morning-brief \
  --schedule "0 30 7 * * *" \
  --tz Europe/Copenhagen \
  --command "node /home/kab/personal-assistant-oc/scripts/morning-brief.mjs"
```
(Confirm exact command shape from current OpenClaw cron docs at execution.)

### 6.3 Remove Friday belief cron if present
```bash
openclaw cron list --json
# If friday-belief-check exists:
openclaw cron remove friday-belief-check
```

### 6.4 Auto-capture from Messenger
Two viable implementations — pick at execution time based on what the OpenClaw / Messenger plugin surface actually allows:

**Option A — Post-message hook in the Messenger plugin.** After each inbound conversation segment (5+ minute pause), the plugin invokes a clarifier prompt via OpenRouter, writes:
- `memory/sessions/YYYY-MM-DD/transcript.md`
- `memory/sessions/YYYY-MM-DD/clarification.md`

The Cognee plugin's "rescan on agent run" auto-picks them up.

**Option B — OpenClaw post-run hook.** Same effect, but driven by the gateway's run lifecycle rather than the channel plugin.

### 6.5 Forget shortcut
Messenger message `forget: <fact>` deletes or edits the relevant file under `memory/` and posts a confirmation. The Cognee plugin handles the re-sync; we don't call Cognee directly.

### 6.6 Phase 6 verification
- `node scripts/morning-brief.mjs --dry-run` outputs the brief without sending.
- `--send` lands the brief in Messenger.
- A test 6-minute-gap conversation produces `memory/sessions/YYYY-MM-DD/` files.
- Next morning brief includes the "captured yesterday" acknowledgment.
- `openclaw cron list --json` shows `morning-brief`, no `friday-belief-check`.

### 6.7 Phase 6 commit
`git commit -m "Add morning brief cron and Messenger auto-capture into memory/sessions/"`

## Phase 7 — Repo hygiene and final wiring

### 7.1 Update `.gitignore`
Add:
```
.cognee_system/
.env.cognee
.env
*.log
plugins/openclaw-messenger/node_modules/
plugins/openclaw-messenger/dist/
```

### 7.2 Rewrite `package.json`
Remove scripts:
- `mem`, `mem:*`, `memory:*`

Add scripts:
- `brief` → `node scripts/morning-brief.mjs`
- `brief:dry` → `node scripts/morning-brief.mjs --dry-run`
- `repo:check` (kept; updated)
- `check` → runs `repo:check` and `gws --help` smoke test

Keep:
- `gws`

### 7.3 Rewrite `scripts/repo-check.mjs`
New checks:
- No `.env`, `.env.cognee`, OAuth credential files committed
- No `node_modules/` or `dist/` committed under `plugins/`
- `.cognee_system/` is gitignored
- Top-level identity files (IDENTITY/SOUL/USER/AGENTS/TOOLS/MEMORY/HEARTBEAT/README) are non-empty
- `memory/` exists with `profile/`, `beliefs/`, `shadow/`, `sessions/`, `life/`, `sources/`, `conflicts.md`
- `memory/profile/belief-philosophy.md` contains Perceived Best Option Principle

### 7.4 Update `docs/`
- Rewrite `docs/architecture.md` for Cognee-plugin + Messenger + file-first memory.
- Create `docs/cognee-setup.md` documenting plugin install, env config, fallback path, and the known install bug workaround.
- Light edit to `docs/openclaw-setup.md` for single-agent personal config.

### 7.5 Phase 7 commit
`git commit -m "Update gitignore, package.json scripts, repo-check, and docs for plugin-based Cognee"`

## Phase 8 — End-to-end verification

Two test passes. The first verifies plumbing (does memory survive, does the plugin index, does the brief land). The second verifies posture (is the agent actually an active interlocutor, or is it slipping into mirror mode).

### 8.1 Plumbing test (five steps)
1. Cognee plugin healthy: `openclaw plugins list` shows `memory-cognee` enabled and no errors. `.cognee_system/` has recent activity.
2. Messenger conversation: "I keep avoiding hard conversations with my mom." Wait 6 minutes. Confirm `memory/sessions/YYYY-MM-DD/clarification.md` exists with a shadow signal noted. Optionally, agent has drafted `memory/shadow/avoidance-hard-conversations.md`.
3. (Simulated) 3 days later, Messenger: "Same thing happened with my brother." Agent's reply references the prior pattern (Cognee retrieval is working).
4. Morning brief includes the active belief candidate or shadow pattern with day count.
5. Hand-edit `memory/shadow/avoidance-hard-conversations.md`. Trigger next agent run. Confirm the agent's reply reflects the edited content (plugin re-sync works).

### 8.2 Posture test (five behaviors)
Across a real conversation of moderate depth, the agent should exhibit each of these at least once without being asked:

1. **Propose an interpretation** with explicit hypothesis framing ("My read is..." or "One possibility is...").
2. **Offer at least two reframings** when Kristian brings a belief or stuck situation.
3. **Draw a cross-session parallel** unprompted (references something from a prior session that the current conversation echoes).
4. **Suggest a concrete experiment** Kristian could run this week.
5. **Disagree or push back** at least once when there is reason to (does not just agree).

If the agent only ever reflects and agrees, the AGENTS.md rules are not landing. Strengthen them and retest.

### 8.3 Verification outcomes
- All ten checks pass → project is live.
- Plumbing fails → stop, diagnose, fix, retest.
- Plumbing passes but posture fails → revisit AGENTS.md and SOUL.md; the rules aren't biting. Do not declare done until both pass.

### 8.4 Phase 8 commit
`git commit -m "End-to-end verification of Companion: memory plumbing and active-interlocutor posture"`

## Out of scope (parking lot)

- Rename Companion to its real name
- Default shadow framework (Jungian / IFS / etc.)
- Google Keep API integration beyond Google Tasks via gog
- Tailscale Funnel public exposure
- Belief↔life data cross-referencing beyond loose conversational signals
- Migration of any actual content from `archive/` into `memory/` (intentional fresh start)
- Backup strategy for `.cognee_system/` (regenerable from `memory/`, low priority)
- Pattern analyst as a separate scheduled batch role
- Auditor batch role for unsupported claims

## Hard rules for any executing agent

- **Do not edit `PHILOSOPHY.md` without explicit approval from Kristian.** If a phase requires changing the philosophy, stop and ask. The whole architecture depends on this file being the stable center.
- **Do not skip the posture test in Phase 8.2.** Plumbing passing alone is not done. The agent must demonstrate active-interlocutor behaviors or this project has failed even if everything technically works.
- **Do not migrate content out of `archive/` into `memory/` opportunistically.** The fresh-start posture is deliberate. If Kristian wants something brought forward, he names it specifically.
- **Do not commit `.env.cognee`, `.cognee_system/`, OAuth tokens, or any other secret.** Verify with `git status` before every commit.
