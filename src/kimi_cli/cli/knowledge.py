from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.table import Table

from kimi_cli.knowledge import (
    Category,
    DocumentMetadata,
    DocumentStatus,
    KBStore,
    ensure_kb_dirs,
    generate_slug,
    get_kb_root,
)
from kimi_cli.knowledge.compiler import compile_wiki_index
from kimi_cli.knowledge.converter import PDFConverter, URLConverter
from kimi_cli.knowledge.models import SourceType
from kimi_cli.knowledge.paths import get_document_dir
from kimi_cli.wiki import ensure_wiki_dirs, get_wiki_root
from kimi_cli.wiki.ingest import distill_source_to_page
from kimi_cli.wiki.session_import import import_session_file

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
        Category | None, typer.Option("--category", "-c", help="Filter by category")
    ] = None,
    status: Annotated[
        DocumentStatus | None, typer.Option("--status", "-s", help="Filter by status")
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


@cli.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 10,
):
    """Search for documents in the Knowledge Base using FTS5."""
    store = get_store()
    results = store.search(query, limit=limit)

    if not results:
        typer.echo("No documents found matching your query.")
        return

    for res in results:
        typer.echo("-" * 40)
        typer.echo(
            f"ID: [cyan]{str(res.metadata.id)[:8]}[/cyan] | "
            f"Title: [bold white]{res.metadata.title}[/bold white]"
        )
        typer.echo(
            f"Category: [green]{res.metadata.category.value}[/green] | "
            f"Subcategory: {res.metadata.subcategory}"
        )
        typer.echo(f"Snippet: {res.snippet}")
    typer.echo("-" * 40)


@cli.command("sync")
def sync():
    """Synchronize Knowledge Base from disk."""
    root = get_kb_root()
    store = get_store()
    store.sync_from_disk(root)

    docs = store.list_documents()
    typer.echo(f"Synchronization complete. Total documents: {len(docs)}")
    
    # Recompile index
    compile_wiki_index(root)
    typer.echo(f"Index updated at {root}/index.md")


@cli.command("index")
def index():
    """Recompile the Knowledge Base index.md."""
    root = get_kb_root()
    compile_wiki_index(root)
    typer.echo(f"Index recompiled at {root}/index.md")


@cli.command("ingest")
def ingest(
    source: Annotated[str, typer.Argument(help="URL or local file path to ingest")],
):
    """Distill a URL or local file into a Markdown wiki page."""

    root = get_wiki_root()
    ensure_wiki_dirs(root)

    if source.startswith(("http://", "https://")):
        source_type = SourceType.URL
        content = URLConverter.convert_url_to_md(source)
        source_title = _source_title_from_url(source)
    else:
        path = Path(source).expanduser().resolve()
        if not path.exists():
            typer.echo(f"Error: File not found: {source}")
            return
        source_type = SourceType.File
        source_title = path.stem
        if path.suffix.lower() == ".pdf":
            content = PDFConverter.convert_pdf_to_md(path)
        else:
            content = path.read_text(encoding="utf-8")

    if not content:
        typer.echo(f"Error: Failed to extract content from {source_type.value}.")
        return

    result = distill_source_to_page(
        root=root,
        source_text=content,
        source_title=source_title,
        page_kind="concept",
        page_slug=source_title,
    )
    typer.echo(f"Distilled source into wiki page: [[{result.page_slug}]]")
    typer.echo(f"Page path: {result.page_path}")
    typer.echo(f"Index updated at {result.index_path}")
    typer.echo(f"Log updated at {root / 'log.md'}")


@cli.command("orient")
def orient():
    """Print the active wiki root and core files."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    typer.echo(f"Wiki root: {root}")
    typer.echo(f"Index: {root / 'index.md'}")
    typer.echo(f"Log: {root / 'log.md'}")
    for name in ("entities", "concepts", "comparisons", "queries", "raw/sessions", "raw/sources"):
        typer.echo(f"- {root / name}")


@cli.command("import-session")
def import_session(
    source: Annotated[
        str, typer.Argument(help="Session JSONL file to archive into the wiki raw store")
    ],
    session_id: Annotated[
        str, typer.Option("--session-id", help="Stable session id to archive under")
    ],
):
    """Archive a raw session file into the wiki filesystem store."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    archived = import_session_file(root, Path(source), session_id=session_id)
    typer.echo(f"Archived session to {archived.raw_path}")
    typer.echo(f"Metadata written to {archived.metadata_path}")


@cli.command("graph")
def graph(
    doc_id: Annotated[str, typer.Argument(help="ID (short or full) of the document to explore")],
):
    """Explore the knowledge graph for a document."""
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

    console = Console()
    console.print(
        f"[bold magenta]Connections for:[/bold magenta] "
        f"[cyan]{str(target_doc.id)[:8]}[/cyan] [white]{target_doc.title}[/white]"
    )
    console.print("-" * 50)

    # 1. Outbound Links
    outbound = store.get_outgoing_links(target_doc.id)
    console.print("[bold cyan]Links To (Outbound):[/bold cyan]")
    if not outbound:
        console.print("  (None)")
    for doc in outbound:
        console.print(f"  -> [dim]{str(doc.id)[:8]}[/dim] {doc.title}")

    # 2. Inbound Links
    inbound = store.get_backlinks(target_doc.id)
    console.print("\n[bold green]Backlinks (Inbound):[/bold green]")
    if not inbound:
        console.print("  (None)")
    for doc in inbound:
        console.print(f"  <- [dim]{str(doc.id)[:8]}[/dim] {doc.title}")

    # 3. Related (by Tags - filtered to remove direct links)
    related_results = store.get_related_documents(target_doc.id)
    linked_ids = {str(d.id) for d in outbound} | {str(d.id) for d in inbound}
    
    tag_related = [(d, s) for d, s in related_results if str(d.id) not in linked_ids]
    
    console.print("\n[bold yellow]Related (by Tags):[/bold yellow]")
    if not tag_related:
        console.print("  (None)")
    for doc, score in tag_related:
        console.print(f"  ~ [dim]{str(doc.id)[:8]}[/dim] {doc.title} (score: {score})")


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

    for doc in docs:
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


def _edit_and_sync(doc: DocumentMetadata) -> None:
    """Helper to open editor and sync metadata."""
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


def _source_title_from_url(source: str) -> str:
    parsed = urlparse(source)
    last_segment = parsed.path.rstrip("/").split("/")[-1]
    return last_segment or parsed.netloc or "web-source"
