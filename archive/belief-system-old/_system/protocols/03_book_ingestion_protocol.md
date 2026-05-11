# Book Ingestion Protocol

The goal is to turn a book into actionable belief change.

For long books, do not ingest the whole book in one pass unless the user explicitly asks for a rough overview. Use `_system/protocols/18_chapter_ingestion_protocol.md` and process the book piece by piece.

## Folder

Create:

```text
02_sources/books/<book-slug>/
```

Required files:

- `00_manifest.json`
- `00_source_metadata.md`
- `01_surface_summary.md`
- `02_core_model.md`
- `03_belief_candidates.md`
- `04_daily_life_implications.md`
- `05_exercises.md`
- `06_key_passages.md`
- `07_related_beliefs.md`
- `08_open_questions.md`
- `09_ingestion_audit.md`

## Extraction Questions

Ask:

- What is the book's model of human behavior?
- What does the book say people misunderstand?
- Which beliefs does the book try to weaken?
- Which beliefs does the book try to strengthen?
- What would the user do differently tomorrow if they fully understood the book?
- What does the book make less valuable?
- What does the book make more valuable?
- What situations should trigger a new action?
- What claims need skepticism or external evidence?

## Recommended Flow

1. Create the source folder and manifest.
2. Ask whether the user wants chapter-by-chapter ingestion, section-by-section ingestion, or rough overview.
3. If detail matters, ingest chapters or sections one at a time.
4. After each chapter, write chapter-level belief candidates and daily-life implications.
5. After several chapters, synthesize repeated themes.
6. Only create whole-book conclusions after all supplied chapters are processed or the folder is marked partial.

## Belief Candidate Format

Each candidate should include:

- Old belief challenged.
- New belief proposed.
- Expected behavior shift.
- Source chapters or passages.
- Confidence in extraction.
- Whether the user has adopted, rejected, or only noticed the idea.

## Daily-Life Test

For every major source idea, write:

```text
If I actually understood this, then in normal life I would...
```

This prevents surface reading.

## Freedom Model Lens

When using The Freedom Model or similar material, separate:

- The author's claim.
- The user's own belief.
- The behavioral preference implied by the belief.
- The perceived benefit the old behavior provides.
- The new understanding that could change preference.

Do not turn the book into doctrine. Use it as source material for user-owned inspection.
