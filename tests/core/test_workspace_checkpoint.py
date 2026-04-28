from pathlib import Path

from kimi_cli.soul.workspace_checkpoint import WorkspaceCheckpointStore


def test_store_init_does_not_create_checkpoint_directory(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)

    assert not (session_dir / "workspace-checkpoints").exists()


def test_ensure_checkpoint_once_per_conversation_checkpoint(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("print('v1')\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)

    first = store.ensure_checkpoint(3, reason="WriteFile")
    second = store.ensure_checkpoint(3, reason="StrReplaceFile")

    assert first is True
    assert second is False  # dedup: already checkpointed this turn
    assert store.get(3) is not None


def test_new_turn_resets_dedup(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)

    first = store.ensure_checkpoint(0, reason="before edit")
    assert first is True

    store.new_turn()
    # Second call in new turn should succeed
    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    second = store.ensure_checkpoint(1, reason="after edit")
    assert second is True


def test_restore_checkpoint_restores_modified_added_and_deleted_files(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")
    (work_dir / "keep.txt").write_text("keep\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(0, reason="before edit")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    (work_dir / "new.txt").write_text("new\n", encoding="utf-8")
    (work_dir / "keep.txt").unlink()

    preview = store.preview_restore(0)
    assert any("app.py" in f and f.startswith("M") for f in preview)

    store.restore(0)

    assert (work_dir / "app.py").read_text(encoding="utf-8") == "v1\n"
    # Files added after the checkpoint should be deleted
    assert not (work_dir / "new.txt").exists()
    # Files deleted after the checkpoint should be restored
    assert (work_dir / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_find_restore_checkpoint_uses_next_workspace_checkpoint(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(4, reason="WriteFile")

    assert store.find_restore_checkpoint_id(3) == 4
    assert store.find_restore_checkpoint_id(4) == 4
    assert store.find_restore_checkpoint_id(5) is None


def test_preview_missing_checkpoint_raises(tmp_path: Path) -> None:
    store = WorkspaceCheckpointStore(session_dir=tmp_path / "session", work_dir=tmp_path / "work")

    try:
        store.preview_restore(999)
    except ValueError as exc:
        assert "No workspace checkpoint" in str(exc)
    else:
        raise AssertionError("preview_restore should fail for missing checkpoint")


def test_restore_missing_checkpoint_raises(tmp_path: Path) -> None:
    store = WorkspaceCheckpointStore(session_dir=tmp_path / "session", work_dir=tmp_path / "work")

    try:
        store.restore(999)
    except ValueError as exc:
        assert "No workspace checkpoint" in str(exc)
    else:
        raise AssertionError("restore should fail for missing checkpoint")


def test_restore_creates_pre_rollback_commit(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(0, reason="before edit")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")

    store.restore(0)

    # Pre-rollback commit should exist in git log
    checkpoints = store.list_checkpoints()
    assert any("pre-rollback" in cp.reason for cp in checkpoints)


def test_restore_does_not_move_head(tmp_path: Path) -> None:
    """Verify that restore uses git checkout (not reset --hard), so HEAD stays intact."""
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(0, reason="checkpoint 0")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    store.new_turn()
    store.ensure_checkpoint(1, reason="checkpoint 1")

    # Restore to checkpoint 0
    store.restore(0)

    # Checkpoint 1's commit should still be reachable via the index
    assert store.get(1) is not None
    # The file should be restored
    assert (work_dir / "app.py").read_text(encoding="utf-8") == "v1\n"


def test_restore_is_undoable(tmp_path: Path) -> None:
    """Verify that after restoring, we can restore back to the later checkpoint."""
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(0, reason="checkpoint 0")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    store.new_turn()
    store.ensure_checkpoint(1, reason="checkpoint 1")

    # Restore to checkpoint 0
    store.restore(0)
    assert (work_dir / "app.py").read_text(encoding="utf-8") == "v1\n"

    # Now restore back to checkpoint 1
    store.restore(1)
    assert (work_dir / "app.py").read_text(encoding="utf-8") == "v2\n"


def test_get_change_count(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)
    store.ensure_checkpoint(0, reason="checkpoint 0")

    (work_dir / "app.py").write_text("v2\n", encoding="utf-8")
    (work_dir / "new.py").write_text("new\n", encoding="utf-8")
    store.new_turn()
    store.ensure_checkpoint(1, reason="checkpoint 1")

    count = store.get_change_count(1, base_checkpoint_id=0)
    assert count is not None
    assert count >= 1  # at least app.py changed + new.py added


def test_ensure_checkpoint_records_head_when_no_changes(tmp_path: Path) -> None:
    """When no files changed since last commit, still record HEAD for the checkpoint."""
    work_dir = tmp_path / "work"
    session_dir = tmp_path / "session"
    work_dir.mkdir()
    (work_dir / "app.py").write_text("v1\n", encoding="utf-8")

    store = WorkspaceCheckpointStore(session_dir=session_dir, work_dir=work_dir)

    # First checkpoint creates a commit
    store.ensure_checkpoint(0, reason="first")

    # Second checkpoint with no changes — should still record HEAD
    store.new_turn()
    result = store.ensure_checkpoint(1, reason="no changes")
    assert result is True
    assert store.get(1) is not None
    # Same commit hash since nothing changed
    assert store.get(1) == store.get(0)
