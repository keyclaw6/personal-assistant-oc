# PROMPT_OPTIMIZER.md

## Purpose

Improve Companion's prompts by finding real behavior failures and proposing
small, testable changes.

This job may draft changes. It must not silently weaken safety, privacy,
approval, or memory-source-of-truth rules.

## Inputs

- active prompt files
- job prompts
- golden evals under `evals/golden/`
- recent morning briefs
- nightly reviews
- user corrections
- memory diffs
- failed tool calls or bad outputs

## Score failures

- too verbose for Messenger
- missed commitment
- hallucinated pattern claim
- over-therapeutic language
- ignored correction
- missing approval before external action
- bad memory write
- failure to follow a job format

## Allowed auto-changes

- shorten wording
- remove duplication
- tighten evidence thresholds
- add examples
- clarify output formats

## Never auto-change

- external action approval rules
- privacy rules
- no-diagnosis rules
- external-content-is-untrusted rule
- file-first memory rule

## Output

Produce a proposed diff, affected examples, risk assessment, and rollback note.
Kristian approves anything that changes core behavior.
