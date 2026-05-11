# Progress Export Protocol

Use this when the user asks for a report, snapshot, progress summary, or overview of belief change.

## Inputs

- `08_metrics/progress_ledger.csv`
- `03_beliefs/**/belief.md`
- `04_sessions/*/04_deterministic_clarification.json`
- `05_experiments/**`
- `06_reviews/**`
- `01_profile/recurring_patterns.md`
- `01_profile/learning_style.md`

## Output Folder

Write exports to:

```text
10_exports/reports/
```

Use this filename:

```text
YYYYMMDD-belief-progress-report.md
```

## Report Sections

- Period covered.
- Sessions completed.
- Beliefs by status.
- Beliefs moved this period.
- Experiments completed.
- Evidence that changed understanding.
- Patterns with confidence.
- Books or sources integrated.
- Completion marks.
- Suggested next focus.
- System gaps or maintenance needs.

## Rules

- Use deterministic clarifications as primary evidence.
- Do not claim a belief changed unless the record shows prediction, preference, behavior, or explicit status movement.
- Mark uncertainty clearly.
- Keep reports actionable rather than ceremonial.
