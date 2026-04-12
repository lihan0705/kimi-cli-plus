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
