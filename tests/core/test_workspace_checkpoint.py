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
