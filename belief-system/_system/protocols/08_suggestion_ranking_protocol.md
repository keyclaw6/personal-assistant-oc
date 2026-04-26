# Suggestion And Ranking Protocol

This protocol decides what belief to work on next.

## Inputs

Use:

- Active beliefs.
- Testing beliefs.
- Candidate beliefs.
- Source-derived belief candidates.
- Recent deterministic clarifications.
- Active experiments.
- User goals and current life context.

## Ranking Factors

Score 0 to 5.

### Leverage

How many behaviors, goals, or other beliefs would change if this belief changed?

### Recurrence

How often does the belief appear across sessions, sources, or avoided actions?

### Cost

How much does the belief currently block life quality, freedom, action, or social behavior?

### Readiness

How ready is the user to inspect it without the session becoming too vague, defensive, or unsafe?

### Evidence Availability

Can the belief be tested with real examples, source material, or small experiments?

### Source Momentum

Is a current book, conversation, or life event already making this belief easier to update?

## Priority Score

```text
priority = leverage + recurrence + cost + readiness + evidence_availability + source_momentum
```

Maximum: 30.

## Output

Write suggested focus lists to:

```text
06_reviews/pattern_reports/YYYYMMDD-next-beliefs-to-work.md
```

Each suggestion must include:

- Belief slug.
- Current status.
- Priority score.
- Why now.
- What session should ask first.
- What experiment may follow.
- Why not work on it yet, if relevant.

## Important Rule

The highest score is a recommendation, not a command. The user chooses.
