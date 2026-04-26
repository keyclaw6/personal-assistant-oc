# Pattern Analysis Protocol

Pattern analysis should be done by a separate agent whenever possible.

## Primary Inputs

Use:

- `04_sessions/*/04_deterministic_clarification.json`
- `03_beliefs/**/belief.md`
- `05_experiments/**`
- `08_metrics/progress_ledger.csv`

Use interpretive analyses only as secondary context.

## Pattern Types

Track:

- Repeating belief themes.
- Repeating protective functions.
- Repeating avoided experiments.
- Repeating forms of evidence that change the user.
- Repeating forms of evidence that do not change the user.
- Beliefs that are intellectually updated but behaviorally untrusted.
- Books or sources that repeatedly point to the same theme.
- Contradictions between stated values and active preference logic.

## Confidence

- `low`: visible once or twice.
- `medium`: repeated across at least three sessions or two life domains.
- `high`: repeated across time, contexts, and behavior.

## Output

Write pattern reports to:

```text
06_reviews/pattern_reports/YYYYMMDD-pattern-report.md
```

Each report must include:

- Pattern name.
- Evidence.
- Confidence.
- Related beliefs.
- Possible next belief to work.
- Suggested experiment.
- What would disconfirm the pattern.

## No Overreach

Do not diagnose. Do not claim hidden motives as fact. Use language like:

```text
The records suggest...
One possible pattern is...
This is not yet strong enough to treat as established...
```
