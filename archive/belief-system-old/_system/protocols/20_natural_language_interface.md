# Natural Language Interface

The user should not need to know commands, filenames, folder names, or internal workflows.

## Principle

The user speaks naturally. The agent routes the request, loads the right context, runs the necessary protocol, and saves the right records.

## User May Say

Any ordinary phrase can trigger the workflow:

- "I want to work on a belief."
- "I think I am done for today."
- "Let's wrap this up."
- "Save this."
- "Can you remember this?"
- "I finished this belief."
- "I want to read this book properly."
- "Here is chapter 2."
- "Make me a prompt I can use in ChatGPT."
- "Here is a transcript from another chat."
- "What should I work on next?"
- "Show me my progress."

## Agent Responsibilities

The agent must infer the task and run the framework without asking the user to name protocols.

When the user gives a natural request:

1. Identify the likely capability using `_system/protocols/14_capability_routing.md`.
2. Load only task-relevant context using `_system/protocols/17_context_loading_policy.md`.
3. Run the protocol.
4. Save records automatically when the task creates durable memory.
5. Tell the user briefly what was saved or what is needed next.

## Natural Session Closure

Treat these as session-close intent:

- `end`
- "I'm done"
- "done for today"
- "wrap this up"
- "save this session"
- "let's stop here"
- "close the session"
- "that's enough for now"

Do not require exact wording.

## Automatic Background Work

The user should not have to ask for:

- Loading relevant prior context.
- Looking for related patterns.
- Creating summaries.
- Updating belief files.
- Updating experiments.
- Updating the progress ledger.
- Producing deterministic clarification.
- Adding candidate beliefs discovered during the session.
- Suggesting next focus when enough evidence exists.

These are default responsibilities of the system.

## Clarifying Questions

Ask a question only when needed to avoid a bad write or wrong task route.

Good clarifying questions:

- "Is this a new belief or part of an existing one?"
- "Do you want chapter-level ingestion or just a rough overview?"
- "Should I treat this as an external transcript to import?"

Avoid asking the user to choose internal protocol names.

## User-Facing Style

Use plain language:

- "I found the related belief file and two prior sessions."
- "I'll save this as a session and update the belief."
- "This looks like a book-ingestion task, so I'll process it chapter by chapter."

Do not say:

- "Run protocol 02."
- "Update schema-bound artifact."
- "Invoke deterministic clarification workflow."

## Done Means

The user can use the system by saying what they want in ordinary language, while the agent handles routing, memory, summaries, and updates.
