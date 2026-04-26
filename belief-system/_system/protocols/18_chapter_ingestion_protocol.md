# Chapter Ingestion Protocol

Use this for books, long articles, transcripts, or any source where detail matters.

## Purpose

Avoid shallow whole-book summaries by ingesting source material piece by piece, then synthesizing across pieces.

## Folder Structure

For each book:

```text
02_sources/books/<book-slug>/
  chapters/
    001-chapter-title/
      00_chapter_manifest.json
      01_raw_notes.md
      02_chapter_summary.md
      03_belief_extraction.md
      04_daily_life_implications.md
      05_exercises.md
      06_questions_for_user.md
      07_passage_index.md
      08_chapter_audit.md
```

## Passes

### Pass 1: Comprehension

Capture what the chapter says in plain language.

Output:

- Chapter thesis.
- Key claims.
- Key examples.
- Terms or models introduced.
- Questions or unclear parts.

### Pass 2: Belief Extraction

Extract what the chapter tries to change in the reader.

Output:

- Old beliefs challenged.
- New beliefs proposed.
- Hidden assumptions.
- Preference changes implied.
- Identity or social implications.

### Pass 3: Daily-Life Translation

For each major chapter idea, answer:

```text
If I actually understood this chapter, then in normal life I would...
```

Output:

- Behaviors that would change.
- Situations that should trigger the idea.
- Decisions that would be made differently.
- Exercises or experiments.

### Pass 4: User Relevance

Compare chapter ideas against:

- Existing beliefs.
- Active experiments.
- User goals.
- Recurring patterns.

Output:

- Related existing beliefs.
- New candidate beliefs.
- Suggested follow-up questions.
- Confidence and uncertainty.

## Synthesis

After several chapters, create or update:

- `02_core_model.md`
- `03_belief_candidates.md`
- `04_daily_life_implications.md`
- `05_exercises.md`
- `07_related_beliefs.md`
- `08_open_questions.md`

Do not finalize whole-book conclusions until all supplied chapters have been processed or the ingestion is explicitly marked partial.

## User Questions

Ask the user questions when:

- The chapter's relevance depends on personal context.
- A belief candidate could be important but uncertain.
- The chapter suggests a practice but the right scale is unclear.
- The source conflicts with existing user values or beliefs.

Keep questions few and high-value.

## Done Means

A chapter is ingested when:

- The chapter folder has all required files.
- The chapter has gone through all four passes.
- Candidate beliefs are marked as source-derived, not user-adopted.
- Daily-life implications and exercises exist.
- Open questions are written for the user.
