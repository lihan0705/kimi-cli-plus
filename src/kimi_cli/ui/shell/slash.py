from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from prompt_toolkit.shortcuts.choice_input import ChoiceInput

from kimi_cli.auth.platforms import (
    get_platform_name_for_provider,
    parse_openai_legacy_name,
    refresh_managed_models,
)
from kimi_cli.cli import Reload, SwitchToWeb
from kimi_cli.config import load_config, save_config
from kimi_cli.exception import ConfigError
from kimi_cli.session import Session
from kimi_cli.soul.kimisoul import KimiSoul
from kimi_cli.ui.shell.console import console
from kimi_cli.utils.changelog import CHANGELOG
from kimi_cli.utils.datetime import format_relative_time
from kimi_cli.utils.slashcmd import SlashCommand, SlashCommandRegistry

if TYPE_CHECKING:
    from kimi_cli.ui.shell import Shell

type ShellSlashCmdFunc = Callable[[Shell, str], None | Awaitable[None]]
"""
A function that runs as a Shell-level slash command.

Raises:
    Reload: When the configuration should be reloaded.
"""


registry = SlashCommandRegistry[ShellSlashCmdFunc]()
shell_mode_registry = SlashCommandRegistry[ShellSlashCmdFunc]()


def ensure_kimi_soul(app: Shell) -> KimiSoul | None:
    if not isinstance(app.soul, KimiSoul):
        console.print("[red]KimiSoul required[/red]")
        return None
    return app.soul


# Side-effect imports for slash command registration
from . import (  # noqa: F401, E402
    debug,  # pyright: ignore[reportUnusedImport]
    export_import,  # pyright: ignore[reportUnusedImport]
    oauth,  # pyright: ignore[reportUnusedImport]
    setup,  # pyright: ignore[reportUnusedImport]
    update,  # pyright: ignore[reportUnusedImport]
    usage,  # pyright: ignore[reportUnusedImport]
)


@registry.command(aliases=["quit"])
@shell_mode_registry.command(aliases=["quit"])
def exit(app: Shell, args: str):
    """Exit the application"""
    # should be handled by `Shell`
    raise NotImplementedError


SKILL_COMMAND_PREFIX = "skill:"

_KEYBOARD_SHORTCUTS = [
    ("Ctrl-X", "Toggle agent/shell mode"),
    ("Ctrl-O", "Edit in external editor ($VISUAL/$EDITOR)"),
    ("Ctrl-J / Alt-Enter", "Insert newline"),
    ("Ctrl-V", "Paste (supports images)"),
    ("Ctrl-D", "Exit"),
    ("Ctrl-C", "Interrupt"),
]


@registry.command(aliases=["h", "?"])
@shell_mode_registry.command(aliases=["h", "?"])
def help(app: Shell, args: str):
    """Show help information"""
    from rich.console import Group, RenderableType
    from rich.text import Text

    from kimi_cli.utils.rich.columns import BulletColumns

    def section(title: str, items: list[tuple[str, str]], color: str) -> BulletColumns:
        lines: list[RenderableType] = [Text.from_markup(f"[bold]{title}:[/bold]")]
        for name, desc in items:
            lines.append(
                BulletColumns(
                    Text.from_markup(f"[{color}]{name}[/{color}]: [grey50]{desc}[/grey50]"),
                    bullet_style=color,
                )
            )
        return BulletColumns(Group(*lines))

    renderables: list[RenderableType] = []
    renderables.append(
        BulletColumns(
            Group(
                Text.from_markup("[grey50]Help! I need somebody. Help! Not just anybody.[/grey50]"),
                Text.from_markup("[grey50]Help! You know I need someone. Help![/grey50]"),
                Text.from_markup("[grey50]\u2015 The Beatles, [italic]Help![/italic][/grey50]"),
            ),
            bullet_style="grey50",
        )
    )
    renderables.append(
        BulletColumns(
            Text(
                "Sure, Kimi is ready to help! "
                "Just send me messages and I will help you get things done!"
            ),
        )
    )

    commands: list[SlashCommand[Any]] = []
    skills: list[SlashCommand[Any]] = []
    for cmd in app.available_slash_commands.values():
        if cmd.name.startswith(SKILL_COMMAND_PREFIX) or cmd.name.startswith("plugin:"):
            skills.append(cmd)
        else:
            commands.append(cmd)

    renderables.append(section("Keyboard shortcuts", _KEYBOARD_SHORTCUTS, "yellow"))
    renderables.append(
        section(
            "Slash commands",
            [(c.slash_name(), c.description) for c in sorted(commands, key=lambda c: c.name)],
            "blue",
        )
    )
    if skills:
        renderables.append(
            section(
                "Skills",
                [(c.slash_name(), c.description) for c in sorted(skills, key=lambda c: c.name)],
                "cyan",
            )
        )

    with console.pager(styles=True):
        console.print(Group(*renderables))


@registry.command
@shell_mode_registry.command
def version(app: Shell, args: str):
    """Show version information"""
    from kimi_cli.constant import VERSION

    console.print(f"kimi, version {VERSION}")


@registry.command
async def model(app: Shell, args: str):
    """Switch LLM model or thinking mode"""
    from kimi_cli.llm import derive_model_capabilities

    soul = ensure_kimi_soul(app)
    if soul is None:
        return
    config = soul.runtime.config

    await refresh_managed_models(config)

    if not config.models:
        console.print('[yellow]No models configured, send "/login" to login.[/yellow]')
        return

    if not config.is_from_default_location:
        console.print(
            "[yellow]Model switching requires the default config file; "
            "restart without --config/--config-file.[/yellow]"
        )
        return

    # Find current model/thinking from runtime (may be overridden by --model/--thinking)
    curr_model_cfg = soul.runtime.llm.model_config if soul.runtime.llm else None
    curr_model_name: str | None = None
    if curr_model_cfg is not None:
        for name, model_cfg in config.models.items():
            if model_cfg == curr_model_cfg:
                curr_model_name = name
                break
    curr_thinking = soul.thinking

    # Step 1: Select model
    model_choices: list[tuple[str, str]] = []
    for name in sorted(config.models):
        model_cfg = config.models[name]
        provider_label = get_platform_name_for_provider(model_cfg.provider) or model_cfg.provider

        # For OpenAI Legacy, show custom name instead of generic label
        if model_cfg.provider.startswith("managed:openai-legacy:"):
            custom_name = parse_openai_legacy_name(model_cfg.provider)
            if custom_name:
                provider_label = f"OpenAI Legacy ({custom_name})"

        marker = " (current)" if name == curr_model_name else ""
        label = f"{model_cfg.model} ({provider_label}){marker}"
        model_choices.append((name, label))

    try:
        selected_model_name = await ChoiceInput(
            message="Select a model (↑↓ navigate, Enter select, Ctrl+C cancel):",
            options=model_choices,
            default=curr_model_name or model_choices[0][0],
        ).prompt_async()
    except (EOFError, KeyboardInterrupt):
        return

    if not selected_model_name:
        return

    selected_model_cfg = config.models[selected_model_name]
    selected_provider = config.providers.get(selected_model_cfg.provider)
    if selected_provider is None:
        console.print(f"[red]Provider not found: {selected_model_cfg.provider}[/red]")
        return

    # Step 2: Determine thinking mode
    capabilities = derive_model_capabilities(selected_model_cfg)
    new_thinking: bool

    if "always_thinking" in capabilities:
        new_thinking = True
    elif "thinking" in capabilities:
        thinking_choices: list[tuple[str, str]] = [
            ("off", "off" + (" (current)" if not curr_thinking else "")),
            ("on", "on" + (" (current)" if curr_thinking else "")),
        ]
        try:
            thinking_selection = await ChoiceInput(
                message="Enable thinking mode? (↑↓ navigate, Enter select, Ctrl+C cancel):",
                options=thinking_choices,
                default="on" if curr_thinking else "off",
            ).prompt_async()
        except (EOFError, KeyboardInterrupt):
            return

        if not thinking_selection:
            return

        new_thinking = thinking_selection == "on"
    else:
        new_thinking = False

    # Check if anything changed
    model_changed = curr_model_name != selected_model_name
    thinking_changed = curr_thinking != new_thinking

    if not model_changed and not thinking_changed:
        console.print(
            f"[yellow]Already using {selected_model_name} "
            f"with thinking {'on' if new_thinking else 'off'}.[/yellow]"
        )
        return

    # Save and reload
    prev_model = config.default_model
    prev_thinking = config.default_thinking
    config.default_model = selected_model_name
    config.default_thinking = new_thinking
    try:
        config_for_save = load_config()
        config_for_save.default_model = selected_model_name
        config_for_save.default_thinking = new_thinking
        save_config(config_for_save)
    except (ConfigError, OSError) as exc:
        config.default_model = prev_model
        config.default_thinking = prev_thinking
        console.print(f"[red]Failed to save config: {exc}[/red]")
        return

    console.print(
        f"[green]Switched to {selected_model_name} "
        f"with thinking {'on' if new_thinking else 'off'}. "
        "Reloading...[/green]"
    )
    raise Reload(session_id=soul.runtime.session.id)


@registry.command
@shell_mode_registry.command
async def editor(app: Shell, args: str):
    """Set default external editor for Ctrl-O"""
    from kimi_cli.utils.editor import get_editor_command

    soul = ensure_kimi_soul(app)
    if soul is None:
        return
    config = soul.runtime.config
    config_file = config.source_file
    if config_file is None:
        console.print(
            "[yellow]Editor switching is unavailable with inline --config; "
            "use --config-file to persist this setting.[/yellow]"
        )
        return

    current_editor = config.default_editor

    # If args provided directly, use as editor command
    if args.strip():
        new_editor = args.strip()
    else:
        options: list[tuple[str, str]] = [
            ("code --wait", "VS Code (code --wait)"),
            ("vim", "Vim"),
            ("nano", "Nano"),
            ("", "Auto-detect (use $VISUAL/$EDITOR)"),
        ]
        # Mark current selection
        options = [
            (val, label + (" ← current" if val == current_editor else "")) for val, label in options
        ]

        try:
            choice = cast(
                str | None,
                await ChoiceInput(
                    message="Select an editor (↑↓ navigate, Enter select, Ctrl+C cancel):",
                    options=options,
                    default=(
                        current_editor
                        if current_editor in {v for v, _ in options}
                        else "code --wait"
                    ),
                ).prompt_async(),
            )
        except (EOFError, KeyboardInterrupt):
            return

        if choice is None:
            return
        new_editor = choice

    # Validate the editor binary is available
    if new_editor:
        import shlex
        import shutil

        try:
            parts = shlex.split(new_editor)
        except ValueError:
            console.print(f"[red]Invalid editor command: {new_editor}[/red]")
            return

        binary = parts[0]
        if not shutil.which(binary):
            console.print(
                f"[yellow]Warning: '{binary}' not found in PATH. "
                f"Saving anyway — make sure it's installed before using Ctrl-O.[/yellow]"
            )

    if new_editor == current_editor:
        console.print(f"[yellow]Editor is already set to: {new_editor or 'auto-detect'}[/yellow]")
        return

    # Save to disk
    try:
        config_for_save = load_config(config_file)
        config_for_save.default_editor = new_editor
        save_config(config_for_save, config_file)
    except (ConfigError, OSError) as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        return

    # Sync in-memory config so Ctrl-O picks it up immediately
    config.default_editor = new_editor

    if new_editor:
        console.print(f"[green]Editor set to: {new_editor}[/green]")
    else:
        resolved = get_editor_command()
        label = " ".join(resolved) if resolved else "none"
        console.print(f"[green]Editor set to auto-detect (resolved: {label})[/green]")


@registry.command(aliases=["release-notes"])
@shell_mode_registry.command(aliases=["release-notes"])
def changelog(app: Shell, args: str):
    """Show release notes"""
    from rich.console import Group, RenderableType
    from rich.text import Text

    from kimi_cli.utils.rich.columns import BulletColumns

    renderables: list[RenderableType] = []
    for ver, entry in CHANGELOG.items():
        title = f"[bold]{ver}[/bold]"
        if entry.description:
            title += f": {entry.description}"

        lines: list[RenderableType] = [Text.from_markup(title)]
        for item in entry.entries:
            if item.lower().startswith("lib:"):
                continue
            lines.append(
                BulletColumns(
                    Text.from_markup(f"[grey50]{item}[/grey50]"),
                    bullet_style="grey50",
                ),
            )
        renderables.append(BulletColumns(Group(*lines)))

    with console.pager(styles=True):
        console.print(Group(*renderables))


@registry.command
@shell_mode_registry.command
def feedback(app: Shell, args: str):
    """Submit feedback to make Kimi Code CLI better"""
    import webbrowser

    ISSUE_URL = "https://github.com/lihan0705/kimi-cli-plus/issues"
    if webbrowser.open(ISSUE_URL):
        return
    console.print(f"Please submit feedback at [underline]{ISSUE_URL}[/underline].")


@registry.command(aliases=["reset"])
async def clear(app: Shell, args: str):
    """Clear the context"""
    if ensure_kimi_soul(app) is None:
        return
    await app.run_soul_command("/clear")
    raise Reload()


@registry.command
async def new(app: Shell, args: str):
    """Start a new session"""
    soul = ensure_kimi_soul(app)
    if soul is None:
        return
    current_session = soul.runtime.session
    work_dir = current_session.work_dir
    # Clean up the current session if it has no content, so that chaining
    # /new commands (or switching away before the first message) does not
    # leave orphan empty session directories on disk.
    if current_session.is_empty():
        await current_session.delete()
    session = await Session.create(work_dir)
    console.print("[green]New session created. Switching...[/green]")
    raise Reload(session_id=session.id)


@registry.command(name="sessions", aliases=["resume"])
async def list_sessions(app: Shell, args: str):
    """List sessions and resume optionally"""
    soul = ensure_kimi_soul(app)
    if soul is None:
        return

    work_dir = soul.runtime.session.work_dir
    current_session = soul.runtime.session
    current_session_id = current_session.id
    sessions = [
        session for session in await Session.list(work_dir) if session.id != current_session_id
    ]

    await current_session.refresh()
    sessions.insert(0, current_session)

    choices: list[tuple[str, str]] = []
    for session in sessions:
        time_str = format_relative_time(session.updated_at)
        marker = " (current)" if session.id == current_session_id else ""
        label = f"{session.title}, {time_str}{marker}"
        choices.append((session.id, label))

    try:
        selection = await ChoiceInput(
            message="Select a session to switch to (↑↓ navigate, Enter select, Ctrl+C cancel):",
            options=choices,
            default=choices[0][0],
        ).prompt_async()
    except (EOFError, KeyboardInterrupt):
        return

    if not selection:
        return

    if selection == current_session_id:
        console.print("[yellow]You are already in this session.[/yellow]")
        return

    console.print(f"[green]Switching to session {selection}...[/green]")
    raise Reload(session_id=selection)


@registry.command
def web(app: Shell, args: str):
    """Open Kimi Code Web UI in browser"""
    soul = ensure_kimi_soul(app)
    session_id = soul.runtime.session.id if soul else None
    raise SwitchToWeb(session_id=session_id)


@registry.command
async def plugin(app: Shell, args: str):
    """Manage plugins: show|list|add|remove|help"""
    soul = ensure_kimi_soul(app)
    if soul is None:
        return

    args = args.strip()
    if not args:
        # Default: show installed plugins
        await _show_plugins(app, soul)
        return

    # Parse subcommands
    parts = args.split()
    subcommand = parts[0].lower()

    if subcommand in ("list", "show"):
        await _show_plugins(app, soul)
    elif subcommand == "add":
        console.print("[yellow]Plugin add functionality not implemented yet[/yellow]")
    elif subcommand == "remove":
        if len(parts) < 2:
            console.print("[red]Usage: /plugin remove <plugin_name>[/red]")
            return
        plugin_name = parts[1]
        msg = f"Plugin remove functionality not implemented yet: {plugin_name}"
        console.print(f"[yellow]{msg}[/yellow]")
    elif subcommand == "help":
        console.print("[bold]Plugin Commands:[/bold]")
        console.print("  /plugin              - Show installed plugins")
        console.print("  /plugin list          - List installed plugins")
        console.print("  /plugin add           - Add a plugin")
        console.print("  /plugin remove <name> - Remove a plugin")
        console.print("  /plugin help          - Show this help")
    else:
        console.print(f"[red]Unknown plugin subcommand: {subcommand}. Use /plugin help[/red]")


async def _show_plugins(app: Shell, soul: KimiSoul) -> None:
    """Show installed plugins and their commands"""
    from rich.console import Group, RenderableType
    from rich.text import Text

    from kimi_cli.plugin import Plugin
    from kimi_cli.utils.rich.columns import BulletColumns

    plugins: list[Plugin] = soul.runtime.plugins
    if not plugins:
        console.print("[yellow]No plugins installed.[/yellow]")
        return

    console.print(f"[bold]Installed Plugins ({len(plugins)}):[/bold]")

    for p in plugins:
        plugin_text = f"[green]{p.name}[/green]"
        lines: list[RenderableType] = [Text.from_markup(plugin_text)]

        # Skills info with full command paths (ONLY plugin:plugin_name:skill_name format)
        for skill in p.skills:
            primary_cmd = f"/plugin:{p.name}:{skill.name}"

            skill_info = f"[cyan]Skill:[/cyan] {skill.description}\n"
            skill_info += f"  Command: [bold blue]{primary_cmd}[/bold blue]"

            lines.append(
                BulletColumns(
                    Text.from_markup(skill_info),
                    bullet_style="cyan",
                )
            )

        # Tools info
        if p.loaded_tools:
            tools_text = ", ".join(t.name for t in p.loaded_tools)
            lines.append(
                BulletColumns(
                    Text.from_markup(f"[yellow]Tools:[/yellow] {tools_text}"),
                    bullet_style="yellow",
                )
            )

        # MCP info
        if p.mcp_config_file:
            lines.append(
                BulletColumns(
                    Text.from_markup("[blue]MCP Config found[/blue]"),
                    bullet_style="blue",
                )
            )

        console.print(BulletColumns(Group(*lines), bullet_style="green"))


@registry.command(aliases=["knowledge", "kb"])
async def wiki(app: Shell, args: str):
    """Wiki operations: /wiki [list|read|relink|audit|delete]"""
    from rich.table import Table

    from kimi_cli.wiki import (
        delete_pages,
        ensure_wiki_dirs,
        get_wiki_root,
        list_pages,
        read_page,
    )
    from kimi_cli.wiki.index import rebuild_wiki_index
    from kimi_cli.wiki.relationships import (
        WikiRelationshipParseError,
        audit_relationships,
        rebuild_relationships,
    )

    root = get_wiki_root()
    ensure_wiki_dirs(root)
    parts = args.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "list"
    sub_args = parts[1] if len(parts) > 1 else ""

    if subcmd == "list":
        pages = list_pages(root)
        if not pages:
            console.print("[yellow]No wiki pages found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Kind")
        table.add_column("Slug")
        table.add_column("Title")
        for page in pages:
            table.add_row(page.page_kind, page.slug, page.title)
        console.print(table)

    elif subcmd == "read":
        if not sub_args:
            console.print("[red]Usage: /wiki read <slug>[/red]")
            return
        try:
            page = read_page(root, sub_args.strip())
        except FileNotFoundError:
            console.print(f"[red]Wiki page not found: {sub_args.strip()}[/red]")
            return
        console.print(page.content)

    elif subcmd == "relink":
        try:
            result = rebuild_relationships(root)
        except WikiRelationshipParseError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return
        console.print(f"[green]Rebuilt relationships for {result.page_count} pages.[/green]")

    elif subcmd == "audit":
        try:
            result = audit_relationships(root)
        except WikiRelationshipParseError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return
        console.print(f"[green]Audit updated at {result.audit_path}[/green]")

    elif subcmd == "delete":
        slugs = sub_args.split()
        if not slugs:
            console.print("[red]Usage: /wiki delete <slug1> [slug2 ...][/red]")
            return
        result = delete_pages(root, slugs)
        rebuild_wiki_index(root)
        rebuild_relationships(root)
        deleted = ", ".join(result.deleted_slugs) if result.deleted_slugs else "(none)"
        console.print(f"[green]Deleted:[/green] {deleted}")
        if result.missing_slugs:
            console.print(f"[yellow]Missing:[/yellow] {', '.join(result.missing_slugs)}")

    else:
        console.print("[red]Usage: /wiki [list|read <slug>|relink|audit|delete <slug...>][/red]")


@registry.command
async def mcp(app: Shell, args: str):
    """Show MCP servers and tools"""
    from rich.console import Group, RenderableType
    from rich.text import Text

    from kimi_cli.soul.toolset import KimiToolset
    from kimi_cli.utils.rich.columns import BulletColumns

    soul = ensure_kimi_soul(app)
    if soul is None:
        return
    toolset = soul.agent.toolset
    if not isinstance(toolset, KimiToolset):
        console.print("[red]KimiToolset required[/red]")
        return

    servers = toolset.mcp_servers

    if not servers:
        console.print("[yellow]No MCP servers configured.[/yellow]")
        return

    n_conn = sum(1 for s in servers.values() if s.status == "connected")
    n_tools = sum(len(s.tools) for s in servers.values())
    console.print(
        BulletColumns(
            Text.from_markup(
                f"[bold]MCP Servers:[/bold] {n_conn}/{len(servers)} connected, {n_tools} tools"
            )
        )
    )

    status_colors = {
        "connected": "green",
        "connecting": "cyan",
        "pending": "yellow",
        "failed": "red",
        "unauthorized": "red",
    }
    for name, info in servers.items():
        color = status_colors.get(info.status, "red")
        server_text = f"[{color}]{name}[/{color}]"
        if info.status == "unauthorized":
            server_text += " [grey50](unauthorized - run: kimi mcp auth {name})[/grey50]"
        elif info.status != "connected":
            server_text += f" [grey50]({info.status})[/grey50]"

        lines: list[RenderableType] = [Text.from_markup(server_text)]
        for tool in info.tools:
            lines.append(
                BulletColumns(
                    Text.from_markup(f"[grey50]{tool.name}[/grey50]"),
                    bullet_style="grey50",
                )
            )
        console.print(BulletColumns(Group(*lines), bullet_style=color))
