# Session Protocol

## Session Setup

Create a session ID:

```text
YYYYMMDD-HHMMSS-belief-slug
```

Create:

```text
04_sessions/<session-id>/
```

Required files:

- `00_manifest.json`
- `01_transcript.md`
- `02_context_loaded.md`
- `03_interpretive_analysis.md`
- `04_deterministic_clarification.json`
- `05_belief_updates.md`
- `06_next_actions.md`
- `07_audit.md`

## Opening Move

The agent should begin with a brief loaded-context recap:

- Belief being worked.
- Current status.
- Prior pattern signals.
- Open experiments.
- Most relevant unresolved question.

Then ask:

```text
What feels most alive about this belief today?
```

If the user already gave a clear entry point, start there.

## Coaching Arc

1. Name the belief in plain language.
2. Find recent examples.
3. Map the preference logic.
4. Identify what the belief protects.
5. Identify what it costs.
6. Separate evidence from interpretation.
7. Generate alternative models.
8. Ask what daily behavior would change if the new model were true.
9. Design one small experiment.
10. End with a summary and explicit next action.

## End Protocol

When the user says `end` or naturally indicates closure, such as "I'm done", "wrap this up", "save this", "let's stop here", or "done for today":

1. Save transcript if available.
2. Write interpretive analysis.
3. Produce deterministic clarification using `_system/schemas/session_clarification.schema.json`.
4. Update belief file.
5. Update experiment files.
6. Update `08_metrics/progress_ledger.csv`.
7. Add candidates discovered during the session.
8. Write next actions.
9. If completion was discussed, create a completion review.

## Deterministic Clarification Rules

The clarification:

- Uses restrained language.
- Records observable session facts.
- Separates direct user claims from agent inferences.
- Uses confidence fields.
- Does not include advice unless advice was explicitly chosen as a next action.
- Does not claim a pattern unless it can point to current-session evidence.
