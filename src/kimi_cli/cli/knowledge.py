from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from kimi_cli.wiki import delete_pages, ensure_wiki_dirs, get_wiki_root, list_pages, read_page
from kimi_cli.wiki.index import rebuild_wiki_index
from kimi_cli.wiki.ingest import WikiSourceLoadError, distill_source_to_page, load_source_material
from kimi_cli.wiki.relationships import (
    WikiRelationshipParseError,
    audit_relationships,
    rebuild_relationships,
)
from kimi_cli.wiki.session_import import import_session_file

cli = typer.Typer(help="Manage the Markdown-first wiki.")


@cli.command("list")
def list_docs() -> None:
    """List wiki pages."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    pages = list_pages(root)

    if not pages:
        typer.echo("No wiki pages found.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Kind")
    table.add_column("Slug")
    table.add_column("Title")
    table.add_column("Summary")
    for page in pages:
        table.add_row(page.page_kind, page.slug, page.title, page.summary_preview)

    Console().print(table)


@cli.command("read")
def read(slug: Annotated[str, typer.Argument(help="Wiki page slug")]) -> None:
    """Read a wiki page by slug."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    try:
        page = read_page(root, slug)
    except FileNotFoundError:
        typer.echo(f"Error: Wiki page not found: {slug}")
        return
    typer.echo(page.content)


@cli.command("delete")
def delete(
    slugs: Annotated[list[str], typer.Argument(help="One or more page slugs to delete")],
) -> None:
    """Delete wiki pages by slug and refresh generated artifacts."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)

    result = delete_pages(root, slugs)
    index_path = rebuild_wiki_index(root)
    relations = rebuild_relationships(root)

    typer.echo(f"Deleted: {', '.join(result.deleted_slugs) if result.deleted_slugs else '(none)'}")
    if result.missing_slugs:
        typer.echo(f"Missing: {', '.join(result.missing_slugs)}")
    typer.echo(f"Index updated at {index_path}")
    typer.echo(f"Relations updated at {relations.relations_path}")


@cli.command("index")
def index() -> None:
    """Rebuild wiki index."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    path = rebuild_wiki_index(root)
    typer.echo(f"Index recompiled at {path}")


@cli.command("ingest")
def ingest(
    source: Annotated[str, typer.Argument(help="URL or local file path to ingest")],
) -> None:
    """Distill a URL or local file into a Markdown wiki page."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    try:
        material = load_source_material(source)
    except WikiSourceLoadError as exc:
        typer.echo(f"Error: {exc}")
        return
    except Exception as exc:  # pragma: no cover - unexpected failures
        typer.echo(f"Error: Ingestion failed: {exc}")
        return

    try:
        result = distill_source_to_page(
            root=root,
            source_text=material.source_text,
            source_title=material.source_title,
            page_kind="concept",
            page_slug=material.source_title,
            source_identity=material.source_identity,
        )
    except Exception as exc:  # pragma: no cover - unexpected filesystem failures
        typer.echo(f"Error: Ingestion failed: {exc}")
        return
    typer.echo(f"Distilled source into wiki page: [[{result.page_slug}]]")
    typer.echo(f"Page path: {result.page_path}")
    typer.echo(f"Index updated at {result.index_path}")
    typer.echo(f"Log updated at {root / 'log.md'}")


@cli.command("orient")
def orient() -> None:
    """Print the active wiki root and core files."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    typer.echo(f"Wiki root: {root}")
    typer.echo(f"Index: {root / 'index.md'}")
    typer.echo(f"Log: {root / 'log.md'}")
    for name in ("entities", "concepts", "comparisons", "queries", "raw/sessions", "raw/sources"):
        typer.echo(f"- {root / name}")


@cli.command("relink")
def relink() -> None:
    """Rebuild page links, backlinks, and relation reports."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    try:
        result = rebuild_relationships(root)
    except WikiRelationshipParseError as exc:
        typer.echo(f"Error: {exc}")
        return
    typer.echo("Relationship rebuild complete.")
    typer.echo(f"Pages scanned: {result.page_count}")
    typer.echo(f"Relations updated at {result.relations_path}")
    typer.echo(f"Audit updated at {result.audit_path}")


@cli.command("audit")
def audit() -> None:
    """Run read-only wiki audit."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    try:
        result = audit_relationships(root)
    except WikiRelationshipParseError as exc:
        typer.echo(f"Error: {exc}")
        return
    typer.echo(f"Audit updated at {result.audit_path}")


@cli.command("import-session")
def import_session(
    source: Annotated[
        str, typer.Argument(help="Session JSONL file to archive into the wiki raw store")
    ],
    session_id: Annotated[
        str, typer.Option("--session-id", help="Stable session id to archive under")
    ],
) -> None:
    """Archive a raw session file into the wiki filesystem store."""
    root = get_wiki_root()
    ensure_wiki_dirs(root)
    archived = import_session_file(root, Path(source), session_id=session_id)
    typer.echo(f"Archived session to {archived.raw_path}")
    typer.echo(f"Metadata written to {archived.metadata_path}")
