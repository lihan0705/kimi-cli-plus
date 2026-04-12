# WikiSearch

Search the Knowledge Base for relevant documents using full-text search (FTS5).
This tool returns matching documents with their titles, IDs, categories, and brief snippets of the matching content.

## When to Use
- When you need to find information previously ingested into the Knowledge Base.
- When you want to find specific concepts, decisions, or references.
- To discover what's available in the Knowledge Base related to a topic.

## Parameters
- `query`: (Required) The search query string. Supports SQLite FTS5 syntax.
- `limit`: (Optional) Maximum number of results to return (default: 10).

## Example
If you search for "SQLite FTS5", it might return:
### SQLite FTS5 Implementation
- **ID**: `550e8400-e29b-41d4-a716-446655440000`
- **Category**: concept
- **Snippet**: ...we are using **SQLite FTS5** for the Knowledge Base to provide precision search...
