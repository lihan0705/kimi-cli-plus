import json
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


def test_restore_keeps_pre_restore_snapshot_out_of_checkpoint_index(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.create_once(0, reason="before edit")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")

    store.restore(0)

    index_file = session_dir / "workspace-checkpoints" / "index.json"
    index = json.loads(index_file.read_text(encoding="utf-8"))
    assert "-1" not in index
    assert store.get(-1) is None

    pre_restore_dir = session_dir / "workspace-checkpoints" / "pre-restore"
    pre_restore_snapshots = list(pre_restore_dir.iterdir())
    assert len(pre_restore_snapshots) == 1
    assert (pre_restore_snapshots[0] / "app.py").read_text(encoding="utf-8") == "v2\n"


def test_restore_missing_checkpoint_raises(tmp_path: Path) -> None:
    store = WorkspaceCheckpointStore(session_dir=tmp_path / "session", work_dir=tmp_path / "work")

    try:
        store.restore(999)
    except ValueError as exc:
        assert "No workspace checkpoint" in str(exc)
    else:
        raise AssertionError("restore should fail for missing checkpoint")
