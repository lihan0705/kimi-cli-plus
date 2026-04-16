---
name: llm-wiki
description: Use this skill when the user wants to distill source material into the Markdown-first wiki. It focuses on writing or updating canonical wiki pages on disk, then refreshing index.md and appending log.md.
---

# LLM Wiki Distillation

## Goal
Turn raw source material into a durable Markdown wiki page in the filesystem-first wiki layout.

## Workflow
1. Identify the target wiki page kind: `entity`, `concept`, `comparison`, or `query`.
2. Choose or normalize a stable page slug.
3. Distill the source into a Markdown page under the matching directory.
4. Refresh `index.md` from the current page set.
5. Append an entry to `log.md` describing the source and written page.

## Rules
- Treat the filesystem as canonical. Do not require a database write for the happy path.
- Prefer updating an existing page when the slug already exists instead of creating variants.
- Keep provenance lightweight but explicit in the page frontmatter or body.
- If the source is noisy, preserve only the useful distilled content in the page and keep raw archives elsewhere.

## Output Shape
- Page file: `<wiki-root>/<page-kind-directory>/<page-slug>.md`
- Index entry: `[[page-slug]]` in `index.md`
- Log entry: timestamped line in `log.md`
