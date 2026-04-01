from __future__ import annotations

from typing import TYPE_CHECKING

from kosong.tooling import CallableTool, ToolError, ToolOk, ToolReturnValue

from kimi_cli.skill import read_skill_text

if TYPE_CHECKING:
    from kimi_cli.soul.agent import Runtime
    from kimi_cli.soul.kimisoul import KimiSoul


class SkillTool(CallableTool):
    """
    Run a skill. Skills are reusable, composable capabilities that provide
    specialized knowledge, workflow patterns, and tool integrations.
    """

    def __init__(self, runtime: Runtime, soul: KimiSoul):
        super().__init__(
            name="skill",
            description="Run a skill by name. Use this to invoke specialized capabilities.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The name of the skill to run (e.g., 'skill-creator', "
                            "'plugin:superpower:executing-plans')."
                        ),
                    },
                    "args": {
                        "type": "string",
                        "description": "Optional arguments or instructions for the skill.",
                    },
                },
                "required": ["name"],
            },
        )
        self._runtime = runtime
        self._soul = soul

    async def __call__(self, name: str, args: str = "") -> ToolReturnValue:
        # Normalize name for lookup
        lookup_name = name.lower()
        if lookup_name.startswith("skill:"):
            lookup_name = lookup_name[6:]

        skill = self._runtime.skills.get(lookup_name)

        # If not found, try to match by plugin-qualified name or alias
        if not skill:
            # Search through all skills for a name match
            for s in self._runtime.skills.values():
                if s.name.lower() == lookup_name:
                    skill = s
                    break

        # Check plugin aliases
        if not skill:
            for plugin in self._runtime.plugins:
                plugin_alias = getattr(plugin, "alias", None)
                if plugin_alias:
                    prefix = f"{plugin_alias.lower()}:"
                    if lookup_name.startswith(prefix):
                        skill_name = lookup_name[len(prefix) :]
                        for s in plugin.skills:
                            if s.name.lower() == skill_name:
                                skill = s
                                break
                if skill:
                    break

        if not skill:
            return ToolError(message=f"Skill not found: {name}", brief="")

        skill_text = await read_skill_text(skill)
        if skill_text is None:
            return ToolError(message=f"Failed to load skill text for: {name}", brief="")

        extra = args.strip()
        if extra:
            skill_text = f"{skill_text}\n\nUser request:\n{extra}"

        # To allow skill-to-skill calling, we return the instruction as the tool result,
        # so the LLM proceeds with those instructions in context.
        return ToolOk(output=f"Skill '{name}' content loaded:\n\n{skill_text}")
