import os
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from kimi_cli.knowledge.log import LogManager


@pytest.fixture
def kb_root(tmp_path):
    root = tmp_path / "test_kb"
    root.mkdir(parents=True, exist_ok=True)
    yield root
    if root.exists():
        shutil.rmtree(root)


def test_init_creates_log_file_with_header(kb_root):
    LogManager(kb_root)
    log_file = kb_root / "log.md"
    assert log_file.exists()
    content = log_file.read_text()
    assert "# Knowledge Base Activity Log" in content


def test_append_adds_line(kb_root):
    lm = LogManager(kb_root)
    log_file = kb_root / "log.md"
    doc_id = UUID("12345678-1234-5678-1234-567812345678")
    
    fixed_now = datetime(2023, 10, 27, 10, 0, 0)
    with patch("kimi_cli.knowledge.log.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        mock_datetime.strptime.side_effect = datetime.strptime
        lm.append("create", "Test Doc", doc_id)
    
    content = log_file.read_text()
    expected_line = "- [2023-10-27 10:00:00] create: Test Doc (12345678-1234-5678-1234-567812345678)"
    assert expected_line in content


def test_append_without_doc_id(kb_root):
    lm = LogManager(kb_root)
    log_file = kb_root / "log.md"
    fixed_now = datetime(2023, 10, 27, 10, 0, 0)
    with patch("kimi_cli.knowledge.log.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        mock_datetime.strptime.side_effect = datetime.strptime
        lm.append("delete", "Old Doc")
    
    content = log_file.read_text()
    expected_line = "- [2023-10-27 10:00:00] delete: Old Doc ()"
    assert expected_line in content


def test_rotation_same_week(kb_root):
    log_file = kb_root / "log.md"
    archive_dir = kb_root / "log_archive"
    
    # Friday Oct 27, 2023
    now1 = datetime(2023, 10, 27, 10, 0, 0)
    # Sunday Oct 29, 2023 (same ISO week 43)
    now2 = datetime(2023, 10, 29, 10, 0, 0)
    
    with patch("kimi_cli.knowledge.log.datetime") as mock_datetime:
        mock_datetime.now.return_value = now1
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        mock_datetime.strptime.side_effect = datetime.strptime
        
        lm = LogManager(kb_root)
        # Set mtime to now1 to avoid rotation on first append
        os.utime(log_file, (now1.timestamp(), now1.timestamp()))
        
        lm.append("action1", "title1")
        
        mock_datetime.now.return_value = now2
        lm.append("action2", "title2")
        
    assert log_file.exists()
    assert not list(archive_dir.glob("**/*.md"))
    content = log_file.read_text()
    assert "action1" in content
    assert "action2" in content


def test_rotation_new_week(kb_root):
    log_file = kb_root / "log.md"
    archive_dir = kb_root / "log_archive"
    
    # Friday Oct 27, 2023 (ISO week 43)
    now1 = datetime(2023, 10, 27, 10, 0, 0)
    # Monday Oct 30, 2023 (ISO week 44)
    now2 = datetime(2023, 10, 30, 10, 0, 0)
    
    with patch("kimi_cli.knowledge.log.datetime") as mock_datetime:
        mock_datetime.now.return_value = now1
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        mock_datetime.strptime.side_effect = datetime.strptime
        
        lm = LogManager(kb_root)
        # Set mtime to now1 to avoid rotation on first append
        os.utime(log_file, (now1.timestamp(), now1.timestamp()))
        
        lm.append("action1", "title1")
        
        # Verify action1 is in log.md
        assert "action1" in log_file.read_text()
        
        mock_datetime.now.return_value = now2
        lm.append("action2", "title2")
        
    # log.md should be rotated
    # Archive path: log_archive/2023/10/week-43.md
    archive_path = archive_dir / "2023" / "10" / "week-43.md"
    assert archive_path.exists()
    assert "action1" in archive_path.read_text()
    
    # New log.md should only have action2
    new_content = log_file.read_text()
    assert "# Knowledge Base Activity Log" in new_content
    assert "action1" not in new_content
    assert "action2" in new_content
