# Belief Change System

This is the root workspace for the Belief Change System.

This is an OpenClaw-ready workspace for deliberate belief change, book integration, session logging, pattern analysis, experiment design, and progress tracking. The system treats beliefs as lived models of reality: they shape what seems painful, joyful, safe, possible, costly, and worth doing.

## Purpose

The system exists to help you:

- Work on specific beliefs across many sessions without losing continuity.
- Turn books into practical belief-change maps rather than surface summaries.
- Track active, testing, integrated, maintained, and archived beliefs.
- Create clear completion marks when you decide a belief is finished.
- Store every session in its own session ID folder.
- Separate coaching interpretation from deterministic clarification.
- Let later agents analyze session clarifications for long-term patterns.
- Learn how you learn, how your preferences shift, and what kinds of evidence actually change you.

This is a self-improvement and reflection system. It is not medical care, therapy, diagnosis, or crisis support. For addiction, mental health, or safety-critical issues, use qualified human support when needed.

## Central Philosophy

The system is built around your stated view:

> People do what currently seems best to them, given their understanding of the world, their perceived options, and their expected pain and joy.

This workspace calls that the **Perceived Best Option Principle**. The point of belief work is not to force yourself to believe something nicer. The point is to update understanding until different choices honestly appear better, freer, more accurate, or more aligned with the life you want.

## OpenClaw Shape

OpenClaw can use a workspace with root prompt files and workspace skills. This project therefore includes:

- `AGENTS.md`: standing operating instructions for agents.
- `SOUL.md`: tone, philosophy, and coaching posture.
- `TOOLS.md`: file and tool-use conventions.
- `skills/belief_change_system/SKILL.md`: OpenClaw-compatible workspace skill.
- `_system/openclaw/openclaw.example.json5`: optional configuration example.
- `HEARTBEAT.md`: OpenClaw heartbeat checklist for weekly inactivity reminders.

To use this as an OpenClaw workspace, configure OpenClaw's agent workspace to this folder, or copy the `skills/belief_change_system` folder into the active OpenClaw workspace `skills/` directory.

## Daily Use

Use natural language. You do not need to remember protocol names, exact commands, or folder names.

Start a belief session by saying something like:

```text
I want to work on the belief: I need to be fully ready before I act.
```

Start a book integration by saying:

```text
Ingest this book into the belief system.
```

For long books, the default is chapter-by-chapter or section-by-section ingestion so the system does not flatten the book into a shallow summary.

Create an external chat prompt by saying:

```text
Create an external chat prompt for the belief: <belief name>
```

Import an external transcript by placing it in `00_inbox/session_requests` or pasting it into the agent and saying:

```text
Import this external belief-session transcript.
```

End a session naturally:

```text
I'm done for today. Please wrap this up and save it.
```

When closure is implied, the agent should:

1. Save the session in a unique session ID folder.
2. Produce an interpretive analysis.
3. Produce a deterministic clarification file.
4. Update the relevant belief files.
5. Update experiments and next actions.
6. Add pattern observations only when evidence supports them.
7. Create or update completion records if you explicitly mark a belief as finished.

The agent should automatically load relevant patterns, prior sessions, summaries, and active experiments. You should not have to remember to ask for those.

## Core Folders And Files

- `00_inbox`: raw books, notes, and session requests.
- `01_profile`: your values, goals, life context, learning style, and recurring pattern map.
- `02_sources`: books, articles, videos, podcasts, and their extracted belief maps.
- `03_beliefs`: the belief lifecycle database.
- `04_sessions`: one folder per session ID.
- `05_experiments`: real-world tests of updated understanding.
- `06_reviews`: weekly, monthly, quarterly, pattern, and completion reviews.
- `07_agent_outputs`: outputs separated by agent role.
- `08_metrics`: progress ledgers and scoring definitions.
- `09_prompts`: role prompts for coach, librarian, clarifier, pattern analyst, auditor, experiment designer, and completion reviewer.
- `10_exports`: generated reports and snapshots.
- `10_exports/prompts`: focused prompts for external chat apps.
- `HEARTBEAT.md`: weekly session-inactivity reminder instructions for OpenClaw heartbeat.
- `_system`: protocols, templates, schemas, rubrics, and OpenClaw notes.

## Belief Lifecycle

Beliefs move through:

```text
candidate -> active -> testing -> integrated -> maintenance -> archived
```

A belief can be completed in several ways:

- **Integrated**: the updated belief is now the normal operating model.
- **Dissolved**: the original belief no longer feels coherent or necessary.
- **Contextualized**: the belief is useful only in narrower contexts.
- **Rejected**: the candidate belief is not actually yours or not worth working on.
- **Archived**: the belief is no longer current priority, but may be revisited.

Completion always requires a user-owned completion mark. The agent can recommend completion, but you decide.

## Book Integration

A book is processed into:

- Core claims.
- Implied belief changes.
- Old beliefs challenged by the book.
- New models the book tries to install.
- What would change in daily life if you fully understood it.
- Exercises and behavioral experiments.
- Passages to revisit.
- Related beliefs already in your system.

The output lives under `02_sources/books/<book-slug>/`.

## Agent Roles

The system separates roles so one model can coach while another can later audit and analyze:

- **Coach**: runs the live belief-change conversation.
- **Librarian**: breaks down books and source material.
- **Clarifier**: produces deterministic session summaries from transcript only.
- **Pattern Analyst**: reviews many clarifications for recurring patterns.
- **Auditor**: checks for unsupported claims, coercive framing, or unsafe advice.
- **Experiment Designer**: turns belief updates into daily-life tests.
- **Completion Reviewer**: checks whether a belief deserves a user-owned completion mark.

## Important Rule

The system should never try to hypnotize, pressure, shame, or trick you into a belief. It should help you inspect what you already believe, compare alternatives, understand tradeoffs, and test new models in reality.

## Hardening

The system includes a reusable hardening prompt at `_system/prompts/hardening_prompt.md`. Run it periodically after structural changes, OpenClaw upgrades, or several completed sessions.
