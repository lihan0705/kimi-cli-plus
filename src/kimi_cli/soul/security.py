from __future__ import annotations

import enum
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from kimi_cli.acp.kaos import KaosPath


class SecurityLevel(enum.Enum):
    PASS = "pass"
    FORCE_CONFIRM = "force_confirm"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SecurityResult:
    level: SecurityLevel
    reason: str | None = None


class SecurityChecker:
    """
    Security checker for tool execution.
    Provides blacklisting for dangerous commands and sensitive paths.
    """

    # Commands that are absolutely forbidden
    BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs.*",
        "dd if=* of=/dev/*",
        "shred *",
    ]

    # Commands that require confirmation even in YOLO mode
    SENSITIVE_COMMANDS = [
        "rm -rf *",
        "sudo *",
        "chown *",
        "chmod 777 *",
        "curl * | bash",
        "wget * -O- | bash",
    ]

    # Paths that are absolutely forbidden to access
    BLOCKED_PATHS = [
        "/etc/shadow",
        "/etc/sudoers",
        "/etc/pam.d/*",
    ]

    # Paths that require confirmation even in YOLO mode
    SENSITIVE_PATHS = [
        "~/.ssh/*",
        "~/.aws/*",
        "~/.kube/*",
        "~/.bashrc",
        "~/.zshrc",
        "~/.profile",
        "~/.netrc",
        "~/.credentials/*",
        "/etc/passwd",
        "/etc/hosts",
    ]

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or KaosPath.cwd().unsafe_to_local_path()

    def is_path_safe(self, path: str | Path) -> bool:
        """
        Check if the path is within the project root.
        """
        try:
            path = Path(os.path.expanduser(str(path))).resolve()
            return self.project_root in path.parents or path == self.project_root
        except Exception:
            return False

    def check_command(self, command: str) -> SecurityResult:
        """
        Check if a command is blacklisted or sensitive.
        """
        # Clean the command for matching
        cmd = command.strip()

        # Check blocked commands
        for pattern in self.BLOCKED_COMMANDS:
            if fnmatch.fnmatch(cmd, pattern) or cmd.startswith(pattern.replace("*", "").strip()):
                return SecurityResult(
                    level=SecurityLevel.BLOCKED,
                    reason=f"Command matches blocked pattern: {pattern}",
                )

        # Check sensitive commands
        for pattern in self.SENSITIVE_COMMANDS:
            if fnmatch.fnmatch(cmd, pattern) or cmd.startswith(pattern.replace("*", "").strip()):
                return SecurityResult(
                    level=SecurityLevel.FORCE_CONFIRM,
                    reason=f"Command matches sensitive pattern: {pattern}",
                )

        return SecurityResult(level=SecurityLevel.PASS)

    def check_path(self, path_str: str) -> SecurityResult:
        """
        Check if a path is blacklisted or sensitive.
        """
        # Expand user path for checking
        try:
            expanded_path = os.path.expanduser(path_str)
        except Exception:
            expanded_path = path_str

        # Check blocked paths
        for pattern in self.BLOCKED_PATHS:
            if fnmatch.fnmatch(expanded_path, os.path.expanduser(pattern)):
                return SecurityResult(
                    level=SecurityLevel.BLOCKED,
                    reason=f"Path matches blocked pattern: {pattern}",
                )

        # Check sensitive paths
        for pattern in self.SENSITIVE_PATHS:
            if fnmatch.fnmatch(expanded_path, os.path.expanduser(pattern)):
                return SecurityResult(
                    level=SecurityLevel.FORCE_CONFIRM,
                    reason=f"Path matches sensitive pattern: {pattern}",
                )

        # Check if path is outside project root
        if not self.is_path_safe(path_str):
            # We don't block out-of-bounds access, but we might want to force confirm it
            # if it's a write operation (handled by evaluate)
            pass

        return SecurityResult(level=SecurityLevel.PASS)

    def evaluate(
        self,
        command: str | None = None,
        file_path: str | None = None,
        is_write: bool = False,
    ) -> SecurityResult:
        """
        Evaluate the security of an action.
        """
        if command:
            cmd_res = self.check_command(command)
            if cmd_res.level != SecurityLevel.PASS:
                return cmd_res

        if file_path:
            path_res = self.check_path(file_path)
            if path_res.level != SecurityLevel.PASS:
                return path_res

            # Force confirm write operations outside project root
            if is_write and not self.is_path_safe(file_path):
                return SecurityResult(
                    level=SecurityLevel.FORCE_CONFIRM,
                    reason=f"Write operation outside project root: {file_path}",
                )

        return SecurityResult(level=SecurityLevel.PASS)
