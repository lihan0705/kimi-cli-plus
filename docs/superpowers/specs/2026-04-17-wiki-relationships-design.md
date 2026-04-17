# Wiki Relationships Design

## Goal

Extend the filesystem-backed wiki under `~/.kimi/wiki` so canonical markdown pages
can maintain Hermes-style relationships:

- explicit and machine-added `[[wikilinks]]`
- backlinks
- global relationship summaries
- audit reports for broken or ambiguous relationships

This design applies only to the markdown wiki layer. It does not merge the wiki
filesystem with `knowledge.db`.

## Scope

This design covers:

- canonical wiki page relationship extraction and maintenance
- page-local `Links` and `Backlinks` sections
- global `RELATIONS.md` and `audit.md` artifacts
- CLI commands to rebuild and inspect relationship state
- ingest-time partial relinking for affected wiki pages

This design does not cover:

- watcher/background sync processes
- `knowledge.db` integration
- semantic entity resolution with embeddings or LLM disambiguation
- automatic guessing for ambiguous link candidates
- restructuring the existing wiki directory layout

## Problem

The current wiki feature can distill sources into canonical markdown pages, but it
does not maintain page-to-page relationships. That leaves the wiki with page files,
an index, and a log, but without the interlinked graph behavior expected from an
LLM wiki workflow like Hermes.

## Decision

The first relationship-enabled version will use a standalone markdown relationship
module with two operating modes:

1. **Local update during ingest**
   After `kimi wiki ingest`, the new or updated page will be relinked and any pages
   whose backlink sections change will also be rewritten.

2. **Full rebuild via CLI**
   A new `kimi wiki relink` command will rescan all canonical pages and rebuild:
   - page-local `Links` sections
   - page-local `Backlinks` sections
   - `RELATIONS.md`
   - `audit.md`

`kimi wiki audit` will run the same analysis pass but expose the audit-focused
output to the user as a dedicated command.

## Relationship Rules

### Source of truth

Canonical page markdown files remain the source of truth.

Relationships are derived from:

- existing explicit `[[...]]` links already present in page content
- safe machine-added links generated from unique title/slug/alias matches

The system will not persist a separate graph database for the wiki layer.

### Matching strategy

Link resolution follows a conservative three-step policy:

1. Preserve explicit links already written by the page author.
2. Auto-link only when a candidate uniquely resolves to one existing page.
3. Do not guess when resolution is ambiguous or absent; report these cases in
   `audit.md`.

### Normalization

Matching will normalize candidate strings by:

- lowercasing
- trimming whitespace
- collapsing spaces, underscores, and hyphens into one normalized separator
- removing simple punctuation

Auto-generated links will target the canonical page slug form:

- `[[page-slug]]`

Machine output should not depend on mutable display titles.

## Page Format

Canonical pages keep their current structure:

- frontmatter
- display title
- `## Summary`
- optional `## Outline`

The relationship module will additionally maintain machine-owned trailing sections:

- `## Links`
- `## Backlinks`

These sections are rewritten by the relationship module and should be treated as
derived content.

## Global Artifacts

### `SCHEMA.md`

`SCHEMA.md` remains documentation for layout and rules. It is not used as a runtime
relationship index.

### `RELATIONS.md`

`RELATIONS.md` is the wiki-global relationship summary. It should provide a compact
overview for each page, including:

- page slug or title
- number of outgoing links
- number of backlinks
- whether the page is isolated

### `audit.md`

`audit.md` is the machine-generated exception report. It should include:

- broken explicit links
- ambiguous candidate links
- unresolved link candidates
- duplicate title or alias conflicts
- isolated pages

## CLI Design

The CLI will expose three relationship-aware entry points:

- `kimi wiki ingest <source>`
  - distills the source into a canonical page
  - runs local relinking for the changed page and affected backlink targets

- `kimi wiki relink`
  - rescans all canonical pages
  - rewrites relationship sections
  - rebuilds `RELATIONS.md`
  - refreshes `audit.md`

- `kimi wiki audit`
  - runs the same analysis phase
  - refreshes `audit.md`
  - prints a user-facing summary of the findings

## Module Boundaries

The implementation should introduce a dedicated wiki relationship module rather than
embedding graph logic directly into the CLI entrypoints or the existing ingest
renderer.

Recommended responsibilities:

- page discovery and page metadata extraction
- link target registry and normalization
- explicit link parsing
- safe auto-link insertion
- backlink computation
- global relations rendering
- audit rendering

The existing ingest module should remain focused on source loading and canonical page
distillation.

## Error Handling

Relationship rebuilds should fail closed and explain the filesystem target involved.

Expected behavior:

- malformed page files should be reported in `audit.md`
- broken explicit links should remain visible in the source page and be reported,
  not silently removed
- ambiguous auto-link candidates should remain plain text and be reported

## Risks

The main risks are:

- rewriting user-authored markdown too aggressively
- generating unstable diffs if section formatting is not deterministic
- introducing false-positive links from over-broad normalization

The design addresses these risks by:

- limiting machine rewriting to owned relationship sections
- auto-linking only on unique safe matches
- pushing uncertain matches into `audit.md` instead of guessing

## Success Criteria

This feature is complete when:

- canonical pages can expose stable `Links` and `Backlinks` sections
- `kimi wiki relink` rebuilds relationship state for the full wiki root
- `kimi wiki audit` reports broken, ambiguous, unresolved, duplicate, and isolated
  cases
- `kimi wiki ingest` updates relationship state for newly written pages
- the markdown wiki remains independent from `knowledge.db`
