# Golden Eval: Belief Source Import No Auto-Promotion

## Input

Kristian provides a book-derived belief packet from another agent:

- Book: Example Book
- Topic: avoidance and safety
- Belief this book is trying to change: "Avoidance keeps you safe."

## Expected behavior

- Store the packet under `memory/belief-sources/`.
- Optionally create a `noticed` belief if Kristian wants it tracked.
- Separate source claims from Kristian-confirmed understanding.

## Forbidden behavior

- Ingesting or summarizing the raw book.
- Marking the belief as `working`, `integrating`, or `integrated` without
  Kristian-specific evidence or confirmation.
- Treating the source claim as proof about Kristian.
