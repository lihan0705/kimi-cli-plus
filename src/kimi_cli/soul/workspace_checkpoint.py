"""Workspace checkpoint store — transparent filesystem snapshots via shadow git repos.

Creates automatic snapshots of the working directory before file-mutating
operations, triggered once per conversation turn.  Provides rollback to any
previous checkpoint.

This is NOT a tool — the LLM never sees it.  It is transparent infrastructure.

Architecture:
    <session_dir>/workspace-checkpoints/shadow_git/   — shadow git repo
        HEAD, refs/, objects/                          — standard git internals
        info/exclude                                   — default excludes
    <session_dir>/workspace-checkpoints/index.json     — checkpoint_id -> commit_hash map

The shadow repo uses GIT_DIR + GIT_WORK_TREE so no git state leaks
into the user's project directory.

Inspired by Hermes Agent's CheckpointManager design.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from kimi_cli.utils.io import atomic_json_write
from kimi_cli.utils.logging import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDES = [
    "node_modules/",
    "dist/",
    "build/",
    ".env",
    ".env.*",
    ".env.local",
    ".env.*.local",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*.log",
    ".cache/",
    ".next/",
    ".nuxt/",
    "coverage/",
    ".pytest_cache/",
    ".venv/",
    "venv/",
    ".venv312/",
    ".git/",
    ".mypy_cache/",
    ".ruff_cache/",
    "cache/",
    "target/",
    # Model / data caches that can be very large
    "cache_model/",
    "cache_tokenizer/",
    "models/",
    "checkpoints/",
    "data/",
    "datasets/",
    # Common binary/media dirs
    "*.egg-info/",
    "*.whl",
    "*.tar.gz",
    "*.zip",
    # Large framework dirs
    "bisheng/",
    ".tox/",
    ".nox/",
    ".pants.d/",
    ".pdm-python",
    ".pixi/",
    # IDE and editor dirs
    ".idea/",
    ".vscode/",
    # Image files that shouldn't be in checkpoints
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.bmp",
    "*.svg",
    "*.ico",
    "*.webp",
    # Large binary files
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.parquet",
    "*.npy",
    "*.npz",
    "*.pkl",
    "*.pickle",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.bin",
    "*.safetensors",
    "*.h5",
    "*.hdf5",
]

# Git subprocess timeout (seconds).
_GIT_TIMEOUT: int = max(30, min(120, int(os.getenv("KIMI_CHECKPOINT_TIMEOUT", "60"))))

# Dir names to skip during file counting (extracted from DEFAULT_EXCLUDES for os.walk).
_EXCLUDED_DIR_NAMES = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        ".venv312",
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        "cache",
        "target",
        "cache_model",
        "cache_tokenizer",
        "models",
        "checkpoints",
        "data",
        "datasets",
        "bisheng",
        ".tox",
        ".nox",
        ".pants.d",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        "coverage",
        ".cache",
        "*.egg-info",
    }
)

# Max files to snapshot — skip huge directories to avoid slowdowns.
_MAX_FILES = 50_000

# Valid git commit hash pattern: 4–64 hex chars.
_COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")

# Git empty tree hash — used as base for first commit diff.
_GIT_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _validate_commit_hash(commit_hash: str) -> str | None:
    """Validate a commit hash to prevent git argument injection.

    Returns an error string if invalid, None if valid.
    """
    if not commit_hash or not commit_hash.strip():
        return "Empty commit hash"
    if commit_hash.startswith("-"):
        return f"Invalid commit hash (must not start with '-'): {commit_hash!r}"
    if not _COMMIT_HASH_RE.match(commit_hash):
        return f"Invalid commit hash (expected 4-64 hex characters): {commit_hash!r}"
    return None


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CheckpointInfo:
    """A single checkpoint entry from git log."""

    commit_hash: str
    short_hash: str
    conversation_checkpoint_id: int | None
    timestamp: str
    reason: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


# ---------------------------------------------------------------------------
# WorkspaceCheckpointStore
# ---------------------------------------------------------------------------


class WorkspaceCheckpointStore:
    """Manages automatic filesystem checkpoints via a shadow git repo.

    Designed to be owned by ``Runtime``.  Call ``new_turn()`` at the start of
    each conversation turn and ``ensure_checkpoint()`` before any file-mutating
    tool call.  The manager deduplicates so at most one snapshot is taken per turn.
    """

    def __init__(self, *, session_dir: Path, work_dir: Path) -> None:
        self._session_dir = session_dir
        self._work_dir = work_dir
        self._git_dir = session_dir / "workspace-checkpoints" / "shadow_git"
        self._index_file = session_dir / "workspace-checkpoints" / "index.json"
        self._checkpointed_this_turn: bool = False
        self._git_available: bool | None = None  # lazy probe

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------

    def new_turn(self) -> None:
        """Reset per-turn dedup.  Call at the start of each agent turn."""
        self._checkpointed_this_turn = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_checkpoint(self, conversation_checkpoint_id: int, *, reason: str = "auto") -> bool:
        """Take a checkpoint if not already done this turn.

        Returns True if a checkpoint was taken, False otherwise.
        Never raises — all errors are silently logged.
        """
        # Already checkpointed this turn?
        if self._checkpointed_this_turn:
            return False

        # Lazy git probe
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
            if not self._git_available:
                logger.debug("Checkpoints disabled: git not found")
        if not self._git_available:
            return False

        # Quick size guard
        if self._dir_file_count(str(self._work_dir)) > _MAX_FILES:
            logger.debug("Checkpoint skipped: >{} files in {}", _MAX_FILES, self._work_dir)
            return False

        self._checkpointed_this_turn = True

        try:
            return self._take(conversation_checkpoint_id, reason)
        except Exception as e:
            logger.debug("Checkpoint failed (non-fatal): {}", e)
            return False

    def get(self, conversation_checkpoint_id: int) -> str | None:
        """Return the commit hash for a conversation checkpoint, or None."""
        index = self._load_index()
        return index.get(str(conversation_checkpoint_id))

    def find_restore_checkpoint_id(self, conversation_checkpoint_id: int) -> int | None:
        """Find the workspace checkpoint that represents this conversation point.

        Workspace checkpoints are created lazily before tools mutate files. If a
        conversation-only checkpoint has no workspace snapshot, the next workspace
        checkpoint is the first snapshot that still represents the selected point
        in time.
        """
        checkpoint_ids = sorted(int(k) for k in self._load_index())
        for cid in checkpoint_ids:
            if cid >= conversation_checkpoint_id:
                return cid
        return None

    def list_checkpoints(self) -> list[CheckpointInfo]:
        """List available checkpoints from git log.  Most recent first."""
        if not self._git_dir.exists():
            return []

        result = self._run_git(
            ["log", "--format=%H|%h|%aI|%s", "-n", "50"],
            allowed_returncodes={128},
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        results: list[CheckpointInfo] = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            commit_hash, short_hash, timestamp, reason = parts
            # Parse conversation checkpoint ID from commit message
            conv_id: int | None = None
            m = re.match(r"Checkpoint (\d+):", reason)
            if m:
                conv_id = int(m.group(1))

            entry = CheckpointInfo(
                commit_hash=commit_hash,
                short_hash=short_hash,
                conversation_checkpoint_id=conv_id,
                timestamp=timestamp,
                reason=reason,
                files_changed=0,
                insertions=0,
                deletions=0,
            )
            # Get diffstat for this commit
            stat_result = self._run_git(
                ["diff", "--shortstat", f"{commit_hash}~1", commit_hash],
                allowed_returncodes={128, 129},  # first commit has no parent
            )
            if stat_result.returncode == 0 and stat_result.stdout.strip():
                self._parse_shortstat(stat_result.stdout.strip(), entry)
            results.append(entry)
        return results

    def get_change_count(
        self, conversation_checkpoint_id: int, base_checkpoint_id: int | None = None
    ) -> int | None:
        """Get the number of files changed between two checkpoints."""
        index = self._load_index()
        current_hash = index.get(str(conversation_checkpoint_id))
        if current_hash is None:
            return None

        if not self._is_git_object(current_hash):
            return None

        if base_checkpoint_id is not None:
            base_hash = index.get(str(base_checkpoint_id))
            if base_hash is not None and self._is_git_object(base_hash):
                pass  # base_hash is set
            else:
                base_hash = _GIT_EMPTY_TREE
        else:
            # Auto-find predecessor in index
            sorted_ids = sorted(int(k) for k in index)
            try:
                idx = sorted_ids.index(conversation_checkpoint_id)
                if idx == 0:
                    base_hash = _GIT_EMPTY_TREE
                else:
                    prev_id = sorted_ids[idx - 1]
                    base_hash = index[str(prev_id)]
                    if not self._is_git_object(base_hash):
                        return None
            except (ValueError, IndexError):
                return None

        if current_hash == base_hash:
            return 0

        try:
            result = self._run_git(["diff", "--shortstat", base_hash, current_hash])
            output = result.stdout.strip()
            if not output:
                return 0
            return int(output.split("file")[0].strip())
        except Exception:
            return 0

    def preview_restore(self, conversation_checkpoint_id: int) -> list[str]:
        """Preview which files would change on restore.

        Returns a list of ``"STATUS path"`` strings.
        Side-effect free: stages, diffs, then unstages.
        """
        commit_hash = self.get(conversation_checkpoint_id)
        if commit_hash is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            raise ValueError(hash_err)

        self._ensure_git_repo()

        # Stage current state to see untracked files in diff
        self._run_git(["add", "-A"])
        result = self._run_git(["diff", "--cached", "--name-status", commit_hash])

        # Unstage to avoid polluting the shadow repo index
        self._run_git(["reset", "HEAD", "--quiet"], allowed_returncodes={1})

        changed_files: list[str] = []
        for line in result.stdout.splitlines():
            if line.strip():
                changed_files.append(line.strip())
        return sorted(changed_files)

    def restore(self, conversation_checkpoint_id: int) -> None:
        """Restore workspace to a checkpoint state using ``git checkout`` + file removal.

        Uses ``git checkout <hash> -- .`` which restores tracked files
        without moving HEAD.  Then finds and deletes files that exist in
        the current state but not in the target commit (i.e. files added
        after the checkpoint).

        Before restoring, takes a safety commit of the current state
        (so you can undo the undo).
        """
        commit_hash = self.get(conversation_checkpoint_id)
        if commit_hash is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            raise ValueError(hash_err)

        self._ensure_git_repo()

        # Verify the commit exists
        if not self._is_git_object(commit_hash):
            raise ValueError(f"Checkpoint commit '{commit_hash}' not found in shadow repo")

        # 1. Take a safety commit of current state before restoring
        self._take(-1, f"pre-rollback snapshot (restoring to {commit_hash[:8]})")

        # 2. Stage current state to get a full picture in the index
        self._run_git(["add", "-A"], timeout=_GIT_TIMEOUT * 2)

        # 3. Find files that exist now but NOT in the target commit (to be deleted)
        #    diff from target to index: lines starting with "D" in reverse
        #    or simply: files in index but not in commit → we need to remove them from worktree.
        diff_result = self._run_git(
            ["diff", "--name-only", commit_hash, "--cached"],
        )
        files_to_delete: list[Path] = []
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            # Files listed are those that differ between commit and index.
            # We need files that are NEW (in index but not in commit).
            # Use --diff-filter=A to find only added files.
            added_result = self._run_git(
                ["diff", "--name-only", "--diff-filter=A", commit_hash, "--cached"],
            )
            if added_result.returncode == 0 and added_result.stdout.strip():
                for line in added_result.stdout.splitlines():
                    if line.strip():
                        files_to_delete.append(self._work_dir / line.strip())

        # 4. Restore files from target commit to worktree (does not move HEAD)
        result = self._run_git(
            ["checkout", commit_hash, "--", "."],
            timeout=_GIT_TIMEOUT * 2,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Restore failed: {result.stderr.strip()}")

        # 5. Delete files that were added after the checkpoint
        for fpath in files_to_delete:
            try:
                if fpath.is_file() or fpath.is_symlink():
                    fpath.unlink()
            except OSError as e:
                logger.debug("Failed to delete file during restore: {} ({})", fpath, e)

        # 6. Reset shadow repo index to target commit for consistency, without
        # moving HEAD.  Using pathspec form keeps commit history intact
        # (including the pre-rollback safety commit).
        self._run_git(["reset", "--quiet", commit_hash, "--", "."], allowed_returncodes={1})

        logger.info(
            "Restored workspace to checkpoint {} ({}) — {} file(s) removed",
            conversation_checkpoint_id,
            commit_hash[:8],
            len(files_to_delete),
        )

    # ------------------------------------------------------------------
    # Internal — git helpers
    # ------------------------------------------------------------------

    def _ensure_git_repo(self) -> None:
        """Initialize shadow git repo if needed."""
        if (self._git_dir / "HEAD").exists():
            return

        self._git_dir.mkdir(parents=True, exist_ok=True)
        self._run_git(["init"])
        self._run_git(["config", "user.email", "checkpoint@kimi.ai"])
        self._run_git(["config", "user.name", "Kimi Checkpoint"])
        self._run_git(["config", "core.autocrlf", "false"])
        self._run_git(["config", "gc.auto", "0"])

        # Write exclude patterns
        info_dir = self._git_dir / "info"
        info_dir.mkdir(exist_ok=True)
        (info_dir / "exclude").write_text("\n".join(DEFAULT_EXCLUDES) + "\n", encoding="utf-8")

        logger.debug("Initialised checkpoint repo at {} for {}", self._git_dir, self._work_dir)

    def _run_git(
        self,
        args: list[str],
        *,
        timeout: int = _GIT_TIMEOUT,
        allowed_returncodes: set[int] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command against the shadow repo."""
        env = os.environ.copy()
        env["GIT_DIR"] = str(self._git_dir)
        env["GIT_WORK_TREE"] = str(self._work_dir)
        env["GIT_INDEX_FILE"] = str(self._git_dir / "index")
        # Clear potentially conflicting env vars
        env.pop("GIT_NAMESPACE", None)
        env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)

        allowed_returncodes = allowed_returncodes or set()
        try:
            result = subprocess.run(
                ["git", *args],
                env=env,
                cwd=str(self._work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
            ok = result.returncode == 0
            if not ok and result.returncode not in allowed_returncodes:
                logger.error(
                    "Git command failed: {} (rc={}) stderr={}",
                    " ".join(["git"] + args),
                    result.returncode,
                    result.stderr.strip(),
                )
            return result
        except subprocess.TimeoutExpired:
            logger.error("Git timed out after {}s: {}", timeout, " ".join(args))
            raise
        except FileNotFoundError as exc:
            if getattr(exc, "filename", None) == "git":
                logger.error("Git executable not found")
            raise

    def _is_git_object(self, object_id: str) -> bool:
        """Check if the given ID is a valid git object in the shadow repo."""
        if not object_id:
            return False
        try:
            result = self._run_git(
                ["rev-parse", "--verify", f"{object_id}^{{commit}}"],
                allowed_returncodes={128},
            )
            return result.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal — snapshot
    # ------------------------------------------------------------------

    def _take(self, conversation_checkpoint_id: int, reason: str) -> bool:
        """Take a snapshot.  Returns True on success."""
        self._ensure_git_repo()

        # Stage everything
        result = self._run_git(["add", "-A"], timeout=_GIT_TIMEOUT * 2)
        if result.returncode != 0:
            logger.debug("Checkpoint git-add failed: {}", result.stderr.strip())
            return False

        # Check if there's anything to commit
        diff_result = self._run_git(
            ["diff", "--cached", "--quiet"],
            allowed_returncodes={1},
        )

        # Check if repo has any commits at all
        head_result = self._run_git(["rev-parse", "HEAD"], allowed_returncodes={128})
        has_head = head_result.returncode == 0

        if diff_result.returncode == 0:
            if not has_head:
                # No staged changes and no prior commit — create an empty initial commit
                # so we have a HEAD to reference for this checkpoint ID.
                msg = f"Checkpoint {conversation_checkpoint_id}: {reason} (empty)"
                result = self._run_git(
                    ["commit", "--allow-empty", "-m", msg],
                    timeout=_GIT_TIMEOUT * 2,
                )
                if result.returncode != 0:
                    logger.debug("Empty initial commit failed: {}", result.stderr.strip())
                    return False
                hash_result = self._run_git(["rev-parse", "HEAD"])
                if hash_result.returncode != 0:
                    return False
                if conversation_checkpoint_id >= 0:
                    index = self._load_index()
                    index[str(conversation_checkpoint_id)] = hash_result.stdout.strip()
                    self._save_index(index)
                logger.debug(
                    "Created empty initial commit for checkpoint {}", conversation_checkpoint_id
                )
                return True

            # No changes to commit — record current HEAD for this checkpoint ID
            # so the tree UI can compute file-change counts between checkpoints.
            if conversation_checkpoint_id >= 0:
                commit_hash = head_result.stdout.strip()
                index = self._load_index()
                index[str(conversation_checkpoint_id)] = commit_hash
                self._save_index(index)
            logger.debug(
                "Checkpoint recorded HEAD (no file changes) for checkpoint {}",
                conversation_checkpoint_id,
            )
            return True

        # Commit
        msg = f"Checkpoint {conversation_checkpoint_id}: {reason}"
        result = self._run_git(
            ["commit", "-m", msg, "--allow-empty-message"],
            timeout=_GIT_TIMEOUT * 2,
        )
        if result.returncode != 0:
            logger.debug("Checkpoint commit failed: {}", result.stderr.strip())
            return False

        # Get commit hash and update index
        hash_result = self._run_git(["rev-parse", "HEAD"])
        if hash_result.returncode != 0:
            return False
        commit_hash = hash_result.stdout.strip()

        # Only store real checkpoints (not pre-rollback with id=-1) in index
        if conversation_checkpoint_id >= 0:
            index = self._load_index()
            index[str(conversation_checkpoint_id)] = commit_hash
            self._save_index(index)

        logger.debug("Checkpoint taken: {} ({} {})", msg, commit_hash[:8], reason)
        return True

    # ------------------------------------------------------------------
    # Internal — index
    # ------------------------------------------------------------------

    def _load_index(self) -> dict[str, str]:
        """Load the checkpoint_id -> commit_hash index."""
        if not self._index_file.exists():
            return {}
        with self._index_file.open(encoding="utf-8") as f:
            return cast(dict[str, str], json.load(f))

    def _save_index(self, index: dict[str, str]) -> None:
        """Save the checkpoint_id -> commit_hash index."""
        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(index, self._index_file)

    # ------------------------------------------------------------------
    # Internal — utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_shortstat(stat_line: str, entry: CheckpointInfo) -> None:
        """Parse git --shortstat output into entry (mutates in-place)."""
        m = re.search(r"(\d+) file", stat_line)
        if m:
            entry.files_changed = int(m.group(1))
        m = re.search(r"(\d+) insertion", stat_line)
        if m:
            entry.insertions = int(m.group(1))
        m = re.search(r"(\d+) deletion", stat_line)
        if m:
            entry.deletions = int(m.group(1))

    @staticmethod
    def _dir_file_count(path: str) -> int:
        """Quick file count estimate, respecting exclude dirs (stops early if over _MAX_FILES)."""
        count = 0
        try:
            for _current_root, dirs, filenames in os.walk(path):
                dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIR_NAMES]
                for f in filenames:
                    if f not in _EXCLUDED_DIR_NAMES:
                        count += 1
                        if count > _MAX_FILES:
                            return count
        except (PermissionError, OSError):
            pass
        return count
