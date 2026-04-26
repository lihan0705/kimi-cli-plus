# `/tree` Checkpoint Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-first `/tree` workflow that can rewind conversation to an existing checkpoint and optionally restore workspace files from a matching snapshot.

**Architecture:** Keep the existing linear `context.jsonl` model for the first slice. Add a timeline parser for user-facing checkpoint rows, a session-owned workspace checkpoint store backed by snapshot directories plus metadata, and a shell `/tree` command that orchestrates preview, confirmation, restore, and conversation rewind. File-changing tools create at most one workspace checkpoint per conversation checkpoint before they modify files.

**Tech Stack:** Python 3.12+, Typer shell command registry, prompt-toolkit `ChoiceInput`, `kosong.message.Message`, existing `Context`, `Session`, `Runtime`, pytest + pytest-asyncio, Ruff/Pyright.

---

## File Structure

- Create `src/kimi_cli/soul/timeline.py`
  - Parse raw `context.jsonl` records.
  - Build user-facing `TimelineNode` rows from `_checkpoint` records and following real user messages.
  - Provide checkpoint existence validation.

- Create `src/kimi_cli/soul/workspace_checkpoint.py`
  - Store workspace snapshots under `<session_dir>/workspace-checkpoints/`.
  - Persist `index.json` metadata.
  - Create snapshots before file-changing tools.
  - Preview and restore changed files.

- Modify `src/kimi_cli/soul/context.py`
  - Add `has_checkpoint(checkpoint_id: int) -> bool`.
  - Add `rewind_to(checkpoint_id: int, note: str) -> None` wrapper around `revert_to()` that appends a synthetic user/system note.

- Modify `src/kimi_cli/soul/agent.py`
  - Add `workspace_checkpoints: WorkspaceCheckpointStore` to `Runtime`.
  - Initialize it from `session.dir` and `session.work_dir`.
  - Add `current_checkpoint_id: int | None` so tools can snapshot against the active
    conversation checkpoint.

- Modify `src/kimi_cli/soul/kimisoul.py`
  - Update `Runtime.current_checkpoint_id` whenever `KimiSoul` creates a conversation checkpoint.

- Modify `tests/conftest.py`
  - Update the `Runtime(...)` and `Shell(...)` test fixtures for the new runtime fields and Shell
    constructor.

- Modify `src/kimi_cli/tools/file/write.py`
  - Before approved writes, create a workspace checkpoint for the current conversation checkpoint.

- Modify `src/kimi_cli/tools/file/replace.py`
  - Same checkpoint hook before approved edits.

- Modify `src/kimi_cli/tools/shell/__init__.py`
  - After command approval and before execution, create a conservative workspace checkpoint.

- Create `src/kimi_cli/ui/shell/tree.py`
  - Implement interactive `/tree` flow and non-interactive helpers used by tests.

- Modify `src/kimi_cli/ui/shell/slash.py`
  - Register `/tree` and delegate to `ui.shell.tree`.

- Tests:
  - Create `tests/core/test_timeline.py`
  - Create `tests/core/test_workspace_checkpoint.py`
  - Create `tests/core/test_context_rewind.py`
  - Extend `tests/tools/test_write_file.py`
  - Extend `tests/tools/test_str_replace_file.py`
  - Extend `tests/tools/test_shell_bash.py`
  - Create `tests/ui_and_conv/test_shell_tree.py`

---

### Task 1: Timeline Parser

**Files:**
- Create: `src/kimi_cli/soul/timeline.py`
- Test: `tests/core/test_timeline.py`

- [ ] **Step 1: Write failing timeline tests**

Create `tests/core/test_timeline.py`:

```python
from pathlib import Path

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.soul.timeline import TimelineNode, build_timeline, checkpoint_exists
from kimi_cli.wire.types import TextPart


@pytest.mark.asyncio
async def test_build_timeline_maps_checkpoint_to_following_user_turn(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="build auth")]))
    await context.append_message(Message(role="assistant", content=[TextPart(text="done")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="fix auth tests")]))

    nodes = await build_timeline(context_file)

    assert nodes == [
        TimelineNode(checkpoint_id=0, title="build auth", message_index=0),
        TimelineNode(checkpoint_id=1, title="fix auth tests", message_index=2),
    ]


@pytest.mark.asyncio
async def test_build_timeline_ignores_synthetic_checkpoint_user_messages(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=True)
    await context.append_message(Message(role="user", content=[TextPart(text="real request")]))

    nodes = await build_timeline(context_file)

    assert nodes == [TimelineNode(checkpoint_id=0, title="real request", message_index=1)]


@pytest.mark.asyncio
async def test_checkpoint_exists_reads_raw_checkpoint_records(tmp_path: Path) -> None:
    context_file = tmp_path / "context.jsonl"
    context = Context(context_file)

    await context.checkpoint(add_user_message=False)

    assert await checkpoint_exists(context_file, 0) is True
    assert await checkpoint_exists(context_file, 1) is False
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_timeline.py -q
```

Expected: fail because `kimi_cli.soul.timeline` does not exist.

- [ ] **Step 3: Implement timeline parser**

Create `src/kimi_cli/soul/timeline.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kosong.message import Message


@dataclass(frozen=True, slots=True)
class TimelineNode:
    checkpoint_id: int
    title: str
    message_index: int | None


def _is_checkpoint_user_message(message: Message) -> bool:
    if message.role != "user" or len(message.content) != 1:
        return False
    return message.extract_text().startswith("<system>CHECKPOINT ")


def _title_for_message(message: Message) -> str:
    text = " ".join(message.extract_text(" ").split())
    if not text:
        return "(empty user message)"
    return text if len(text) <= 80 else text[:77] + "..."


async def build_timeline(context_file: Path) -> list[TimelineNode]:
    records: list[tuple[str, int | None, Message | None]] = []
    if not context_file.exists():
        return []

    with context_file.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint":
                records.append(("_checkpoint", int(data["id"]), None))
            elif data.get("role", "").startswith("_"):
                continue
            else:
                records.append(("message", None, Message.model_validate(data)))

    nodes: list[TimelineNode] = []
    message_index = -1
    pending_checkpoint: int | None = None
    for kind, checkpoint_id, message in records:
        if kind == "_checkpoint":
            pending_checkpoint = checkpoint_id
            continue
        assert message is not None
        message_index += 1
        if pending_checkpoint is None:
            continue
        if message.role == "user" and not _is_checkpoint_user_message(message):
            nodes.append(
                TimelineNode(
                    checkpoint_id=pending_checkpoint,
                    title=_title_for_message(message),
                    message_index=message_index,
                )
            )
            pending_checkpoint = None

    if pending_checkpoint is not None:
        nodes.append(
            TimelineNode(
                checkpoint_id=pending_checkpoint,
                title="(checkpoint before next turn)",
                message_index=None,
            )
        )
    return nodes


async def checkpoint_exists(context_file: Path, checkpoint_id: int) -> bool:
    if checkpoint_id < 0 or not context_file.exists():
        return False
    with context_file.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("role") == "_checkpoint" and data.get("id") == checkpoint_id:
                return True
    return False
```

- [ ] **Step 4: Run timeline tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_timeline.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit timeline parser**

```bash
git add src/kimi_cli/soul/timeline.py tests/core/test_timeline.py
git commit -m "feat(tree): build context checkpoint timeline"
```

---

### Task 2: User-Facing Context Rewind

**Files:**
- Modify: `src/kimi_cli/soul/context.py`
- Test: `tests/core/test_context_rewind.py`

- [ ] **Step 1: Write failing context rewind tests**

Create `tests/core/test_context_rewind.py`:

```python
from pathlib import Path

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.wire.types import TextPart


@pytest.mark.asyncio
async def test_rewind_to_truncates_context_and_appends_note(tmp_path: Path) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))
    await context.append_message(Message(role="assistant", content=[TextPart(text="answer")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="second")]))

    await context.rewind_to(1, "The user rewound to checkpoint 1.")

    assert [m.extract_text() for m in context.history] == [
        "first",
        "answer",
        "<system>The user rewound to checkpoint 1.</system>",
    ]
    assert context.n_checkpoints == 2


@pytest.mark.asyncio
async def test_has_checkpoint(tmp_path: Path) -> None:
    context = Context(tmp_path / "context.jsonl")

    await context.checkpoint(add_user_message=False)

    assert context.has_checkpoint(0) is True
    assert context.has_checkpoint(1) is False
```

- [ ] **Step 2: Run failing context tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_context_rewind.py -q
```

Expected: fail because `rewind_to` and `has_checkpoint` do not exist.

- [ ] **Step 3: Implement context helpers**

Modify `src/kimi_cli/soul/context.py`:

```python
    def has_checkpoint(self, checkpoint_id: int) -> bool:
        return 0 <= checkpoint_id < self._next_checkpoint_id

    async def rewind_to(self, checkpoint_id: int, note: str):
        if not self.has_checkpoint(checkpoint_id):
            raise ValueError(f"Checkpoint {checkpoint_id} does not exist")
        await self.revert_to(checkpoint_id)
        await self.checkpoint(add_user_message=False)
        await self.append_message(Message(role="user", content=[system(note)]))
```

Place these methods after `checkpoint()` and before `revert_to()`.

- [ ] **Step 4: Run context tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_context_rewind.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit context rewind helper**

```bash
git add src/kimi_cli/soul/context.py tests/core/test_context_rewind.py
git commit -m "feat(tree): add user-facing context rewind"
```

---

### Task 3: Workspace Checkpoint Store

**Files:**
- Create: `src/kimi_cli/soul/workspace_checkpoint.py`
- Test: `tests/core/test_workspace_checkpoint.py`

- [ ] **Step 1: Write failing workspace checkpoint tests**

Create `tests/core/test_workspace_checkpoint.py`:

```python
from pathlib import Path

from kimi_cli.soul.workspace_checkpoint import WorkspaceCheckpointStore


def test_create_checkpoint_once_per_conversation_checkpoint(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("print('v1')\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)

    first = store.create_once(3, reason="WriteFile")
    second = store.create_once(3, reason="StrReplaceFile")

    assert first is not None
    assert second == first
    assert store.get(3) == first


def test_restore_checkpoint_restores_modified_added_and_deleted_files(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")
    (work_dir / "keep.txt").write_text("keep\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    checkpoint = store.create_once(0, reason="before edit")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    (work_dir / "new.txt").write_text("new\n", encoding="utf-8")
    (work_dir / "keep.txt").unlink()

    preview = store.preview_restore(0)
    assert preview.changed_files == ["A new.txt", "D keep.txt", "M app.py"]

    store.restore(0)

    assert (work_dir / "app.py").read_text(encoding="utf-8") == "v1\n"
    assert (work_dir / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (work_dir / "new.txt").exists()
    assert checkpoint.conversation_checkpoint_id == 0


def test_restore_missing_checkpoint_raises(tmp_path: Path) -> None:
    store = WorkspaceCheckpointStore(session_dir=tmp_path / "session", work_dir=tmp_path / "work")

    try:
        store.restore(999)
    except ValueError as exc:
        assert "No workspace checkpoint" in str(exc)
    else:
        raise AssertionError("restore should fail for missing checkpoint")
```

- [ ] **Step 2: Run failing workspace checkpoint tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_workspace_checkpoint.py -q
```

Expected: fail because `workspace_checkpoint.py` does not exist.

- [ ] **Step 3: Implement snapshot-directory checkpoint store**

Create `src/kimi_cli/soul/workspace_checkpoint.py`:

```python
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from kimi_cli.utils.io import atomic_json_write


EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


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
        self._index_file = self._root / "index.json"
        self._root.mkdir(parents=True, exist_ok=True)
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

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
            raise ValueError(f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}")
        snapshot_path = self._snapshots_dir / checkpoint.snapshot_id
        return RestorePreview(
            conversation_checkpoint_id=conversation_checkpoint_id,
            changed_files=self._changed_files(snapshot_path),
        )

    def restore(self, conversation_checkpoint_id: int) -> None:
        checkpoint = self.get(conversation_checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"No workspace checkpoint for conversation checkpoint {conversation_checkpoint_id}")
        snapshot_path = self._snapshots_dir / checkpoint.snapshot_id
        self.create_once(-1, reason=f"pre-restore-{conversation_checkpoint_id}")
        self._restore_snapshot(snapshot_path)

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
```

- [ ] **Step 4: Run workspace checkpoint tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_workspace_checkpoint.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit workspace checkpoint store**

```bash
git add src/kimi_cli/soul/workspace_checkpoint.py tests/core/test_workspace_checkpoint.py
git commit -m "feat(tree): add workspace checkpoint store"
```

---

### Task 4: Runtime Wiring

**Files:**
- Modify: `src/kimi_cli/soul/agent.py`
- Modify: `src/kimi_cli/soul/kimisoul.py`
- Modify: `tests/conftest.py`
- Test: `tests/core/test_load_agent.py`

- [ ] **Step 1: Write failing runtime wiring test**

Append to `tests/core/test_load_agent.py`:

```python
def test_runtime_has_workspace_checkpoint_store(runtime: Runtime) -> None:
    assert runtime.workspace_checkpoints is not None
    assert runtime.workspace_checkpoints.get(0) is None
    assert runtime.current_checkpoint_id is None
```

If `Runtime` is not imported in that file, add:

```python
from kimi_cli.soul.agent import Runtime
```

- [ ] **Step 2: Run failing runtime test**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_load_agent.py::test_runtime_has_workspace_checkpoint_store -q
```

Expected: fail because `Runtime.workspace_checkpoints` does not exist.

- [ ] **Step 3: Add store to Runtime**

Modify `src/kimi_cli/soul/agent.py`:

```python
from kimi_cli.soul.workspace_checkpoint import WorkspaceCheckpointStore
```

Add a dataclass field to `Runtime`:

```python
    workspace_checkpoints: WorkspaceCheckpointStore
    current_checkpoint_id: int | None
```

In `Runtime.create(...)`, add to the returned `Runtime(...)`:

```python
            workspace_checkpoints=WorkspaceCheckpointStore(
                session_dir=session.dir,
                work_dir=Path(str(session.work_dir)),
            ),
            current_checkpoint_id=None,
```

In `copy_for_fixed_subagent()` and `copy_for_dynamic_subagent()`, pass through the same shared
checkpoint store and current checkpoint id:

```python
            workspace_checkpoints=self.workspace_checkpoints,
            current_checkpoint_id=self.current_checkpoint_id,
```

`Path` is already imported in `agent.py`.

- [ ] **Step 4: Update checkpoint tracking**

Modify `src/kimi_cli/soul/kimisoul.py`:

```python
    async def _checkpoint(self):
        await self._context.checkpoint(self._checkpoint_with_user_message)
        self._runtime.current_checkpoint_id = self._context.n_checkpoints - 1
```

- [ ] **Step 5: Update test fixtures**

Modify `tests/conftest.py` imports:

```python
from kimi_cli.soul.workspace_checkpoint import WorkspaceCheckpointStore
```

In the `runtime(...)` fixture, add these `Runtime(...)` arguments:

```python
        workspace_checkpoints=WorkspaceCheckpointStore(
            session_dir=session.dir,
            work_dir=Path(str(session.work_dir)),
        ),
        current_checkpoint_id=None,
```

In the `shell_tool(...)` fixture, add `runtime: Runtime` to the fixture parameters and construct
the tool with the new signature:

```python
@pytest.fixture
def shell_tool(
    runtime: Runtime,
    approval: Approval,
    environment: Environment,
) -> Generator[Shell]:
    """Create a Shell tool instance."""
    with tool_call_context("Shell"):
        yield Shell(runtime, approval, environment)
```

- [ ] **Step 6: Run runtime test**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_load_agent.py::test_runtime_has_workspace_checkpoint_store -q
```

Expected: pass.

- [ ] **Step 7: Commit runtime wiring**

```bash
git add src/kimi_cli/soul/agent.py src/kimi_cli/soul/kimisoul.py tests/conftest.py tests/core/test_load_agent.py
git commit -m "feat(tree): attach workspace checkpoints to runtime"
```

---

### Task 5: Tool Checkpoint Hooks

**Files:**
- Modify: `src/kimi_cli/tools/file/write.py`
- Modify: `src/kimi_cli/tools/file/replace.py`
- Modify: `src/kimi_cli/tools/shell/__init__.py`
- Test: `tests/tools/test_write_file.py`
- Test: `tests/tools/test_str_replace_file.py`
- Test: `tests/tools/test_shell_bash.py`

- [ ] **Step 1: Write failing tool hook tests**

Add this helper class to `tests/tools/test_write_file.py`, `tests/tools/test_str_replace_file.py`,
and `tests/tools/test_shell_bash.py`:

```python
class FakeWorkspaceCheckpoints:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def create_once(self, conversation_checkpoint_id: int, *, reason: str):
        self.calls.append((conversation_checkpoint_id, reason))
        return object()
```

In `tests/tools/test_write_file.py`, add this exact test:

```python
async def test_write_file_creates_workspace_checkpoint(
    write_file_tool: WriteFile,
    runtime: Runtime,
    temp_work_dir: KaosPath,
) -> None:
    checkpoints = FakeWorkspaceCheckpoints()
    runtime.workspace_checkpoints = checkpoints
    runtime.current_checkpoint_id = 3
    file_path = temp_work_dir / "checkpointed.txt"

    result = await write_file_tool(Params(path=str(file_path), content="content"))

    assert not result.is_error
    assert checkpoints.calls == [(3, "WriteFile")]
```

Add these imports if they are missing:

```python
from kimi_cli.soul.agent import Runtime
```

In `tests/tools/test_str_replace_file.py`, add this exact test:

```python
async def test_str_replace_file_creates_workspace_checkpoint(
    str_replace_file_tool: StrReplaceFile,
    runtime: Runtime,
    temp_work_dir: KaosPath,
) -> None:
    checkpoints = FakeWorkspaceCheckpoints()
    runtime.workspace_checkpoints = checkpoints
    runtime.current_checkpoint_id = 3
    file_path = temp_work_dir / "checkpointed.txt"
    await file_path.write_text("old content")

    result = await str_replace_file_tool(
        Params(path=str(file_path), edit=[Edit(old="old", new="new")])
    )

    assert not result.is_error
    assert checkpoints.calls == [(3, "StrReplaceFile")]
```

Add these imports if they are missing:

```python
from kimi_cli.soul.agent import Runtime
```

In `tests/tools/test_shell_bash.py`, add this exact test:

```python
async def test_shell_creates_workspace_checkpoint(
    shell_tool: Shell,
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoints = FakeWorkspaceCheckpoints()
    runtime.workspace_checkpoints = checkpoints
    runtime.current_checkpoint_id = 3

    async def fake_run_shell_command(command, stdout_cb, stderr_cb, timeout):
        return 0

    monkeypatch.setattr(shell_tool, "_run_shell_command", fake_run_shell_command)

    result = await shell_tool(Params(command="touch file.txt"))

    assert not result.is_error
    assert checkpoints.calls == [(3, "Shell")]
```

Add this import if it is missing:

```python
from kimi_cli.soul.agent import Runtime
```

- [ ] **Step 2: Run failing tool tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py -q
```

Expected: fail because tools do not call `runtime.workspace_checkpoints`.

- [ ] **Step 3: Add checkpoint hook to write tool**

In `src/kimi_cli/tools/file/write.py`, keep `runtime` on the instance:

```python
        self._runtime = runtime
```

After approval succeeds and before writing:

```python
            checkpoint_id = self._runtime.current_checkpoint_id
            if checkpoint_id is not None:
                self._runtime.workspace_checkpoints.create_once(checkpoint_id, reason=self.name)
```

- [ ] **Step 4: Add checkpoint hook to replace and shell tools**

In `src/kimi_cli/tools/file/replace.py`, mirror the `WriteFile` hook using `reason=self.name`.

In `src/kimi_cli/tools/shell/__init__.py`, accept `runtime: Runtime` in `Shell.__init__`, store it as
`self._runtime`, and call the same hook after approval and before `_run_shell_command(...)`.

Because tool dependency injection uses positional annotated parameters, update the constructor to:

```python
    def __init__(self, runtime: Runtime, approval: Approval, environment: Environment):
```

Add the import:

```python
from kimi_cli.soul.agent import Runtime
```

- [ ] **Step 5: Run tool tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py -q
```

Expected: pass.

- [ ] **Step 6: Commit tool hooks**

```bash
git add src/kimi_cli/soul/agent.py src/kimi_cli/tools/file/write.py src/kimi_cli/tools/file/replace.py src/kimi_cli/tools/shell/__init__.py tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py
git commit -m "feat(tree): checkpoint workspace before mutations"
```

---

### Task 6: Shell `/tree` Command

**Files:**
- Create: `src/kimi_cli/ui/shell/tree.py`
- Modify: `src/kimi_cli/ui/shell/slash.py`
- Test: `tests/ui_and_conv/test_shell_tree.py`

- [ ] **Step 1: Write failing shell tree tests**

Create `tests/ui_and_conv/test_shell_tree.py`:

```python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from kosong.message import Message

from kimi_cli.soul.context import Context
from kimi_cli.ui.shell import tree as shell_tree
from kimi_cli.wire.types import TextPart


class FakeWorkspaceCheckpoints:
    def __init__(self, has_checkpoint: bool = False) -> None:
        self.has_checkpoint = has_checkpoint
        self.restored: list[int] = []

    def get(self, checkpoint_id: int):
        return object() if self.has_checkpoint else None

    def preview_restore(self, checkpoint_id: int):
        return SimpleNamespace(changed_files=["M app.py"])

    def restore(self, checkpoint_id: int) -> None:
        self.restored.append(checkpoint_id)


async def _make_context(tmp_path: Path) -> Context:
    context = Context(tmp_path / "context.jsonl")
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="first")]))
    await context.checkpoint(add_user_message=False)
    await context.append_message(Message(role="user", content=[TextPart(text="second")]))
    return context


@pytest.mark.asyncio
async def test_conversation_only_rewinds_context(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    app = Mock()
    app.soul.context = context
    app.soul.runtime.session.context_file = context.file_backend
    app.soul.runtime.workspace_checkpoints = FakeWorkspaceCheckpoints()

    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="conversation"))

    await shell_tree.tree(app, "")

    assert [m.extract_text() for m in context.history] == [
        "first",
        "<system>The user rewound the conversation to checkpoint 1 with mode conversation-only. Continue from that point.</system>",
    ]


@pytest.mark.asyncio
async def test_restore_mode_restores_files_before_rewind(tmp_path: Path, monkeypatch) -> None:
    context = await _make_context(tmp_path)
    checkpoints = FakeWorkspaceCheckpoints(has_checkpoint=True)
    app = Mock()
    app.soul.context = context
    app.soul.runtime.session.context_file = context.file_backend
    app.soul.runtime.workspace_checkpoints = checkpoints

    monkeypatch.setattr(shell_tree, "_select_checkpoint", AsyncMock(return_value=1))
    monkeypatch.setattr(shell_tree, "_select_mode", AsyncMock(return_value="restore"))
    monkeypatch.setattr(shell_tree, "_confirm_restore", AsyncMock(return_value=True))

    await shell_tree.tree(app, "")

    assert checkpoints.restored == [1]
```

- [ ] **Step 2: Run failing shell tree tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/ui_and_conv/test_shell_tree.py -q
```

Expected: fail because `kimi_cli.ui.shell.tree` does not exist.

- [ ] **Step 3: Implement shell tree module**

Create `src/kimi_cli/ui/shell/tree.py`:

```python
from __future__ import annotations

from typing import Literal

from prompt_toolkit.shortcuts import button_dialog
from rich.console import Console

from kimi_cli.soul.timeline import TimelineNode, build_timeline
from kimi_cli.ui.shell.slash import ensure_kimi_soul

console = Console()
TreeMode = Literal["conversation", "restore", "cancel"]


async def _select_checkpoint(nodes: list[TimelineNode]) -> int | None:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    if not nodes:
        return None
    choices = [
        (str(node.checkpoint_id), f"#{node.checkpoint_id} {node.title}") for node in nodes
    ]
    selected = await ChoiceInput(
        message="Select a checkpoint to continue from:",
        options=choices,
        default=choices[-1][0],
    ).prompt_async()
    return int(selected) if selected else None


async def _select_mode(has_workspace_checkpoint: bool) -> TreeMode:
    from prompt_toolkit.shortcuts.choice_input import ChoiceInput

    choices = [("conversation", "Conversation only")]
    if has_workspace_checkpoint:
        choices.append(("restore", "Conversation + restore files"))
    choices.append(("cancel", "Cancel"))
    selected = await ChoiceInput(
        message="How should Kimi continue?",
        options=choices,
        default="conversation",
    ).prompt_async()
    return selected if selected in {"conversation", "restore", "cancel"} else "cancel"


async def _confirm_restore(changed_files: list[str]) -> bool:
    if changed_files:
        console.print("Files that may change:")
        for file in changed_files:
            console.print(f"  {file}")
    else:
        console.print("No file changes detected for restore.")
    result = await button_dialog(
        title="Restore files?",
        text="Restore workspace files from this checkpoint?",
        buttons=[("Yes", True), ("No", False)],
    ).run_async()
    return bool(result)


async def tree(app, args: str) -> None:
    soul = ensure_kimi_soul(app)
    if soul is None:
        return

    nodes = await build_timeline(soul.runtime.session.context_file)
    if not nodes:
        console.print("[yellow]No checkpoints available in this session.[/yellow]")
        return

    checkpoint_id = await _select_checkpoint(nodes)
    if checkpoint_id is None:
        return

    store = soul.runtime.workspace_checkpoints
    has_workspace_checkpoint = store.get(checkpoint_id) is not None
    mode = await _select_mode(has_workspace_checkpoint)
    if mode == "cancel":
        return

    if mode == "restore":
        preview = store.preview_restore(checkpoint_id)
        if not await _confirm_restore(preview.changed_files):
            return
        store.restore(checkpoint_id)

    note = (
        f"The user rewound the conversation to checkpoint {checkpoint_id} "
        f"with mode {'conversation-only' if mode == 'conversation' else 'conversation-and-files'}. "
        "Continue from that point."
    )
    await soul.context.rewind_to(checkpoint_id, note)
    console.print(f"[green]Rewound to checkpoint {checkpoint_id}.[/green]")
```

- [ ] **Step 4: Register shell command**

Modify `src/kimi_cli/ui/shell/slash.py`:

```python
@registry.command
async def tree(app: Shell, args: str):
    """Browse checkpoints and rewind conversation optionally with files"""
    from kimi_cli.ui.shell.tree import tree as run_tree

    await run_tree(app, args)
    raise Reload(session_id=app.soul.runtime.session.id)
```

Place it near `/sessions` and `/new`.

- [ ] **Step 5: Run shell tree tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/ui_and_conv/test_shell_tree.py -q
```

Expected: pass.

- [ ] **Step 6: Commit shell tree command**

```bash
git add src/kimi_cli/ui/shell/tree.py src/kimi_cli/ui/shell/slash.py tests/ui_and_conv/test_shell_tree.py
git commit -m "feat(tree): add interactive shell rewind command"
```

---

### Task 7: Validation and Polish

**Files:**
- Modify files touched by prior tasks only if validation fails.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run pytest tests/core/test_timeline.py tests/core/test_context_rewind.py tests/core/test_workspace_checkpoint.py tests/ui_and_conv/test_shell_tree.py tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Ruff on changed source and tests**

Run:

```bash
env UV_PROJECT_ENVIRONMENT=.venv312 UV_PYTHON=/Users/lihan/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/bin/python3 uv run ruff check src/kimi_cli/soul/timeline.py src/kimi_cli/soul/workspace_checkpoint.py src/kimi_cli/soul/context.py src/kimi_cli/soul/agent.py src/kimi_cli/tools/file/write.py src/kimi_cli/tools/file/replace.py src/kimi_cli/tools/shell/__init__.py src/kimi_cli/ui/shell/tree.py src/kimi_cli/ui/shell/slash.py tests/core/test_timeline.py tests/core/test_context_rewind.py tests/core/test_workspace_checkpoint.py tests/ui_and_conv/test_shell_tree.py tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py
```

Expected: no Ruff errors.

- [ ] **Step 3: Run project check**

Run:

```bash
make check-kimi-cli
```

Expected: all checks pass. `ty` remains non-blocking per project policy.

- [ ] **Step 4: Commit validation fixes if validation changed files**

```bash
git add src/kimi_cli/soul/timeline.py src/kimi_cli/soul/workspace_checkpoint.py src/kimi_cli/soul/context.py src/kimi_cli/soul/agent.py src/kimi_cli/soul/kimisoul.py src/kimi_cli/tools/file/write.py src/kimi_cli/tools/file/replace.py src/kimi_cli/tools/shell/__init__.py src/kimi_cli/ui/shell/tree.py src/kimi_cli/ui/shell/slash.py tests/core/test_timeline.py tests/core/test_context_rewind.py tests/core/test_workspace_checkpoint.py tests/core/test_load_agent.py tests/ui_and_conv/test_shell_tree.py tests/tools/test_write_file.py tests/tools/test_str_replace_file.py tests/tools/test_shell_bash.py
git commit -m "fix(tree): polish checkpoint restore workflow"
```

If validation required no changes, do not create an empty commit.
