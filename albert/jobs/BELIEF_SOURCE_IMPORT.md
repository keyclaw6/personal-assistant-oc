# BELIEF_SOURCE_IMPORT.md

## Purpose

Import a structured belief source packet created elsewhere. Albert does not
ingest books directly. Another agent or Kristian may provide the book/source
title, topic, and beliefs the source is trying to change.

Use this for:

- book-derived belief lists from another agent
- article/podcast/source summaries already distilled into beliefs
- external LLM syntheses Kristian wants tracked
- Kristian's own written belief breakdowns

## Input shape

Expected input should include as much as available:

```md
Source title:
Source type: book | article | podcast | external-agent | personal-note | other
Topic:
Beliefs this source is trying to change:
1.
2.
3.
Supporting arguments / why these may be true:
What Kristian has confirmed:
What Kristian has not confirmed:
Cautions:
```

## Output

Write a source packet under:

```txt
memory/belief-sources/<slug>.md
```

Shape:

```md
# Belief Source: <title>

Source type:
Imported:
Topic:
Status: imported | partly-linked | archived

## Candidate beliefs
- <belief> — status: not-created | noticed | linked:<belief-slug>

## Supporting arguments

## What Kristian confirmed

## What Kristian has not confirmed

## Suggested belief files to create or update

## Cautions
```

## Rules

- Do not analyze raw books directly.
- Do not auto-promote source claims into Kristian's beliefs.
- Candidate beliefs may become `noticed` belief files when the source is clear
  and Kristian wants them tracked.
- `working`, `integrating`, or `integrated` requires Kristian-specific evidence
  or confirmation.
- Separate source claims from Kristian's own words.
- If creating or touching a belief file, update `memory/beliefs/_index.md`.

End with:

```txt
BELIEF_SOURCE_IMPORT_OK <paths-written>
```
