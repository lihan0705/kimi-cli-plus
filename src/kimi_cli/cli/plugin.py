import shutil
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

cli = typer.Typer(help="Manage Kimi Code CLI plugins.")

def get_plugin_dir() -> Path:
    """Get the user-level plugin directory."""
    from kimi_cli.share import get_share_dir
    d = get_share_dir() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d

@cli.command("list")
def plugin_list():
    """List all installed plugins."""
    from kimi_cli.plugin import get_user_plugin_dir, get_project_plugin_dir
    from kaos.path import KaosPath
    import asyncio

    async def _list():
        user_dir = get_user_plugin_dir()
        project_dir = get_project_plugin_dir(KaosPath.cwd())
        
        typer.echo(f"User plugins: {user_dir}")
        if await user_dir.is_dir():
            async for p in user_dir.iterdir():
                if await p.is_dir():
                    typer.echo(f"- {p.name}")
        else:
            typer.echo("  (none)")

        typer.echo(f"\nProject plugins: {project_dir}")
        if await project_dir.is_dir():
            async for p in project_dir.iterdir():
                if await p.is_dir():
                    typer.echo(f"- {p.name}")
        else:
            typer.echo("  (none)")

    asyncio.run(_list())

@cli.command("add")
def plugin_add(
    path_or_url: Annotated[str, typer.Argument(help="Local path or Git URL of the plugin.")]
):
    """Add a plugin from a local path or Git URL."""
    plugin_dir = get_plugin_dir()
    
    if path_or_url.startswith(("http://", "https://", "git@")):
        # Git clone logic
        import subprocess
        name = path_or_url.split("/")[-1].removesuffix(".git")
        target = plugin_dir / name
        if target.exists():
            typer.echo(f"Plugin '{name}' already exists.")
            raise typer.Exit(1)
        
        typer.echo(f"Cloning plugin from {path_or_url}...")
        try:
            subprocess.run(["git", "clone", "--depth", "1", path_or_url, str(target)], check=True)
            typer.echo(f"Plugin '{name}' installed successfully.")
        except subprocess.CalledProcessError as e:
            typer.echo(f"Failed to clone plugin: {e}", err=True)
            raise typer.Exit(1)
    else:
        # Local path logic
        source = Path(path_or_url).expanduser().resolve()
        if not source.exists():
            typer.echo(f"Path '{source}' does not exist.", err=True)
            raise typer.Exit(1)
        
        name = source.name
        target = plugin_dir / name
        if target.exists():
            typer.echo(f"Plugin '{name}' already exists.")
            raise typer.Exit(1)
        
        typer.echo(f"Installing plugin from {source}...")
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            # Single file plugin? We might want to support this later.
            typer.echo("Currently only directory-based plugins are supported.", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"Plugin '{name}' installed successfully.")

@cli.command("remove")
def plugin_remove(
    name: Annotated[str, typer.Argument(help="Name of the plugin to remove.")]
):
    """Remove an installed plugin."""
    plugin_dir = get_plugin_dir()
    target = plugin_dir / name
    
    if not target.exists():
        typer.echo(f"Plugin '{name}' not found.", err=True)
        raise typer.Exit(1)
    
    typer.echo(f"Removing plugin '{name}'...")
    shutil.rmtree(target)
    typer.echo(f"Plugin '{name}' removed.")
