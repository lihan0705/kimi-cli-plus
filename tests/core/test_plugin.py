"""Tests for plugin discovery and skill registration."""

from __future__ import annotations

from pathlib import Path

import pytest
from kaos.path import KaosPath
from kosong.tooling.empty import EmptyToolset

from kimi_cli.plugin import Plugin, _load_plugin_metadata, discover_plugins
from kimi_cli.skill import Skill
from kimi_cli.soul.agent import Agent, Runtime
from kimi_cli.soul.context import Context
from kimi_cli.soul.kimisoul import KimiSoul


def _write_skill(skill_dir: Path, content: str) -> None:
    """Helper to write a SKILL.md file."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


# =============================================================================
# Plugin Discovery Tests
# =============================================================================


@pytest.mark.asyncio
async def test_load_plugin_metadata_discovers_root_skill(tmp_path: Path) -> None:
    """Test that a SKILL.md at plugin root is discovered."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()
    _write_skill(
        plugin_dir,
        """---
name: root-skill
description: Skill at plugin root
---
""",
    )

    plugin = await _load_plugin_metadata(KaosPath.unsafe_from_local_path(plugin_dir))

    assert plugin is not None
    assert plugin.name == "test-plugin"
    assert len(plugin.skills) == 1
    assert plugin.skills[0].name == "root-skill"


@pytest.mark.asyncio
async def test_load_plugin_metadata_discovers_nested_skills(tmp_path: Path) -> None:
    """Test that skills in skills/ subdirectory are discovered."""
    plugin_dir = tmp_path / "test-plugin"
    skills_dir = plugin_dir / "skills"

    _write_skill(
        skills_dir / "skill-one",
        """---
name: skill-one
description: First nested skill
---
""",
    )
    _write_skill(
        skills_dir / "skill-two",
        """---
name: skill-two
description: Second nested skill
---
""",
    )

    plugin = await _load_plugin_metadata(KaosPath.unsafe_from_local_path(plugin_dir))

    assert plugin is not None
    assert len(plugin.skills) == 2
    skill_names = {s.name for s in plugin.skills}
    assert skill_names == {"skill-one", "skill-two"}


@pytest.mark.asyncio
async def test_load_plugin_metadata_discovers_both_root_and_nested(tmp_path: Path) -> None:
    """Test that both root SKILL.md and nested skills are discovered."""
    plugin_dir = tmp_path / "test-plugin"
    skills_dir = plugin_dir / "skills"

    # Root skill
    _write_skill(
        plugin_dir,
        """---
name: root-skill
description: Root level skill
---
""",
    )
    # Nested skill
    _write_skill(
        skills_dir / "nested-skill",
        """---
name: nested-skill
description: Nested skill
---
""",
    )

    plugin = await _load_plugin_metadata(KaosPath.unsafe_from_local_path(plugin_dir))

    assert plugin is not None
    assert len(plugin.skills) == 2
    skill_names = {s.name for s in plugin.skills}
    assert skill_names == {"root-skill", "nested-skill"}


@pytest.mark.asyncio
async def test_load_plugin_metadata_handles_mcp_and_tools(tmp_path: Path) -> None:
    """Test that mcp.json and tools.py are detected."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()

    # Create mcp.json
    (plugin_dir / "mcp.json").write_text('{"command": "test"}', encoding="utf-8")

    # Create tools.py
    (plugin_dir / "tools.py").write_text("# Tools", encoding="utf-8")

    plugin = await _load_plugin_metadata(KaosPath.unsafe_from_local_path(plugin_dir))

    assert plugin is not None
    assert plugin.mcp_config_file is not None
    assert plugin.tools_py is not None


@pytest.mark.asyncio
async def test_discover_plugins_from_multiple_roots(tmp_path: Path) -> None:
    """Test discovering plugins from multiple root directories."""
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"

    # Plugin in root1
    plugin1_dir = root1 / "plugin-one"
    _write_skill(
        plugin1_dir,
        """---
name: skill-one
description: Plugin one skill
---
""",
    )

    # Plugin in root2
    plugin2_dir = root2 / "plugin-two"
    _write_skill(
        plugin2_dir,
        """---
name: skill-two
description: Plugin two skill
---
""",
    )

    plugins = await discover_plugins(
        [
            KaosPath.unsafe_from_local_path(root1),
            KaosPath.unsafe_from_local_path(root2),
        ]
    )

    assert len(plugins) == 2
    plugin_names = {p.name for p in plugins}
    assert plugin_names == {"plugin-one", "plugin-two"}


# =============================================================================
# Plugin Skill Registration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_plugin_skills_register_with_hierarchical_prefix(
    runtime: Runtime, tmp_path: Path
) -> None:
    """Test that plugin skills are registered as /plugin:<plugin>:<skill>."""
    # Create a plugin with a skill
    plugin_skill_dir = tmp_path / "test-plugin" / "skills" / "test-skill"
    _write_skill(
        plugin_skill_dir,
        """---
name: test-skill
description: A test skill
---
""",
    )

    plugin = Plugin(
        name="test-plugin",
        dir=KaosPath.unsafe_from_local_path(tmp_path / "test-plugin"),
    )
    plugin.skills = [
        Skill(
            name="test-skill",
            description="A test skill",
            type="standard",
            dir=KaosPath.unsafe_from_local_path(plugin_skill_dir),
        )
    ]

    runtime.plugins = [plugin]
    runtime.skills = {plugin.skills[0].name: plugin.skills[0]}

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = KimiSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    command_names = {cmd.name for cmd in soul.available_slash_commands}

    # Plugin skill should be registered with hierarchical prefix
    assert "plugin:test-plugin:test-skill" in command_names
    # Case-insensitive version should also be registered
    assert "plugin:test-plugin:test-skill".lower() in command_names


@pytest.mark.asyncio
async def test_plugin_skills_do_not_register_as_skill_prefix(
    runtime: Runtime, tmp_path: Path
) -> None:
    """Test that plugin skills are NOT registered as /skill:<name>."""
    plugin_skill_dir = tmp_path / "test-plugin" / "skills" / "unique-skill"
    _write_skill(
        plugin_skill_dir,
        """---
name: unique-skill
description: A unique skill
---
""",
    )

    plugin = Plugin(
        name="test-plugin",
        dir=KaosPath.unsafe_from_local_path(tmp_path / "test-plugin"),
    )
    plugin.skills = [
        Skill(
            name="unique-skill",
            description="A unique skill",
            type="standard",
            dir=KaosPath.unsafe_from_local_path(plugin_skill_dir),
        )
    ]

    runtime.plugins = [plugin]
    runtime.skills = {plugin.skills[0].name: plugin.skills[0]}

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = KimiSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    command_names = {cmd.name for cmd in soul.available_slash_commands}

    # Plugin skill should NOT be registered as /skill:
    assert "skill:unique-skill" not in command_names


# =============================================================================
# Regular Skill Registration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_regular_skills_register_with_skill_prefix(runtime: Runtime, tmp_path: Path) -> None:
    """Test that regular (non-plugin) skills are registered as /skill:<name>."""
    skill_dir = tmp_path / "regular-skill"
    _write_skill(
        skill_dir,
        """---
name: regular-skill
description: A regular skill
---
""",
    )

    skill = Skill(
        name="regular-skill",
        description="A regular skill",
        type="standard",
        dir=KaosPath.unsafe_from_local_path(skill_dir),
    )

    runtime.skills = {"regular-skill": skill}
    runtime.plugins = []  # No plugins

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = KimiSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    command_names = {cmd.name for cmd in soul.available_slash_commands}

    # Regular skill should be registered with /skill: prefix
    assert "skill:regular-skill" in command_names


@pytest.mark.asyncio
async def test_regular_skills_do_not_register_with_superpower_prefix(
    runtime: Runtime, tmp_path: Path
) -> None:
    """Test that regular skills are NOT registered as /superpower:<name>."""
    skill_dir = tmp_path / "regular-skill"
    _write_skill(
        skill_dir,
        """---
name: regular-skill
description: A regular skill
---
""",
    )

    skill = Skill(
        name="regular-skill",
        description="A regular skill",
        type="standard",
        dir=KaosPath.unsafe_from_local_path(skill_dir),
    )

    runtime.skills = {"regular-skill": skill}
    runtime.plugins = []  # No plugins

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = KimiSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    command_names = {cmd.name for cmd in soul.available_slash_commands}

    # Regular skill should NOT be registered with /superpower: prefix
    assert "superpower:regular-skill" not in command_names


# =============================================================================
# Plugin vs Regular Skill Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_plugin_and_regular_skills_with_different_names(
    runtime: Runtime, tmp_path: Path
) -> None:
    """Test that plugin skills and regular skills with different names both work."""
    # Regular skill
    regular_skill_dir = tmp_path / "skills" / "regular-skill"
    _write_skill(
        regular_skill_dir,
        """---
name: regular-skill
description: A regular skill
---
""",
    )

    # Plugin skill with different name
    plugin_skill_dir = tmp_path / "test-plugin" / "skills" / "plugin-skill"
    _write_skill(
        plugin_skill_dir,
        """---
name: plugin-skill
description: A plugin skill
---
""",
    )

    regular_skill = Skill(
        name="regular-skill",
        description="A regular skill",
        type="standard",
        dir=KaosPath.unsafe_from_local_path(regular_skill_dir),
    )

    plugin = Plugin(
        name="test-plugin",
        dir=KaosPath.unsafe_from_local_path(tmp_path / "test-plugin"),
    )
    plugin.skills = [
        Skill(
            name="plugin-skill",
            description="A plugin skill",
            type="standard",
            dir=KaosPath.unsafe_from_local_path(plugin_skill_dir),
        )
    ]

    runtime.skills = {"regular-skill": regular_skill, "plugin-skill": plugin.skills[0]}
    runtime.plugins = [plugin]

    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = KimiSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    command_names = {cmd.name for cmd in soul.available_slash_commands}

    # Plugin skill should use hierarchical prefix
    assert "plugin:test-plugin:plugin-skill" in command_names
    # Regular skill should use /skill: prefix
    assert "skill:regular-skill" in command_names
    # No /superpower: prefix should exist
    assert "superpower:regular-skill" not in command_names
    assert "superpower:plugin-skill" not in command_names


# =============================================================================
# Plugin.skills Property Tests
# =============================================================================


def test_plugin_skill_property_returns_first_skill() -> None:
    """Test that Plugin.skill property returns the first skill for backward compatibility."""
    plugin = Plugin(
        name="test-plugin",
        dir=KaosPath.unsafe_from_local_path(Path("/tmp/test")),
    )

    skill1 = Skill(name="skill1", description="First", type="standard", dir=KaosPath("/tmp/1"))
    skill2 = Skill(name="skill2", description="Second", type="standard", dir=KaosPath("/tmp/2"))

    plugin.skills = [skill1, skill2]

    assert plugin.skill == skill1


def test_plugin_skill_property_returns_none_when_no_skills() -> None:
    """Test that Plugin.skill property returns None when no skills exist."""
    plugin = Plugin(
        name="test-plugin",
        dir=KaosPath.unsafe_from_local_path(Path("/tmp/test")),
    )

    plugin.skills = []

    assert plugin.skill is None
