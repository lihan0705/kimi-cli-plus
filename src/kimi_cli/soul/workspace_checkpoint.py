from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from kimi_cli.utils.io import atomic_json_write

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


@dataclass(frozen=True, slots=True)
class WorkspaceCheckpoint:
    conversation_checkpoint_id: int
    snapshot_id: str
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
        self._snapshots_dir = self._root / "snapshots"
        self._pre_restore_dir = self._root / "pre-restore"
        self._index_file = self._root / "index.json"
        self._root.mkdir(parents=True, exist_ok=True)
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._pre_restore_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict[str, dict[str, object]]:
        if not self._index_file.exists():
            return {}
        with self._index_file.open(encoding="utf-8") as f:
            return json.load(f)

    def _save_index(self, index: dict[str, dict[str, object]]) -> None:
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
        snapshot_id = f"cp-{conversation_checkpoint_id}-{int(time.time() * 1000)}"
        snapshot_path = self._snapshots_dir / snapshot_id
        self._copy_worktree(snapshot_path)
        checkpoint = WorkspaceCheckpoint(
            conversation_checkpoint_id=conversation_checkpoint_id,
            snapshot_id=snapshot_id,
            reason=reason,
            created_at=time.time(),
        )
        index = self._load_index()
        index[str(conversation_checkpoint_id)] = asdict(checkpoint)
        self._save_index(index)
        return checkpoint

    def preview_restore(self, conversation_checkpoint_id: int) -> RestorePreview:
        checkpoint = self.get(conversation_checkpoint_id)
        if checkpoint is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        snapshot_path = self._snapshots_dir / checkpoint.snapshot_id
        return RestorePreview(
            conversation_checkpoint_id=conversation_checkpoint_id,
            changed_files=self._changed_files(snapshot_path),
        )

    def restore(self, conversation_checkpoint_id: int) -> None:
        checkpoint = self.get(conversation_checkpoint_id)
        if checkpoint is None:
            raise ValueError(
                f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}"
            )
        snapshot_path = self._snapshots_dir / checkpoint.snapshot_id
        self._copy_pre_restore_snapshot(conversation_checkpoint_id)
        self._restore_snapshot(snapshot_path)

    def _copy_pre_restore_snapshot(self, conversation_checkpoint_id: int) -> None:
        snapshot_id = f"pre-restore-{conversation_checkpoint_id}-{time.time_ns()}"
        self._copy_worktree(self._pre_restore_dir / snapshot_id)

    def _copy_worktree(self, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=False)
        for path in self._iter_files(self._work_dir):
            rel = path.relative_to(self._work_dir)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    def _restore_snapshot(self, snapshot_path: Path) -> None:
        for path in self._iter_files(self._work_dir):
            rel = path.relative_to(self._work_dir)
            if not (snapshot_path / rel).exists():
                path.unlink()
        for path in self._iter_files(snapshot_path):
            rel = path.relative_to(snapshot_path)
            dest = self._work_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    def _changed_files(self, snapshot_path: Path) -> list[str]:
        current = {p.relative_to(self._work_dir): p for p in self._iter_files(self._work_dir)}
        snap = {p.relative_to(snapshot_path): p for p in self._iter_files(snapshot_path)}
        changed: list[str] = []
        for rel in sorted(current.keys() - snap.keys()):
            changed.append(f"A {rel.as_posix()}")
        for rel in sorted(snap.keys() - current.keys()):
            changed.append(f"D {rel.as_posix()}")
        for rel in sorted(current.keys() & snap.keys()):
            if current[rel].read_bytes() != snap[rel].read_bytes():
                changed.append(f"M {rel.as_posix()}")
        return changed

    def _iter_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        files: list[Path] = []
        for path in root.rglob("*"):
            rel_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_DIRS for part in rel_parts):
                continue
            if path.is_file():
                files.append(path)
        return files
