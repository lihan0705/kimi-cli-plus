from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from kimi_cli.utils.io import atomic_json_write
from kimi_cli.utils.logging import logger

# Directories to exclude from checkpoints regardless of .gitignore
EXCLUDED_DIRS = {
    ".git",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "cache",
    "dist",
    "node_modules",
    "target",
    "venv",
}


@dataclass(frozen=True, slots=True)
class WorkspaceCheckpoint:
    conversation_checkpoint_id: int
    snapshot_id: str  # This will store the Git commit hash
    reason: str
    created_at: float


@dataclass(frozen=True, slots=True)
class RestorePreview:
    conversation_checkpoint_id: int
    changed_files: list[str]


class WorkspaceCheckpointStore:
    def __init__(self, *, session_dir: Path, work_dir: Path) -> None:
        self._session_dir = session_dir
        self._work_dir = work_dir
        self._root = session_dir / "workspace-checkpoints"
        self._git_dir = self._root / "shadow_git"
        self._index_file = self._root / "index.json"

        self._ensure_git_repo()

    def _ensure_git_repo(self) -> None:
        if not self._git_dir.exists():
            self._git_dir.mkdir(parents=True, exist_ok=True)
            self._run_git(["init"])
            # Configure git to be quiet and isolated
            self._run_git(["config", "user.name", "Kimi Checkpoint"])
            self._run_git(["config", "user.email", "checkpoint@kimi.ai"])
            self._run_git(["config", "core.autocrlf", "false"])
            self._run_git(["config", "gc.auto", "0"])  # Disable auto GC to keep it fast

        # Update exclude patterns
        exclude_file = self._git_dir / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        exclude_file.write_text("\n".join(EXCLUDED_DIRS) + "\n", encoding="utf-8")

    def _run_git(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GIT_DIR"] = str(self._git_dir)
        env["GIT_WORK_TREE"] = str(self._work_dir)
        # Use a custom index file to avoid locking issues with the project's own git
        env["GIT_INDEX_FILE"] = str(self._git_dir / "index")

        try:
            return subprocess.run(
                ["git", *args],
                env=env,
                cwd=str(self._work_dir),
                capture_output=True,
                text=True,
                check=check,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e.cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}")
            raise

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self._index_file.exists():
            return {}
        with self._index_file.open(encoding="utf-8") as f:
            return cast(dict[str, dict[str, Any]], json.load(f))

    def _save_index(self, index: dict[str, dict[str, Any]]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        atomic_json_write(index, self._index_file)

    def get(self, conversation_checkpoint_id: int) -> WorkspaceCheckpoint | None:
        raw = self._load_index().get(str(conversation_checkpoint_id))
        if raw is None:
            return None
        return WorkspaceCheckpoint(
            conversation_checkpoint_id=int(raw["conversation_checkpoint_id"]),
            snapshot_id=str(raw["snapshot_id"]),
            reason=str(raw["reason"]),
            created_at=float(raw["created_at"]),
        )

    def create_once(self, conversation_checkpoint_id: int, *, reason: str) -> WorkspaceCheckpoint:
        existing = self.get(conversation_checkpoint_id)
        if existing is not None:
            return existing

        # 1. Stage all changes
        self._run_git(["add", "-A"])

        # 2. Commit changes
        msg = f"Checkpoint {conversation_checkpoint_id}: {reason}"
        self._run_git(["commit", "--allow-empty", "-m", msg])

        # 3. Get commit hash
        commit_hash = self._run_git(["rev-parse", "HEAD"]).stdout.strip()

        checkpoint = WorkspaceCheckpoint(
            conversation_checkpoint_id=conversation_checkpoint_id,
            snapshot_id=commit_hash,
            reason=reason,
            created_at=time.time(),
        )
        index = self._load_index()
        index[str(conversation_checkpoint_id)] = asdict(checkpoint)
        self._save_index(index)
        return checkpoint

    def _is_git_object(self, object_id: str) -> bool:
        """Check if the given ID is a valid git object in the shadow repo."""
        if not object_id:
            return False
        try:
            # rev-parse returns 0 if the object exists
            self._run_git(["rev-parse", "--verify", f"{object_id}^{{commit}}"], check=True)
            return True
        except Exception:
            return False

    def get_change_count(
        self, conversation_checkpoint_id: int, base_checkpoint_id: int | None = None
    ) -> int | None:
        """Get the number of files changed between two checkpoints."""
        index = self._load_index()
        current = index.get(str(conversation_checkpoint_id))
        if current is None:
            return None

        current_hash = current["snapshot_id"]
        if not self._is_git_object(current_hash):
            return None

        if base_checkpoint_id is not None:
            base = index.get(str(base_checkpoint_id))
            if base is not None and self._is_git_object(base["snapshot_id"]):
                base_hash = base["snapshot_id"]
            else:
                # If base is specified but invalid, compare against empty tree
                base_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        else:
            # Auto-find predecessor in index
            sorted_ids = sorted([int(k) for k in index.keys()])
            try:
                idx = sorted_ids.index(conversation_checkpoint_id)
                if idx == 0:
                    base_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # Git empty tree hash
                else:
                    prev_id = sorted_ids[idx - 1]
                    base_hash = index[str(prev_id)]["snapshot_id"]
                    if not self._is_git_object(base_hash):
                        return None
            except (ValueError, IndexError):
                return None

        if current_hash == base_hash:
            return 0

        # Run git diff --shortstat
        try:
            result = self._run_git(["diff", "--shortstat", base_hash, current_hash])
            output = result.stdout.strip()
            if not output:
                return 0
            # Extract the number of files changed (e.g., " 3 files changed, ...")
            return int(output.split("file")[0].strip())
        except Exception:
            return 0

    def preview_restore(self, conversation_checkpoint_id: int) -> RestorePreview:
        checkpoint = self.get(conversation_checkpoint_id)
        if checkpoint is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        target_hash = checkpoint.snapshot_id

        # Get diff status between current worktree and target commit
        # We need to add all files first to see untracked files in diff
        self._run_git(["add", "-A"])
        result = self._run_git(["diff", "--name-status", "HEAD", target_hash])

        changed_files: list[str] = []
        for line in result.stdout.splitlines():
            if line.strip():
                status, path = line.split(None, 1)
                changed_files.append(f"{status} {path}")

        return RestorePreview(
            conversation_checkpoint_id=conversation_checkpoint_id,
            changed_files=sorted(changed_files),
        )

    def restore(self, conversation_checkpoint_id: int) -> None:
        checkpoint = self.get(conversation_checkpoint_id)
        if checkpoint is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        target_hash = checkpoint.snapshot_id

        # 1. Take a safety snapshot of current state before restoring
        self.create_once(999999, reason=f"Pre-restore safety for CP {conversation_checkpoint_id}")

        # 2. Restore files from target commit to worktree
        # We use checkout here as it is more widely compatible than 'git restore'
        self._run_git(["checkout", target_hash, "--", "."])

        # 3. Clean untracked files that were not in the snapshot
        # (This makes it a true 'restore' to the exact state)
        self._run_git(["clean", "-fd"])

        logger.info(f"Restored workspace to checkpoint {conversation_checkpoint_id} ({target_hash})")
