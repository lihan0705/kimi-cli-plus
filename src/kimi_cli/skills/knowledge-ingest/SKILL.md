---
name: knowledge-ingest
description: Use this skill when the user wants to ingest, save, or archive information into the Knowledge Base (Wiki). This includes processing URLs, PDF files, chat sessions, or manual notes. The skill guides the transformation of raw content into structured knowledge entries, generating a complete Markdown file with YAML frontmatter for human editing.
---

# Knowledge Ingestion Skill

## Overview
This skill transforms raw information into structured, human-editable Wiki pages. It uses a two-step process to ensure accurate classification and high-quality metadata extraction.

## Ingestion Workflow

### 1. Content Pre-processing
Ensure the content is clean and formatted as Markdown:
- **URLs**: Extract main text, strip navigation/ads.
- **PDFs**: 
    - < 5 pages/2MB: Direct read.
    - > 5 pages/2MB: Use local tools (e.g., `pdftotext`) first.
- **Sessions**: Format as `### User` / `### Assistant`.

### 2. Two-Step Classification

#### Step 1: Identify Primary Category
Choose exactly one from the **8 Seed Categories**:
`concept`, `howto`, `decision`, `reference`, `analysis`, `source`, `snippet`, `project`.

#### Step 2: Metadata Extraction
Extract: `title`, `description`, `tags`, `subcategory`, `relevance_score` (1-10), `temporal_type` (`evergreen`/`time_sensitive`), and `key_claims` (max 5).

### 3. Output Format
Provide TWO blocks in your response:

**Block 1: JSON Metadata** (For system processing)
```json
{
  "title": "...",
  "category": "...",
  "subcategory": "...",
  "tags": [...],
  "confidence": 0.95,
  "relevance_score": 8,
  "temporal_type": "evergreen",
  "key_claims": [...]
}
```

**Block 2: Final Wiki Page** (The actual .md file)
```markdown
---
title: [Title]
category: [Category]
subcategory: [Subcategory]
tags: [tag1, tag2]
relevance_score: [1-10]
key_claims:
  - [Claim 1]
  - [Claim 2]
---

# [Title]

[Cleaned and formatted content goes here...]
```

## Guidelines
- **User Ownership**: The Wiki Page (Block 2) is what the user will see and edit. Make it look professional.
- **Slug-Ready Titles**: Concise and descriptive.
- **Confidence Gate**: If confidence < 0.8, ensure the status in your internal thinking is "needs_review".
