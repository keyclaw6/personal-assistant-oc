# Architecture — Albert

Albert is one Messenger-first OpenClaw agent for Kristian Bilstrup. The goal
is practical help and understanding-first belief change: keep commitments
visible, make daily life easier, track what Kristian is trying to understand,
and notice evidence-backed patterns without turning the assistant into a
therapist or mythology engine.

## Runtime shape

```txt
Facebook Messenger ─▶ OpenClaw gateway ─▶ Albert workspace
                                      │
                                      ├─ openclaw-messenger plugin
                                      ├─ cognee-openclaw indexes albert/memory/
                                      ├─ composio-limited tools for Gmail/Calendar/Tasks/LinkedIn
                                      └─ scheduled jobs: morning brief, evening journal, nightly review
```

## Active prompt layers

Use OpenClaw's native workspace files only:

```txt
albert/
  SOUL.md      # voice/tone/boundaries
  AGENTS.md    # operating contract
  USER.md      # stable user facts
  IDENTITY.md  # short presentation
  TOOLS.md     # tool conventions and approval policy
  MEMORY.md    # memory contract
  HEARTBEAT.md # tiny heartbeat checklist
  jobs/        # explicit scheduled-job prompts
  methods/     # belief/pattern methods
```

`albert/archive/design/PHILOSOPHY.old.md` is archived rationale, not runtime
instruction.

## Memory directory

```txt
albert/memory/
  profile/          stable/current context and preferences
  life/             commitments, journals, briefings, nightly/weekly reviews
  observations/     lightweight dated observations
  patterns/         evidence-backed recurring patterns
  beliefs/          belief understanding and integration logs
  belief-sources/   structured imported belief candidates
  sessions/         dated therapy/belief-chat/messenger summaries
  conflicts.md      contested or corrected memory
```

Legacy `memory/shadow/` may remain for old material, but new recurring
self-development work goes to `memory/patterns/` with `shadow` only as an
optional tag.

## Operating principle

Live chat stays lightweight and useful. Deeper synthesis happens in scheduled
nightly/weekly reviews. Belief change is understanding-first: track what lands,
what does not land, and what signs show integration. Experiments are optional
evidence, not the core mechanism. Pattern claims require dated evidence,
confidence, and an alternative explanation. Weak evidence becomes a question.

## Scheduled routines

- Morning brief — 07:30 Europe/Copenhagen.
- Evening journal reminder — 21:00 Europe/Copenhagen if today's journal is
  missing.
- Nightly review — local-only consolidation while Kristian sleeps.

## External tools

Composio is the active Google/LinkedIn path. Reading/summarizing/drafting is
allowed when useful. Sending, deleting, posting, editing calendar events,
marking tasks complete, or changing integrations requires explicit approval for
that exact action.
