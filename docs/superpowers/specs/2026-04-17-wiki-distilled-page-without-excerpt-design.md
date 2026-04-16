# Wiki Distilled Page Without Source Excerpt Design

## Goal

Remove the `Source Excerpt` section from canonical wiki pages produced by
`distill_source_to_page(...)` so distilled pages store only distilled knowledge,
not raw source passages.

## Scope

This change is limited to the markdown page rendering path in
`src/kimi_cli/wiki/ingest.py` and the corresponding ingest tests in
`tests/wiki/test_ingest.py`.

The change does not alter:

- page frontmatter fields
- slug generation or `source_identity` behavior
- wiki index rebuilding
- wiki log entries
- source loading from files, PDFs, or URLs
- CLI command surface

## Problem

The current distilled page format includes a `## Source Excerpt` block.
That block leaks a verbatim slice of the original source into the canonical page.
This conflicts with the intended role of the canonical page as a distilled,
stable knowledge artifact.

## Decision

Canonical wiki pages will contain only these content sections after frontmatter:

- title
- `## Summary`
- `## Outline` when headings are available

The page renderer will no longer compute or emit any excerpt content.

## Design

### Rendering path

`_distill_source_text(...)` will return only:

- summary lines
- outline lines

`_render_page(...)` will render:

1. frontmatter
2. display title
3. summary block
4. optional outline block

No `Source Excerpt` heading or body will be produced.

### Test coverage

`tests/wiki/test_ingest.py` will explicitly assert that:

- `## Summary` is still present
- `## Source Excerpt` is not present
- raw tail text from the source does not appear in the page

Existing tests covering slug stability, source identity, index rebuilding, and log
writing remain the regression net for unchanged behavior.

## Error Handling

No new error paths are introduced. The change is a format reduction inside the
existing successful ingest flow.

## Risks

The main risk is an incomplete cleanup where helper code for excerpts remains but
is unused. The implementation should remove the excerpt-generation path entirely
so the rendered format and helper surface stay aligned.

## Success Criteria

The change is complete when:

- distilled pages no longer contain `## Source Excerpt`
- canonical pages still contain summary content and optional outline content
- ingest tests pass with the new format expectation
