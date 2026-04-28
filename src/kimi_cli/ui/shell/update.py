from __future__ import annotations

import asyncio
import os
import re
from enum import Enum, auto
from typing import Any, cast

import aiohttp

from kimi_cli.share import get_share_dir
from kimi_cli.ui.shell.console import console
from kimi_cli.utils.aiohttp import new_client_session
from kimi_cli.utils.logging import logger

DEFAULT_TAGS_API_URL = "https://api.github.com/repos/lihan0705/kimi-cli-plus/tags"
TAGS_API_URL = os.getenv("KIMI_CLI_TAGS_API_URL", DEFAULT_TAGS_API_URL)
UPGRADE_COMMAND = (
    "curl -LsSf https://raw.githubusercontent.com/lihan0705/"
    "kimi-cli-plus/main/scripts/install.sh | bash"
)


class UpdateResult(Enum):
    UPDATE_AVAILABLE = auto()
    UPDATED = auto()
    UP_TO_DATE = auto()
    FAILED = auto()
    UNSUPPORTED = auto()


_UPDATE_LOCK = asyncio.Lock()


def semver_tuple(version: str) -> tuple[int, int, int]:
    v = version.strip()
    if v.startswith("v"):
        v = v[1:]
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", v)
    if not match:
        return (0, 0, 0)
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def _normalize_tag_version(tag_name: str) -> str | None:
    name = tag_name.strip()
    if re.fullmatch(r"v?\d+\.\d+\.\d+", name):
        return name
    return None


async def _get_latest_version(session: aiohttp.ClientSession) -> str | None:
    try:
        async with session.get(TAGS_API_URL) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if not isinstance(data, list):
                return None
            versions: list[str] = []
            for item in cast(list[Any], data):
                if not isinstance(item, dict):
                    continue
                item_dict = cast(dict[str, object], item)
                tag_name = item_dict.get("name")
                if isinstance(tag_name, str):
                    normalized = _normalize_tag_version(tag_name)
                    if normalized is not None:
                        versions.append(normalized)
            if not versions:
                return None
            versions.sort(key=semver_tuple, reverse=True)
            return versions[0]
    except aiohttp.ClientError:
        logger.exception("Failed to get latest version:")
        return None


async def do_update(*, print: bool = True, check_only: bool = False) -> UpdateResult:
    async with _UPDATE_LOCK:
        return await _do_update(print=print, check_only=check_only)


LATEST_VERSION_FILE = get_share_dir() / "latest_version.txt"


async def _do_update(*, print: bool, check_only: bool) -> UpdateResult:
    from kimi_cli.constant import VERSION as current_version

    def _print(message: str) -> None:
        if print:
            console.print(message)

    async with new_client_session() as session:
        logger.info("Checking for updates...")
        _print("Checking for updates...")
        latest_version = await _get_latest_version(session)
        if not latest_version:
            logger.debug("No valid release tags found; skip update reminder.")
            return UpdateResult.UP_TO_DATE

        logger.debug("Latest version: {latest_version}", latest_version=latest_version)
        LATEST_VERSION_FILE.write_text(latest_version, encoding="utf-8")

        cur_t = semver_tuple(current_version)
        lat_t = semver_tuple(latest_version)

        if cur_t >= lat_t:
            logger.debug("Already up to date: {current_version}", current_version=current_version)
            _print("[green]Already up to date.[/green]")
            return UpdateResult.UP_TO_DATE

        if check_only:
            logger.info(
                "Update available: current={current_version}, latest={latest_version}",
                current_version=current_version,
                latest_version=latest_version,
            )
            _print(f"[yellow]Update available: {latest_version}[/yellow]")
            return UpdateResult.UPDATE_AVAILABLE

        _print("[yellow]New version found. Run:[/yellow]")
        _print(f"[bold]{UPGRADE_COMMAND}[/bold]")
        return UpdateResult.UPDATE_AVAILABLE


# @meta_command
# async def update(app: "Shell", args: list[str]):
#     """Check for updates"""
#     await do_update(print=True)


# @meta_command(name="check-update")
# async def check_update(app: "Shell", args: list[str]):
#     """Check for updates"""
#     await do_update(print=True, check_only=True)
