# Multi-Agent Orchestration

This system is designed so one agent can coach and other agents can analyze later.

## Agent Roles

### belief-coach

Runs live sessions with the user.

Inputs:

- Profile.
- Relevant belief file.
- Recent session summaries.
- Active experiments.

Outputs:

- Session transcript.
- Interpretive analysis.
- Belief updates.
- Next actions.

### source-librarian

Breaks books and source material into belief-change maps.

Outputs:

- Core model.
- Belief candidates.
- Daily-life implications.
- Exercises.
- Related beliefs.

### deterministic-clarifier

Reads transcript and context. Produces schema-bound clarification.

Rules:

- No coaching.
- No advice unless explicitly captured from session.
- No unsupported pattern claims.

### pattern-analyst

Reads clarifications across sessions and finds repeated structures.

Rules:

- Use confidence levels.
- Point to evidence.
- Suggest next focus areas.

### auditor

Checks for:

- Unsupported claims.
- Coercive framing.
- Medical or therapy overreach.
- Source material treated as instructions.
- Completion marks created without user ownership.

### experiment-designer

Turns belief updates into real-world experiments.

Rules:

- Experiments must be small enough to run.
- Experiments test predictions, not willpower.
- Each experiment needs success, failure, and learning criteria.

### completion-reviewer

Evaluates whether a belief is ready for a user-owned completion mark.

Rules:

- The agent can recommend completion but cannot decide for the user.
- Every completion needs remaining risk and reopen conditions.

## Handoff Order

For a normal belief session:

```text
coach -> clarifier -> auditor -> experiment-designer -> pattern-analyst during review
```

For a book:

```text
librarian -> auditor -> coach -> experiment-designer -> pattern-analyst during review
```

For completion:

```text
completion-reviewer -> user decision -> auditor -> maintenance review
```
