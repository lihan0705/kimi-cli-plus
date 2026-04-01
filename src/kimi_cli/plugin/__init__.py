"""Plugin loading and discovery utilities."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from kaos.path import KaosPath
from loguru import logger

from kimi_cli.share import get_share_dir
from kimi_cli.skill import Skill, parse_skill_text

if TYPE_CHECKING:
    from kimi_cli.soul.agent import Runtime
    from kimi_cli.soul.toolset import KimiToolset


@dataclass
class Plugin:
    """Information about a single plugin."""

    name: str
    dir: KaosPath
    skills: list[Skill] = field(default_factory=list[Skill])
    mcp_config_file: KaosPath | None = None
    tools_py: KaosPath | None = None
    loaded_tools: list[Any] = field(default_factory=list[Any])
    manifest: dict[str, Any] = field(default_factory=dict[str, Any])
    alias: str | None = None
    description: str | None = None

    @property
    def skill(self) -> Skill | None:
        """Legacy property for single skill access."""
        return self.skills[0] if self.skills else None


def get_user_plugin_dir() -> KaosPath:
    """Get the user-level plugin directory."""
    return KaosPath.unsafe_from_local_path(get_share_dir() / "plugins")


def get_project_plugin_dir(work_dir: KaosPath) -> KaosPath:
    """Get the project-level plugin directory."""
    return work_dir / ".kimi" / "plugins"


async def resolve_plugin_roots(work_dir: KaosPath) -> list[KaosPath]:
    """Resolve plugin roots (user and project)."""
    roots: list[KaosPath] = []

    user_dir = get_user_plugin_dir()
    if await user_dir.is_dir():
        roots.append(user_dir)

    project_dir = get_project_plugin_dir(work_dir)
    if await project_dir.is_dir():
        roots.append(project_dir)

    return roots


async def discover_plugins(plugin_roots: Iterable[KaosPath]) -> list[Plugin]:
    """Discover all plugins in the given roots."""
    plugins: list[Plugin] = []

    for root in plugin_roots:
        if not await root.is_dir():
            continue

        async for plugin_dir in root.iterdir():
            if not await plugin_dir.is_dir():
                continue

            plugin = await _load_plugin_metadata(plugin_dir)
            if plugin:
                plugins.append(plugin)

    return plugins


async def _load_plugin_metadata(plugin_dir: KaosPath) -> Plugin | None:
    """Load a single plugin's metadata from a directory."""
    name = plugin_dir.name
    skills: list[Skill] = []
    mcp_config_file = None
    tools_py = None
    manifest: dict[str, Any] = {}
    alias = None
    description = None

    # 1. Load manifest if it exists
    for manifest_name in ("manifest.json", "plugin.json"):
        manifest_file = plugin_dir / manifest_name
        if await manifest_file.is_file():
            try:
                content = await manifest_file.read_text(encoding="utf-8")
                manifest = json.loads(content)
                name = manifest.get("name", name)
                alias = manifest.get("alias")
                description = manifest.get("description")
                break
            except Exception as e:
                logger.warning("Failed to parse {} for plugin {}: {}", manifest_name, name, e)

    # Check for SKILL.md at plugin root
    skill_md = plugin_dir / "SKILL.md"
    if await skill_md.is_file():
        try:
            content = await skill_md.read_text(encoding="utf-8")
            skill = parse_skill_text(content, dir_path=plugin_dir)
            if skill:
                skills.append(skill)
        except Exception as e:
            logger.warning("Failed to parse SKILL.md for plugin {}: {}", name, e)

    # Check for skills/ subdirectory with nested skills
    skills_dir = plugin_dir / "skills"
    if await skills_dir.is_dir():
        async for skill_subdir in skills_dir.iterdir():
            if not await skill_subdir.is_dir():
                continue
            nested_skill_md = skill_subdir / "SKILL.md"
            if await nested_skill_md.is_file():
                try:
                    content = await nested_skill_md.read_text(encoding="utf-8")
                    skill = parse_skill_text(content, dir_path=skill_subdir)
                    if skill:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(
                        "Failed to parse SKILL.md for plugin {}/{}: {}", name, skill_subdir.name, e
                    )

    # Check for mcp.json
    mcp_json = plugin_dir / "mcp.json"
    if await mcp_json.is_file():
        mcp_config_file = mcp_json

    # Check for tools.py
    tools_file = plugin_dir / "tools.py"
    if await tools_file.is_file():
        tools_py = tools_file

    return Plugin(
        name=name,
        dir=plugin_dir,
        skills=skills,
        mcp_config_file=mcp_config_file,
        tools_py=tools_py,
        manifest=manifest,
        alias=alias,
        description=description,
    )


async def load_plugin_tools(plugin: Plugin, toolset: KimiToolset, runtime: Runtime):
    """Load tools from a plugin (both Python and MCP)."""
    from fastmcp.mcp_config import MCPConfig

    # 1. Load Python tools
    if plugin.tools_py:
        try:
            await _load_python_tools(plugin, toolset, runtime)
        except Exception as e:
            logger.error("Failed to load Python tools for plugin {}: {}", plugin.name, e)

    # 2. Load MCP tools
    if plugin.mcp_config_file:
        try:
            content = await plugin.mcp_config_file.read_text(encoding="utf-8")
            mcp_data = json.loads(content)
            # If it's a single server config, wrap it
            if "mcpServers" not in mcp_data:
                mcp_data = {"mcpServers": {plugin.name: mcp_data}}

            mcp_config = MCPConfig.model_validate(mcp_data)
            await toolset.load_mcp_tools([mcp_config], runtime, in_background=True)
        except Exception as e:
            logger.error("Failed to load MCP tools for plugin {}: {}", plugin.name, e)


async def _load_python_tools(plugin: Plugin, toolset: KimiToolset, runtime: Runtime):
    """Dynamically import tools.py and register tools."""
    if not plugin.tools_py:
        return

    module_name = f"kimi_plugin_{plugin.name}"
    local_path = str(plugin.tools_py.unsafe_to_local_path())

    spec = importlib.util.spec_from_file_location(module_name, local_path)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    from kosong.tooling import Tool

    from kimi_cli.soul.agent import Runtime
    from kimi_cli.soul.toolset import KimiToolset

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, Tool) and attr is not Tool:
            try:
                deps = {Runtime: runtime, KimiToolset: toolset}
                tool_instance = _instantiate_tool(attr, deps)
                if tool_instance:
                    toolset.add(tool_instance)
                    plugin.loaded_tools.append(tool_instance)
                    logger.info(
                        "Loaded Python tool {} from plugin {}", tool_instance.name, plugin.name
                    )
            except Exception as e:
                logger.warning(
                    "Failed to instantiate tool {} from plugin {}: {}", attr_name, plugin.name, e
                )


def _instantiate_tool(tool_cls: type, dependencies: dict[type[Any], Any]) -> Any:
    """Helper to instantiate a tool class with dependency injection."""
    import inspect

    args: list[Any] = []
    if "__init__" in tool_cls.__dict__:
        sig = inspect.signature(tool_cls)
        for name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                break
            if name in ("self", "args", "kwargs"):
                continue
            if param.annotation in dependencies:
                args.append(dependencies[param.annotation])
            elif param.annotation is inspect.Parameter.empty:
                continue
            else:
                logger.debug(
                    "Dependency {} not found for tool {}", param.annotation, tool_cls.__name__
                )
                return None
    return tool_cls(*args)
