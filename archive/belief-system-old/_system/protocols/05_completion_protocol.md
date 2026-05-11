# Completion Protocol

Completion means the user has intentionally closed a belief work item.

## Completion Readiness Rubric

A belief may be ready for completion when most of the following are true:

- The old belief can be stated clearly.
- The updated model can be stated clearly.
- The user knows what the old belief was trying to protect.
- The user knows the cost of keeping it.
- The user has tested or reasoned through the new model.
- The new model changes at least one concrete behavior or prediction.
- The user can name where the old belief may still be useful or contextually true.
- There is a plan for maintenance if needed.

## Completion Mark

Create a file:

```text
06_reviews/completion_reviews/YYYYMMDD-belief-slug-completion.md
```

Required fields:

```text
Belief:
Completion type:
Date:
User completion mark:
Agent recommendation:
Evidence summary:
Remaining risk:
Reopen condition:
30-day review date:
90-day review date:
```

## Completion Types

- `complete_integrated`
- `complete_dissolved`
- `complete_contextualized`
- `complete_rejected`
- `complete_archived`

## Reopen Conditions

Every completed belief should include at least one condition that would justify reopening it.

Example:

```text
Reopen if the user avoids three relevant opportunities because readiness again feels required before action.
```
