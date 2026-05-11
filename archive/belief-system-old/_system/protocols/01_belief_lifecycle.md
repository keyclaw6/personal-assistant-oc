# Belief Lifecycle Protocol

## States

### candidate

A possible belief worth inspecting. It may come from a book, session, pattern report, or user note.

Exit criteria:

- User chooses to activate it.
- User rejects it.
- Agent marks it as duplicate or low relevance.

### active

A belief currently being explored.

Exit criteria:

- The belief is ready for experiments.
- The belief is dissolved or rejected.
- The belief is paused.

### testing

A belief with one or more behavioral experiments.

Exit criteria:

- Experiments produce enough evidence to update the model.
- Experiments reveal the belief needs reframing.
- User decides the belief is complete, abandoned, or no longer priority.

### integrated

The updated belief is now the user's normal operating model in relevant contexts.

Exit criteria:

- Move to maintenance after a review interval.
- Reopen if the old belief repeatedly returns with force.

### maintenance

The belief is mostly integrated but reviewed periodically.

Exit criteria:

- Archive after stable review.
- Reopen if new evidence or life context changes.

### archived

The belief is no longer active. It is preserved for historical pattern analysis.

## Completion Types

- `integrated`: a new model has become normal.
- `dissolved`: the old belief no longer makes sense.
- `contextualized`: the belief is true only in narrower conditions.
- `rejected`: the belief candidate was not worth adopting.
- `archived`: the belief is not current priority.

## User-Owned Completion

Agents can recommend completion, but the final completion mark requires:

```text
USER_COMPLETION_MARK: yes
Date:
Belief:
Completion type:
User statement:
```

The user statement should be short and direct:

```text
I consider this belief complete because...
```

## Reopening

Reopening a belief is not failure. It means new context exposed a remaining prediction, fear, preference, or identity hook.
