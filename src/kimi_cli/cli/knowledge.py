from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from kimi_cli.knowledge import (
    Category,
    DocumentStatus,
    KBStore,
    ensure_kb_dirs,
    get_kb_root,
)

cli = typer.Typer(help="Manage Knowledge Base (Wiki).")


def get_store() -> KBStore:
    root = get_kb_root()
    ensure_kb_dirs(root)
    db_path = root / "knowledge.db"
    return KBStore(db_path)


@cli.command("status")
def status():
    """Show Knowledge Base status."""
    root = get_kb_root()
    store = get_store()

    docs = store.list_documents()
    total = len(docs)
    needs_review = len([d for d in docs if d.status == DocumentStatus.needs_review])

    category_counts: dict[str, int] = {}
    for cat in Category:
        category_counts[cat.value] = 0
    for d in docs:
        category_counts[d.category.value] = category_counts.get(d.category.value, 0) + 1

    typer.echo(f"Knowledge Base Root: {root}")
    typer.echo(f"Total Documents: {total}")
    typer.echo(f"Needs Review: {needs_review}")
    typer.echo("\nBreakdown by Category:")
    # Sort categories by count (descending)
    sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    for cat, count in sorted_cats:
        if count > 0:
            typer.echo(f"  {cat}: {count}")


@cli.command("list")
def list_docs(
    category: Annotated[
        Optional[Category], typer.Option("--category", "-c", help="Filter by category")
    ] = None,
    status: Annotated[
        Optional[DocumentStatus], typer.Option("--status", "-s", help="Filter by status")
    ] = None,
):
    """List documents in the Knowledge Base."""
    store = get_store()
    docs = store.list_documents(category=category, status=status)

    if not docs:
        typer.echo("No documents found.")
        return

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Title")
    table.add_column("Category")
    table.add_column("Status")

    for doc in docs:
        table.add_row(str(doc.id)[:8], doc.title, doc.category.value, doc.status.value)

    console.print(table)


@cli.command("sync")
def sync():
    """Synchronize Knowledge Base from disk."""
    root = get_kb_root()
    store = get_store()
    store.sync_from_disk(root)

    docs = store.list_documents()
    typer.echo(f"Synchronization complete. Total documents: {len(docs)}")


@cli.command("ingest")
def ingest(
    source: Annotated[str, typer.Argument(help="URL or local file path to ingest")],
):
    """Ingest a URL or local file into the Knowledge Base."""
    from kimi_cli.app import KimiCLI
    from kimi_cli.knowledge.ingest import IngestPipeline
    from kimi_cli.knowledge.converter import URLConverter, PDFConverter
    from kimi_cli.knowledge.log import LogManager
    from kimi_cli.knowledge.models import SourceType
    import asyncio

    async def _run():
        root = get_kb_root()
        ensure_kb_dirs(root)
        
        # We need a chat provider. Use KimiCLI to load the default one.
        kimi = KimiCLI.create()
        if not kimi.runtime.llm:
            typer.echo("Error: No LLM configured.")
            return

        # 1. Convert
        if source.startswith(("http://", "https://")):
            source_type = SourceType.URL
            content = URLConverter.convert_url_to_md(source)
        else:
            path = Path(source).expanduser().resolve()
            if not path.exists():
                typer.echo(f"Error: File not found: {source}")
                return
            source_type = SourceType.File
            if path.suffix.lower() == ".pdf":
                content = PDFConverter.convert_pdf_to_md(path)
            else:
                content = path.read_text(encoding="utf-8")

        if not content:
            typer.echo("Error: Failed to extract content.")
            return

        # 2. Pipeline
        db_path = root / "knowledge.db"
        kb_store = KBStore(db_path)
        log_manager = LogManager(root)
        
        pipeline = IngestPipeline(
            root=root,
            chat_provider=kimi.runtime.llm.chat_provider,
            kb_store=kb_store,
            log_manager=log_manager
        )

        typer.echo(f"Ingesting {source_type} content...")
        metadata = await pipeline.run(content, source_type, source)
        
        typer.echo(f"Successfully ingested: {metadata.title}")
        typer.echo(f"ID: {metadata.id}")
        typer.echo(f"Category: {metadata.category}")
        typer.echo(f"Status: {metadata.status}")

    asyncio.run(_run())


@cli.command("review")
def review():
    """Review documents in the 'needs_review' queue."""
    store = get_store()
    docs = store.list_documents(status=DocumentStatus.needs_review)

    if not docs:
        typer.echo("No documents need review. Your knowledge base is clean!")
        return

    console = Console()
    table = Table(title="Documents Needing Review")
    table.add_column("ID (Short)", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Category", style="green")
    table.add_column("Created At", style="dim")

    for i, doc in enumerate(docs):
        table.add_row(
            str(doc.id)[:8],
            doc.title,
            doc.category.value,
            doc.created_at.strftime("%Y-%m-%d"),
        )

    console.print(table)
    
    choice = typer.prompt("Enter the ID (short) of the document to review (or 'q' to quit)")
    if choice.lower() == 'q':
        return

    # Find the document
    target_doc = None
    for doc in docs:
        if str(doc.id).startswith(choice):
            target_doc = doc
            break
    
    if not target_doc:
        typer.echo(f"Error: No document found with ID starting with '{choice}'")
        return

    _edit_and_sync(target_doc)


@cli.command("edit")
def edit(
    doc_id: Annotated[str, typer.Argument(help="ID (short or full) of the document to edit")],
):
    """Edit any document in the knowledge base."""
    store = get_store()
    # Find the document
    all_docs = store.list_documents()
    target_doc = None
    for doc in all_docs:
        if str(doc.id).startswith(doc_id):
            target_doc = doc
            break
    
    if not target_doc:
        typer.echo(f"Error: No document found with ID '{doc_id}'")
        return

    _edit_and_sync(target_doc)


def _edit_and_sync(doc):
    """Helper to open editor and sync metadata."""
    import os
    import subprocess
    from kimi_cli.knowledge.paths import get_document_dir, get_kb_root
    
    root = get_kb_root()
    # Need to find the current physical path (could be in raw/ or knowledge/)
    slug = generate_slug(doc.title, doc.id)
    doc_dir = get_document_dir(root, slug, doc.status, doc.category, doc.subcategory)
    
    # Fallback if get_document_dir fails to find it due to state mismatch
    if not doc_dir.exists():
        # Try raw/
        doc_dir = root / "raw" / slug
        if not doc_dir.exists():
            # Try knowledge/misc/
            doc_dir = root / "knowledge" / "misc" / slug
            if not doc_dir.exists():
                # Brute force search
                found = list(root.rglob(f"*{str(doc.id)[:8]}"))
                if found:
                    doc_dir = found[0]
                else:
                    typer.echo("Error: Could not locate document directory on disk.")
                    return

    file_to_edit = doc_dir / "document.md"
    editor = os.environ.get("EDITOR", "vim")
    
    typer.echo(f"Opening {file_to_edit} in {editor}...")
    subprocess.call([editor, str(file_to_edit)])
    
    # Sync after editing
    store = get_store()
    new_dir = store.sync_metadata_from_md(doc_dir)
    
    if new_dir != doc_dir:
        typer.echo(f"Document promoted/moved to: {new_dir.relative_to(root)}")
    typer.echo("Sync complete.")
