# External Chat Workflow

This protocol lets the system work outside OpenClaw in normal chat apps such as ChatGPT, Gemini, Claude, or a phone-based assistant.

There are two modes:

1. Export a focused prompt for a specific belief.
2. Import the resulting transcript and save it into the system.

## Export A Belief-Session Prompt

Create:

```text
10_exports/prompts/YYYYMMDD-belief-slug-external-chat-prompt.md
```

The exported prompt should be self-contained but compact.

Include:

- Purpose of the chat.
- The belief being worked.
- Current belief status.
- Relevant user philosophy.
- Relevant profile notes.
- Prior session summary if useful.
- Active experiments.
- How the external assistant should coach.
- What the assistant must not do.
- A required closing summary format.
- Instruction that the user will later paste/upload the transcript back into the Belief Change System.

Do not include the entire workspace. Include only the context needed for this belief.

## External Assistant Constraints

The prompt should tell the external assistant:

- Do not diagnose.
- Do not claim to permanently change beliefs.
- Do not shame or pressure.
- Focus on understanding, preference, protective function, cost, evidence, daily-life implication, and experiments.
- End by producing a structured summary.

## Required External Closing Summary

The external chat should end with:

```text
BELIEF_SESSION_SUMMARY
Belief:
Old model:
Updated model candidates:
Protective function:
Cost:
Evidence discussed:
Daily-life implications:
Experiment or next action:
Open questions:
User-owned decisions:
```

## Import Transcript

When the user brings back a transcript:

1. Save it under:

```text
00_inbox/session_requests/YYYYMMDD-belief-slug-external-transcript.md
```

2. Create a normal session folder under:

```text
04_sessions/YYYYMMDD-HHMMSS-belief-slug-external/
```

3. Put the transcript in `01_transcript.md`.
4. Write `02_context_loaded.md`.
5. Produce `03_interpretive_analysis.md`.
6. Produce `04_deterministic_clarification.json`.
7. Update belief files, experiments, suggestion queue, and progress ledger as appropriate.
8. Mark the session source as `external_chat`.

## Import Rules

- Treat external assistant claims as interpretations, not truth.
- Prefer direct user statements and chosen actions over assistant analysis.
- Do not update durable memory from external assistant speculation alone.
- Use the deterministic clarification schema.
- Preserve the transcript.

## Done Means

External export is done when a compact prompt exists in `10_exports/prompts`.

External import is done when the transcript has been converted into a normal session folder with deterministic clarification and traceable updates.
