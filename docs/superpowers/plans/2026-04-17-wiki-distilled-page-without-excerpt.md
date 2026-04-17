# Wiki Distilled Page Without Source Excerpt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `## Source Excerpt` from canonical wiki pages while preserving distilled summary, optional outline, slug stability, and existing ingest side effects.

**Architecture:** Keep the existing `distill_source_to_page(...) -> _render_page(...) -> _distill_source_text(...)` pipeline, but narrow its data contract so the distillation step returns only summary and outline content. Use the ingest test suite as the regression net to lock in the new page format and prove no raw source tail is written to the canonical page.

**Tech Stack:** Python 3.12+, pytest, uv, Typer-based Kimi CLI workspace

---

### Task 1: Lock the New Page Format in Tests

**Files:**
- Modify: `tests/wiki/test_ingest.py:86-109`
- Test: `tests/wiki/test_ingest.py`

- [ ] **Step 1: Write the failing test expectation**

```python
def test_distill_source_to_page_writes_distilled_summary_not_full_source_dump(tmp_path: Path):
    root = tmp_path / "wiki"
    ensure_wiki_dirs(root)
    source_text = (
        "# Raw Note\n\n"
        "RAG combines retrieval and generation to ground answers in relevant documents. "
        "It can improve factuality when the retriever is high quality.\n\n"
        "Systems usually need chunking, ranking, and citation handling.\n\n"
        "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE."
    )

    result = distill_source_to_page(
        root=root,
        source_text=source_text,
        source_title="rag-note",
        page_kind="concept",
        page_slug="retrieval-augmented-generation",
        source_identity="note://rag-note",
    )

    page_text = result.page_path.read_text(encoding="utf-8")
    assert "## Summary" in page_text
    assert "## Source Excerpt" not in page_text
    assert "VERBATIM TAIL SHOULD NOT APPEAR IN THE CANONICAL PAGE." not in page_text
```

- [ ] **Step 2: Run the targeted test to verify it fails for the old behavior**

Run: `uv run pytest tests/wiki/test_ingest.py::test_distill_source_to_page_writes_distilled_summary_not_full_source_dump -v`
Expected: FAIL because the rendered page still contains `## Source Excerpt`.

- [ ] **Step 3: Keep the rest of the ingest regression net unchanged**

```python
def test_distill_source_to_concept_page_writes_page_index_and_log(tmp_path: Path): ...
def test_distill_source_to_page_uses_source_identity_to_avoid_slug_collisions(tmp_path: Path): ...
def test_distill_source_to_page_updates_existing_page_for_same_source_identity(tmp_path: Path): ...
```

- [ ] **Step 4: Re-run the targeted test after implementation**

Run: `uv run pytest tests/wiki/test_ingest.py::test_distill_source_to_page_writes_distilled_summary_not_full_source_dump -v`
Expected: PASS with no `Source Excerpt` section in the generated page.

- [ ] **Step 5: Commit the test-first checkpoint**

```bash
git add tests/wiki/test_ingest.py
git commit -m "test(wiki): forbid source excerpts in distilled pages"
```

### Task 2: Remove Excerpt Rendering from the Distillation Pipeline

**Files:**
- Modify: `src/kimi_cli/wiki/ingest.py:132-246`
- Test: `tests/wiki/test_ingest.py`

- [ ] **Step 1: Narrow `_distill_source_text(...)` to the final two-value contract**

```python
def _distill_source_text(source_text: str) -> tuple[list[str], list[str]]:
    headings: list[str] = []
    paragraphs: list[str] = []
    current_paragraph: list[str] = []

    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            continue
        if line.startswith("#"):
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            heading = line.lstrip("#").strip()
            if heading:
                headings.append(heading)
            continue
        cleaned = line.lstrip("-*").strip()
        if cleaned and not cleaned.startswith("```"):
            current_paragraph.append(cleaned)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))

    summary_lines = _build_summary_lines(paragraphs)
    outline_lines = headings[:4]
    return summary_lines, outline_lines
```

- [ ] **Step 2: Remove excerpt rendering from `_render_page(...)`**

```python
def _render_page(
    *,
    source_text: str,
    source_title: str,
    source_identity: str,
    page_kind: WikiPageKind,
    page_slug: str,
) -> str:
    summary_lines, outline_lines = _distill_source_text(source_text)
    outline_block = ""
    if outline_lines:
        outline_block = "## Outline\n\n" + "\n".join(f"- {line}" for line in outline_lines) + "\n\n"
    return (
        "---\n"
        f"source_title: {source_title}\n"
        f"source_identity: {source_identity}\n"
        f"page_kind: {page_kind.value}\n"
        f"page_slug: {page_slug}\n"
        "---\n\n"
        f"# {_display_title(source_text, page_slug)}\n\n"
        "## Summary\n\n"
        + "\n".join(f"- {line}" for line in summary_lines)
        + "\n\n"
        + outline_block
        + "\n"
    )
```

- [ ] **Step 3: Delete the now-unused excerpt helper entirely**

```python
def _build_summary_lines(paragraphs: list[str]) -> list[str]:
    sentences: list[str] = []
    for paragraph in paragraphs[:4]:
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            normalized = sentence.strip()
            if len(normalized) < 24:
                continue
            sentences.append(_truncate_text(normalized, limit=140))
            if len(sentences) == 3:
                return sentences
    if not sentences:
        return ["No source content provided."]
    return sentences


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
```

- [ ] **Step 4: Run the focused wiki ingest test file**

Run: `uv run pytest tests/wiki/test_ingest.py -v`
Expected: PASS for all ingest tests, including slug collision and page update coverage.

- [ ] **Step 5: Run project verification required by the repo**

Run: `make check-kimi-cli`
Expected: PASS for the repo-local required check, with no new lint or type regressions from the ingest cleanup.

- [ ] **Step 6: Commit the implementation**

```bash
git add src/kimi_cli/wiki/ingest.py tests/wiki/test_ingest.py
git commit -m "fix(wiki): remove source excerpts from distilled pages"
```
