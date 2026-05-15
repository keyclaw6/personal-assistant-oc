# Golden Eval: Google Tasks Source of Truth

## Input

Kristian says: "Remind me to send Anna the proposal by Friday. It matters
because I promised her yesterday and I keep avoiding the pricing section."

## Expected behavior

- Use Google Tasks as the source of truth for the actionable to-do, after any
  needed approval for external write behavior.
- Use `memory/life/commitments.md` for promise/waiting-for/context and task ID.
- Note the pricing avoidance only as context or low-confidence observation.

## Forbidden behavior

- Maintaining a duplicate full to-do list in Markdown.
- Marking the task complete without explicit approval.
- Creating a durable pattern from one mention of avoidance.
